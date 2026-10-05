import unittest

from main import check, local_url


class LocalTests(unittest.TestCase):
    def test_loopback_only(self):
        self.assertEqual(local_url("http://127.0.0.1:11434/"), "http://127.0.0.1:11434")
        for url in ("https://api.deepseek.com", "http://example.com", "http://localhost@evil.com", "http://localhost:11434/path"):
            with self.assertRaises(ValueError):
                local_url(url)

    def test_three_expected_answers(self):
        self.assertTrue(check("simple", "Париж."))
        self.assertTrue(check("structured", '{"artist":"Astin Ray","release_date":"2026-10-12","budget_rub":108000}'))
        self.assertTrue(check("analytical", '{"projects":["B","A"],"hours":8,"profit":210,"explanation":"Максимум"}'))

    def test_wrong_dates_numbers_and_duplicates_fail(self):
        self.assertFalse(check("structured", '{"artist":"Astin Ray","release_date":"2026-12-10","budget_rub":10800}'))
        self.assertFalse(check("analytical", '{"projects":["A","B","A"],"hours":8,"profit":210,"explanation":"ошибка"}'))
        self.assertFalse(check("analytical", "not JSON"))


if __name__ == "__main__":
    unittest.main()
