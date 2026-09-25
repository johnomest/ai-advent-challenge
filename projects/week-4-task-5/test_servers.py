import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


PROJECT_DIR = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


musicbrainz = load_module("day20_musicbrainz", "musicbrainz_server.py")
itunes = load_module("day20_itunes", "itunes_server.py")
main = load_module("day20_main", "main.py")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json

        return json.dumps(self.payload).encode("utf-8")


class ServerTests(unittest.TestCase):
    @patch.object(musicbrainz, "urlopen")
    def test_musicbrainz_normalizes_results(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {
                "count": 1,
                "recordings": [
                    {
                        "id": "mbid",
                        "title": "Aerodynamic",
                        "first-release-date": "2001",
                        "score": 100,
                        "releases": [{"title": "Discovery"}],
                    }
                ],
            }
        )
        result = musicbrainz.search_recordings("Daft Punk", "Aerodynamic", 1)
        self.assertEqual(result["recordings"][0]["releases"], ["Discovery"])

    @patch.object(musicbrainz.time, "sleep")
    @patch.object(musicbrainz, "urlopen")
    def test_musicbrainz_retries_temporary_failure(self, mocked_urlopen, mocked_sleep):
        mocked_urlopen.side_effect = [
            HTTPError("https://musicbrainz.org", 503, "Busy", {}, None),
            FakeResponse({"count": 0, "recordings": []}),
        ]
        result = musicbrainz.search_recordings("Daft Punk", "Aerodynamic", 1)
        self.assertEqual(result["recordings"], [])
        mocked_sleep.assert_called_once_with(1.2)

    @patch.object(itunes, "urlopen")
    def test_itunes_normalizes_results(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {
                "resultCount": 1,
                "results": [
                    {
                        "trackId": 1,
                        "artistName": "Daft Punk",
                        "trackName": "Aerodynamic",
                        "collectionName": "Discovery",
                        "primaryGenreName": "Electronic",
                    }
                ],
            }
        )
        result = itunes.search_tracks("Daft Punk", "Aerodynamic", "US", 1)
        self.assertEqual(result["tracks"][0]["album"], "Discovery")

    def test_root_env_points_to_repository(self):
        self.assertEqual(main.ROOT_ENV.name, ".env")
        self.assertEqual(main.ROOT_ENV.parent.name, "ai-advent-challenge")

    def test_airtable_allowlist_is_read_only(self):
        self.assertEqual(
            main.AIRTABLE_TOOLS,
            {"search_bases", "list_tables_for_base"},
        )

    def test_airtable_table_schema_is_compacted(self):
        import json

        content = json.dumps(
            {
                "tables": [
                    {
                        "id": "tbl123",
                        "name": "releases",
                        "fields": [{"id": "fld123", "name": "title"}],
                    }
                ]
            }
        )
        result = json.loads(main.compact_tool_result("airtable_list_tables_for_base", content))
        self.assertEqual(result, {"table_count": 1, "tables": [{"id": "tbl123", "name": "releases"}]})


if __name__ == "__main__":
    unittest.main()
