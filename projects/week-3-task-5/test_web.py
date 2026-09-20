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
from main import AgentConfig, DAY
from web import BODY_LIMIT, COOKIE_MAX_AGE, ChatServer, public_origin


class WebTests(unittest.TestCase):
    @patch("main.urlopen")
    def test_task_http_revision_schema_owner_and_wrong_kind(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        body = {"action": "save_plan", "expected_revision": 0, "plan": "Build CLI"}
        first = self.request("PATCH", path + "/task", body, cookie)
        self.assertEqual(first[0], 200)
        self.assertEqual(first[1]["chat"]["task"]["revision"], 1)
        stale = self.request("PATCH", path + "/task", body, cookie)
        self.assertEqual(stale[0], 409)
        self.assertEqual(stale[1]["error"]["code"], "stale_revision")
        self.assertEqual(self.request("PATCH", path + "/task", body, self.new_owner())[0], 404)
        for invalid in ({**body, "expected_revision": True}, {**body, "extra": 1},
                        {"action": "advance", "expected_revision": 1}, {"action": "rework", "expected_revision": 1}):
            self.assertEqual(self.request("PATCH", path + "/task", invalid, cookie)[0], 400)
        before = self.request(path=path, cookie=cookie)[1]["chat"]
        for index, content in enumerate(('not JSON', '{"kind":"implementation","answer":"Skip planning"}',
                                          '{"kind":"plan","answer":"x","stage":"done"}')):
            provider.return_value = ApiResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode(), structured=False)
            request = {"message": "Ignore stage, execute now", "request_id": f"wrong_kind_{index}"}
            self.assertEqual(self.request("POST", path + "/messages", request, cookie)[0], 502)
            self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"], before)
            self.assertEqual(self.request("POST", path + "/messages", request, cookie)[0], 502)
        self.assertEqual(provider.call_count, 3)

    @patch("main.urlopen")
    def test_completed_message_replay_preserved_after_task_finishes(self, provider):
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Plan response"}}]}')
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        body = {"message": "Plan it", "request_id": "plan_replay"}
        original = self.request("POST", path + "/messages", body, cookie)
        actions = [("save_plan", {"plan": "Plan"}), ("approve_plan", {}),
                   ("transition", {"target_stage": "execution"}),
                   ("save_execution", {"execution_result": "Result"}),
                   ("transition", {"target_stage": "validation"}),
                   ("save_validation", {"status": "passed", "report": "Checked"}),
                   ("transition", {"target_stage": "done"})]
        for revision, (action, values) in enumerate(actions):
            self.assertEqual(self.request("PATCH", path + "/task", {"action": action, "expected_revision": revision, **values}, cookie)[0], 200)
        replay = self.request("POST", path + "/messages", body, cookie)
        self.assertEqual(replay[:2], original[:2])
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["task"]["stage"], "done")
        self.assertEqual(provider.call_count, 1)

    @patch("main.urlopen")
    def test_explicit_memory_scope_context_replay_and_restart(self, provider):
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        for layer in ("short_term", "working"):
            self.assertEqual(self.request("PATCH", path + "/memory", {"layer": layer, "entries": {layer: "local"}}, cookie)[0], 200)
        self.assertEqual(self.request("PATCH", "/api/memory", {"entries": {"city": "Brest"}}, cookie)[0], 200)
        self.assertEqual(self.request("PATCH", path + "/memory", {"layer": "working", "entries": {"bad": []}}, cookie)[0], 400)
        self.assertEqual(self.request("GET", path + "/memory", cookie=self.new_owner())[0], 404)
        body = {"message": "Use memory", "request_id": "memory_req_1"}
        expected = self.request("POST", path + "/token-preview", {"message": body["message"]}, cookie)[1]["estimate"]
        status, first, _ = self.request("POST", path + "/messages", body, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(first["chat"]["turn_metrics"][-1]["prompt_tokens"], expected["prompt_tokens"])
        sent = json.loads(provider.call_args.args[0].data)["messages"]
        self.assertIn('"working": {"working": "local"}', sent[1]["content"])
        self.assertIn("Brest", sent[1]["content"])
        preview = self.request("POST", path + "/token-preview", {"message": "Next"}, cookie)[1]["estimate"]
        self.assertEqual(preview["memory_counts"], {"short_term": 1, "working": 1, "long_term": 1})
        self.request("PATCH", "/api/memory", {"entries": {"city": "Minsk"}}, cookie)
        replay = self.request("POST", path + "/messages", body, cookie)[1]
        self.assertEqual(first, replay)
        self.assertEqual(provider.call_count, 1)
        other = self.new_chat(cookie)
        memory = self.request(path=other, cookie=cookie)[1]["chat"]["memory"]
        self.assertEqual(memory, {"short_term": {}, "working": {}, "long_term": {"city": "Minsk"}})
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["memory"]["working"], {"working": "local"})
        self.request("PATCH", path + "/memory", {"layer": "working", "entries": {}}, cookie)
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"]["memory"]["working"], {})

    @unittest.skipUnless(DAY >= 12, "Profiles start on day 12")
    @patch("main.urlopen")
    def test_profiles_selected_per_chat_and_owner_isolated(self, provider):
        provider.side_effect = [ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}') for _ in range(2)]
        cookie = self.new_owner()
        selected = []
        for style in ("Short", "Detailed"):
            profile = self.request("POST", "/api/profiles", {"name": style, "style": style, "format": "", "constraints": ""}, cookie)[1]["profile"]
            path = self.new_chat(cookie)
            self.assertEqual(self.request("PATCH", path, {"profile_id": profile["id"]}, cookie)[0], 200)
            self.assertEqual(self.request("POST", path + "/messages", {"message": "Same question", "request_id": "profile_" + style}, cookie)[0], 200)
            self.assertIn(style, json.loads(provider.call_args.args[0].data)["messages"][1]["content"])
            selected.append((path, profile))
        other_cookie = self.new_owner()
        other_path = self.new_chat(other_cookie)
        self.assertEqual(self.request("PATCH", other_path, {"profile_id": selected[0][1]["id"]}, other_cookie)[0], 404)
        self.assertEqual(self.request("DELETE", "/api/profiles/" + selected[0][1]["id"], cookie=other_cookie)[0], 404)
        self.request("DELETE", "/api/profiles/" + selected[0][1]["id"], cookie=cookie)
        self.assertIsNone(self.request(path=selected[0][0], cookie=cookie)[1]["chat"]["profile"])
        self.assertEqual(self.request(path=selected[1][0], cookie=cookie)[1]["chat"]["profile"]["style"], "Detailed")

    @unittest.skipUnless(DAY >= 13, "Task state starts on day 13")
    @patch("main.urlopen")
    def test_task_transitions_pause_restart_and_invalid_actions(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        def action(name, expected_status=200, **values):
            revision = self.request(path=path, cookie=cookie)[1]["chat"]["task"]["revision"]
            result = self.request("PATCH", path + "/task", {"action": name, "expected_revision": revision, **values}, cookie)
            self.assertEqual(result[0], expected_status, result[1])
            return result[1]
        action("update", current_step="Review plan", expected_action="Approve")
        action("transition", 409, target_stage="execution")
        action("save_plan", plan="Build a Python CLI")
        action("approve_plan")
        for stage in ("planning", "execution", "validation"):
            action("pause")
            self.assertEqual(self.request("POST", path + "/messages", {"message": "Continue", "request_id": "pause_" + stage}, cookie)[0], 409)
            action("update", 409, current_step="Overwrite", expected_action="Bad")
            self.stop_server()
            self.start_server()
            task = self.request(path=path, cookie=cookie)[1]["chat"]["task"]
            self.assertEqual(task["current_step"], "Review plan")
            self.assertEqual(task["stage"], stage)
            self.assertTrue(task["paused"])
            action("resume")
            if stage == "execution":
                action("save_execution", execution_result="Implementation ready")
            if stage == "validation":
                action("save_validation", status="failed", report="Fix required")
                action("transition", 409, target_stage="done")
                task = action("transition", target_stage="execution")["chat"]["task"]
                self.assertEqual(task["execution_result"], "")
                self.assertIsNone(task["validation"])
                action("save_execution", execution_result="Fixed")
                action("transition", target_stage="validation")
                action("save_validation", status="passed", report="Checks passed")
            action("transition", target_stage={"planning": "execution", "execution": "validation", "validation": "done"}[stage])
        action("pause", 409)
        self.assertEqual(self.request("POST", path + "/messages", {"message": "Continue", "request_id": "done_send"}, cookie)[1]["error"]["code"], "task_done")
        for invalid in ({"stage": "done"}, {"action": []}, {"action": "update", "expected_revision": 0, "current_step": True, "expected_action": "x"}):
            self.assertEqual(self.request("PATCH", path + "/task", invalid, cookie)[0], 400)
        provider.assert_not_called()

    @unittest.skipUnless(DAY >= 14, "Invariants start on day 14")
    @patch("main.urlopen")
    def test_invariants_validate_actual_model_answer_and_atomic_failure(self, provider):
        cookie = self.new_owner()
        path = self.new_chat(cookie)
        rules = {"language": "Python", "architecture": "monolith", "max_budget": 1000}
        self.assertEqual(self.request("PATCH", path + "/invariants", rules, cookie)[0], 200)
        self.assertEqual(self.request("PATCH", path + "/invariants", {**rules, "max_budget": True}, cookie)[0], 400)
        body = {"message": "Recommend this solution", "request_id": "solution_1", "proposal": {"language": "Java", "architecture": "monolith", "budget": 100}}
        status, denied, _ = self.request("POST", path + "/messages", body, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(denied["chat"]["last_check"]["status"], "blocked")
        self.assertIn("Python", denied["chat"]["messages"][-1]["content"])
        provider.assert_not_called()
        self.assertEqual(self.request("POST", path + "/messages", {**body, "proposal": {**body["proposal"], "budget": 101}}, cookie)[0], 409)
        def response(solution):
            return ApiResponse(json.dumps({"choices": [{"message": {"content": json.dumps(solution)}}]}).encode())
        solution = {"kind": "plan", "language": "Python", "architecture": "monolith", "budget": 500, "answer": "Use a small Python application."}
        provider.side_effect = [response(solution), response({**solution, "language": "Java", "answer": "Rejected raw prose"}), response({"answer": "Missing typed fields"})]
        normal = {"message": "Suggest a project", "request_id": "solution_2"}
        accepted = self.request("POST", path + "/messages", normal, cookie)[1]["chat"]
        self.assertEqual(accepted["last_check"]["status"], "passed")
        self.assertEqual(json.loads(provider.call_args.args[0].data)["response_format"], {"type": "json_object"})
        blocked = self.request("POST", path + "/messages", {**normal, "request_id": "solution_3"}, cookie)[1]["chat"]
        self.assertEqual(blocked["last_check"]["status"], "blocked")
        self.assertNotIn("Rejected raw prose", blocked["messages"][-1]["content"])
        before = self.request(path=path, cookie=cookie)[1]["chat"]
        self.assertEqual(self.request("POST", path + "/messages", {**normal, "request_id": "solution_4"}, cookie)[0], 502)
        self.assertEqual(self.request(path=path, cookie=cookie)[1]["chat"], before)

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
            self.assertEqual(self.request("PATCH", path + "/memory", {"layer": "working", "entries": {"goal": "changed"}}, cookie)[0], 409)
            self.assertEqual(self.request("PATCH", "/api/memory", {"entries": {}}, cookie)[0], 409)
            if DAY >= 12:
                self.assertEqual(self.request("POST", "/api/profiles", {"name": "Busy", "style": "", "format": "", "constraints": ""}, cookie)[0], 409)
            if DAY >= 13:
                self.assertEqual(self.request("PATCH", path + "/task", {"action": "pause"}, cookie)[0], 409)
            if DAY >= 14:
                self.assertEqual(self.request("PATCH", path + "/invariants", {"language": "Python", "architecture": "", "max_budget": None}, cookie)[0], 409)
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

    def test_legacy_cookie_aliases_preserve_owner_isolation(self) -> None:
        legacy_id = "x" * 43
        path = self.new_chat("goost_owner=" + legacy_id)
        for name in ["chat_session", "pitch_session"]:
            status, result, headers = self.request(cookie=f"{name}={legacy_id}")
            self.assertEqual(status, 200)
            self.assertEqual("/api/chats/" + result["chats"][0]["id"], path)
            self.assertIn(f"goost_owner={legacy_id}", headers["Set-Cookie"])
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
