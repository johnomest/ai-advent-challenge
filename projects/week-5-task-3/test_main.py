import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("week_5_task_3", MODULE_PATH)
main = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = main
SPEC.loader.exec_module(main)


class RerankerTests(unittest.TestCase):
    def test_rerank_filters_and_deduplicates(self) -> None:
        candidates = [
            {
                "score": 0.60,
                "source": "manager.md",
                "section": "Audio",
                "title": "Rules",
                "text": "WAV stereo 24 bit audio",
            },
            {
                "score": 0.59,
                "source": "manager.md",
                "section": "Audio",
                "title": "Rules",
                "text": "Duplicate audio block",
            },
            {
                "score": 0.40,
                "source": "drive.md",
                "section": "Archive",
                "title": "Drive",
                "text": "File archive",
            },
        ]

        result = main.rerank(candidates, "audio WAV stereo bit", top_k=5, threshold=0.43)

        self.assertEqual(1, len(result))
        self.assertEqual("manager.md", result[0]["source"])
        self.assertGreater(result[0]["score"], result[0]["vector_score"])

    def test_terms_remove_common_words(self) -> None:
        self.assertEqual({"требования", "аудио"}, main.terms("Какие требования для аудио?"))

    def test_manager_sources_have_highest_authority(self) -> None:
        self.assertGreater(
            main.source_authority("managers/knowledge-base.md"),
            main.source_authority("legacy/old.md"),
        )

    def test_merge_candidates_keeps_best_score(self) -> None:
        merged = main.merge_candidates(
            [{"chunk_id": "a", "score": 0.4}],
            [{"chunk_id": "a", "score": 0.7}, {"chunk_id": "b", "score": 0.6}],
        )
        self.assertEqual(["a", "b"], [item["chunk_id"] for item in merged])
        self.assertEqual(0.7, merged[0]["score"])


if __name__ == "__main__":
    unittest.main()
