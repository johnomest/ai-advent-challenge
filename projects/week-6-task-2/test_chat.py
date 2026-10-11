import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("chat27_test", Path(__file__).with_name("main.py"))
chat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chat)


class ChatTests(unittest.TestCase):
    def test_history_success_and_failure(self):
        history = []
        with patch.object(chat, "generate", return_value={"answer": "OK", "seconds": 1, "tokens": 1}):
            for _ in range(8):
                chat.turn("Hello", history, None)
        self.assertEqual(len(history), 10)
        before = list(history)
        with patch.object(chat, "generate", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                chat.turn("Hello", history, None)
        self.assertEqual(history, before)

    def test_remote_urls_and_cloud_models_blocked(self):
        with self.assertRaises(ValueError):
            chat.request("https://example.com", "/api/chat", {})
        args = SimpleNamespace(url="http://127.0.0.1:11434")
        with patch.object(chat, "request", return_value={"remote_host": "example.com"}):
            with self.assertRaises(ValueError):
                chat.ensure_local_model(args.url, "remote")

    def test_truncation_rejected(self):
        args = SimpleNamespace(url="http://127.0.0.1:8080", model="Qwen3.5-9B-Q8_0", max_tokens=100)
        with patch.object(chat, "request", return_value={"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}):
            with self.assertRaises(RuntimeError):
                chat.generate([], args)

    def test_llama_response_and_request(self):
        args = chat.arguments().parse_args([])
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "Париж"}}],
                    "usage": {"completion_tokens": 3}}
        with patch.object(chat, "request", return_value=response) as request:
            result = chat.generate([{"role": "user", "content": "Столица Франции?"}], args)
        self.assertEqual(result["answer"], "Париж")
        self.assertEqual(result["tokens"], 3)
        self.assertEqual(request.call_args.args[1], "/v1/chat/completions")
        self.assertFalse(request.call_args.args[2]["chat_template_kwargs"]["enable_thinking"])
        for invalid in ({"choices": []}, {"choices": [None]},
                        {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}):
            with patch.object(chat, "request", return_value=invalid):
                with self.assertRaises(RuntimeError):
                    chat.generate([], args)

    def test_wrong_server_model_rejected(self):
        args = chat.arguments().parse_args([])
        with patch.object(chat, "request", return_value={"data": [{"id": "other-model"}]}):
            with self.assertRaises(ValueError):
                chat.validate(args)

    def test_explicit_sampling_and_server_timings(self):
        args = chat.arguments().parse_args([])
        args.temperature, args.seed, args.cache_prompt = .3, 42, False
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                    "usage": {"completion_tokens": 2, "prompt_tokens": 12},
                    "timings": {"predicted_per_second": 40}}
        with patch.object(chat, "request", return_value=response) as request:
            result = chat.generate([], args)
        payload = request.call_args.args[2]
        self.assertEqual((payload["temperature"], payload["seed"], payload["cache_prompt"]), (.3, 42, False))
        self.assertEqual(result["timings"]["predicted_per_second"], 40)
        self.assertEqual(result["prompt_tokens"], 12)

    def test_connection_reset_reported_as_unavailable(self):
        with patch.object(chat, "build_opener") as opener:
            opener.return_value.open.side_effect = ConnectionResetError("starting")
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                chat.request("http://127.0.0.1:8080", "/health")

    def test_reset_and_redirect(self):
        seen = []
        def answer(question, history):
            seen.append(list(history))
            history.append({"role": "user", "content": question})
            return {"answer": "OK", "seconds": 0, "tokens": 1}
        with patch("builtins.input", side_effect=["Hello", "/reset", "Again", "/exit"]):
            chat.chat_loop(answer)
        self.assertEqual(seen, [[], []])
        self.assertIsNone(chat.NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_context_limit_checked_before_generation(self):
        args = chat.arguments().parse_args([])
        args.context_limit, args.max_tokens, args.request_timeout = 100, 40, 30
        with patch.object(chat, "request", side_effect=[{"prompt": "formatted"}, {"tokens": list(range(61))}]) as request:
            with self.assertRaisesRegex(ValueError, "Context limit"):
                chat.generate([{"role": "user", "content": "Q"}], args)
        self.assertEqual([call.args[1] for call in request.call_args_list], ["/apply-template", "/tokenize"])
        self.assertTrue(all(call.kwargs["timeout"] == 30 for call in request.call_args_list))


if __name__ == "__main__":
    unittest.main()
