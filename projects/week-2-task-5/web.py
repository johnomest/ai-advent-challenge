"""Local, cookie-isolated web interface for ChatAgent."""

import argparse
import json
import re
import secrets
import threading
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from main import (AgentConfig, ChatAgent, ContextStore, ContextLimitError, DATA_DIR,
                  build_context, decode_metrics, estimate_context, validate_strategy)


STATIC = Path(__file__).resolve().parent / "static"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/tokens.css": ("tokens.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/goost-typo.svg": ("goost-typo.svg", "image/svg+xml"),
    "/goost-logo.svg": ("goost-logo.svg", "image/svg+xml"),
    "/fonts/tt-wellingtons-regular.woff2": ("fonts/tt-wellingtons-regular.woff2", "font/woff2"),
    "/fonts/tt-wellingtons-demibold.woff2": ("fonts/tt-wellingtons-demibold.woff2", "font/woff2"),
    "/fonts/tt-wellingtons-bold.woff2": ("fonts/tt-wellingtons-bold.woff2", "font/woff2"),
}
BODY_LIMIT = 32 * 1024
COOKIE_MAX_AGE = 365 * 24 * 60 * 60
ACTIVE_OWNER_LIMIT = 32
COOKIE_NAME = "goost_owner"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
CHAT_ROUTE = re.compile(r"/api/chats/([A-Za-z0-9_-]{1,128})(/messages|/token-preview|/branches)?")
REQUEST_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,128}")


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
    def __init__(self, status: int, code: str, message: str, estimate: dict | None = None) -> None:
        self.status = status
        self.code = code
        self.estimate = estimate
        super().__init__(message)


class ChatServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        port: int = 8000,
        external_origin: str | None = None,
        database_path: Path | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.store = ContextStore(database_path or DATA_DIR / "context.sqlite3")
        super().__init__(("127.0.0.1", port), Handler)
        self.external_origin = external_origin
        self.external_host = urlsplit(external_origin).netloc if external_origin else None
        # ponytail: one local server process; use database leases for multiple workers.
        self.active_owners: set[str] = set()
        self.owners_lock = threading.Lock()

    def acquire_owner(self, owner_id: str) -> None:
        with self.owners_lock:
            if owner_id in self.active_owners:
                raise RequestError(409, "busy", "Ответ ещё готовится. Подождите.")
            if len(self.active_owners) >= ACTIVE_OWNER_LIMIT:
                raise RequestError(503, "capacity", "Сервер занят. Попробуйте позже.")
            self.active_owners.add(owner_id)

    def release_owner(self, owner_id: str) -> None:
        with self.owners_lock:
            self.active_owners.discard(owner_id)

    def is_busy(self, owner_id: str) -> bool:
        with self.owners_lock:
            return owner_id in self.active_owners


class Handler(BaseHTTPRequestHandler):
    server: ChatServer

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
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={COOKIE_MAX_AGE}{secure}")
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
        for name in (COOKIE_NAME, "chat_session", "pitch_session"):
            value = cookie.get(name)
            if value and TOKEN_PATTERN.fullmatch(value.value):
                return value.value
        return None

    def chat_dto(self, chat: dict, busy: bool = False) -> dict:
        return {**chat, "model": self.server.config.model, "busy": busy,
                "config": {"context_limit": self.server.config.context_limit, "max_tokens": self.server.config.max_tokens},
                "context": self.preview(chat, "")}

    def preview(self, chat: dict, message: str) -> dict:
        context = build_context(ChatAgent.system_prompt, chat["messages"], chat.get("strategy", "sliding_window"),
                                chat.get("window_turns", 3), chat.get("facts", {}))
        estimate = estimate_context(context, message, self.server.config)
        turns = len(chat["messages"]) // 2
        estimate.update(strategy=chat.get("strategy", "sliding_window"), total_turns=turns,
                        selected_turns=turns if chat.get("strategy") == "branching" else min(turns, chat.get("window_turns", 3)),
                        facts_count=len(chat.get("facts", {})))
        return estimate

    @staticmethod
    def replay(prior: dict, chat_id: str, message: str) -> dict:
        if prior["chat_id"] != chat_id or prior["message"] != message:
            raise RequestError(409, "request_conflict", "Этот идентификатор уже использован для другого сообщения.")
        if prior["state"] == "complete":
            result = json.loads(prior["response"])
            # Legacy request snapshots predate token metrics; unknown history stays unknown.
            result.setdefault("turn_metrics", [])
            decode_metrics(json.dumps(result["turn_metrics"]), len(result["messages"]) // 2)
            return result
        if prior["state"] == "pending":
            raise RequestError(409, "request_pending", "Исход запроса неизвестен. Обновите чат перед новой отправкой.")
        raise RequestError(502, "provider_error", "Запрос не выполнен. Повторите отправку с новым идентификатором.")

    def send_message(self, owner_id: str, chat: dict, data: dict) -> dict:
        if (
            set(data) != {"message", "request_id"}
            or not isinstance(data["message"], str)
            or not data["message"].strip()
            or len(data["message"]) > 4000
            or not isinstance(data["request_id"], str)
            or not REQUEST_PATTERN.fullmatch(data["request_id"])
        ):
            raise RequestError(400, "invalid_input", "Проверьте сообщение и идентификатор запроса.")
        message, request_id = data["message"].strip(), data["request_id"]
        prior = self.server.store.get_request(owner_id, request_id)
        if prior:
            return self.replay(prior, chat["id"], message)
        estimate = self.preview(chat, message)
        if estimate["overflow"] and chat["strategy"] != "sticky_facts":
            raise RequestError(422, "context_limit", "Контекст переполнен. Сократите сообщение или начните новый чат.", estimate)
        prior = self.server.store.reserve_request(owner_id, chat["id"], request_id, message)
        if prior:
            return self.replay(prior, chat["id"], message)
        try:
            agent = ChatAgent(config=self.server.config, strategy=chat["strategy"], window_turns=chat["window_turns"])
            agent.messages.extend(chat["messages"])
            agent.total_tokens = chat["total_tokens"]
            agent.turn_metrics = chat["turn_metrics"]
            agent.facts = chat["facts"]
            agent.ask(message)
        except ContextLimitError as error:
            self.server.store.fail_request(owner_id, request_id)
            raise RequestError(422, "context_limit", "Контекст переполнен после формирования памяти. Сократите сообщение или окно.", error.estimate) from error
        except Exception as error:
            self.server.store.fail_request(owner_id, request_id)
            raise RequestError(502, "provider_error", "Не удалось получить ответ модели. Попробуйте ещё раз.") from error
        return self.server.store.finish_request(owner_id, chat["id"], request_id, agent.messages[1:], agent.total_tokens, agent.turn_metrics, agent.facts)

    @staticmethod
    def strategy_input(data: dict, current: dict | None = None) -> tuple[str, int]:
        if set(data) - {"strategy", "window_turns"}:
            raise RequestError(400, "invalid_input", "Неизвестные настройки контекста.")
        strategy = data.get("strategy", (current or {}).get("strategy", "sliding_window"))
        window = data.get("window_turns", (current or {}).get("window_turns", 3))
        try:
            validate_strategy(strategy, window)
        except ValueError as error:
            raise RequestError(400, "invalid_input", "Выберите стратегию и окно от 1 до 20 ходов.") from error
        return strategy, window

    def handle_request(self) -> None:
        owner_id = None
        acquired = False
        try:
            modifying = self.command in {"POST", "PATCH", "DELETE"}
            self.validate_origin(modifying)
            if self.command == "GET" and self.path in ASSETS:
                filename, content_type = ASSETS[self.path]
                try:
                    data = (STATIC / filename).read_bytes()
                except FileNotFoundError as error:
                    raise RequestError(404, "not_found", "Файл не найден.") from error
                self.reply(200, data, content_type)
                return
            match = CHAT_ROUTE.fullmatch(self.path)
            collection = self.path == "/api/chats" and self.command in {"GET", "POST"}
            detail = match and ((match[2] is None and self.command in {"GET", "PATCH", "DELETE"})
                                or (match[2] and self.command == "POST"))
            if not collection and not detail:
                raise RequestError(404, "not_found", "Страница не найдена.")
            data = self.read_json() if self.command in {"POST", "PATCH"} else {}
            if self.command == "DELETE" and self.headers.get("Content-Length", "0") != "0":
                data = self.read_json()
            owner_id = self.cookie_token() or secrets.token_urlsafe(32)
            preview_route = bool(match and match[2] == "/token-preview")
            if modifying and not preview_route:
                self.server.acquire_owner(owner_id)
                acquired = True
            status = 200
            if collection:
                if self.command == "GET":
                    result = {"chats": self.server.store.list_chats(owner_id), "model": self.server.config.model,
                              "busy": self.server.is_busy(owner_id)}
                else:
                    strategy, window = self.strategy_input(data)
                    result = {"chat": self.chat_dto(self.server.store.create_chat(owner_id, strategy=strategy, window_turns=window))}
                    status = 201
            else:
                chat_id = match[1]
                chat = self.server.store.get_chat(owner_id, chat_id)
                if chat is None:
                    raise RequestError(404, "not_found", "Чат не найден.")
                if preview_route:
                    if set(data) != {"message"} or not isinstance(data["message"], str) or len(data["message"]) > 4000:
                        raise RequestError(400, "invalid_input", "Сообщение должно содержать не более 4000 символов.")
                    self.json_reply(200, {"estimate": self.preview(chat, data["message"])}, owner_id)
                    return
                if match[2] == "/branches":
                    if (set(data) != {"checkpoint_turn", "request_id"} or type(data["checkpoint_turn"]) is not int
                            or not isinstance(data["request_id"], str) or not REQUEST_PATTERN.fullmatch(data["request_id"])):
                        raise RequestError(400, "invalid_input", "Укажите завершённый ход и идентификатор запроса.")
                    try:
                        branches, replayed = self.server.store.branch(owner_id, chat_id, data["checkpoint_turn"], data["request_id"])
                    except ValueError as error:
                        if str(error) == "Branch request conflict":
                            raise RequestError(409, "request_conflict", "Этот идентификатор использован для другого ветвления.") from error
                        raise RequestError(400, "invalid_input", "Выберите существующий завершённый ход.") from error
                    self.json_reply(200 if replayed else 201, {"branches": [self.chat_dto(branch) for branch in branches]}, owner_id)
                    return
                if self.command == "DELETE":
                    if data:
                        raise RequestError(400, "invalid_input", "Ожидается пустой объект JSON.")
                    self.server.store.delete_chat(owner_id, chat_id)
                    result = {"deleted": chat_id}
                else:
                    if self.command == "PATCH":
                        if set(data) == {"title"}:
                            if not isinstance(data["title"], str) or not 1 <= len(data["title"].strip()) <= 100:
                                raise RequestError(400, "invalid_input", "Название должно содержать от 1 до 100 символов.")
                            self.server.store.rename_chat(owner_id, chat_id, data["title"].strip())
                        else:
                            if not data:
                                raise RequestError(400, "invalid_input", "Укажите настройки контекста.")
                            strategy, window = self.strategy_input(data, chat)
                            try:
                                self.server.store.configure_chat(owner_id, chat_id, strategy, window)
                            except ValueError as error:
                                raise RequestError(409, "strategy_locked", "Настройки доступны только в пустом чате.") from error
                        chat = self.server.store.get_chat(owner_id, chat_id)
                    elif self.command == "POST":
                        chat = self.send_message(owner_id, chat, data)
                    result = {"chat": self.chat_dto(chat, self.server.is_busy(owner_id) if not modifying else False)}
            self.json_reply(status, result, owner_id)
        except RequestError as error:
            detail = {"code": error.code, "message": str(error)}
            if error.estimate is not None:
                detail["estimate"] = error.estimate
            self.json_reply(error.status, {"error": detail}, owner_id)
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:
            self.json_reply(500, {"error": {"code": "server_error", "message": "Ошибка сервера. Проверьте локальную конфигурацию."}})
        finally:
            if acquired:
                self.server.release_owner(owner_id)

    do_GET = handle_request
    do_POST = handle_request
    do_PATCH = handle_request
    do_DELETE = handle_request


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local GOOST CHAT website.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--public-origin", type=public_origin)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with ChatServer(args.port, args.public_origin, DATA_DIR / "context.sqlite3") as server:
        print(f"GOOST CHAT: http://127.0.0.1:{server.server_port}")
        if args.public_origin:
            print(f"Public origin: {args.public_origin}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
