import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class EnvironmentTest(unittest.TestCase):
    def test_reads_named_value_without_exposing_other_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OTHER_SECRET=hidden\nAIRTABLE_PAT='patExample'\n", encoding="utf-8")
            self.assertEqual(main.read_env_value(path, "AIRTABLE_PAT"), "patExample")

    def test_environment_takes_priority(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_PAT": "patFromEnvironment"}, clear=False):
            self.assertEqual(main.load_airtable_pat(), "patFromEnvironment")

    def test_rejects_non_pat_value(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_PAT": "invalid"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "does not look like"):
                main.load_airtable_pat()


if __name__ == "__main__":
    unittest.main()
