"""Day 30: private local RAG HTTP API with a Telegram client."""

import argparse
from collections import OrderedDict, deque
from concurrent.futures import CancelledError, Future, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import secrets
import sys
import threading
import time
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("opt29_service", ROOT / "projects/week-6-task-4/main.py")
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)
DATA = Path(__file__).parent / "data"
MAX_QUESTION = 1200
MAX_BODY = 16384
RATE = 6
WINDOW = 60
MAX_SESSIONS = 128
SESSION_TTL = 1800
DEADLINE = 120
SESSION = re.compile(r"(?:api:[A-Za-z0-9_-]{1,64}|telegram:[1-9][0-9]{0,19})\Z")


def environment():
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    values.update(os.environ)
    return values


def api_key(values):
    key = values.get("LOCAL_AI_API_TOKEN", "")
    if not key:
        key = secrets.token_urlsafe(32)
        path = ROOT / ".env"
        data = path.read_bytes() if path.exists() else b""
        newline = b"\r\n" if b"\r\n" in data else b"\n"
        # Replace an empty placeholder as well; never append duplicate keys.
        lines = data.splitlines(keepends=True)
        replacement = b"LOCAL_AI_API_TOKEN=" + key.encode() + newline
        found = False
        for i, line in enumerate(lines):
            if line.split(b"=", 1)[0].strip() == b"LOCAL_AI_API_TOKEN":
                lines[i], found = replacement, True
        if not found:
            if lines and not lines[-1].endswith(b"\n"):
                lines[-1] += newline
            lines.append(replacement)
        DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=DATA, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(b"".join(lines))
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if len(key) < 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("LOCAL_AI_API_TOKEN must be at least 32 URL-safe characters.")
    return key


class ServiceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Engine:
    """One GPU worker, bounded admission, separate and transactional histories."""

    def __init__(self, backend, capacity=8):
        self.backend = backend
        self.jobs = queue.Queue(maxsize=capacity)
        self.lock = threading.Lock()
        self.sessions = OrderedDict()
        self.busy = set()
        self.futures = {}
        self.closed = False
        self.stats = {"completed": 0, "failed": 0, "rejected": 0}
        self.worker = threading.Thread(target=self.work, name="local-rag", daemon=True)
        self.worker.start()

    def reject(self, status, message):
        self.stats["rejected"] += 1
        raise ServiceError(status, message)

    def submit(self, session, question):
        if not isinstance(session, str) or not SESSION.fullmatch(session):
            raise ServiceError(400, "Invalid session identifier.")
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
            raise ServiceError(400, f"Question must contain 1–{MAX_QUESTION} characters.")
        try:
            question.encode("utf-8")
        except UnicodeError:
            raise ServiceError(400, "Invalid Unicode question.") from None
        now = time.monotonic()
        with self.lock:
            if self.closed:
                self.reject(503, "Service is stopping.")
            for key, state in list(self.sessions.items()):
                if key not in self.busy and now - state["last"] > SESSION_TTL:
                    del self.sessions[key]
            if session in self.busy:
                self.reject(409, "Previous question is still being processed.")
            if session not in self.sessions:
                if len(self.sessions) >= MAX_SESSIONS:
                    self.reject(503, "Session capacity reached. Retry later.")
                self.sessions[session] = {"history": [], "times": deque(), "last": now}
            state = self.sessions[session]
            while state["times"] and now - state["times"][0] >= WINDOW:
                state["times"].popleft()
            if len(state["times"]) >= RATE:
                self.reject(429, "Limit: 6 questions per 60 seconds per session.")
            future = Future()
            try:
                self.jobs.put_nowait((session, question.strip(), future, now))
            except queue.Full:
                self.reject(503, "Queue is full. Retry later.")
            self.busy.add(session)
            self.futures[session] = future
            state["times"].append(now)
            state["last"] = now
            self.sessions.move_to_end(session)
            return future

    def work(self):
        while True:
            job = self.jobs.get()
            if job is None:
                self.jobs.task_done()
                return
            session, question, future, admitted = job
            started = time.monotonic()
            try:
                if future.cancelled() or started - admitted >= DEADLINE:
                    raise ServiceError(504, "Request deadline expired in queue.")
                with self.lock:
                    history = list(self.sessions[session]["history"])
                result = self.backend(question, history)
                with self.lock:
                    if future.cancelled() or time.monotonic() - admitted >= DEADLINE:
                        raise ServiceError(504, "Request deadline expired; history unchanged.")
                    self.sessions[session]["history"] = history[-10:]
                    self.sessions[session]["last"] = time.monotonic()
                    self.stats["completed"] += 1
                    future.set_result({**result, "session": session,
                                       "queue_seconds": round(started - admitted, 3)})
            except Exception as error:
                if isinstance(error, ValueError):
                    error = ServiceError(413, "Context limit reached. Use /reset or shorten the question.")
                elif not isinstance(error, ServiceError):
                    print(f"RAG request failed ({type(error).__name__}).", flush=True)
                    error = ServiceError(503, "Local model unavailable or answer incomplete; history unchanged.")
                with self.lock:
                    self.stats["failed"] += 1
                    if not future.cancelled():
                        future.set_exception(error)
            finally:
                with self.lock:
                    self.busy.discard(session)
                    self.futures.pop(session, None)
                self.jobs.task_done()

    def reset(self, session):
        if not isinstance(session, str) or not SESSION.fullmatch(session):
            raise ServiceError(400, "Invalid session identifier.")
        with self.lock:
            if session in self.busy:
                raise ServiceError(409, "Wait for the current answer before resetting history.")
            if session in self.sessions:
                self.sessions[session]["history"] = []
        return {"status": "history cleared", "session": session}

    def snapshot(self):
        with self.lock:
            return {**self.stats, "pending": self.jobs.qsize(), "active_sessions": len(self.busy),
                    "sessions": len(self.sessions), "queue_capacity": self.jobs.maxsize,
                    "rate_limit": RATE, "rate_window_seconds": WINDOW,
                    "max_question_characters": MAX_QUESTION, "context_tokens": 8192,
                    "max_answer_tokens": 768, "model": opt.model_args(opt.SELECTED).model}

    def close(self):
        with self.lock:
            self.closed = True
            for future in self.futures.values():
                future.cancel()
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            if job:
                session, _, future, _ = job
                with self.lock:
                    self.busy.discard(session)
                    if not future.cancelled():
                        future.set_exception(ServiceError(503, "Service stopped before processing."))
            self.jobs.task_done()
        self.jobs.put(None)
        self.worker.join(timeout=3)


def handler(engine, key):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalAI/1"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # Headers, prompts and credentials never enter access logs.

        def send_json(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            if status in (429, 503):
                self.send_header("Retry-After", "60" if status == 429 else "5")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            value = self.headers.get("Authorization", "")
            return secrets.compare_digest(value.encode("utf-8"), ("Bearer " + key).encode())

        def dispatch(self):
            future = None
            try:
                if not self.authorized():
                    raise ServiceError(401, "Bearer token required.")
                if self.command == "GET" and self.path == "/health":
                    self.send_json(200, {"status": "ok", **engine.snapshot()})
                    return
                if self.command != "POST" or self.path not in ("/chat", "/reset"):
                    raise ServiceError(404, "Endpoint not found.")
                if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                    raise ServiceError(400, "One Content-Length header is required.")
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    raise ServiceError(400, "Invalid Content-Length.") from None
                if not 0 < length <= MAX_BODY:
                    raise ServiceError(413, "JSON body exceeds limit.")
                if self.headers.get_content_type() != "application/json":
                    raise ServiceError(415, "Content-Type must be application/json.")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ServiceError(400, "Incomplete request body.")
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeError, RecursionError):
                    raise ServiceError(400, "Invalid JSON.") from None
                if not isinstance(payload, dict) or set(payload) - {"session", "question"}:
                    raise ServiceError(400, "Allowed fields: session, question.")
                session = payload.get("session", "api:" + uuid4().hex)
                if self.path == "/reset":
                    if "session" not in payload or "question" in payload:
                        raise ServiceError(400, "Reset requires only a session.")
                    result = engine.reset(session)
                else:
                    future = engine.submit(session, payload.get("question"))
                    result = future.result(timeout=DEADLINE + 5)
                self.send_json(200, result)
            except FutureTimeout:
                if future:
                    with engine.lock:
                        future.cancel()
                self.send_json(504, {"error": "Request deadline expired."})
            except CancelledError:
                self.send_json(503, {"error": "Service is stopping."})
            except ServiceError as error:
                self.send_json(error.status, {"error": str(error)})
            except (OSError, ValueError):
                if future:
                    with engine.lock:
                        future.cancel()

        do_GET = dispatch
        do_POST = dispatch

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, request_handler):
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(address, request_handler)

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.connections.release()


def backend():
    index = opt.rag.read_index(opt.rag.DEFAULT_INDEX)
    generation = opt.model_args(opt.SELECTED)
    retrieval = opt.model_args({**opt.BASELINE, "quantization": opt.SELECTED["quantization"]})
    for args in (generation, retrieval):
        args.context_limit, args.request_timeout = 8192, 30
    opt.rag.day27.validate(generation)
    opt.rag.day27.ensure_local_model(generation.embedding_url, index["model"])
    props = opt.rag.day27.request(generation.url, "/props", timeout=30)
    if props["default_generation_settings"]["n_ctx"] != 8192 or props["total_slots"] != 1:
        raise ValueError("Start the Day 29 Q4 profile with context 8192 and one slot.")

    def reply(question, history):
        result = opt.rag.answer(question, history, index, retrieval,
                                system=opt.system(opt.SELECTED), generation_args=generation)
        return {key: result[key] for key in ("answer", "sources", "seconds", "tokens")}

    return reply


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-only", action="store_true", help="Run without Telegram polling")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be 1024–65535")
    values = environment()
    key = api_key(values)
    engine = Engine(backend())
    server = None
    bot = None
    try:
        server = Server(("127.0.0.1", args.port), handler(engine, key))
        base = f"http://127.0.0.1:{args.port}"
        if not args.api_only:
            connector = opt.rag.load("telegram30", Path(__file__).with_name("telegram_bot.py"))
            bot = connector.Bot(values.get("TELEGRAM_BOT_TOKEN", ""), base, key,
                                values.get("TELEGRAM_ALLOWED_USER_IDS", ""), DATA)
        print(f"DAY 30 | {opt.model_args(opt.SELECTED).model} | private HTTP API {base}", flush=True)
        if bot:
            bot.start()
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        print("Stopping Day 30.", flush=True)
    finally:
        if bot:
            bot.stop()
        if server:
            server.server_close()
        engine.close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(f"Day 30 could not start: {error}") from None
    except OSError:
        raise SystemExit("Day 30 could not start. Check local servers, port and configuration files.") from None
