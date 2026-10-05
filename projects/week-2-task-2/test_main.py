import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from main import ChatAgent, ContextStore


class ApiResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ChatAgentTests(unittest.TestCase):
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
