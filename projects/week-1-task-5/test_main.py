import json
import unittest
from datetime import datetime, timezone

from main import (
    ANALYTICAL_TASK,
    CONFIGURATIONS,
    SYSTEM_PROMPT,
    build_payload,
    calculate_cost,
    is_peak,
)


class ComparisonTests(unittest.TestCase):
    def test_prompt_is_identical_for_all_configurations(self) -> None:
        payloads = [json.loads(build_payload(item)) for item in CONFIGURATIONS]

        self.assertEqual(len(payloads), 6)
        self.assertTrue(
            all(payload["messages"][0]["content"] == SYSTEM_PROMPT for payload in payloads)
        )
        self.assertTrue(
            all(payload["messages"][1]["content"] == ANALYTICAL_TASK for payload in payloads)
        )

    def test_model_levels_are_ordered(self) -> None:
        self.assertEqual(
            [item["level"] for item in CONFIGURATIONS[:3]],
            ["Слабая", "Средняя", "Сильная"],
        )
        self.assertEqual(CONFIGURATIONS[0]["thinking"], "disabled")
        self.assertEqual(CONFIGURATIONS[1]["reasoning_effort"], "low")
        self.assertEqual(CONFIGURATIONS[2]["reasoning_effort"], "max")

    def test_opencode_models_are_distinct_and_use_same_controls(self) -> None:
        configurations = CONFIGURATIONS[3:]
        payloads = [json.loads(build_payload(item)) for item in configurations]

        self.assertEqual(len({item["model"] for item in configurations}), 3)
        self.assertTrue(all(item["provider"] == "OpenCode Zen" for item in configurations))
        self.assertEqual(
            [item["level"] for item in configurations],
            ["Zen слабая", "Zen средняя", "Zen сильная"],
        )
        self.assertTrue(all("thinking" not in payload for payload in payloads))
        self.assertEqual(len({payload["max_tokens"] for payload in payloads}), 1)

    def test_peak_windows_use_utc(self) -> None:
        self.assertTrue(is_peak(datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc)))
        self.assertFalse(is_peak(datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc)))
        self.assertTrue(is_peak(datetime(2026, 9, 5, 9, 59, tzinfo=timezone.utc)))
        self.assertFalse(is_peak(datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)))

    def test_cost_uses_cache_and_output_prices(self) -> None:
        usage = {
            "prompt_tokens": 1_000_000,
            "prompt_cache_hit_tokens": 250_000,
            "prompt_cache_miss_tokens": 750_000,
            "completion_tokens": 100_000,
        }

        self.assertAlmostEqual(
            calculate_cost("deepseek-v4-flash", usage, peak=False),
            0.23275,
        )
        self.assertAlmostEqual(
            calculate_cost("deepseek-v4-pro", usage, peak=True),
            1.397,
        )


if __name__ == "__main__":
    unittest.main()
