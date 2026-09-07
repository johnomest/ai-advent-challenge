import json
import threading
import time
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from test_main import ApiResponse
from web import BODY_LIMIT, SESSION_TTL, PitchServer, public_origin


class WebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_patch = patch("main.load_api_key", return_value="test-key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.server = PitchServer(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method="GET", path="/api/session", payload=None, cookie=None, headers=None):
        request_headers = {"Origin": self.origin}
        if cookie:
            request_headers["Cookie"] = cookie
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            result = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def new_session(self):
        status, data, headers = self.request()
        self.assertEqual(status, 200)
        self.assertIsNone(data["track"])
        self.assertEqual(data["messages"], [])
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";", 1)[0]

    @patch("main.urlopen")
    def test_lifecycle_and_cookie_isolation(self, provider) -> None:
        provider.side_effect = [
            ApiResponse(json.dumps({"choices": [{"message": {"content": answer}}], "usage": {"total_tokens": 10}}).encode())
            for answer in ["First pitch.", "Revised pitch."]
        ]
        cookie = self.new_session()
        status, data, _ = self.request("POST", "/api/messages", {"name": "Artist - Track", "description": "Phonk"}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["track"]["name"], "Artist - Track")
        self.assertEqual(len(data["messages"]), 2)
        self.assertNotIn("system", [message["role"] for message in data["messages"]])
        status, data, _ = self.request("POST", "/api/messages", {"message": "Shorter"}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["total_tokens"], 20)
        self.assertEqual(len(data["messages"]), 4)
        self.assertEqual(self.request(cookie=cookie)[1], data)
        self.new_session()
        status, cleared, _ = self.request("DELETE", "/api/session", {}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(cleared["messages"], [])
        self.assertIsNone(cleared["track"])
        self.assertEqual(cleared["total_tokens"], 0)
        self.assertEqual(self.request(cookie=cookie)[1], cleared)

    @patch("main.urlopen", side_effect=RuntimeError("SECRET provider details"))
    def test_provider_failure_is_safe_and_atomic(self, provider) -> None:
        cookie = self.new_session()
        before = self.request(cookie=cookie)[1]
        status, data, _ = self.request("POST", "/api/messages", {"name": "A", "description": "B"}, cookie)
        self.assertEqual(status, 502)
        self.assertEqual(data["error"]["code"], "provider_error")
        self.assertNotIn("SECRET", json.dumps(data))
        self.assertEqual(self.request(cookie=cookie)[1], before)

    def test_busy_expiry_and_capacity(self) -> None:
        cookie = self.new_session()
        token = cookie.split("=", 1)[1]
        session = self.server.sessions[token]
        with session.lock:
            for method, path, payload in [("GET", "/api/session", None), ("DELETE", "/api/session", {}), ("POST", "/api/messages", {"name": "A", "description": "B"})]:
                self.assertEqual(self.request(method, path, payload, cookie)[0], 409)
        with patch("web.SESSION_LIMIT", 1):
            self.assertEqual(self.request()[0], 503)
        session.touched = time.monotonic() - SESSION_TTL - 1
        status, data, headers = self.request(cookie=cookie)
        self.assertEqual(status, 200)
        self.assertNotIn(token, self.server.sessions)
        self.assertNotEqual(headers["Set-Cookie"].split(";", 1)[0], cookie)

    @patch("main.urlopen")
    def test_input_origin_and_static_security(self, provider) -> None:
        cookie = self.new_session()
        invalid = [None, [], {"name": "A"}, {"name": "A", "description": " "}, {"name": 3, "description": "B"}, {"name": "A" * 301, "description": "B"}, {"name": "A", "description": "B" * 8001}, {"name": "A", "description": "B", "model": "other"}]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:50]):
                self.assertIn(self.request("POST", "/api/messages", payload, cookie)[0], [400, 415])
        self.assertEqual(self.request("POST", "/api/messages", {}, cookie, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/messages", {}, cookie, {"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.request("POST", "/api/messages", {"name": "X" * BODY_LIMIT}, cookie)[0], 413)
        self.assertEqual(self.request("POST", "/api/messages", {}, cookie, {"Content-Type": "text/plain"})[0], 415)
        for path in ["/.env", "/main.py", "/../.env", "/static/app.js", "/%2e%2e/.env"]:
            self.assertEqual(self.request(path=path)[0], 404)
        status, _, headers = self.request()
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        provider.assert_not_called()

    def test_exact_public_origin_and_secure_cookie(self) -> None:
        origin = "https://demo.trycloudflare.com"
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = PitchServer(0, origin)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        headers = {"Host": "demo.trycloudflare.com", "Origin": origin}
        status, _, response_headers = self.request(headers=headers)
        self.assertEqual(status, 200)
        self.assertIn("Secure", response_headers["Set-Cookie"])
        self.assertEqual(self.request(headers={"Host": "other.trycloudflare.com"})[0], 403)
        self.assertEqual(self.request("POST", "/api/messages", {}, headers={**headers, "Origin": "https://evil.example"})[0], 403)

    def test_public_origin_validation(self) -> None:
        self.assertEqual(public_origin("https://demo.example/"), "https://demo.example")
        for value in ["http://demo.example", "https://demo.example/path", "https://user@demo.example"]:
            with self.subTest(value=value), self.assertRaises(Exception):
                public_origin(value)


if __name__ == "__main__":
    unittest.main()
