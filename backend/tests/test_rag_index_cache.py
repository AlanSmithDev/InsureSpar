import builtins
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.tools.rag_index_cache import (
    build_source_fingerprint,
    load_index_cache,
    save_index_cache,
)


class RagIndexCacheTest(unittest.TestCase):
    def test_second_startup_loads_docs_and_vectors_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge.json"
            source.write_text('[{"content":"first"}]', encoding="utf-8")

            fingerprint = build_source_fingerprint([source], "test-model")
            docs = [{"title": "rule", "content": "first", "search_text": "first"}]
            embeddings = np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32)

            cache_path = save_index_cache(
                root / "cache", fingerprint, "test-model", docs, embeddings
            )
            cached = load_index_cache(cache_path, fingerprint, "test-model")

            self.assertIsNotNone(cached)
            cached_docs, cached_embeddings = cached
            self.assertEqual(cached_docs, docs)
            np.testing.assert_array_equal(cached_embeddings, embeddings)

    def test_source_change_invalidates_cache_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "knowledge.json"
            source.write_text("one", encoding="utf-8")
            before = build_source_fingerprint([source], "test-model")

            source.write_text("different-size", encoding="utf-8")
            after = build_source_fingerprint([source], "test-model")

            self.assertNotEqual(before, after)

    def test_rag_tool_second_import_skips_source_read_and_document_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "insurance_rules.json").write_text(
                json.dumps([{"rule_id": "r1", "content": "rule", "tags": []}]),
                encoding="utf-8",
            )
            (data_dir / "insurance_law_structured.json").write_text(
                json.dumps([{"article_number": "1", "content": "law", "text_for_embedding": "law"}]),
                encoding="utf-8",
            )
            (data_dir / "insurance_definitions_structured.json").write_text(
                json.dumps([{"entity_name": "term", "content": "definition", "text_for_embedding": "definition"}]),
                encoding="utf-8",
            )

            counters = {"model_loads": 0, "encoded_documents": 0}

            class FakeSentenceTransformer:
                def __init__(self, _model_name):
                    counters["model_loads"] += 1

                def encode(self, texts):
                    counters["encoded_documents"] += len(texts)
                    return np.ones((len(texts), 3), dtype=np.float32)

            class FakeBM25:
                def __init__(self, _documents):
                    pass

            fake_modules = {
                "app.core.config": types.SimpleNamespace(DATA_DIR=data_dir),
                "langchain_core": types.ModuleType("langchain_core"),
                "langchain_core.tools": types.SimpleNamespace(tool=lambda func: func),
                "sentence_transformers": types.SimpleNamespace(
                    SentenceTransformer=FakeSentenceTransformer
                ),
                "rank_bm25": types.SimpleNamespace(BM25Okapi=FakeBM25),
                "jieba": types.SimpleNamespace(cut=lambda text: text.split()),
            }
            rag_path = Path(__file__).parents[1] / "app" / "tools" / "rag_tool.py"

            def import_rag_tool(module_name):
                spec = importlib.util.spec_from_file_location(module_name, rag_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            with patch.dict(sys.modules, fake_modules), patch.dict(
                os.environ,
                {"RAG_FORCE_REBUILD": "", "RAG_PRELOAD_FALLBACK": "false"},
                clear=False,
            ), patch("builtins.print"):
                first = import_rag_tool("rag_tool_first_start")
                self.assertEqual(len(first.unified_docs), 3)
                self.assertEqual(counters, {"model_loads": 1, "encoded_documents": 3})

                class FailingQwen:
                    def encode(self, _texts):
                        raise first.EmbeddingProviderError("simulated outage")

                class WorkingLocal:
                    def encode(self, _texts):
                        return np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32)

                first.RAG_EMBEDDING_MODE = "auto"
                first.qwen_doc_embeddings = np.ones((3, 4), dtype=np.float32)
                first.local_doc_embeddings = np.eye(3, dtype=np.float32)
                first.qwen_provider = FailingQwen()
                first.local_provider = WorkingLocal()
                _indices, provider_name, _margin = first._vector_top_indices("query", 2)
                self.assertEqual(provider_name, "minilm-fallback")

                source_paths = {path.resolve() for path in first.SOURCE_PATHS}
                real_open = builtins.open

                def reject_source_reads(file, *args, **kwargs):
                    try:
                        candidate = Path(file).resolve()
                    except TypeError:
                        return real_open(file, *args, **kwargs)
                    if candidate in source_paths:
                        raise AssertionError(f"cache hit reread source file: {candidate}")
                    return real_open(file, *args, **kwargs)

                with patch("builtins.open", side_effect=reject_source_reads):
                    second = import_rag_tool("rag_tool_second_start")

                self.assertEqual(len(second.unified_docs), 3)
                self.assertEqual(counters, {"model_loads": 1, "encoded_documents": 3})


if __name__ == "__main__":
    unittest.main()
