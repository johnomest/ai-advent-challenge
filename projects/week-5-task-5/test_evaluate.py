import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate.py")
SPEC = importlib.util.spec_from_file_location("week5_task5_evaluate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LongDialogScenarioTests(unittest.TestCase):
    def test_two_complete_twelve_turn_scenarios(self):
        self.assertEqual((2, 2), MODULE.evaluate())

    def test_missing_goal_is_rejected(self):
        scenario = {
            "turns": ["q"] * 12,
            "constraints": ["c"],
            "terms": ["t"],
            "expected_checks": list(MODULE.REQUIRED_CHECKS),
        }
        self.assertIn("goal is required", MODULE.validate_scenario(scenario))


if __name__ == "__main__":
    unittest.main()
