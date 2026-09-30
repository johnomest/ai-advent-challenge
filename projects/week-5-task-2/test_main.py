import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("week_5_task_2", MODULE_PATH)
main = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = main
SPEC.loader.exec_module(main)


class RagTests(unittest.TestCase):
    def test_retrieve_orders_chunks_by_similarity(self) -> None:
        index = {
            "chunks": [
                {"chunk_id": "a", "embedding": [1.0, 0.0]},
                {"chunk_id": "b", "embedding": [0.0, 1.0]},
            ]
        }
        result = main.retrieve(index, [0.9, 0.1], top_k=1)
        self.assertEqual("a", result[0]["chunk_id"])
        self.assertGreater(result[0]["score"], 0.9)

    def test_cosine_rejects_different_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            main.cosine_similarity([1.0], [1.0, 2.0])

    def test_evaluation_counts_expected_source(self) -> None:
        index = {"model": "test", "chunks": []}
        original_embed = main.embed_question
        original_retrieve = main.retrieve
        main.embed_question = lambda *args: [1.0]
        main.retrieve = lambda *args: [{"source": "manager.md"}]
        try:
            with tempfile.TemporaryDirectory() as directory:
                questions = Path(directory) / "questions.json"
                questions.write_text(
                    '[{"question":"Q","source":"manager.md#Section"}]',
                    encoding="utf-8",
                )
                self.assertEqual((1, 1), main.evaluate_retrieval(index, questions, 5, "url"))
        finally:
            main.embed_question = original_embed
            main.retrieve = original_retrieve


if __name__ == "__main__":
    unittest.main()
