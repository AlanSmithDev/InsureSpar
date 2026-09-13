"""Embedding providers used by the insurance RAG primary/fallback indexes."""

from __future__ import annotations

import os
import threading
import time

import numpy as np


class EmbeddingProviderError(RuntimeError):
    """Safe provider failure that never includes credentials or response bodies."""


class QwenEmbeddingProvider:
    def __init__(self, model_name: str, base_url: str, batch_size: int = 20):
        self.model_name = model_name
        self.base_url = base_url
        self.batch_size = batch_size
        self._client = None
        self._client_lock = threading.Lock()
        self._unavailable_until = 0.0

    @property
    def available(self) -> bool:
        return bool(os.getenv("DASHSCOPE_API_KEY"))

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self._unavailable_until

    def _get_client(self):
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is not None:
                return self._client
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise EmbeddingProviderError("未配置 DASHSCOPE_API_KEY")
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout=float(os.getenv("RAG_QWEN_TIMEOUT_SECONDS", "5")),
                    max_retries=int(os.getenv("RAG_QWEN_MAX_RETRIES", "0")),
                )
            except (ImportError, ValueError) as exc:
                raise EmbeddingProviderError(
                    f"Qwen 客户端初始化失败: {type(exc).__name__}"
                ) from exc
            return self._client

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        if self.circuit_open:
            raise EmbeddingProviderError("Qwen 向量服务处于故障冷却期")
        client = self._get_client()
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), self.batch_size):
                response = client.embeddings.create(
                    model=self.model_name,
                    input=texts[start:start + self.batch_size],
                )
                items = sorted(response.data, key=lambda item: item.index)
                vectors.extend(item.embedding for item in items)
        except Exception as exc:
            cooldown = float(os.getenv("RAG_QWEN_FAILURE_COOLDOWN_SECONDS", "60"))
            self._unavailable_until = time.monotonic() + max(cooldown, 0.0)
            raise EmbeddingProviderError(
                "Qwen 向量请求失败: "
                f"{type(exc).__name__}, status={getattr(exc, 'status_code', None)}, "
                f"code={getattr(exc, 'code', None)}"
            ) from exc
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(texts):
            raise EmbeddingProviderError("Qwen 返回的向量数量或维度无效")
        self._unavailable_until = 0.0
        return matrix


class LocalMiniLMEmbeddingProvider:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._load_attempted = False
        self._model_lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._get_model() is not None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def warmup(self) -> None:
        self._get_model()

    def _get_model(self):
        if self._model is not None or self._load_attempted:
            return self._model
        with self._model_lock:
            if self._model is not None or self._load_attempted:
                return self._model
            self._load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                print(f"⏳ 正在加载本地降级向量模型: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                print(f"⚠️ 本地降级向量模型加载失败: {type(exc).__name__}: {exc}")
            return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._get_model()
        if model is None:
            raise EmbeddingProviderError("MiniLM 本地向量模型不可用")
        try:
            matrix = np.asarray(model.encode(texts), dtype=np.float32)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"MiniLM 向量计算失败: {type(exc).__name__}"
            ) from exc
        if matrix.ndim != 2 or matrix.shape[0] != len(texts):
            raise EmbeddingProviderError("MiniLM 返回的向量数量或维度无效")
        return matrix
