import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate.py")
SPEC = importlib.util.spec_from_file_location("week5_task4_evaluate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GroundingEvaluationTests(unittest.TestCase):
    def test_all_synthetic_cases_match_expected_policy(self):
        self.assertEqual((10, 10), MODULE.evaluate())

    def test_non_exact_quote_is_rejected(self):
        case = {"chunk": "Точный текст.", "quote": "Другой текст."}
        self.assertEqual("refuse", MODULE.validate_case(case))


if __name__ == "__main__":
    unittest.main()
