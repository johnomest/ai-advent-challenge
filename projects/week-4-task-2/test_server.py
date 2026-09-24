import unittest

from server import normalize_recordings, search_recordings


class MusicBrainzToolTests(unittest.TestCase):
    def test_normalize_recordings_keeps_only_useful_fields(self) -> None:
        payload = {
            "recordings": [
                {
                    "id": "recording-1",
                    "title": "Aerodynamic",
                    "artist-credit": [{"name": "Daft Punk", "joinphrase": ""}],
                    "first-release-date": "2001-03-07",
                    "releases": [
                        {"title": "Discovery"},
                        {"title": "Discovery"},
                        {"title": "Aerodynamic"},
                    ],
                    "score": 100,
                    "ignored": "value",
                }
            ]
        }

        self.assertEqual(
            normalize_recordings(payload),
            [
                {
                    "id": "recording-1",
                    "title": "Aerodynamic",
                    "artist": "Daft Punk",
                    "first_release_date": "2001-03-07",
                    "releases": ["Discovery", "Aerodynamic"],
                    "score": 100,
                }
            ],
        )

    def test_limit_is_validated_before_network_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 10"):
            search_recordings("Daft Punk", limit=11)


if __name__ == "__main__":
    unittest.main()
