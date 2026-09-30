import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("week_5_task_1", MODULE_PATH)
main = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(main)


class IndexerTests(unittest.TestCase):
    def test_chunking_strategies_keep_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text(
                "# Guide\n\nIntro text.\n\n## Delivery\n\nOne two three four five six.",
                encoding="utf-8",
            )

            fixed = main.fixed_chunks(root, size=5, overlap=1)
            structured = main.structured_chunks(root, size=5, overlap=1)

        self.assertTrue(fixed)
        self.assertTrue(structured)
        self.assertEqual("guide.md", fixed[0].source)
        self.assertEqual("Guide", fixed[0].title)
        self.assertIn("Delivery", {chunk.section for chunk in structured})
        self.assertEqual({"Guide"}, {chunk.section for chunk in fixed})

    def test_word_windows_validate_overlap(self) -> None:
        with self.assertRaises(ValueError):
            main.word_windows("one two", size=2, overlap=2)

    def test_build_index_adds_vectors(self) -> None:
        chunk = main.Chunk("fixed-00001", "a.md", "A", "A", "fixed", "text")
        original = main.embed_batch
        main.embed_batch = lambda texts, model, base_url: [[0.5, 0.5] for _ in texts]
        try:
            index = main.build_index([chunk], "test", "http://localhost")
        finally:
            main.embed_batch = original

        self.assertEqual(2, index["dimensions"])
        self.assertEqual([0.5, 0.5], index["chunks"][0]["embedding"])


if __name__ == "__main__":
    unittest.main()
