import copy
import unittest

from index_pdf import validate_index


class PdfIndexTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "dimensions": 2,
            "chunks": [{"chunk_id": "structure-00001", "text": "Example", "page": 2, "embedding": [0.1, 0.2]}],
        }

    def test_valid_index(self):
        validate_index(self.index)

    def test_invalid_vectors_and_page_are_rejected(self):
        for value in [[0, 0], [float("nan"), 1], [1]]:
            with self.subTest(vector=value):
                index = copy.deepcopy(self.index)
                index["chunks"][0]["embedding"] = value
                with self.assertRaises(AssertionError):
                    validate_index(index)
        self.index["chunks"][0]["page"] = 0
        with self.assertRaises(AssertionError):
            validate_index(self.index)

    def test_duplicate_ids_are_rejected(self):
        self.index["chunks"].append(copy.deepcopy(self.index["chunks"][0]))
        with self.assertRaises(AssertionError):
            validate_index(self.index)


if __name__ == "__main__":
    unittest.main()
