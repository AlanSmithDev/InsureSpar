import os
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from app.tools.rag_embedding_providers import (
    EmbeddingProviderError,
    QwenEmbeddingProvider,
)


class QwenEmbeddingProviderTest(unittest.TestCase):
    def test_requires_api_key_without_contacting_service(self):
        provider = QwenEmbeddingProvider("test-model", "https://example.invalid/v1")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EmbeddingProviderError):
                provider.encode(["query"])

    def test_batches_documents_and_preserves_response_order(self):
        calls = []

        class FakeEmbeddings:
            def create(self, model, input):
                calls.append((model, list(input)))
                data = [
                    types.SimpleNamespace(index=index, embedding=[float(index), 1.0])
                    for index in reversed(range(len(input)))
                ]
                return types.SimpleNamespace(data=data)

        class FakeOpenAI:
            def __init__(self, **_kwargs):
                self.embeddings = FakeEmbeddings()

        fake_openai = types.SimpleNamespace(OpenAI=FakeOpenAI)
        provider = QwenEmbeddingProvider("test-model", "https://example.invalid/v1", batch_size=2)
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-only"}), patch.dict(
            sys.modules, {"openai": fake_openai}
        ):
            result = provider.encode(["a", "b", "c"])

        self.assertEqual([len(call[1]) for call in calls], [2, 1])
        np.testing.assert_array_equal(
            result,
            np.asarray([[0.0, 1.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32),
        )

    def test_network_failure_opens_circuit(self):
        calls = 0

        class FailingEmbeddings:
            def create(self, **_kwargs):
                nonlocal calls
                calls += 1
                raise TimeoutError("simulated")

        class FakeOpenAI:
            def __init__(self, **_kwargs):
                self.embeddings = FailingEmbeddings()

        provider = QwenEmbeddingProvider("test-model", "https://example.invalid/v1")
        with patch.dict(
            os.environ,
            {
                "DASHSCOPE_API_KEY": "test-only",
                "RAG_QWEN_FAILURE_COOLDOWN_SECONDS": "60",
            },
        ), patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=FakeOpenAI)}):
            with self.assertRaises(EmbeddingProviderError):
                provider.encode(["first"])
            with self.assertRaisesRegex(EmbeddingProviderError, "冷却期"):
                provider.encode(["second"])

        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
