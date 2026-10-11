import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("rag28_test", Path(__file__).with_name("main.py"))
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)


class RagTests(unittest.TestCase):
    def test_weak_context_skips_answer_model(self):
        with patch.object(rag, "retrieve", return_value=([], "query", {})), patch.object(rag.day27, "generate") as generate:
            result = rag.answer("Unknown?", [], {}, None)
        generate.assert_not_called()
        self.assertFalse(result["sources"])
        self.assertIn("Не знаю", result["answer"])

    def test_context_and_history_sent_with_canonical_sources(self):
        chunk = {"chunk_id": "a", "source": "book.pdf", "section": "A", "page": 1, "text": "Evidence", "vector_score": .8}
        history = []
        with patch.object(rag, "retrieve", return_value=([chunk], "query", {})), patch.object(rag.day27, "generate", return_value={"answer": "Supported [a]", "tokens": 3}) as generate:
            result = rag.answer("Question?", history, {}, None)
        self.assertEqual(result["sources"][0]["chunk_id"], "a")
        self.assertIn("Evidence", generate.call_args.args[0][-1]["content"])
        self.assertEqual(len(history), 2)

    def test_bad_embeddings_rejected(self):
        self.assertFalse(rag.vector_valid([float("nan")], 1))
        index = {"model": "embeddinggemma", "dimensions": 2}
        args = SimpleNamespace(url="http://127.0.0.1:8080", embedding_url="http://127.0.0.1:11434")
        with patch.object(rag.day27, "generate", return_value={"answer": "query"}), patch.object(rag.day27, "request", return_value={"embeddings": [[1], [2]]}):
            with self.assertRaises(RuntimeError):
                rag.retrieve("Question?", [], index, args)

    def test_generation_override_does_not_change_retrieval(self):
        chunk = {"chunk_id": "a", "source": "book.pdf", "section": "A", "page": 1,
                 "text": "Evidence", "vector_score": .8}
        retrieval_args, generation_args = object(), object()
        with patch.object(rag, "retrieve", return_value=([chunk], "query", {})) as retrieve, \
                patch.object(rag.day27, "generate", return_value={"answer": "OK", "tokens": 1}) as generate:
            rag.answer("Q?", [], {}, retrieval_args, system="custom", generation_args=generation_args)
        self.assertIs(retrieve.call_args.args[-1], retrieval_args)
        self.assertIs(generate.call_args.args[-1], generation_args)
        self.assertEqual(generate.call_args.args[0][0]["content"], "custom")

    def test_evaluation_records_failure_without_counting_it_as_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "projects/week-5-task-2/control_questions.json"
            cases_path.parent.mkdir(parents=True)
            cases_path.write_text(json.dumps([
                {"question": "A?", "expected": "A", "pages": [1], "terms": ["A"]},
                {"question": "B?", "expected": "B", "pages": [1], "terms": ["B"]},
            ]), encoding="utf-8")
            args = SimpleNamespace(model="local", url="http://127.0.0.1:8080",
                                   embedding_url="http://127.0.0.1:11434", top_k=5,
                                   threshold=.4, max_tokens=1536, output=root / "evaluation.json")
            index = {"model": "embeddinggemma", "chunks": [], "source_sha256": "source"}
            success = {"answer": "A", "seconds": 1.25,
                       "sources": [{"chunk_id": "a", "page": 1, "text": "A"}]}
            with patch.object(rag, "ROOT", root), patch.object(rag, "answer", side_effect=[success, RuntimeError("offline")]):
                with self.assertRaises(SystemExit) as failure:
                    rag.evaluate(index, args)
            self.assertEqual(failure.exception.code, 1)
            report = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["completed"], 1)
            self.assertEqual(report["summary"]["requests"], 2)
            self.assertEqual(report["summary"]["average_seconds"], 1.25)
            self.assertEqual(report["results"][1]["error"], "offline")

    def test_review_requires_same_answer_evidence_and_configuration(self):
        case = {"question": "Q?", "pages": [1], "terms": ["Evidence"]}
        source = {"chunk_id": "structure-00001", "page": 1, "text": "Evidence"}
        report = {key: "same" for key in (
            "model", "source_sha256", "embedding_model", "settings", "answer_system", "rewrite_system")}
        previous = {"question": "Q?", "answer": "Answer [structure-00001]", "expected": "Answer", "sources": [source]}
        reference = {**report, "results": [previous]}
        reviews = {"Q?": {"manual_quality": "complete", "note": "Checked"}}
        result = dict(previous)
        rag.assess_answer(case, result, report, reference, reviews)
        self.assertEqual(result["manual_review"]["status"], "complete")
        self.assertTrue(all(result["checks"].values()))
        changed = {**previous, "answer": "Changed [structure-00001]"}
        rag.assess_answer(case, changed, report, reference, reviews)
        self.assertEqual(changed["manual_review"]["status"], "unreviewed")
        changed = {**previous, "sources": [{**source, "text": "Different evidence"}]}
        rag.assess_answer(case, changed, report, reference, reviews)
        self.assertEqual(changed["manual_review"]["status"], "unreviewed")
        rag.assess_answer(case, result, {**report, "model": "other"}, reference, reviews)
        self.assertEqual(result["manual_review"]["status"], "unreviewed")

    def test_unknown_citation_fails_without_semantic_quality_claim(self):
        case = {"question": "Q?", "pages": [1], "terms": ["Evidence"]}
        result = {"answer": "[structure-99999]", "sources": [
            {"chunk_id": "structure-00001", "page": 1, "text": "Evidence"}]}
        rag.assess_answer(case, result, {}, None, {})
        self.assertTrue(result["checks"]["evidence_hit"])
        self.assertFalse(result["checks"]["citations_in_sources"])
        self.assertEqual(result["manual_review"]["status"], "unreviewed")

    def test_cloud_conclusion_requires_same_archived_answer(self):
        case = {"question": "Q?", "pages": [1], "terms": ["Evidence"]}
        report = {key: "same" for key in (
            "model", "source_sha256", "embedding_model", "settings", "answer_system", "rewrite_system")}
        report["cloud_model"] = "cloud"
        previous = {"question": "Q?", "expected": "Answer", "answer": "[structure-00001]",
                    "sources": [{"chunk_id": "structure-00001", "page": 1, "text": "Evidence"}],
                    "archived_cloud_answer": "Cloud answer"}
        reference = {**report, "results": [previous]}
        reviews = {"Q?": {"manual_quality": "complete", "note": "Checked",
                          "cloud_model": "cloud", "cloud_comparison": "Checked comparison"}}
        result = dict(previous)
        rag.assess_answer(case, result, report, reference, reviews)
        self.assertEqual(result["manual_review"]["cloud_comparison"], "Checked comparison")
        result["archived_cloud_answer"] = "Changed cloud answer"
        rag.assess_answer(case, result, report, reference, reviews)
        self.assertNotIn("cloud_comparison", result["manual_review"])

    def test_video_requires_cloud_archive_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "projects/week-5-task-2/control_questions.json"
            path.parent.mkdir(parents=True)
            path.write_text('[{"question": "Q?"}]', encoding="utf-8")
            with patch.object(rag, "ROOT", root), patch.object(rag, "answer") as answer:
                with self.assertRaisesRegex(ValueError, "архивные облачные ответы"):
                    rag.evaluate({}, SimpleNamespace(video_test=True))
            answer.assert_not_called()

    def test_video_writes_comparison_and_fails_on_wrong_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "projects/week-5-task-2"
            (folder / "data").mkdir(parents=True)
            (folder / "control_questions.json").write_text(json.dumps([
                {"question": "Q?", "expected": "Expected", "pages": [1], "terms": ["Evidence"]}
            ]), encoding="utf-8")
            (folder / "data/evaluation-answers.json").write_text(json.dumps({
                "source_sha256": "source", "model": "cloud",
                "results": [{"question": "Q?", "with_rag": "Archived answer"}]
            }), encoding="utf-8")
            args = SimpleNamespace(video_test=True, model="local", url="http://127.0.0.1:8080",
                                   embedding_url="http://127.0.0.1:11434", top_k=5, threshold=.4,
                                   max_tokens=1536, output=root / "video.json")
            index = {"source_sha256": "source", "model": "embeddinggemma", "chunks": []}
            result = {"answer": "[structure-00001]", "seconds": 1.25, "sources": [{
                "chunk_id": "structure-00001", "page": 2, "text": "Evidence", "studio": "IV"}]}
            with patch.object(rag, "ROOT", root), patch.object(rag, "load_manual_review", return_value=(None, {})), \
                    patch.object(rag, "answer", return_value=result), patch("sys.stdout", new=rag.io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    rag.evaluate(index, args)
            self.assertEqual(failure.exception.code, 1)
            report = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["completed"], 1)
            self.assertEqual(report["summary"]["evidence_hits"], 0)
            self.assertEqual(report["summary"]["review_unreviewed"], 1)
            markdown = args.output.with_suffix(".md").read_text(encoding="utf-8")
            self.assertIn("Archived answer", markdown)
            self.assertIn("нужная страница: НЕТ", markdown)
            self.assertIn("## Выводы", markdown)


if __name__ == "__main__":
    unittest.main()
