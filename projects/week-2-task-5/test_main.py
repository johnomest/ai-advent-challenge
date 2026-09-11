import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from main import (AgentConfig, ChatAgent, ContextLimitError, ContextStore, ProviderUsage,
                  build_context, decode_metrics, estimate_context, estimate_cost, estimate_text_tokens)


class ApiResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ChatAgentTests(unittest.TestCase):
    def test_context_strategies_keep_pairs_and_do_not_mutate_transcript(self):
        messages = [{"role": role, "content": f"{role}-{turn}"} for turn in range(5)
                    for role in ("user", "assistant")]
        before = json.dumps(messages)
        selected = build_context("system", messages, "sliding_window", 2)
        self.assertEqual(selected[1:], messages[-4:])
        sticky = build_context("system", messages, "sticky_facts", 1, {"name": "Alice"})
        self.assertEqual(sticky[1]["role"], "user")
        self.assertIn("Alice", sticky[1]["content"])
        self.assertEqual(sticky[2:], messages[-2:])
        self.assertEqual(build_context("system", messages, "branching")[1:], messages)
        self.assertEqual(json.dumps(messages), before)
        for window in (0, 21, True):
            with self.assertRaises(ValueError):
                build_context("system", messages, window_turns=window)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_sticky_extraction_boundary_usage_and_atomic_failure(self, provider, _key):
        def response(content):
            return ApiResponse(json.dumps({"choices": [{"message": {"content": content}}],
                                           "usage": {"total_tokens": 7}}).encode())
        provider.side_effect = [response('{"name":"Alice"}'), response("Hello Alice"),
                                response('{"name":"Bob"}'), response(" ")]
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(Path(directory) / "context.sqlite3")
            agent = ChatAgent(store=store, strategy="sticky_facts", window_turns=1)
            agent.ask("My name is Alice")
            self.assertEqual(agent.total_tokens, 14)
            self.assertEqual(agent.turn_metrics[0]["facts_usage"]["total_tokens"], 7)
            before = store.get_chat("default", "default")
            with self.assertRaises(RuntimeError):
                agent.ask("My name is Bob")
            self.assertEqual(agent.facts, {"name": "Alice"})
            self.assertEqual(store.get_chat("default", "default"), before)
            extraction = json.loads(provider.call_args_list[2].args[0].data)
            self.assertEqual(len(extraction["messages"]), 2)
            self.assertEqual(json.loads(extraction["messages"][1]["content"]),
                             {"old_facts": {"name": "Alice"}, "current_user": "My name is Bob"})
            self.assertNotIn("Hello Alice", json.dumps(extraction))

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_invalid_facts_and_post_extraction_overflow(self, provider, _key):
        for raw in ('[]', '{"x": 1}', '{"x":"a","x":"b"}', json.dumps({"x": "a" * 241})):
            agent = ChatAgent(strategy="sticky_facts")
            provider.return_value = ApiResponse(json.dumps({"choices": [{"message": {"content": raw}}]}).encode())
            with self.assertRaisesRegex(RuntimeError, "invalid facts"):
                agent.ask("Hello")
            self.assertEqual(agent.facts, {})
            self.assertEqual(len(agent.messages), 1)
        provider.reset_mock()
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"{}"}}]}')
        agent = ChatAgent(strategy="sticky_facts", config=AgentConfig(context_limit=251, max_tokens=250))
        with self.assertRaises(ContextLimitError):
            agent.ask("Hello")
        provider.assert_called_once()
        self.assertEqual(agent.facts, {})

    def test_config_and_estimator_boundaries(self) -> None:
        for values in ({"context_limit": True}, {"context_limit": 0}, {"max_tokens": False},
                       {"max_tokens": 1.5}, {"context_limit": 250}, {"max_tokens": 16384}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                AgentConfig(**values)
        self.assertEqual(estimate_text_tokens(""), 0)
        self.assertEqual(estimate_text_tokens("abcd"), 1)
        self.assertEqual(estimate_text_tokens("🙂"), 1)
        self.assertEqual(estimate_text_tokens("Привет"), 3)
        messages = [{"role": "system", "content": "abcd"}]
        required = estimate_context(messages, "hello")["required_tokens"]
        for offset, overflow in ((-1, True), (0, False), (1, False)):
            with self.subTest(offset=offset):
                estimate = estimate_context(messages, "hello", AgentConfig(context_limit=required + offset))
                self.assertEqual(estimate["overflow"], overflow)
                self.assertEqual(estimate["remaining_tokens"], offset)
        self.assertEqual(messages, [{"role": "system", "content": "abcd"}])

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_overflow_prevents_network_and_all_state_changes(self, provider, _key) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(Path(directory) / "context.sqlite3")
            agent = ChatAgent(store=store, config=AgentConfig(context_limit=2048, max_tokens=250))
            before = (list(agent.messages), agent.total_tokens, list(agent.turn_metrics))
            with self.assertRaises(ContextLimitError) as raised:
                agent.ask("界" * 4000)
            self.assertTrue(raised.exception.estimate["overflow"])
            self.assertEqual((agent.messages, agent.total_tokens, agent.turn_metrics), before)
            self.assertIsNone(store.get_chat("default", "default"))
            provider.assert_not_called()

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_exact_limit_calls_provider(self, provider, _key) -> None:
        agent = ChatAgent()
        required = estimate_context(agent.messages, "Hello")["required_tokens"]
        agent.config = AgentConfig(context_limit=required)
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"OK"}}]}')
        self.assertEqual(agent.ask("Hello"), "OK")
        provider.assert_called_once()

    def test_provider_usage_contract_and_decimal_cost(self) -> None:
        self.assertIsNone(ProviderUsage.parse({}).total_tokens)
        self.assertIsNone(ProviderUsage.parse({"total_tokens": 17}).prompt_tokens)
        full = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60}
        usage = ProviderUsage.parse(full)
        cost = estimate_cost(usage, "deepseek-v4-flash")
        self.assertEqual(cost["min_usd"], "0.00002668")
        self.assertEqual(cost["max_usd"], "0.00005336")
        self.assertEqual(cost["pricing_date"], "2026-09-09")
        self.assertIsNone(estimate_cost(usage, "other-model"))
        self.assertIsNone(estimate_cost(ProviderUsage.parse({"total_tokens": 120}), "deepseek-v4-flash"))
        bad = [None, [], {**full, "total_tokens": 121}, {**full, "prompt_cache_hit_tokens": 41},
               {"prompt_tokens": 20, "total_tokens": 10}, {"prompt_cache_hit_tokens": 20, "prompt_tokens": 10}]
        for field in full:
            bad.extend({**full, field: value} for value in (True, -1, "1", 1.5, None))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ProviderUsage.parse(value)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_metrics_reload_growth_and_reset(self, provider, _key) -> None:
        full = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60}
        provider.side_effect = [ApiResponse(json.dumps({"choices": [{"message": {"content": "Answer"}}],
                                                       "usage": full}).encode()) for _ in range(2)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.sqlite3"
            first = ChatAgent(store=ContextStore(path))
            first.ask("Hello")
            restored = ChatAgent(store=ContextStore(path))
            self.assertEqual(restored.turn_metrics, first.turn_metrics)
            restored.ask("Hello again")
            self.assertGreater(restored.turn_metrics[1]["history_tokens"], restored.turn_metrics[0]["history_tokens"])
            self.assertGreater(restored.turn_metrics[1]["prompt_tokens"], restored.turn_metrics[0]["prompt_tokens"])
            self.assertEqual(restored.total_tokens, 240)
            self.assertEqual([item["turn_index"] for item in restored.turn_metrics], [1, 2])
            restored.reset()
            self.assertEqual(restored.turn_metrics, [])
            self.assertEqual(restored.total_tokens, 0)
            self.assertIsNone(restored.store.load_agent("default"))

    def test_schema_v1_migrates_without_fabricating_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.sqlite3"
            with closing(sqlite3.connect(path)) as database, database:
                database.execute("CREATE TABLE chats (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL, messages TEXT NOT NULL, total_tokens INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
                database.execute("INSERT INTO chats VALUES ('old', 'owner', 'Title', ?, 99, 1, 2)",
                                 ('[{"role":"user","content":"Hello"},{"role":"assistant","content":"World"}]',))
                database.execute("PRAGMA user_version=1")
            store = ContextStore(path)
            chat = store.get_chat("owner", "old")
            self.assertEqual(chat["total_tokens"], 99)
            self.assertEqual(chat["turn_metrics"], [])
            self.assertEqual(len(chat["messages"]), 2)
            self.assertEqual(ContextStore(path).get_chat("owner", "old"), chat)
            with closing(sqlite3.connect(path)) as database:
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 3)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_invalid_stored_metrics_rejected(self, provider, _key) -> None:
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')
        agent = ChatAgent()
        agent.ask("Hello")
        valid = agent.turn_metrics[0]
        invalid = [None, {}, [1], [{**valid, "answer_tokens": True}],
                   [{**valid, "turn_index": 2}], [valid, valid], [{**valid, "extra": 1}],
                   [{**valid, "provider_usage": {"total_tokens": 1}}],
                   [{**valid, "cost": {"min_usd": "NaN", "max_usd": "1", "currency": "USD",
                                      "pricing_date": "2026-09-09", "source": "https://api-docs.deepseek.com/quick_start/pricing/"}}]]
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(Path(directory) / "context.sqlite3")
            chat = store.create_chat("owner")
            for value in invalid:
                with self.subTest(value=value):
                    with self.assertRaisesRegex(RuntimeError, "Stored turn metrics"):
                        decode_metrics(json.dumps(value), 1)
                    with store.database() as database:
                        database.execute("UPDATE chats SET turn_metrics = ? WHERE id = ?", (json.dumps(value), chat["id"]))
                    with self.assertRaises(RuntimeError):
                        store.get_chat("owner", chat["id"])

    def test_invalid_legacy_migration_rolls_back_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.sqlite3"
            with closing(sqlite3.connect(path)) as database, database:
                database.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, messages TEXT NOT NULL, total_tokens INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
                database.execute("INSERT INTO conversations VALUES ('old', 'invalid json', 0, 1)")
            with self.assertRaisesRegex(RuntimeError, "Stored conversation is invalid"):
                ContextStore(path)
            with closing(sqlite3.connect(path)) as database:
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 0)
                self.assertEqual(database.execute("SELECT messages FROM conversations").fetchone()[0], "invalid json")
                self.assertIsNone(database.execute("SELECT name FROM sqlite_master WHERE name = 'chats'").fetchone())

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_storage_failure_does_not_commit_agent_memory(self, provider, _mock_key) -> None:
        provider.return_value = ApiResponse(b'{"choices":[{"message":{"content":"Answer"}}]}')
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(Path(directory) / "context.sqlite3")
            agent = ChatAgent(store=store)
            with patch.object(store, "save_agent", side_effect=sqlite3.OperationalError("disk full")):
                with self.assertRaises(sqlite3.OperationalError):
                    agent.ask("Hello")
            self.assertEqual(len(agent.messages), 1)
            self.assertIsNone(store.load_agent("default"))

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_malformed_response_does_not_commit_history(self, mock_urlopen, _mock_key) -> None:
        agent = ChatAgent()
        bad_results = [
            {},
            {"choices": []},
            {"choices": [{"message": {"content": " "}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": "Valid"}}], "usage": None},
            *[
                {"choices": [{"message": {"content": "Valid"}}], "usage": {"total_tokens": value}}
                for value in [-1, True, "12", 1.5, None]
            ],
        ]
        for result in bad_results:
            with self.subTest(result=result):
                mock_urlopen.return_value = ApiResponse(json.dumps(result).encode())
                with self.assertRaises(RuntimeError):
                    agent.ask("Hello")
                self.assertEqual(len(agent.messages), 1)
                self.assertEqual(agent.total_tokens, 0)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_usage_is_optional(self, mock_urlopen, _mock_key) -> None:
        mock_urlopen.return_value = ApiResponse(b'{"choices":[{"message":{"content":" Answer "}}]}')
        agent = ChatAgent()
        self.assertEqual(agent.ask("Hello"), "Answer")
        self.assertEqual(agent.total_tokens, 0)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_invalid_provider_json_is_explicit(self, provider, _mock_key) -> None:
        provider.return_value = ApiResponse(b'not json')
        agent = ChatAgent()
        with self.assertRaisesRegex(RuntimeError, "invalid response"):
            agent.ask("Hello")
        self.assertEqual(len(agent.messages), 1)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_agent_keeps_history_and_usage(self, mock_urlopen, _mock_key) -> None:
        responses = [
            {
                "choices": [{"message": {"content": "First pitch."}}],
                "usage": {"total_tokens": 20},
            },
            {
                "choices": [{"message": {"content": "Shorter pitch."}}],
                "usage": {"total_tokens": 12},
            },
        ]
        mock_urlopen.side_effect = [
            ApiResponse(json.dumps(response).encode()) for response in responses
        ]
        agent = ChatAgent()

        self.assertEqual(agent.ask("Create a pitch."), "First pitch.")
        self.assertEqual(agent.ask("Make it shorter."), "Shorter pitch.")

        second_payload = json.loads(mock_urlopen.call_args_list[1].args[0].data)
        self.assertEqual(len(second_payload["messages"]), 4)
        self.assertEqual(second_payload["messages"][2]["content"], "First pitch.")
        self.assertEqual(agent.total_tokens, 32)
        self.assertEqual(len(agent.messages), 5)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_context_survives_restart(self, mock_urlopen, _mock_key) -> None:
        mock_urlopen.side_effect = [
            ApiResponse(b'{"choices":[{"message":{"content":"First"}}],"usage":{"total_tokens":7}}'),
            ApiResponse(b'{"choices":[{"message":{"content":"Second"}}],"usage":{"total_tokens":5}}'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.sqlite3"
            ChatAgent(store=ContextStore(path), conversation_id="demo").ask("Remember this")
            restored = ChatAgent(store=ContextStore(path), conversation_id="demo")
            self.assertEqual(restored.messages[-1]["content"], "First")
            self.assertEqual(restored.total_tokens, 7)
            restored.ask("What do you remember?")

        payload = json.loads(mock_urlopen.call_args_list[1].args[0].data)
        self.assertEqual([message["content"] for message in payload["messages"][-3:]], ["Remember this", "First", "What do you remember?"])
        self.assertEqual(restored.total_tokens, 12)


if __name__ == "__main__":
    unittest.main()
