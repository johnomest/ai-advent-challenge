import unittest
from unittest.mock import patch

from main import enrich, rerank, studio_labels, rewrite


class RerankTests(unittest.TestCase):
    def test_rewrite_does_not_seed_another_studio(self):
        with patch("main.day22.complete", return_value="Framestore diploma") as complete:
            rewrite("Нужен ли диплом для Framestore?", "test-key", "test-model")
        prompt, question, *_ = complete.call_args.args
        self.assertIn("do not add new studio names", prompt)
        self.assertNotIn("IV", prompt)
        self.assertEqual(question, "Нужен ли диплом для Framestore?")

    def item(self, identifier, score=0.6, text="portfolio", studio="IV"):
        return {"chunk_id": identifier, "vector_score": score, "text": text, "studio": studio}

    def rank(self, groups, question="general question", rewritten="portfolio", threshold=0.4, top_k=5):
        index = {"chunks": [item for group in groups for item in group]}
        return rerank(groups, index, question, rewritten, threshold, top_k)

    def test_threshold_can_return_no_context(self):
        found, counts = self.rank([[self.item("a", 0.39)]])
        self.assertEqual(found, [])
        self.assertEqual(counts["after_threshold"], 0)

    def test_merge_uses_best_similarity(self):
        found, counts = self.rank([[self.item("a", 0.5)], [self.item("a", 0.7)]])
        self.assertEqual(counts["merged_candidates"], 1)
        self.assertEqual(found[0]["vector_score"], 0.7)

    def test_studio_scope_uses_original_question(self):
        found, _ = self.rank([[self.item("a"), self.item("b", 0.9, studio="BUCK")]], question="Что советует IV?")
        self.assertEqual([item["chunk_id"] for item in found], ["a"])

    def test_exact_duplicates_and_top_k(self):
        found, _ = self.rank([[self.item("a"), self.item("b"), self.item("c", text="reel")]], top_k=2)
        self.assertEqual(len(found), 2)

    def test_lexical_evidence_changes_ranking(self):
        found, _ = self.rank([[self.item("a", 0.7, "unrelated"), self.item("b", 0.6, "LinkedIn")]], rewritten="LinkedIn", top_k=1)
        self.assertEqual(found[0]["chunk_id"], "b")

    def test_studio_inheritance_and_unchanged_index(self):
        chunks = [
            {"page": 23, "text": "IV\niv.studio\nInterview", "section": "PDF page 23"},
            {"page": 24, "text": "Continuation", "section": "PDF page 24"},
            {"page": 25, "text": "ORDINARY FOLK ordinaryfolk.co More", "section": "PDF page 25"},
        ]
        labels = studio_labels(chunks)
        self.assertEqual(labels[24], "IV")
        self.assertEqual(labels[25], "ORDINARY FOLK")
        self.assertEqual(enrich({"chunks": chunks})["chunks"][1]["studio"], "IV")
        self.assertNotIn("studio", chunks[1])

    def test_studio_word_boundaries(self):
        found, counts = self.rank([[self.item("a")]], question="divide portfolio")
        self.assertEqual(counts["studio_filter"], [])
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
