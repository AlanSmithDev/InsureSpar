import unittest

from app.tools.rag_ranking import (
    adaptive_qwen_result_count,
    weighted_reciprocal_rank_fusion,
)


class RagRankingTest(unittest.TestCase):
    def test_weighted_rrf_prefers_primary_vector_ranking(self):
        result = weighted_reciprocal_rank_fusion(
            [[10, 20, 30], [30, 20, 10]],
            [0.8, 0.2],
        )
        self.assertEqual(result[0], 10)

    def test_qwen_result_count_uses_confidence_margin(self):
        self.assertEqual(adaptive_qwen_result_count(0.02), 2)
        self.assertEqual(adaptive_qwen_result_count(0.005), 4)
        self.assertEqual(adaptive_qwen_result_count(None), 4)

    def test_weight_count_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            weighted_reciprocal_rank_fusion([[1], [2]], [1.0])


if __name__ == "__main__":
    unittest.main()
