import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("opt29_test", Path(__file__).with_name("main.py"))
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)


class OptimizationTests(unittest.TestCase):
    def test_each_experiment_changes_one_factor(self):
        factors = ("quantization", "context", "temperature", "max_tokens", "prompt")
        for config in opt.EXPERIMENTS[1:]:
            self.assertEqual(sum(config[key] != opt.BASELINE[key] for key in factors), 1)

    def test_failure_not_included_in_latency_average(self):
        summary = opt.summarize([
            {"seconds": 2, "tokens": 8, "timings": {"predicted_per_second": 40},
             "checks": {"citations_in_sources": True}},
            {"error": "truncated"},
        ])
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["requests"], 2)
        self.assertEqual(summary["average_generation_seconds"], 2)
        self.assertEqual(summary["average_decode_tokens_per_second"], 40)

    def test_option_change_preserves_other_runtime_flags(self):
        args = ["server.exe", "--host", "127.0.0.1", "--ctx-size", "8192", "--parallel", "1"]
        changed = opt.runtime.set_option(args, "--ctx-size", 4096)
        self.assertEqual(changed, ["server.exe", "--host", "127.0.0.1", "--ctx-size", "4096", "--parallel", "1"])
        self.assertEqual(args[4], "8192")

    def test_benchmark_restores_server_after_error(self):
        index = {"model": "embeddinggemma", "source_sha256": "source"}
        with patch.object(opt.runtime, "Server") as factory, patch.object(opt, "prepare", side_effect=RuntimeError("failed")), \
                patch.object(opt, "pin_embeddings"), \
                patch.object(opt.runtime, "MODELS", {}):
            factory.return_value.original = []
            with self.assertRaisesRegex(RuntimeError, "failed"):
                opt.benchmark(index)
            factory.return_value.restore.assert_called_once()

    def test_runtime_does_not_stop_server_on_similarly_named_port(self):
        process = {"ExecutablePath": str(opt.runtime.RUNTIME), "CommandLine": "server --port 80801",
                   "ProcessId": 123}
        with patch.object(opt.runtime, "processes", return_value=[process]), \
                patch.object(opt.runtime, "split_command", return_value=["server", "--port", "80801"]):
            with self.assertRaisesRegex(RuntimeError, "port 8080"):
                opt.runtime.Server(lambda *args: {}, opt.DATA)

    def test_prepared_context_stays_identical_between_prompts(self):
        case = {"question": "Q?", "sources": [{"chunk_id": "structure-00001", "text": "Evidence"}]}
        with patch.object(opt.rag.day27, "generate", return_value={"answer": "OK"}) as generate:
            opt.answer_prepared(case, opt.BASELINE)
            before = generate.call_args.args[0][-1]
            opt.answer_prepared(case, opt.SELECTED)
            after = generate.call_args.args[0][-1]
        self.assertEqual(before, after)

    def test_manual_grade_fingerprint_ignores_timing_but_detects_changed_evidence(self):
        import copy
        record = {"config": opt.SELECTED, "answer_system": opt.system(opt.SELECTED),
                  "model_sha256": "model", "source_sha256": "source",
                  "results": [{"question": "Q", "answer": "A", "sources": [], "seconds": 1}]}
        changed = copy.deepcopy(record)
        changed["results"][0]["seconds"] = 2
        self.assertEqual(opt.fingerprint(record), opt.fingerprint(changed))
        changed["results"][0]["answer"] = "Different"
        self.assertNotEqual(opt.fingerprint(record), opt.fingerprint(changed))
        changed = copy.deepcopy(record)
        changed["model_sha256"] = "other-model"
        self.assertNotEqual(opt.fingerprint(record), opt.fingerprint(changed))


if __name__ == "__main__":
    unittest.main()
