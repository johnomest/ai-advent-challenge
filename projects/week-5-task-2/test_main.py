import unittest
from unittest.mock import patch

from main import ask, cosine, evaluate_retrieval_case, search


class RagTests(unittest.TestCase):
    def test_cosine(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1)
        self.assertEqual(cosine([0, 0], [1, 0]), 0)
        with self.assertRaises(ValueError):
            cosine([1], [1, 0])

    def test_search_order_and_top_k(self):
        index = {"chunks": [
            {"chunk_id": "b", "embedding": [0, 1]},
            {"chunk_id": "a", "embedding": [1, 0]},
        ]}
        self.assertEqual(search(index, [1, 0], 1)[0]["chunk_id"], "a")

    def test_page_hit_is_not_evidence_hit(self):
        case = {"pages": [13], "terms": ["visa"]}
        result = evaluate_retrieval_case(case, [{"page": 13, "text": "portfolio"}])
        self.assertTrue(result["page_hit"])
        self.assertFalse(result["evidence_hit"])

    def test_baseline_has_no_excerpts(self):
        with patch("main.complete", return_value="Answer") as complete:
            ask("Question", None, "test-key", "test-model")
        self.assertEqual(complete.call_args.args[1], "Question")

    def test_rag_includes_metadata_and_text(self):
        context = [{"chunk_id": "a", "source": "book.pdf", "section": "PDF page 13", "page": 13, "text": "Evidence"}]
        with patch("main.complete", return_value="Answer") as complete:
            ask("Question", context, "test-key", "test-model")
        self.assertIn('"page": 13', complete.call_args.args[1])
        self.assertIn("Evidence", complete.call_args.args[1])

    def test_empty_rag_skips_api(self):
        with patch("main.complete") as complete:
            self.assertIn("Недостаточно", ask("Question", [], "test-key", "test-model"))
        complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
