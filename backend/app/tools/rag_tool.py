# 文件：app/tools/rag_tool.py
"""RAG 混合检索引擎 — 向量检索 + BM25 关键词检索 + RRF 融合"""
import os
import threading
from pathlib import Path

import numpy as np
from langchain_core.tools import tool
from app.core.config import DATA_DIR
from app.tools.insurance_corpus import load_insurance_corpus, source_paths
from app.tools.rag_embedding_providers import (
    EmbeddingProviderError,
    LocalMiniLMEmbeddingProvider,
    QwenEmbeddingProvider,
)
from app.tools.rag_index_cache import (
    build_source_fingerprint,
    get_index_cache_path,
    load_index_cache,
    save_index_cache,
)
from app.tools.rag_ranking import (
    adaptive_qwen_result_count,
    weighted_reciprocal_rank_fusion,
)

# ==========================================
# 初始化：加载多源数据 + 构建统一索引
# ==========================================
unified_docs = []
search_texts = []
doc_embeddings = None
qwen_doc_embeddings = None
local_doc_embeddings = None
bm25_index = None

QWEN_EMBEDDING_MODEL = os.getenv(
    "RAG_QWEN_EMBEDDING_MODEL",
    "qwen3.7-text-embedding",
)
LOCAL_EMBEDDING_MODEL = os.getenv(
    "RAG_LOCAL_EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)
QWEN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
RAG_EMBEDDING_MODE = os.getenv("RAG_EMBEDDING_MODE", "auto").lower()
if RAG_EMBEDDING_MODE not in {"auto", "local"}:
    print(f"⚠️ 未知 RAG_EMBEDDING_MODE={RAG_EMBEDDING_MODE}，回退为 auto")
    RAG_EMBEDDING_MODE = "auto"

# 向后兼容旧的监控/测试引用；默认模型现已是 Qwen。
EMBEDDING_MODEL_NAME = QWEN_EMBEDDING_MODEL
qwen_provider = QwenEmbeddingProvider(QWEN_EMBEDDING_MODEL, QWEN_BASE_URL)
local_provider = LocalMiniLMEmbeddingProvider(LOCAL_EMBEDDING_MODEL)
_cache_dir_setting = os.getenv("RAG_CACHE_DIR")
RAG_CACHE_DIR = Path(_cache_dir_setting) if _cache_dir_setting else DATA_DIR / ".rag_cache"
if not RAG_CACHE_DIR.is_absolute():
    RAG_CACHE_DIR = DATA_DIR.parent / RAG_CACHE_DIR
RAG_FORCE_REBUILD = os.getenv("RAG_FORCE_REBUILD", "").lower() in {"1", "true", "yes"}
SOURCE_PATHS = source_paths(DATA_DIR)
RAG_CANDIDATE_K = int(os.getenv("RAG_CANDIDATE_K", "8"))
RAG_QWEN_VECTOR_WEIGHT = float(os.getenv("RAG_QWEN_VECTOR_WEIGHT", "0.8"))
RAG_QWEN_MIN_RESULTS = int(os.getenv("RAG_QWEN_MIN_RESULTS", "2"))
RAG_QWEN_MAX_RESULTS = int(os.getenv("RAG_QWEN_MAX_RESULTS", "4"))
RAG_QWEN_CONFIDENCE_MARGIN = float(os.getenv("RAG_QWEN_CONFIDENCE_MARGIN", "0.01"))
RAG_FALLBACK_VECTOR_WEIGHT = float(os.getenv("RAG_FALLBACK_VECTOR_WEIGHT", "0.4"))
RAG_FALLBACK_RESULTS = int(os.getenv("RAG_FALLBACK_RESULTS", "6"))


def load_and_unify_data():
    """加载三个 JSON 文件，并统一转换为标准文档格式"""
    global unified_docs, search_texts

    # 防止同一进程内强制重建时重复追加文档。
    unified_docs = []
    search_texts = []

    try:
        unified_docs = load_insurance_corpus(DATA_DIR)
        source_counts = {}
        for document in unified_docs:
            source_type = document["source_type"]
            source_counts[source_type] = source_counts.get(source_type, 0) + 1
        print(f"📄 已加载 {len(unified_docs)} 条保险知识文档: {source_counts}")
    except Exception as e:
        print(f"⚠️ 保险知识库加载失败: {e}")

    # 提取所有用于检索的文本
    search_texts = [doc["search_text"] for doc in unified_docs]


def _build_bm25_index() -> None:
    """从已恢复的文档元数据创建轻量关键词索引。"""
    global bm25_index
    try:
        from rank_bm25 import BM25Okapi
        import jieba

        tokenized_docs = [list(jieba.cut(text)) for text in search_texts]
        bm25_index = BM25Okapi(tokenized_docs)
        print("✅ 全局 BM25 倒排索引构建完成！")
    except ImportError:
        print("⚠️ rank_bm25 或 jieba 未安装，关键词检索不可用。")
    except Exception as exc:
        print(f"⚠️ BM25 索引构建失败: {exc}")


def _adopt_cached_documents(cached_documents: list[dict]) -> bool:
    """Use cache metadata while ensuring both vector spaces share document order."""
    global unified_docs, search_texts
    if not unified_docs:
        unified_docs = cached_documents
        search_texts = [document["search_text"] for document in unified_docs]
        return True
    current_ids = [document.get("doc_id") for document in unified_docs]
    cached_ids = [document.get("doc_id") for document in cached_documents]
    return current_ids == cached_ids


def _load_or_build_index(label, model_name, provider, allow_build: bool):
    """Restore one model-specific matrix, or build and persist it once."""
    fingerprint = build_source_fingerprint(SOURCE_PATHS, model_name)
    cache_path = get_index_cache_path(RAG_CACHE_DIR, fingerprint)
    cached = None if RAG_FORCE_REBUILD else load_index_cache(
        cache_path,
        fingerprint,
        model_name,
    )

    if cached is not None:
        cached_documents, cached_embeddings = cached
        if not _adopt_cached_documents(cached_documents):
            print(f"⚠️ {label} 缓存文档顺序与主索引不一致，将忽略该缓存。")
            cached = None
        else:
            print(
                f"✅ 已恢复 {label} 持久化向量: {len(cached_documents)} 条、"
                f"{cached_embeddings.shape[1]} 维 ({cache_path.name})"
            )
            return cached_embeddings

    if not allow_build:
        print(
            f"ℹ️ {label} 持久化向量不存在且当前不可构建；"
            "本进程将使用可用的降级索引。"
        )
        return None

    if not unified_docs:
        load_and_unify_data()
    if not search_texts:
        return None

    try:
        print(f"⏳ 正在构建 {label} 文档向量: {model_name}")
        embeddings = provider.encode(search_texts)
        current_fingerprint = build_source_fingerprint(SOURCE_PATHS, model_name)
        if all(path.is_file() for path in SOURCE_PATHS) and current_fingerprint == fingerprint:
            saved_path = save_index_cache(
                RAG_CACHE_DIR,
                fingerprint,
                model_name,
                unified_docs,
                embeddings,
            )
            print(
                f"✅ {label} 文档向量已持久化: {embeddings.shape[1]} 维 "
                f"({saved_path.name})"
            )
        else:
            print(f"⚠️ 构建 {label} 期间知识库发生变化，本次不写入缓存。")
        return embeddings
    except EmbeddingProviderError as exc:
        print(f"⚠️ {label} 构建失败，将继续使用降级通道: {exc}")
        return None


def _initialize_indexes() -> None:
    """Restore Qwen primary and MiniLM fallback matrices independently."""
    global qwen_doc_embeddings, local_doc_embeddings, doc_embeddings

    if RAG_FORCE_REBUILD:
        print("♻️ RAG_FORCE_REBUILD 已启用，强制重建所有可用向量索引。")

    if RAG_EMBEDDING_MODE != "local":
        qwen_doc_embeddings = _load_or_build_index(
            "Qwen 主索引",
            QWEN_EMBEDDING_MODEL,
            qwen_provider,
            allow_build=qwen_provider.available,
        )

    local_doc_embeddings = _load_or_build_index(
        "MiniLM 降级索引",
        LOCAL_EMBEDDING_MODEL,
        local_provider,
        allow_build=True,
    )
    doc_embeddings = qwen_doc_embeddings if qwen_doc_embeddings is not None else local_doc_embeddings

    preload_fallback = os.getenv("RAG_PRELOAD_FALLBACK", "true").lower() in {
        "1", "true", "yes"
    }
    if local_doc_embeddings is not None and preload_fallback and not local_provider.loaded:
        print("🔥 正在后台预热 MiniLM 降级模型。")
        threading.Thread(
            target=local_provider.warmup,
            name="rag-minilm-warmup",
            daemon=True,
        ).start()

    if search_texts:
        _build_bm25_index()
    else:
        print("❌ 没有加载到任何文档，跳过索引构建。")


_initialize_indexes()


def get_rag_status() -> dict:
    """Expose non-sensitive readiness information for health checks."""
    return {
        "mode": RAG_EMBEDDING_MODE,
        "primary_model": QWEN_EMBEDDING_MODEL,
        "primary_api_configured": qwen_provider.available,
        "primary_circuit_open": qwen_provider.circuit_open,
        "primary_index_ready": qwen_doc_embeddings is not None,
        "primary_dimension": (
            int(qwen_doc_embeddings.shape[1]) if qwen_doc_embeddings is not None else None
        ),
        "fallback_model": LOCAL_EMBEDDING_MODEL,
        "fallback_index_ready": local_doc_embeddings is not None,
        "fallback_model_loaded": local_provider.loaded,
        "fallback_dimension": (
            int(local_doc_embeddings.shape[1]) if local_doc_embeddings is not None else None
        ),
        "document_count": len(unified_docs),
    }


def _vector_top_indices(
    query: str, top_k: int
) -> tuple[list[int], str, float | None] | None:
    """Use Qwen first and switch to its dimension-matched local index on failure."""
    candidates = []
    if RAG_EMBEDDING_MODE != "local" and qwen_doc_embeddings is not None:
        candidates.append(("qwen", qwen_provider, qwen_doc_embeddings))
    if local_doc_embeddings is not None:
        candidates.append(("minilm-fallback", local_provider, local_doc_embeddings))

    for provider_name, provider, embeddings in candidates:
        try:
            query_embedding = provider.encode([query])
            if query_embedding.shape[1] != embeddings.shape[1]:
                raise EmbeddingProviderError(
                    f"查询向量 {query_embedding.shape[1]} 维与索引 {embeddings.shape[1]} 维不一致"
                )
            from sklearn.metrics.pairwise import cosine_similarity

            similarities = cosine_similarity(query_embedding, embeddings)[0]
            ranking = np.argsort(similarities)[::-1]
            margin = (
                float(similarities[ranking[0]] - similarities[ranking[1]])
                if len(ranking) >= 2
                else None
            )
            return ranking[:top_k].tolist(), provider_name, margin
        except EmbeddingProviderError as exc:
            print(f"⚠️ {provider_name} 查询失败: {exc}")
            if provider_name == "qwen":
                print("↪️ 自动切换到 MiniLM 本地降级通道。")
    return None


# ==========================================
# 工具：统一混合检索 (供 Agent 调用)
# ==========================================
@tool
def search_insurance_knowledge(query: str) -> str:
    """
    当遇到保险条款、核保规则、理赔条件、《保险法》法律条文、重大疾病医学定义、或保险专业术语时，必须调用此工具！
    参数 query: 一句简短的自然语言查询或者词语，例如 "收缩压150能投保吗"、“高血压投保”、"原位癌属于重疾吗" 、“佣金” 或 "保险法中关于如实告知是怎么规定的"。
    """
    if not unified_docs:
        return "【系统错误】知识库未加载或为空。"

    print(f"🔍 [RAG全局检索] 查询: '{query}'")
    # 候选召回与最终上下文数量解耦：先广召回，再按模型置信度裁剪。
    candidate_k = max(RAG_CANDIDATE_K, RAG_FALLBACK_RESULTS, RAG_QWEN_MAX_RESULTS)
    ranked_lists = []
    ranking_weights = []
    vector_provider = None
    cosine_margin = None

    # ---- 通道1：向量语义检索 ----
    vector_result = _vector_top_indices(query, candidate_k)
    if vector_result is not None:
        vec_top_indices, vector_provider, cosine_margin = vector_result
        ranked_lists.append(vec_top_indices)

    # ---- 通道2：BM25 关键词检索 ----
    if bm25_index is not None:
        try:
            import jieba
            tokenized_query = list(jieba.cut(query))
            bm25_scores = bm25_index.get_scores(tokenized_query)
            bm25_top_indices = np.argsort(bm25_scores)[::-1][:candidate_k].tolist()
            ranked_lists.append(bm25_top_indices)
        except Exception as e:
            print(f"  ⚠️ BM25 检索出错: {e}")

    # ---- 融合 ----
    if not ranked_lists:
        return "【系统错误】所有检索通道均不可用。"

    if vector_provider == "qwen":
        result_k = adaptive_qwen_result_count(
            cosine_margin,
            minimum=RAG_QWEN_MIN_RESULTS,
            maximum=RAG_QWEN_MAX_RESULTS,
            confidence_threshold=RAG_QWEN_CONFIDENCE_MARGIN,
        )
        ranking_weights = [RAG_QWEN_VECTOR_WEIGHT, 1.0 - RAG_QWEN_VECTOR_WEIGHT]
    elif vector_provider == "minilm-fallback":
        result_k = RAG_FALLBACK_RESULTS
        ranking_weights = [RAG_FALLBACK_VECTOR_WEIGHT, 1.0 - RAG_FALLBACK_VECTOR_WEIGHT]
    else:
        result_k = RAG_QWEN_MAX_RESULTS

    if len(ranked_lists) >= 2:
        fused_indices = weighted_reciprocal_rank_fusion(
            ranked_lists,
            ranking_weights,
        )[:result_k]
    else:
        fused_indices = ranked_lists[0][:result_k]

    # ---- 组装返回给 Agent 的上下文 ----
    result_str = f"【查询成功】为您在全局知识库中找到最相关的 {len(fused_indices)} 条参考信息：\n\n"

    for rank, idx in enumerate(fused_indices, 1):
        doc = unified_docs[idx]
        result_str += f"=== [参考资料 {rank}] {doc['title']} ===\n"
        result_str += f"{doc['content']}\n\n"

    print(
        f"🎯 [RAG全局检索] 向量通道={vector_provider or 'unavailable'}，"
        f"候选={candidate_k}，返回={len(fused_indices)}，"
        f"命中项: {[unified_docs[i]['title'] for i in fused_indices]}"
    )
    return result_str
