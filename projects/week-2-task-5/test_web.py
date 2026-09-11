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
    @patch("main.urlopen")
    def test_strategy_branch_checkpoint_isolation_replay_and_atomicity(self, provider):
        def answer(text):
            return ApiResponse(json.dumps({"choices": [{"message": {"content": text}}]}).encode())
        provider.side_effect = [answer("First"), answer("Second"), answer("Branch answer")]
        cookie = self.new_owner()
        status, created, _ = self.request("POST", "/api/chats", {"strategy": "branching", "window_turns": 2}, cookie)
        self.assertEqual(status, 201)
        path = "/api/chats/" + created["chat"]["id"]
        self.assertEqual(self.request("PATCH", path, {"strategy": "branching", "window_turns": 1}, cookie)[0], 200)
        for index in range(2):
            self.assertEqual(self.request("POST", path + "/messages", {"message": f"Turn {index}", "request_id": f"request_{index}"}, cookie)[0], 200)
        self.assertEqual(self.request("PATCH", path, {"strategy": "sticky_facts"}, cookie)[0], 409)
        body = {"checkpoint_turn": 1, "request_id": "branch_req_1"}
        status, result, _ = self.request("POST", path + "/branches", body, cookie)
        self.assertEqual(status, 201)
        branches = result["branches"]
        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[0]["messages"], branches[1]["messages"])
        self.assertEqual(len(branches[0]["messages"]), 2)
        self.assertEqual(branches[0]["parent_id"], created["chat"]["id"])
        self.assertEqual(self.request("POST", path + "/branches", body, cookie)[1], result)
        self.assertEqual(self.request("POST", path + "/branches", {**body, "checkpoint_turn": 2}, cookie)[0], 409)
        self.assertEqual(self.request("POST", path + "/branches", body, self.new_owner())[0], 404)
        a_path = "/api/chats/" + branches[0]["id"]
        self.assertEqual(self.request("POST", a_path + "/messages", {"message": "Path A", "request_id": "request_A"}, cookie)[0], 200)
        self.assertEqual(len(self.request(path=path, cookie=cookie)[1]["chat"]["messages"]), 4)
        b_path = "/api/chats/" + branches[1]["id"]
        self.assertEqual(len(self.request(path=b_path, cookie=cookie)[1]["chat"]["messages"]), 2)
        with self.server.store.database() as database:
            database.execute("CREATE TRIGGER fail_branch BEFORE INSERT ON chats WHEN NEW.branch_label='B' BEGIN SELECT RAISE(ABORT, 'fail'); END")
        before = len(self.request(path="/api/chats", cookie=cookie)[1]["chats"])
        self.assertEqual(self.request("POST", path + "/branches", {**body, "request_id": "branch_req_2"}, cookie)[0], 500)
        self.assertEqual(len(self.request(path="/api/chats", cookie=cookie)[1]["chats"]), before)
        with self.server.store.database() as database:
            self.assertIsNone(database.execute("SELECT * FROM branch_requests WHERE request_id='branch_req_2'").fetchone())

    @patch("main.urlopen")
    def test_sticky_preview_no_provider_and_facts_snapshot_atomic(self, provider):
        cookie = self.new_owner()
        status, result, _ = self.request("POST", "/api/chats", {"strategy": "sticky_facts"}, cookie)
        self.assertEqual(status, 201)
        path = "/api/chats/" + result["chat"]["id"]
        self.assertEqual(self.request("POST", path + "/token-preview", {"message": "My name is Alice"}, cookie)[1]["estimate"]["facts_count"], 0)
        provider.assert_not_called()
        def response(text):
            return ApiResponse(json.dumps({"choices": [{"message": {"content": text}}]}).encode())
        provider.side_effect = [response('{"name":"Alice"}'), response("Hello")]
        with self.server.store.database() as database:
            database.execute("CREATE TRIGGER fail_sticky BEFORE UPDATE OF response ON requests BEGIN SELECT RAISE(ABORT, 'fail'); END")
        status, _, _ = self.request("POST", path + "/messages", {"message": "My name is Alice", "request_id": "facts_req_1"}, cookie)
        self.assertEqual(status, 500)
        chat = self.request(path=path, cookie=cookie)[1]["chat"]
        self.assertEqual(chat["facts"], {})
        self.assertEqual(chat["messages"], [])
        self.assertEqual(chat["turn_metrics"], [])

    @patch("main.urlopen")
    def test_preview_is_read_only_isolated_and_strict(self, provider) -> None:
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        before = self.request(path=path, cookie=cookie)[1]
        for message in ("", "Hello", "界" * 4000):
            status, result, _ = self.request("POST", path + "/token-preview", {"message": message}, cookie)
            self.assertEqual(status, 200)
            self.assertFalse(result["estimate"]["overflow"])
            self.assertEqual(result["estimate"]["context_limit"], 16384)
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
        self.server.config = AgentConfig(context_limit=2048, max_tokens=250)
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
        self.server.config = AgentConfig(context_limit=251, max_tokens=250)
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
