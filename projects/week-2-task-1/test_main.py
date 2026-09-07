import json
import unittest
from io import BytesIO
from unittest.mock import patch

from main import PitchAgent


class ApiResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PitchAgentTests(unittest.TestCase):
    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_malformed_response_does_not_commit_history(self, mock_urlopen, _mock_key) -> None:
        agent = PitchAgent()
        bad_results = [
            {},
            {"choices": []},
            {"choices": [{"message": {"content": " "}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": "Valid"}}], "usage": None},
            *[
                {"choices": [{"message": {"content": "Valid"}}], "usage": {"total_tokens": value}}
                for value in [-1, True, "12", 1.5, None]
            ],
        ]
        for result in bad_results:
            with self.subTest(result=result):
                mock_urlopen.return_value = ApiResponse(json.dumps(result).encode())
                with self.assertRaises(RuntimeError):
                    agent.ask("Hello")
                self.assertEqual(len(agent.messages), 1)
                self.assertEqual(agent.total_tokens, 0)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_usage_is_optional(self, mock_urlopen, _mock_key) -> None:
        mock_urlopen.return_value = ApiResponse(b'{"choices":[{"message":{"content":" Answer "}}]}')
        agent = PitchAgent()
        self.assertEqual(agent.ask("Hello"), "Answer")
        self.assertEqual(agent.total_tokens, 0)

    @patch("main.load_api_key", return_value="test-key")
    @patch("main.urlopen")
    def test_agent_keeps_history_and_usage(self, mock_urlopen, _mock_key) -> None:
        responses = [
            {
                "choices": [{"message": {"content": "First pitch."}}],
                "usage": {"total_tokens": 20},
            },
            {
                "choices": [{"message": {"content": "Shorter pitch."}}],
                "usage": {"total_tokens": 12},
            },
        ]
        mock_urlopen.side_effect = [
            ApiResponse(json.dumps(response).encode()) for response in responses
        ]
        agent = PitchAgent()

        self.assertEqual(agent.ask("Create a pitch."), "First pitch.")
        self.assertEqual(agent.ask("Make it shorter."), "Shorter pitch.")

        second_payload = json.loads(mock_urlopen.call_args_list[1].args[0].data)
        self.assertEqual(len(second_payload["messages"]), 4)
        self.assertEqual(second_payload["messages"][2]["content"], "First pitch.")
        self.assertEqual(agent.total_tokens, 32)
        self.assertEqual(len(agent.messages), 5)


if __name__ == "__main__":
    unittest.main()
