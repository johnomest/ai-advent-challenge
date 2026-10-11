"""Telegram long polling, owner pairing and a client for the private local API."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class APIError(RuntimeError):
    def __init__(self, status):
        super().__init__(f"API returned HTTP {status}.")
        self.status = status


def call(url, payload, headers=None, timeout=35):
    request = Request(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      {"Content-Type": "application/json", **(headers or {})})
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=timeout) as response:
            data = json.load(response)
    except HTTPError as error:
        raise APIError(error.code) from None
    except (OSError, ValueError):
        # Telegram credentials form part of the URL; never echo a raw network exception.
        raise RuntimeError("API connection failed or invalid JSON received.") from None
    return data


def split_text(text, limit=3500):
    chunk, length = [], 0
    for character in text:
        width = 2 if ord(character) > 0xFFFF else 1
        if length + width > limit:
            yield "".join(chunk)
            chunk, length = [], 0
        chunk.append(character)
        length += width
    if chunk:
        yield "".join(chunk)


class Access:
    def __init__(self, bot_id, allowed, folder):
        self.bot_id = bot_id
        self.path = folder / "owner.json"
        self.owner = None
        values = [value.strip() for value in allowed.split(",") if value.strip()]
        if len(values) > 64 or any(not re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in values):
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS must contain up to 64 positive IDs.")
        self.allowed = {int(value) for value in values}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(data, dict) or data.get("bot_id") != bot_id
                    or type(data.get("owner")) is not int or data["owner"] <= 0):
                raise ValueError("Saved owner belongs to another bot or is invalid.")
            self.owner = data["owner"]
        self.code = secrets.token_urlsafe(24) if self.owner is None else None
        self.expires = time.monotonic() + 600

    def pair(self, user_id, code):
        if (self.owner is not None or not self.code or time.monotonic() > self.expires
                or not re.fullmatch(r"[A-Za-z0-9_-]{32}", code)
                or not secrets.compare_digest(code.encode(), self.code.encode())):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"bot_id": self.bot_id, "owner": user_id}) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)
        self.owner, self.code = user_id, None
        return True

    def permits(self, user_id):
        return user_id == self.owner or user_id in self.allowed


class Bot:
    def __init__(self, token, base, key, allowed, folder):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token):
            raise ValueError("TELEGRAM_BOT_TOKEN is missing or malformed.")
        self.url = "https://api.telegram.org/bot" + token + "/"
        self.base, self.key = base, key
        self.folder = folder
        self.stopped = threading.Event()
        self.pending = set()
        self.lock = threading.Lock()
        self.denials = OrderedDict()
        self.capacity = threading.BoundedSemaphore(8)
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="telegram-client")
        details = self.telegram("getMe", {})
        self.username = details["username"]
        if self.telegram("getWebhookInfo", {}).get("url"):
            self.executor.shutdown(wait=False, cancel_futures=True)
            raise ValueError("The bot has a webhook; remove it before starting long polling.")
        self.access = Access(details["id"], allowed, folder)
        self.offset_path = folder / f"telegram-offset-{details['id']}.json"
        self.offset = 0
        if self.offset_path.exists():
            self.offset = json.loads(self.offset_path.read_text(encoding="utf-8"))["offset"]
            if type(self.offset) is not int or self.offset < 0:
                raise ValueError("Invalid Telegram update offset.")
        self.thread = threading.Thread(target=self.poll, name="telegram-poll", daemon=True)

    def telegram(self, method, payload):
        response = call(self.url + method, payload)
        if not isinstance(response, dict) or response.get("ok") is not True or "result" not in response:
            raise RuntimeError("Telegram returned an invalid API response.")
        if method == "getUpdates" and not isinstance(response["result"], list):
            raise RuntimeError("Telegram returned invalid updates.")
        return response["result"]

    def send(self, chat_id, text):
        for chunk in split_text(text):
            self.telegram("sendMessage", {"chat_id": chat_id, "text": chunk,
                                          "link_preview_options": {"is_disabled": True}})

    def local(self, endpoint, payload):
        return call(self.base + endpoint, payload, {"Authorization": "Bearer " + self.key}, timeout=130)

    def start(self):
        print(f"Telegram: https://t.me/{self.username}", flush=True)
        if self.access.code:
            print(f"Привязка владельца (один раз, срок 10 минут): "
                  f"https://t.me/{self.username}?start={self.access.code}", flush=True)
        self.thread.start()

    def dispatch(self, update):
        message = update.get("message")
        if not isinstance(message, dict) or message.get("chat", {}).get("type") != "private":
            return
        user_id = message.get("from", {}).get("id")
        chat_id = message["chat"].get("id")
        text = message.get("text")
        if (type(user_id) is not int or user_id <= 0 or chat_id != user_id
                or not isinstance(text, str) or message.get("from", {}).get("is_bot")):
            return
        text = text.strip()
        if text.startswith("/start ") and self.access.pair(user_id, text.partition(" ")[2]):
            self.send(chat_id, "Аккаунт привязан. Задавай вопросы по книге How to Get Hired. /reset — очистить диалог.")
            print("Telegram owner paired.", flush=True)
            return
        if not self.access.permits(user_id):
            now = time.monotonic()
            if now - self.denials.get(user_id, -60) >= 30:
                self.denials[user_id] = now
                self.denials.move_to_end(user_id)
                while len(self.denials) > 128:
                    self.denials.popitem(last=False)
                self.send(chat_id, f"Доступ закрыт. Твой Telegram ID: {user_id}. Передай его владельцу.")
            return
        if text in ("/start", "/help"):
            self.send(chat_id, "Вопросы по How to Get Hired: Framestore, IV и другие студии. "
                      "/reset — новый диалог. /id — твой ID. Лимит: 6 вопросов в минуту.")
            return
        if text == "/id":
            self.send(chat_id, f"Твой Telegram ID: {user_id}")
            return
        if text.startswith("/") and text != "/reset":
            self.send(chat_id, "Команды: /start, /help, /reset, /id.")
            return
        with self.lock:
            if user_id in self.pending:
                busy = True
            else:
                busy = not self.capacity.acquire(blocking=False)
                if not busy:
                    self.pending.add(user_id)
        if busy:
            self.send(chat_id, "Дождись текущего ответа и повтори запрос.")
            return
        self.executor.submit(self.reply, user_id, chat_id, text)

    def reply(self, user_id, chat_id, text):
        try:
            session = f"telegram:{user_id}"
            if text == "/reset":
                self.local("/reset", {"session": session})
                if self.stopped.is_set():
                    return
                self.send(chat_id, "История очищена.")
            else:
                result = self.local("/chat", {"session": session, "question": text})
                if self.stopped.is_set():
                    return
                sources = "\n".join(f"{x['chunk_id']} — {x['studio']}, {x['section']}" for x in result["sources"])
                self.send(chat_id, result["answer"] + f"\n\nВремя: {result['seconds']:.2f} с" +
                          ("\nНайденные источники:\n" + sources if sources else ""))
                print("Telegram question answered.", flush=True)
        except (APIError, RuntimeError) as error:
            if self.stopped.is_set():
                return
            notices = {400: "Некорректный вопрос. Лимит — 1200 символов.",
                       409: "Дождись текущего ответа.", 413: "Контекст заполнен. Используй /reset или сократи вопрос.",
                       429: "Лимит — 6 вопросов в минуту. Подожди минуту.",
                       503: "Сервис занят или модель недоступна. Повтори позже.",
                       504: "Время ожидания истекло. Повтори вопрос."}
            try:
                self.send(chat_id, notices.get(getattr(error, "status", 0), "Не удалось получить ответ. Повтори позже."))
            except (APIError, RuntimeError):
                print("Telegram reply delivery failed.", flush=True)
        finally:
            with self.lock:
                self.pending.discard(user_id)
            self.capacity.release()

    def poll(self):
        while not self.stopped.is_set():
            try:
                updates = self.telegram("getUpdates", {"offset": self.offset, "timeout": 20,
                                                       "limit": 20, "allowed_updates": ["message"]})
                for update in updates:
                    if self.stopped.is_set():
                        return
                    self.dispatch(update)
                    self.offset = update["update_id"] + 1
                    self.folder.mkdir(parents=True, exist_ok=True)
                    temporary = self.offset_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"offset": self.offset}) + "\n", encoding="utf-8")
                    os.replace(temporary, self.offset_path)
            except APIError as error:
                if error.status in (401, 404, 409):
                    print(f"Telegram polling stopped (HTTP {error.status}); check token or another bot process.", flush=True)
                    self.stopped.set()
                    return
                print(f"Telegram polling failed (HTTP {error.status}); retrying.", flush=True)
                self.stopped.wait(5)
            except (RuntimeError, OSError, ValueError):
                print("Telegram polling unavailable; retrying.", flush=True)
                self.stopped.wait(5)

    def stop(self):
        self.stopped.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self.executor.shutdown(wait=False, cancel_futures=True)
