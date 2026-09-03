import unittest

from main import evaluate_response


class EvaluationTests(unittest.TestCase):
    def test_accepts_correct_answer(self) -> None:
        self.assertEqual(
            evaluate_response("Path: A → C → B → D → E → F. Total cost: 13."),
            (True, True, True),
        )

    def test_rejects_wrong_answer(self) -> None:
        self.assertEqual(
            evaluate_response("Path: A-B-D-F. Total cost: 15."),
            (False, False, False),
        )


if __name__ == "__main__":
    unittest.main()
