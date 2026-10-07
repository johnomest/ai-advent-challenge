from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from export_telegram import save_export, serialize_message


class ExportTests(unittest.TestCase):
    def test_message_metadata(self):
        message = SimpleNamespace(
            id=42, action=None, date=datetime(2026, 10, 6, tzinfo=timezone.utc),
            edit_date=None, sender_id=123, reply_to_msg_id=40,
            message="Hello", media=None, grouped_id=None,
        )
        result = serialize_message(message)
        self.assertEqual(result["text"], "Hello")
        self.assertEqual(result["reply_to_message_id"], 40)
        self.assertEqual(result["from_id"], "123")

    def test_replacement_and_failure_preserve_export(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chat" / "result.json"
            save_export(path, {"messages": [1]})
            save_export(path, {"messages": [2]})
            self.assertEqual(json.loads(path.read_text())["messages"], [2])
            with self.assertRaises(TypeError):
                save_export(path, {"invalid": object()})
            self.assertEqual(json.loads(path.read_text())["messages"], [2])
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
