import unittest

from main import evaluate_response


class EvaluationTests(unittest.TestCase):
    def test_accepts_correct_answer(self) -> None:
        checks = evaluate_response(
            "Campaign A: conversion 3%, AOV $300, ROAS 6.0x, profit $36,000. "
            "Campaign B: conversion 4%, AOV $280, ROAS 4.48x, profit $24,800. "
            "Recommend Campaign A because it has better profit and ROAS."
        )
        self.assertTrue(all(checks.values()))

    def test_rejects_wrong_answer(self) -> None:
        checks = evaluate_response("Campaign B wins with a 5% conversion rate.")
        self.assertFalse(any(checks.values()))


if __name__ == "__main__":
    unittest.main()
