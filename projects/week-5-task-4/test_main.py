import unittest
import json
from unittest.mock import patch

from main import ask, validate


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.chunk = {"chunk_id": "c1", "source": "book.pdf", "section": "IV", "page": 24,
                      "text": "Just a portfolio for IV. Resumes are fine, but not necessary in our opinion.",
                      "vector_score": 0.7}
        self.payload = {"status": "answered", "clarification": "", "claims": [
            {"text": "IV достаточно портфолио.", "evidence": [
                {"chunk_id": "c1", "quote": "Just a portfolio for IV."}]}]}

    def test_valid_quotes_produce_canonical_sources(self):
        result = validate(self.payload, [self.chunk])
        self.assertEqual(result["sources"][0]["source"], "book.pdf")
        self.assertEqual(result["quotes"][0]["claim"], 1)
        self.assertEqual(result["status"], "answered")

    def test_only_whitespace_can_change(self):
        self.payload["claims"][0]["evidence"][0]["quote"] = "Just a\n portfolio for IV."
        validate(self.payload, [self.chunk])

    def test_fabricated_quote_rejected(self):
        self.payload["claims"][0]["evidence"][0]["quote"] = "IV requires a university degree."
        with self.assertRaises(ValueError):
            validate(self.payload, [self.chunk])

    def test_unknown_source_rejected(self):
        self.payload["claims"][0]["evidence"][0]["chunk_id"] = "invented"
        with self.assertRaises(ValueError):
            validate(self.payload, [self.chunk])

    def test_unquoted_claim_rejected(self):
        self.payload["claims"][0]["evidence"] = []
        with self.assertRaises(ValueError):
            validate(self.payload, [self.chunk])

    def test_weak_context_skips_generation(self):
        with patch("main.day22.complete") as complete:
            for chunks in ([], [{**self.chunk, "vector_score": 0.1}]):
                result = ask("question", chunks, "key", "model", 0.4)
                self.assertIn("Не знаю.", result["answer"])
                self.assertTrue(result["clarification"])
                self.assertEqual(result["sources"], [])
            complete.assert_not_called()

    def test_malformed_output_fails_closed(self):
        with patch("main.day22.complete", return_value="not JSON") as complete:
            result = ask("question", [self.chunk], "key", "model", 0.4)
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(result["reason"], "invalid_evidence")
        self.assertEqual(result["claims"], [])

    def test_invalid_schema_has_one_repair_attempt(self):
        with patch("main.day22.complete", side_effect=["{}", json.dumps(self.payload)]) as complete:
            result = ask("question", [self.chunk], "key", "model", 0.4)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["generation_attempts"], 2)
        self.assertEqual(len(result["validation_errors"]), 1)
        self.assertIn("validation_feedback", complete.call_args.args[1])

    def test_unknown_requires_clarification(self):
        with self.assertRaises(ValueError):
            validate({"status": "unknown", "claims": [], "clarification": ""}, [])
        result = validate({"status": "unknown", "claims": [], "clarification": "Какую студию вы имеете в виду?"}, [])
        self.assertEqual(result["status"], "unknown")

    def test_metadata_invention_rejected(self):
        self.payload["claims"][0]["evidence"][0]["source"] = "invented.pdf"
        with self.assertRaises(ValueError):
            validate(self.payload, [self.chunk])


if __name__ == "__main__":
    unittest.main()
