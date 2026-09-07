"""Local, cookie-isolated web interface for PitchAgent."""

import argparse
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from main import PitchAgent


STATIC = Path(__file__).resolve().parent / "static"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/tokens.css": ("tokens.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
BODY_LIMIT = 32 * 1024
SESSION_TTL = 2 * 60 * 60
SESSION_LIMIT = 32
COOKIE_NAME = "pitch_session"


def public_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("public origin must be an HTTPS origin without a path")
    return f"https://{parsed.netloc.lower()}"


class RequestError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        super().__init__(message)


@dataclass
class Session:
    agent: PitchAgent
    track: dict[str, str] | None = None
    touched: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def dto(self) -> dict:
        return {
            "track": self.track,
            "messages": self.agent.messages[1:],
            "total_tokens": self.agent.total_tokens,
            "model": self.agent.config.model,
            "busy": False,
        }


class PitchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 8000, external_origin: str | None = None) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.external_origin = external_origin
        self.external_host = urlsplit(external_origin).netloc if external_origin else None
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = threading.Lock()

    def acquire_session(self, token: str | None) -> tuple[str, Session]:
        with self.sessions_lock:
            now = time.monotonic()
            for key, session in list(self.sessions.items()):
                if now - session.touched >= SESSION_TTL and session.lock.acquire(False):
                    del self.sessions[key]
                    session.lock.release()
            if token not in self.sessions:
                if len(self.sessions) >= SESSION_LIMIT:
                    raise RequestError(503, "session_limit", "Слишком много сессий. Попробуйте позже.")
                token = secrets.token_urlsafe(32)
                self.sessions[token] = Session(PitchAgent())
            session = self.sessions[token]
            if not session.lock.acquire(False):
                raise RequestError(409, "busy", "Ответ ещё готовится. Подождите.")
            session.touched = now
            return token, session


class Handler(BaseHTTPRequestHandler):
    server: PitchServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args) -> None:
        # Avoid logging user-controlled URLs or chat text.
        pass

    def reply(self, status: int, data: bytes, content_type: str, cookie: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie:
            secure = "; Secure" if self.server.external_host == self.headers.get("Host", "").lower() else ""
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}{secure}")
        self.end_headers()
        self.wfile.write(data)

    def json_reply(self, status: int, data: dict, cookie: str | None = None) -> None:
        self.reply(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", cookie)

    def validate_origin(self, modifying: bool) -> None:
        hosts = self.headers.get_all("Host", [])
        local_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = hosts[0].lower() if len(hosts) == 1 else ""
        if host not in local_hosts and host != self.server.external_host:
            raise RequestError(403, "invalid_host", "Недопустимый адрес сервера.")
        origins = self.headers.get_all("Origin", [])
        expected_origin = self.server.external_origin if host == self.server.external_host else f"http://{host}"
        if modifying and origins and origins != [expected_origin]:
            raise RequestError(403, "invalid_origin", "Запрос с другого сайта запрещён.")
        if self.headers.get_all("Transfer-Encoding"):
            raise RequestError(400, "invalid_body", "Неподдерживаемый формат запроса.")

    def read_json(self) -> dict:
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise RequestError(415, "content_type", "Ожидается JSON.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise RequestError(400, "invalid_body", "Некорректный размер запроса.")
        length = int(lengths[0])
        if length > BODY_LIMIT:
            raise RequestError(413, "body_limit", "Слишком большой запрос.")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestError(400, "invalid_body", "Неполный запрос.")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise RequestError(400, "invalid_json", "Некорректный JSON.") from error
        if not isinstance(data, dict):
            raise RequestError(400, "invalid_input", "Ожидается объект JSON.")
        return data

    def cookie_token(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        value = cookie.get(COOKIE_NAME)
        return value.value if value else None

    def handle_request(self) -> None:
        session = None
        try:
            modifying = self.command in {"POST", "DELETE"}
            self.validate_origin(modifying)
            if self.command == "GET" and self.path in ASSETS:
                filename, content_type = ASSETS[self.path]
                try:
                    data = (STATIC / filename).read_bytes()
                except FileNotFoundError as error:
                    raise RequestError(404, "not_found", "Файл не найден.") from error
                self.reply(200, data, content_type)
                return
            route = (self.command, self.path)
            if route not in {("GET", "/api/session"), ("POST", "/api/messages"), ("DELETE", "/api/session")}:
                raise RequestError(404, "not_found", "Страница не найдена.")
            data = self.read_json() if modifying else {}
            token, session = self.server.acquire_session(self.cookie_token())
            if self.command == "DELETE":
                if data:
                    raise RequestError(400, "invalid_input", "Ожидается пустой объект JSON.")
                session.agent.messages = session.agent.messages[:1]
                session.agent.total_tokens = 0
                session.track = None
            elif self.command == "POST":
                fields = {"message": 4000} if session.track else {"name": 300, "description": 8000}
                if set(data) != set(fields) or any(
                    not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit
                    for key, limit in fields.items()
                ):
                    raise RequestError(400, "invalid_input", "Заполните поля и проверьте длину текста.")
                values = {key: value.strip() for key, value in data.items()}
                prompt = values.get("message") or (
                    "Write a music pitch in exactly three sentences.\n"
                    f"Track name: {values['name']}\nDescription: {values['description']}"
                )
                try:
                    session.agent.ask(prompt)
                except Exception as error:
                    raise RequestError(502, "provider_error", "Не удалось получить ответ модели. Попробуйте ещё раз.") from error
                if session.track is None:
                    session.track = values
            self.json_reply(200, session.dto(), token)
        except RequestError as error:
            self.json_reply(error.status, {"error": {"code": error.code, "message": str(error)}})
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:
            self.json_reply(500, {"error": {"code": "server_error", "message": "Ошибка сервера. Проверьте локальную конфигурацию."}})
        finally:
            if session is not None:
                session.touched = time.monotonic()
                session.lock.release()

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Pitch Agent website.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--public-origin", type=public_origin)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with PitchServer(args.port, args.public_origin) as server:
        print(f"Pitch Agent: http://127.0.0.1:{server.server_port}")
        if args.public_origin:
            print(f"Public origin: {args.public_origin}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
