import tempfile
import unittest
from pathlib import Path

import server


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = Path(self.temp_dir.name) / "scheduler.db"
        server.init_database()

    def tearDown(self) -> None:
        server.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_schedule_is_persisted(self) -> None:
        result = server.schedule_artist_digest("Daft Punk", interval_seconds=60)
        with server.database() as connection:
            row = connection.execute("SELECT artist, interval_seconds, active FROM schedules").fetchone()
        self.assertEqual((row["artist"], row["interval_seconds"], row["active"]), ("Daft Punk", 60, 1))
        self.assertEqual(result["status"], "scheduled")

    def test_digest_format(self) -> None:
        summary = server.build_digest(
            "Daft Punk",
            [{"title": "Aerodynamic", "first_release_date": "2001", "score": 100}],
        )
        self.assertIn("Aerodynamic (2001)", summary)

    def test_interval_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 5 and 86400"):
            server.schedule_artist_digest("Daft Punk", interval_seconds=1)


if __name__ == "__main__":
    unittest.main()
