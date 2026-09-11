import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from test_main import ApiResponse
from main import AgentConfig
from web import BODY_LIMIT, COOKIE_MAX_AGE, ChatServer, public_origin


class WebTests(unittest.TestCase):
    def seed_history(self, cookie, path, count):
        messages = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"Fact {index}"}
                    for index in range(count)]
        with self.server.store.database() as database:
            database.execute("UPDATE chats SET messages=? WHERE id=?", (json.dumps(messages), path.rsplit("/", 1)[1]))
        return messages

    @patch("main.urlopen")
    def test_compression_backlog_bounded_untrusted_and_replay_snapshot(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        history = self.seed_history(cookie, path, 28)
        owner = cookie.split("=", 1)[1]
        payload = {"message": "Remember?", "request_id": "compress_1"}
        calls = []
        def respond(request, **kwargs):
            self.assertEqual(self.server.store.get_request(owner, "compress_1")["state"], "pending")
            calls.append(json.loads(request.data))
            answer = "Saved facts" if len(calls) < 4 else "Remembered"
            return ApiResponse(json.dumps({"choices": [{"message": {"content": answer}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
                          "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 10}}).encode())
        provider.side_effect = respond
        preview = self.request("POST", path + "/token-preview", {"message": "Remember?"}, cookie)
        self.assertTrue(preview[1]["estimate"]["pending_compression"])
        provider.assert_not_called()
        status, first, _ = self.request("POST", path + "/messages", payload, cookie)
        self.assertEqual(status, 200)
        self.assertEqual([len(json.loads(call["messages"][-1]["content"])["new_messages"]) for call in calls[:3]], [10, 10, 2])
        self.assertEqual(json.loads(calls[1]["messages"][-1]["content"])["previous_summary"], "Saved facts")
        self.assertEqual(calls[3]["messages"][1]["role"], "user")
        self.assertNotIn("Saved facts", calls[3]["messages"][0]["content"])
        self.assertEqual(calls[3]["messages"][2:-1], history[-6:])
        chat = first["chat"]
        self.assertEqual(chat["messages"][:28], history)
        self.assertEqual(chat["compression"]["summarized_count"], 22)
        self.assertEqual(chat["compression"]["summary_api_tokens"], 36)
        self.assertIsNotNone(chat["compression"]["summary_cost"])
        self.assertEqual(chat["total_tokens"], 12)
        self.assertEqual(chat["turn_metrics"][0]["turn_index"], 15)
        self.assertEqual(self.request("POST", path + "/compression", {"mode": "full"}, cookie)[0], 200)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("POST", path + "/messages", payload, cookie)[1], first)
        self.assertEqual(len(calls), 4)
        self.assertEqual(self.request("DELETE", path, cookie=cookie)[0], 200)
        self.assertIsNone(self.server.store.get_request(owner, "compress_1"))

    @patch("main.urlopen")
    def test_compression_failure_and_snapshot_rollback(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        self.seed_history(cookie, path, 8)
        before = self.request(path=path, cookie=cookie)[1]
        provider.side_effect = [ApiResponse(b'{"choices":[{"message":{"content":"Summary"}}]}'), RuntimeError("SECRET")]
        payload = {"message": "Hi", "request_id": "failed_123"}
        self.assertEqual(self.request("POST", path + "/messages", payload, cookie)[0], 502)
        self.assertEqual(self.request("POST", path + "/messages", payload, cookie)[0], 502)
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)
        provider.side_effect = [ApiResponse(b'{"choices":[{"message":{"content":"Summary"}}]}'),
                                ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')]
        with self.server.store.database() as database:
            database.execute("CREATE TRIGGER fail_snapshot BEFORE UPDATE OF response ON requests BEGIN SELECT RAISE(ABORT, 'snapshot failed'); END")
        payload["request_id"] = "snapshot_1"
        self.assertEqual(self.request("POST", path + "/messages", payload, cookie)[0], 500)
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)
        self.assertEqual(self.request("POST", path + "/messages", payload, cookie)[0], 409)
        self.assertEqual(provider.call_count, 4)

    @patch("main.urlopen")
    def test_signed_comparison_mode_validation_and_unknown_summary_usage(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        self.seed_history(cookie, path, 8)
        provider.side_effect = [ApiResponse(json.dumps({"choices": [{"message": {"content": "Long summary " * 60}}]}).encode()),
                                ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')]
        status, result, _ = self.request("POST", path + "/messages", {"message": "Hi", "request_id": "signed_123"}, cookie)
        self.assertEqual(status, 200)
        self.assertLess(result["chat"]["comparison"]["saved_tokens"], 0)
        self.assertIsNone(result["chat"]["compression"]["summary_api_tokens"])
        self.assertIsNone(result["chat"]["compression"]["summary_cost"])
        comparison = result["chat"]["comparison"]
        self.assertEqual(self.request("POST", path + "/compression", {"mode": "full"}, cookie)[1]["chat"]["comparison"], comparison)
        for mode in ([], {}, None, True, "invalid"):
            self.assertEqual(self.request("POST", path + "/compression", {"mode": mode}, cookie)[0], 400)
        alien = self.new_owner()
        self.assertEqual(self.request("POST", path + "/compression", {"mode": "full"}, alien)[0], 404)

    @patch("main.urlopen")
    def test_preview_is_read_only_isolated_and_strict(self, provider) -> None:
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        before = self.request(path=path, cookie=cookie)[1]
        for message in ("", "Hello", "界" * 4000):
            status, result, _ = self.request("POST", path + "/token-preview", {"message": message}, cookie)
            self.assertEqual(status, 200)
            self.assertEqual(result["estimate"]["overflow"], len(message) == 4000)
            self.assertEqual(result["estimate"]["context_limit"], 2048)
        for body in ({}, {"message": 1}, {"message": "x" * 4001}, {"message": "x", "model": "other"}):
            self.assertEqual(self.request("POST", path + "/token-preview", body, cookie)[0], 400)
        self.assertEqual(self.request("POST", path + "/token-preview", {"message": "Hi"}, self.new_owner())[0], 404)
        self.assertEqual(self.request("POST", path + "/token-preview", {"message": "Hi"}, cookie,
                                      {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)
        with self.server.store.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)
        provider.assert_not_called()

    @patch("main.urlopen")
    def test_overflow_returns_estimate_without_reserving_request(self, provider) -> None:
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        before = self.request(path=path, cookie=cookie)[1]
        payload = {"message": "界" * 4000, "request_id": "overflow_1"}
        status, result, _ = self.request("POST", path + "/messages", payload, cookie)
        self.assertEqual(status, 422)
        self.assertEqual(result["error"]["code"], "context_limit")
        self.assertTrue(result["error"]["estimate"]["overflow"])
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)
        self.assertIsNone(self.server.store.get_request(cookie.split("=", 1)[1], "overflow_1"))
        provider.assert_not_called()

    @patch("main.urlopen")
    def test_metrics_replay_precedes_preflight_after_context_grows(self, provider) -> None:
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                 "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60}
        provider.side_effect = [ApiResponse(json.dumps({"choices": [{"message": {"content": "Answer"}}],
                                                       "usage": usage}).encode()) for _ in range(2)]
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        payload = {"message": "Hello", "request_id": "request_1"}
        first = self.request("POST", path + "/messages", payload, cookie)
        self.assertEqual(first[0], 200)
        second = self.request("POST", path + "/messages", {"message": "Again", "request_id": "request_2"}, cookie)
        self.assertEqual(second[0], 200)
        metrics = second[1]["chat"]["turn_metrics"]
        self.assertEqual(len(metrics), 2)
        self.assertGreater(metrics[1]["history_tokens"], metrics[0]["history_tokens"])
        self.assertIsNotNone(metrics[0]["cost"])
        self.server.config = AgentConfig(context_limit=251)
        replay = self.request("POST", path + "/messages", payload, cookie)
        self.assertEqual(replay[0], 200)
        self.assertEqual(replay[1]["chat"]["turn_metrics"], first[1]["chat"]["turn_metrics"])
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["total_tokens"], 240)
        self.assertEqual(len(self.request(path=path, cookie=cookie)[1]["chat"]["turn_metrics"]), 2)
        self.assertEqual(provider.call_count, 2)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["turn_metrics"], metrics)

    @patch("main.urlopen")
    def test_snapshot_failure_rolls_back_messages_and_metrics(self, provider) -> None:
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}],"usage":{"total_tokens":10}}')
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        before = self.request(path=path, cookie=cookie)[1]
        with self.server.store.database() as database:
            database.execute("CREATE TRIGGER fail_snapshot BEFORE UPDATE OF response ON requests BEGIN SELECT RAISE(ABORT, 'snapshot failed'); END")
        status, _, _ = self.request("POST", path + "/messages", {"message": "Hello", "request_id": "request_1"}, cookie)
        self.assertEqual(status, 500)
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)
        request = self.server.store.get_request(cookie.split("=", 1)[1], "request_1")
        self.assertEqual(request["state"], "pending")
        self.assertIsNone(request["response"])

    def setUp(self) -> None:
        self.key_patch = patch("main.load_api_key", return_value="test-key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "context.sqlite3"
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self, external_origin=None) -> None:
        self.server = ChatServer(0, external_origin, self.database_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method="GET", path="/api/chats", payload=None, cookie=None, headers=None):
        request_headers = {"Origin": self.origin}
        if cookie:
            request_headers["Cookie"] = cookie
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            result = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def new_owner(self):
        status, data, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(data["chats"], [])
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertIn(f"Max-Age={COOKIE_MAX_AGE}", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def new_chat(self, cookie):
        status, data, _ = self.request("POST", "/api/chats", {}, cookie)
        self.assertEqual(status, 201)
        self.assertEqual(data["chat"]["messages"], [])
        return "/api/chats/" + data["chat"]["id"]

    @patch("main.urlopen")
    def test_lifecycle_restart_and_cookie_isolation(self, provider) -> None:
        provider.side_effect = [
            ApiResponse(json.dumps({"choices": [{"message": {"content": answer}}], "usage": {"total_tokens": 10}}).encode())
            for answer in ["First answer.", "Revised answer."]
        ]
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        empty_path = self.new_chat(cookie)
        status, data, _ = self.request("POST", path + "/messages", {"message": "Hello", "request_id": "request_1"}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["chat"]["title"], "Hello")
        self.assertEqual(len(data["chat"]["messages"]), 2)
        self.assertNotIn("system", [message["role"] for message in data["chat"]["messages"]])
        status, data, _ = self.request("POST", path + "/messages", {"message": "Shorter", "request_id": "request_2"}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["chat"]["total_tokens"], 20)
        self.assertEqual(len(data["chat"]["messages"]), 4)
        payload = json.loads(provider.call_args_list[1].args[0].data)
        self.assertEqual([item["content"] for item in payload["messages"]][-3:], ["Hello", "First answer.", "Shorter"])
        alien = self.new_owner()
        for method, suffix, body in [("GET", "", None), ("PATCH", "", {"title": "Other"}),
                                      ("DELETE", "", None), ("POST", "/messages", {"message": "X", "request_id": "request_3"})]:
            self.assertEqual(self.request(method, path + suffix, body, alien)[0], 404)
        self.assertEqual(self.request("PATCH", path, {"title": "Custom title"}, cookie)[1]["chat"]["title"], "Custom title")
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["title"], "Custom title")
        self.assertEqual(self.request(path=empty_path, cookie=cookie)[1]["chat"]["messages"], [])
        self.assertEqual(len(self.request(cookie=cookie)[1]["chats"]), 2)
        self.assertEqual(self.request("DELETE", path, cookie=cookie)[0], 200)
        self.assertEqual(self.request(path=path, cookie=cookie)[0], 404)
        self.assertEqual(len(self.request(cookie=cookie)[1]["chats"]), 1)

    @patch("main.urlopen", side_effect=RuntimeError("SECRET provider details"))
    def test_provider_failure_is_safe_atomic_and_not_recalled(self, provider) -> None:
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        before = self.request(path=path, cookie=cookie)[1]
        payload = {"message": "Hello", "request_id": "request_1"}
        for _ in range(2):
            status, data, _ = self.request("POST", path + "/messages", payload, cookie)
            self.assertEqual(status, 502)
            self.assertEqual(data["error"]["code"], "provider_error")
            self.assertNotIn("SECRET", json.dumps(data))
        provider.assert_called_once()
        self.assertEqual(self.request(path=path, cookie=cookie)[1], before)

    @patch("main.urlopen")
    def test_idempotency_replay_conflict_and_pending(self, provider) -> None:
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')
        cookie = self.new_owner()
        owner_id = cookie.split("=", 1)[1]
        path = self.new_chat(cookie)
        payload = {"message": "Hello", "request_id": "request_1"}
        first = self.request("POST", path + "/messages", payload, cookie)
        self.stop_server()
        self.start_server()
        replay = self.request("POST", path + "/messages", payload, cookie)
        self.assertEqual(first[:2], replay[:2])
        provider.assert_called_once()
        status, result, _ = self.request("POST", path + "/messages", {**payload, "message": "Changed"}, cookie)
        self.assertEqual((status, result["error"]["code"]), (409, "request_conflict"))
        self.server.store.reserve_request(owner_id, path.rsplit("/", 1)[1], "pending_1", "Waiting")
        status, result, _ = self.request("POST", path + "/messages", {"message": "Waiting", "request_id": "pending_1"}, cookie)
        self.assertEqual((status, result["error"]["code"]), (409, "request_pending"))
        provider.assert_called_once()

    @patch("main.urlopen")
    def test_get_available_while_model_busy_and_other_mutations_rejected(self, provider) -> None:
        started, release = threading.Event(), threading.Event()
        def respond(*args, **kwargs):
            started.set()
            if not release.wait(4):
                raise TimeoutError()
            return ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')
        provider.side_effect = respond
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        results = []
        worker = threading.Thread(target=lambda: results.append(self.request("POST", path + "/messages", {"message": "Hello", "request_id": "request_1"}, cookie)))
        worker.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertTrue(self.request(cookie=cookie)[1]["busy"])
            self.assertTrue(self.request(path=path, cookie=cookie)[1]["chat"]["busy"])
            for method, route, payload in [("POST", "/api/chats", {}), ("PATCH", path, {"title": "Other"}), ("DELETE", path, None)]:
                self.assertEqual(self.request(method, route, payload, cookie)[0], 409)
        finally:
            release.set()
            worker.join()
        self.assertEqual(results[0][0], 200)
        self.assertFalse(self.request(cookie=cookie)[1]["busy"])

    @patch("main.urlopen")
    def test_input_origin_and_static_security(self, provider) -> None:
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        invalid = [None, [], {}, {"message": " "}, {"message": 3}, {"message": "A" * 4001, "request_id": "request_1"},
                   {"message": "Hello", "request_id": "short"}, {"message": "Hello", "request_id": "request_1", "model": "other"}]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:50]):
                self.assertIn(self.request("POST", path + "/messages", payload, cookie)[0], [400, 415])
        for title in [" ", "a" * 101, 1, None]:
            self.assertEqual(self.request("PATCH", path, {"title": title}, cookie)[0], 400)
        for method in ["POST", "PATCH", "DELETE"]:
            self.assertEqual(self.request(method, path, {}, cookie, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/chats", {}, cookie, {"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.request("POST", "/api/chats", {"name": "X" * BODY_LIMIT}, cookie)[0], 413)
        self.assertEqual(self.request("POST", "/api/chats", {}, cookie, {"Content-Type": "text/plain"})[0], 415)
        for path in ["/.env", "/main.py", "/../.env", "/static/app.js", "/%2e%2e/.env"]:
            self.assertEqual(self.request(path=path)[0], 404)
        for path in ["/goost-typo.svg", "/goost-logo.svg"]:
            status, asset, headers = self.request(path=path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "image/svg+xml")
            self.assertIn(b"<svg", asset)
        for path in [
            "/fonts/tt-wellingtons-regular.woff2",
            "/fonts/tt-wellingtons-demibold.woff2",
            "/fonts/tt-wellingtons-bold.woff2",
        ]:
            status, asset, headers = self.request(path=path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "font/woff2")
            self.assertTrue(asset)
        status, _, headers = self.request()
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        provider.assert_not_called()

    def test_legacy_cookie_migration_keeps_history(self) -> None:
        self.stop_server()
        legacy_id = "x" * 43
        with closing(sqlite3.connect(self.database_path)) as database, database:
            database.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, messages TEXT NOT NULL, total_tokens INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            database.execute("INSERT INTO conversations VALUES (?, ?, 9, 1)", (legacy_id, '[{"role":"user","content":"Remember"},{"role":"assistant","content":"Stored"}]'))
            database.execute("PRAGMA user_version=0")
        self.start_server()
        for name in ["chat_session", "pitch_session"]:
            status, result, headers = self.request(cookie=f"{name}={legacy_id}")
            self.assertEqual(status, 200)
            self.assertNotEqual(result["chats"][0]["id"], legacy_id)
            self.assertEqual(result["chats"][0]["total_tokens"], 9)
            self.assertIn(f"goost_owner={legacy_id}", headers["Set-Cookie"])
        with closing(sqlite3.connect(self.database_path)) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 1)
        self.stop_server()
        self.start_server()
        self.assertEqual(len(self.request(cookie=f"goost_owner={legacy_id}")[1]["chats"]), 1)

    def test_exact_public_origin_and_secure_cookie(self) -> None:
        origin = "https://demo.trycloudflare.com"
        self.stop_server()
        self.start_server(origin)
        headers = {"Host": "demo.trycloudflare.com", "Origin": origin}
        status, _, response_headers = self.request(headers=headers)
        self.assertEqual(status, 200)
        self.assertIn("Secure", response_headers["Set-Cookie"])
        self.assertEqual(self.request(headers={"Host": "other.trycloudflare.com"})[0], 403)
        self.assertEqual(self.request("POST", "/api/chats", {}, headers={**headers, "Origin": "https://evil.example"})[0], 403)

    def test_public_origin_validation(self) -> None:
        self.assertEqual(public_origin("https://demo.example/"), "https://demo.example")
        for value in ["http://demo.example", "https://demo.example/path", "https://user@demo.example"]:
            with self.subTest(value=value), self.assertRaises(Exception):
                public_origin(value)


if __name__ == "__main__":
    unittest.main()
