import unittest

from main import evaluate_response


class EvaluationTests(unittest.TestCase):
    def test_accepts_correct_answer(self) -> None:
        checks = evaluate_response(
            "Кампания A: конверсия 3%, средний чек $300, ROAS 6.0x, "
            "прибыль $36 000. Кампания B: конверсия 4%, средний чек $280, "
            "ROAS 4,48x, прибыль $24 800. Рекомендуем кампанию A, потому что "
            "у неё выше прибыль и ROAS."
        )
        self.assertTrue(all(checks.values()))

    def test_rejects_wrong_answer(self) -> None:
        checks = evaluate_response("Кампания B выигрывает с конверсией 5%.")
        self.assertFalse(any(checks.values()))


if __name__ == "__main__":
    unittest.main()
