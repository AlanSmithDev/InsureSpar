"""Ranking primitives shared by production retrieval and offline evaluation."""

from __future__ import annotations


def weighted_reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    weights: list[float],
    rank_constant: int = 60,
) -> list[int]:
    if len(ranked_lists) != len(weights):
        raise ValueError("ranked_lists and weights must have the same length")
    scores: dict[int, float] = {}
    for ranked_list, weight in zip(ranked_lists, weights):
        for rank, doc_index in enumerate(ranked_list):
            scores[doc_index] = scores.get(doc_index, 0.0) + weight / (
                rank_constant + rank + 1
            )
    return sorted(scores, key=lambda index: (-scores[index], index))


def adaptive_qwen_result_count(
    cosine_margin: float | None,
    minimum: int = 2,
    maximum: int = 4,
    confidence_threshold: float = 0.01,
) -> int:
    """Return less context only when Qwen's first result is clearly separated."""
    if cosine_margin is not None and cosine_margin >= confidence_threshold:
        return minimum
    return maximum
