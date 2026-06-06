"""Benchmark local and Qwen embeddings on the versioned insurance retrieval set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.tools.insurance_corpus import load_insurance_corpus  # noqa: E402
from app.tools.rag_ranking import (  # noqa: E402
    adaptive_qwen_result_count,
    weighted_reciprocal_rank_fusion,
)


DEFAULT_DATASET = BACKEND_DIR / "data" / "evals" / "insurance_retrieval_v1.jsonl"
DEFAULT_LOCAL_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_QWEN_MODEL = "qwen3.7-text-embedding"
DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("local", "qwen", "both"), default="both")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--local-model", default=DEFAULT_LOCAL_MODEL)
    parser.add_argument("--qwen-model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument("--qwen-base-url", default=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_QWEN_BASE_URL))
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if raw_line.strip():
                case = json.loads(raw_line)
                case["_line"] = line_number
                cases.append(case)
    return cases


def validate_cases(cases: list[dict], documents: list[dict]) -> None:
    corpus_ids = {document["doc_id"] for document in documents}
    case_ids: set[str] = set()
    errors = []
    for case in cases:
        missing_fields = {"id", "query", "relevant_doc_ids", "category", "difficulty", "critical"} - case.keys()
        if missing_fields:
            errors.append(f"line {case['_line']}: missing {sorted(missing_fields)}")
        if case.get("id") in case_ids:
            errors.append(f"line {case['_line']}: duplicate id {case.get('id')}")
        case_ids.add(case.get("id"))
        unknown = set(case.get("relevant_doc_ids", [])) - corpus_ids
        if unknown:
            errors.append(f"line {case['_line']}: unknown doc IDs {sorted(unknown)}")
    if errors:
        raise ValueError("Invalid retrieval dataset:\n" + "\n".join(errors))


def normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values), fraction * 100))


def embed_local(model_name: str, documents: list[str], queries: list[str]) -> tuple[np.ndarray, np.ndarray, dict]:
    from sentence_transformers import SentenceTransformer

    load_start = time.perf_counter()
    model = SentenceTransformer(model_name)
    model_load_seconds = time.perf_counter() - load_start

    index_start = time.perf_counter()
    document_vectors = normalize(model.encode(documents, show_progress_bar=False))
    index_seconds = time.perf_counter() - index_start

    query_vectors = []
    query_latencies = []
    for query in queries:
        start = time.perf_counter()
        query_vectors.append(model.encode([query], show_progress_bar=False)[0])
        query_latencies.append(time.perf_counter() - start)

    return document_vectors, normalize(np.asarray(query_vectors)), {
        "model_load_seconds": model_load_seconds,
        "document_embedding_seconds": index_seconds,
        "query_latency_ms": {
            "mean": statistics.fmean(query_latencies) * 1000,
            "p50": percentile(query_latencies, 0.50) * 1000,
            "p95": percentile(query_latencies, 0.95) * 1000,
        },
        "embedding_dimension": int(document_vectors.shape[1]),
        "execution": "local_cpu_or_configured_torch_device",
    }


def qwen_request(client, model_name: str, texts: list[str]) -> list[list[float]]:
    last_error = None
    for attempt in range(3):
        try:
            response = client.embeddings.create(model=model_name, input=texts)
            return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(
        f"Qwen embedding request failed after retries: {type(last_error).__name__} "
        f"status={getattr(last_error, 'status_code', None)} code={getattr(last_error, 'code', None)}"
    ) from last_error


def embed_qwen(model_name: str, base_url: str, documents: list[str], queries: list[str]) -> tuple[np.ndarray, np.ndarray, dict]:
    from openai import OpenAI

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required for --provider qwen/both")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=0)

    document_vectors: list[list[float]] = []
    index_start = time.perf_counter()
    for start in range(0, len(documents), 20):
        document_vectors.extend(qwen_request(client, model_name, documents[start:start + 20]))
    index_seconds = time.perf_counter() - index_start

    query_vectors = []
    query_latencies = []
    for query in queries:
        start = time.perf_counter()
        query_vectors.extend(qwen_request(client, model_name, [query]))
        query_latencies.append(time.perf_counter() - start)

    document_matrix = normalize(np.asarray(document_vectors))
    return document_matrix, normalize(np.asarray(query_vectors)), {
        "model_load_seconds": 0.0,
        "document_embedding_seconds": index_seconds,
        "query_latency_ms": {
            "mean": statistics.fmean(query_latencies) * 1000,
            "p50": percentile(query_latencies, 0.50) * 1000,
            "p95": percentile(query_latencies, 0.95) * 1000,
        },
        "embedding_dimension": int(document_matrix.shape[1]),
        "execution": "remote_api",
        "document_batch_size": 20,
        "base_url_host": base_url.split("//", 1)[-1].split("/", 1)[0],
    }


def rrf(rankings: list[list[int]], rank_constant: int = 60) -> list[int]:
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, index in enumerate(ranking):
            scores[index] += 1.0 / (rank_constant + rank + 1)
    return sorted(scores, key=lambda index: (-scores[index], index))


def build_bm25_ranker(texts: list[str]) -> Callable[[str, int], list[int]]:
    import jieba
    from rank_bm25 import BM25Okapi

    index = BM25Okapi([list(jieba.cut(text)) for text in texts])

    def rank(query: str, top_k: int) -> list[int]:
        scores = index.get_scores(list(jieba.cut(query)))
        return np.argsort(scores)[::-1][:top_k].tolist()

    return rank


def score_rankings(cases: list[dict], document_ids: list[str], rankings: list[list[int]], top_k: int) -> dict:
    rows = []
    for case, ranking in zip(cases, rankings):
        relevant = set(case["relevant_doc_ids"])
        retrieved = [document_ids[index] for index in ranking[:top_k]]
        relevant_ranks = [rank for rank, doc_id in enumerate(retrieved, 1) if doc_id in relevant]
        recall = len(set(retrieved) & relevant) / len(relevant)
        reciprocal_rank = 1.0 / min(relevant_ranks) if relevant_ranks else 0.0
        dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
        ideal_hits = min(len(relevant), top_k)
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "difficulty": case["difficulty"],
            "critical": case["critical"],
            "hit": bool(relevant_ranks),
            "recall": recall,
            "reciprocal_rank": reciprocal_rank,
            "ndcg": dcg / idcg,
            "retrieved_doc_ids": retrieved,
        })

    def aggregate(selected: list[dict]) -> dict:
        return {
            "count": len(selected),
            f"hit_rate@{top_k}": statistics.fmean(row["hit"] for row in selected),
            f"recall@{top_k}": statistics.fmean(row["recall"] for row in selected),
            f"mrr@{top_k}": statistics.fmean(row["reciprocal_rank"] for row in selected),
            f"ndcg@{top_k}": statistics.fmean(row["ndcg"] for row in selected),
        }

    categories = sorted({row["category"] for row in rows})
    difficulties = sorted({row["difficulty"] for row in rows})
    return {
        "overall": aggregate(rows),
        "critical": aggregate([row for row in rows if row["critical"]]),
        "by_category": {category: aggregate([row for row in rows if row["category"] == category]) for category in categories},
        "by_difficulty": {difficulty: aggregate([row for row in rows if row["difficulty"] == difficulty]) for difficulty in difficulties},
        "failures": [row for row in rows if not row["hit"]],
    }


def score_adaptive_rankings(
    cases: list[dict],
    documents: list[dict],
    rankings: list[list[int]],
    result_counts: list[int],
) -> dict:
    hits = []
    recalls = []
    reciprocal_ranks = []
    ndcgs = []
    precisions = []
    context_characters = []
    failures = []
    for case, ranking, result_count in zip(cases, rankings, result_counts):
        relevant = set(case["relevant_doc_ids"])
        selected = ranking[:result_count]
        retrieved = [documents[index]["doc_id"] for index in selected]
        relevant_ranks = [rank for rank, doc_id in enumerate(retrieved, 1) if doc_id in relevant]
        hit = bool(relevant_ranks)
        hits.append(hit)
        recalls.append(len(set(retrieved) & relevant) / len(relevant))
        reciprocal_ranks.append(1.0 / min(relevant_ranks) if relevant_ranks else 0.0)
        precisions.append(len(set(retrieved) & relevant) / len(retrieved))
        dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
        ideal_hits = min(len(relevant), result_count)
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        ndcgs.append(dcg / idcg)
        context_characters.append(sum(len(documents[index]["content"]) for index in selected))
        if not hit:
            failures.append({"id": case["id"], "retrieved_doc_ids": retrieved})
    return {
        "count": len(cases),
        "hit_rate": statistics.fmean(hits),
        "recall": statistics.fmean(recalls),
        "mrr": statistics.fmean(reciprocal_ranks),
        "ndcg": statistics.fmean(ndcgs),
        "context_precision": statistics.fmean(precisions),
        "average_results": statistics.fmean(result_counts),
        "average_context_characters": statistics.fmean(context_characters),
        "failures": failures,
    }


def evaluate_model(
    provider_name: str,
    cases: list[dict],
    documents: list[dict],
    document_vectors: np.ndarray,
    query_vectors: np.ndarray,
    bm25_rank: Callable[[str, int], list[int]],
    top_k: int,
) -> dict:
    search_latencies = []
    vector_rankings = []
    hybrid_rankings = []
    optimized_rankings = []
    optimized_result_counts = []
    candidate_k = top_k
    for case, query_vector in zip(cases, query_vectors):
        start = time.perf_counter()
        similarities = document_vectors @ query_vector
        vector_ranking = np.argsort(similarities)[::-1][:candidate_k].tolist()
        keyword_ranking = bm25_rank(case["query"], candidate_k)
        hybrid_ranking = rrf([vector_ranking, keyword_ranking])[:top_k]
        optimized_candidate_k = 8
        optimized_vector = np.argsort(similarities)[::-1][:optimized_candidate_k].tolist()
        optimized_keyword = bm25_rank(case["query"], optimized_candidate_k)
        if provider_name == "qwen":
            weights = [0.8, 0.2]
            margin = float(
                similarities[optimized_vector[0]] - similarities[optimized_vector[1]]
            )
            optimized_count = adaptive_qwen_result_count(margin)
        else:
            weights = [0.4, 0.6]
            optimized_count = 6
        optimized_ranking = weighted_reciprocal_rank_fusion(
            [optimized_vector, optimized_keyword], weights
        )
        search_latencies.append(time.perf_counter() - start)
        vector_rankings.append(vector_ranking)
        hybrid_rankings.append(hybrid_ranking)
        optimized_rankings.append(optimized_ranking)
        optimized_result_counts.append(optimized_count)

    document_ids = [document["doc_id"] for document in documents]
    return {
        "vector": score_rankings(cases, document_ids, vector_rankings, top_k),
        "hybrid_rrf": score_rankings(cases, document_ids, hybrid_rankings, top_k),
        "baseline_context": score_adaptive_rankings(
            cases,
            documents,
            hybrid_rankings,
            [top_k] * len(cases),
        ),
        "optimized": score_adaptive_rankings(
            cases,
            documents,
            optimized_rankings,
            optimized_result_counts,
        ),
        "exact_search_latency_ms": {
            "mean": statistics.fmean(search_latencies) * 1000,
            "p50": percentile(search_latencies, 0.50) * 1000,
            "p95": percentile(search_latencies, 0.95) * 1000,
        },
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()
    documents = load_insurance_corpus(BACKEND_DIR / "data")
    cases = load_cases(args.dataset)
    validate_cases(cases, documents)
    texts = [document["search_text"] for document in documents]
    queries = [case["query"] for case in cases]
    bm25_rank = build_bm25_ranker(texts)

    result = {
        "benchmark": "insurance_retrieval_v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dataset_path": os.path.relpath(args.dataset.resolve(), BACKEND_DIR),
        "dataset_sha256": sha256_file(args.dataset),
        "corpus_document_count": len(documents),
        "query_count": len(cases),
        "top_k": args.top_k,
        "protocol": "same corpus, same queries, cosine exact search; production-like BM25+RRF also reported",
        "models": {},
    }

    providers = ("local", "qwen") if args.provider == "both" else (args.provider,)
    for provider in providers:
        print(f"Evaluating {provider}...", flush=True)
        if provider == "local":
            doc_vectors, query_vectors, timing = embed_local(args.local_model, texts, queries)
            model_name = args.local_model
        else:
            doc_vectors, query_vectors, timing = embed_qwen(args.qwen_model, args.qwen_base_url, texts, queries)
            model_name = args.qwen_model
        result["models"][provider] = {
            "model_name": model_name,
            "timing": timing,
            **evaluate_model(provider, cases, documents, doc_vectors, query_vectors, bm25_rank, args.top_k),
        }

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Result written to {args.output}")
        for provider, model_result in result["models"].items():
            vector = model_result["vector"]["overall"]
            hybrid = model_result["hybrid_rrf"]["overall"]
            optimized = model_result["optimized"]
            print(
                f"{provider}: vector hit@{args.top_k}={vector[f'hit_rate@{args.top_k}']:.4f}, "
                f"MRR={vector[f'mrr@{args.top_k}']:.4f}; "
                f"hybrid hit@{args.top_k}={hybrid[f'hit_rate@{args.top_k}']:.4f}, "
                f"MRR={hybrid[f'mrr@{args.top_k}']:.4f}; "
                f"optimized hit={optimized['hit_rate']:.4f}, MRR={optimized['mrr']:.4f}, "
                f"avg_results={optimized['average_results']:.2f}"
            )
    else:
        print(payload)


if __name__ == "__main__":
    main()
