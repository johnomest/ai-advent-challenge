import tempfile
import unittest
from pathlib import Path

import server


class PipelineToolTests(unittest.TestCase):
    def test_summarize_uses_search_payload(self) -> None:
        result = server.summarize_recordings(
            artist="Daft Punk",
            requested_title="Aerodynamic",
            total_matches=10,
            recordings=[
                {
                    "id": "recording-1",
                    "title": "Aerodynamic",
                    "first_release_date": "2001",
                    "score": 100,
                }
            ],
        )
        self.assertEqual(result["row_count"], 1)
        self.assertIn("| Aerodynamic | 2001 | 100 | recording-1 |", result["markdown"])

    def test_save_report_stays_inside_report_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original = server.REPORT_DIR
            server.REPORT_DIR = Path(temp_dir)
            try:
                result = server.save_report("../Daft Punk Aerodynamic", "# Report\n")
                saved_files = list(Path(temp_dir).glob("*.md"))
            finally:
                server.REPORT_DIR = original
        self.assertEqual(len(saved_files), 1)
        self.assertNotIn("..", result["path"])

    def test_empty_filename_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "letter or number"):
            server.normalize_filename("---")


if __name__ == "__main__":
    unittest.main()
