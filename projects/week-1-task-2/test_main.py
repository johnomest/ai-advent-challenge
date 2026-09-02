import json
import unittest

from main import validate_controlled_response


class ValidationTests(unittest.TestCase):
    def test_expected_schema(self) -> None:
        response = json.dumps(
            {
                "track": "Astin Ray, VAVA - TAKIPARIO",
                "pitch": "Aggressive phonk with female vocals.",
                "content_uses": ["Edits", "Night clips", "Playlists"],
            }
        )
        self.assertEqual(validate_controlled_response(response), (True, "schema matched"))

    def test_rejects_extra_key(self) -> None:
        response = json.dumps(
            {
                "track": "Track",
                "pitch": "Pitch",
                "content_uses": ["One", "Two", "Three"],
                "genre": "Phonk",
            }
        )
        self.assertEqual(validate_controlled_response(response), (False, "wrong keys"))


if __name__ == "__main__":
    unittest.main()
