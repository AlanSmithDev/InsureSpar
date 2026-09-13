"""Disk persistence for the RAG document metadata and embedding matrix."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np


CACHE_SCHEMA_VERSION = 2
CACHE_FILE_PREFIX = "rag_index_"


def build_source_fingerprint(source_paths: list[Path], model_name: str) -> str:
    """Build a cheap cache key without rereading the source file contents.

    File size and nanosecond mtime invalidate the cache after normal edits. The
    embedding model and schema version are included because either changes the
    meaning or layout of the persisted vectors.
    """
    sources = []
    for path in source_paths:
        resolved = path.resolve()
        try:
            stat = resolved.stat()
            sources.append({
                "path": str(resolved),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            })
        except FileNotFoundError:
            sources.append({"path": str(resolved), "missing": True})

    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "model_name": model_name,
        "sources": sources,
    }
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_index_cache_path(cache_dir: Path, fingerprint: str) -> Path:
    return cache_dir / f"{CACHE_FILE_PREFIX}{fingerprint}.npz"


def load_index_cache(
    cache_path: Path,
    expected_fingerprint: str,
    expected_model_name: str,
) -> tuple[list[dict], np.ndarray] | None:
    """Load and validate a persisted index, returning ``None`` on a miss."""
    if not cache_path.is_file():
        return None

    try:
        with np.load(cache_path, allow_pickle=False) as data:
            schema_version = int(data["schema_version"].item())
            fingerprint = str(data["fingerprint"].item())
            model_name = str(data["model_name"].item())

            if schema_version != CACHE_SCHEMA_VERSION:
                return None
            if fingerprint != expected_fingerprint or model_name != expected_model_name:
                return None

            documents = json.loads(str(data["documents_json"].item()))
            embeddings = np.array(data["embeddings"], dtype=np.float32, copy=True)

        if not isinstance(documents, list) or embeddings.ndim != 2:
            return None
        if len(documents) != embeddings.shape[0]:
            return None
        return documents, embeddings
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"⚠️ RAG 向量缓存读取失败，将重新构建: {exc}")
        return None


def save_index_cache(
    cache_dir: Path,
    fingerprint: str,
    model_name: str,
    documents: list[dict],
    embeddings: np.ndarray,
) -> Path:
    """Persist an index atomically so concurrent readers never see a partial file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = get_index_cache_path(cache_dir, fingerprint)
    matrix = np.asarray(embeddings, dtype=np.float32)

    if matrix.ndim != 2 or len(documents) != matrix.shape[0]:
        raise ValueError("RAG 文档数量与向量矩阵行数不一致")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f".{CACHE_FILE_PREFIX}",
            suffix=".tmp",
            dir=cache_dir,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            np.savez_compressed(
                temp_file,
                schema_version=np.asarray(CACHE_SCHEMA_VERSION),
                fingerprint=np.asarray(fingerprint),
                model_name=np.asarray(model_name),
                documents_json=np.asarray(json.dumps(documents, ensure_ascii=False)),
                embeddings=matrix,
            )
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, cache_path)
        return cache_path
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
