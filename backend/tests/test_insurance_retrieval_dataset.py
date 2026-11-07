import json
import unittest
from pathlib import Path

from app.tools.insurance_corpus import load_insurance_corpus


BACKEND_DIR = Path(__file__).parents[1]


class InsuranceRetrievalDatasetTest(unittest.TestCase):
    def test_document_ids_are_unique_and_all_labels_exist(self):
        documents = load_insurance_corpus(BACKEND_DIR / "data")
        document_ids = [document["doc_id"] for document in documents]
        self.assertEqual(len(document_ids), len(set(document_ids)))

        dataset_path = BACKEND_DIR / "data" / "evals" / "insurance_retrieval_v1.jsonl"
        cases = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertGreaterEqual(len(cases), 50)
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        for case in cases:
            self.assertTrue(case["query"])
            self.assertTrue(case["relevant_doc_ids"])
            self.assertTrue(set(case["relevant_doc_ids"]).issubset(document_ids), case["id"])


if __name__ == "__main__":
    unittest.main()
