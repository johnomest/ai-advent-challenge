import json
import unittest

from main import SYSTEM_PROMPT, TEMPERATURES, TRACKS, build_payload


class PayloadTests(unittest.TestCase):
    def test_temperature_changes_but_prompt_stays_the_same(self) -> None:
        payloads = [
            json.loads(build_payload("Artist", "Track", "фонк", temperature))
            for temperature in TEMPERATURES
        ]

        self.assertEqual([item["temperature"] for item in payloads], [0.0, 0.7, 1.2])
        self.assertTrue(all(item["messages"][0]["content"] == SYSTEM_PROMPT for item in payloads))
        self.assertTrue(all(item["messages"][1] == payloads[0]["messages"][1] for item in payloads))

    def test_demo_contains_three_tracks(self) -> None:
        self.assertEqual(len(TRACKS), 3)
        self.assertTrue(
            all(artists and title and description for artists, title, description in TRACKS)
        )


if __name__ == "__main__":
    unittest.main()
