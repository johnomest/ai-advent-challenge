import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import fresh, load, memory_command, recent, save, turn


class ChatTests(unittest.TestCase):
    def test_memory_survives_restart_and_updates(self):
        session = fresh()
        memory_command(session, "/goal Работа за рубежом")
        memory_command(session, "/studio IV")
        memory_command(session, "/note Нет диплома")
        memory_command(session, "/note Нет диплома")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.json"
            save(path, session)
            resumed = load(path)
        self.assertEqual(resumed, session)
        self.assertEqual(resumed["task"]["clarified"], ["Нет диплома"])
        memory_command(resumed, "/studio Framestore")
        self.assertEqual(resumed["task"]["studio"], "Framestore")
        self.assertEqual(resumed["task"]["goal"], "Работа за рубежом")

    def test_failed_api_does_not_modify_history(self):
        session = fresh()
        with patch("main.answer", side_effect=RuntimeError("network")):
            with self.assertRaises(RuntimeError):
                turn(session, "question", {}, "key", None, Path("unused.json"))
        self.assertEqual(session, fresh())

    def test_commands_are_saved_without_api(self):
        with tempfile.TemporaryDirectory() as directory, patch("main.answer") as answer:
            path = Path(directory) / "chat.json"
            session = fresh()
            turn(session, "/goal Подать заявку", {}, "key", None, path)
            self.assertEqual(load(path)["history"][0]["response"]["status"], "memory")
            answer.assert_not_called()

    def test_recent_history_is_bounded_without_deleting_archive(self):
        session = fresh()
        session["history"] = [{"user": str(i), "response": {"answer": "x" * 2000}} for i in range(15)]
        self.assertEqual(len(recent(session)), 6)
        self.assertEqual(len(recent(session)[0]["assistant"]), 1500)
        self.assertEqual(len(session["history"]), 15)

    def test_invalid_memory_rejected(self):
        with self.assertRaises(ValueError):
            memory_command(fresh(), "/goal ")


if __name__ == "__main__":
    unittest.main()
