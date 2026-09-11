import json
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DATA_DIR = Path(__file__).resolve().parent / "data"
KEEP_LAST_MESSAGES = 6
SUMMARY_BATCH_MESSAGES = 10
MAX_SUMMARY_CHARACTERS = 4000


def decode_compression(raw: str, message_count: int) -> dict:
    try:
        state = json.loads(raw)
        if state == {}:
            return {"mode": "compressed", "summary": "", "summarized_count": 0,
                    "summary_api_tokens": 0, "summary_metrics": []}
        if not isinstance(state, dict) or set(state) != {
            "mode", "summary", "summarized_count", "summary_api_tokens", "summary_metrics"
        }:
            raise ValueError
        if not isinstance(state["mode"], str) or state["mode"] not in {"full", "compressed"}:
            raise ValueError
        count = state["summarized_count"]
        if type(count) is not int or count < 0 or count % 2 or count > max(0, message_count - KEEP_LAST_MESSAGES):
            raise ValueError
        if not isinstance(state["summary"], str) or len(state["summary"]) > MAX_SUMMARY_CHARACTERS:
            raise ValueError
        if bool(state["summary"].strip()) != bool(count):
            raise ValueError
        metrics = decode_metrics(json.dumps(state["summary_metrics"]), count // 2)
        if bool(metrics) != bool(count):
            raise ValueError
        totals = [item["provider_usage"]["total_tokens"] for item in metrics]
        expected = None if any(value is None for value in totals) else sum(totals)
        if state["summary_api_tokens"] != expected or (expected is not None and type(state["summary_api_tokens"]) is not int):
            raise ValueError
    except (TypeError, ValueError, RuntimeError, KeyError) as error:
        raise RuntimeError("Stored compression is invalid") from error
    return state


class ContextStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.database() as database:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute("BEGIN IMMEDIATE")
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version > 3:
                raise RuntimeError("Unsupported database version")
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            database.execute("CREATE INDEX IF NOT EXISTS chats_owner ON chats(owner_id, updated_at)")
            database.execute(
                """CREATE TABLE IF NOT EXISTS requests (
                    owner_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    state TEXT NOT NULL,
                    response TEXT,
                    PRIMARY KEY (owner_id, request_id)
                )"""
            )
            if version == 0:
                legacy = database.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
                ).fetchone()
                if legacy:
                    for row in database.execute("SELECT * FROM conversations").fetchall():
                        messages = self.decode_messages(row["messages"], row["total_tokens"])
                        chat_id = secrets.token_urlsafe(24) if len(row["id"]) == 43 else row["id"]
                        database.execute(
                            "INSERT OR IGNORE INTO chats (id, owner_id, title, messages, total_tokens, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (chat_id, row["id"], self.title_from(messages), row["messages"],
                             row["total_tokens"], row["updated_at"], row["updated_at"]),
                        )
            columns = {row["name"] for row in database.execute("PRAGMA table_info(chats)")}
            if "turn_metrics" not in columns:
                database.execute("ALTER TABLE chats ADD COLUMN turn_metrics TEXT NOT NULL DEFAULT '[]'")
            if "compression" not in columns:
                database.execute("ALTER TABLE chats ADD COLUMN compression TEXT NOT NULL DEFAULT '{}'")
            database.execute("PRAGMA user_version=3")

    @contextmanager
    def database(self):
        database = sqlite3.connect(self.path)
        database.row_factory = sqlite3.Row
        try:
            with database:
                yield database
        finally:
            database.close()

    @staticmethod
    def decode_messages(raw: str, total_tokens: int) -> list[dict[str, str]]:
        try:
            messages = json.loads(raw)
            valid = isinstance(messages, list) and all(
                isinstance(message, dict)
                and set(message) == {"role", "content"}
                and message["role"] in {"user", "assistant"}
                and isinstance(message["content"], str)
                and bool(message["content"])
                for message in messages
            )
            if not valid or type(total_tokens) is not int or total_tokens < 0:
                raise ValueError
            if len(messages) % 2 or any(item["role"] != ("user" if index % 2 == 0 else "assistant")
                                       for index, item in enumerate(messages)):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Stored conversation is invalid") from error
        return messages

    @staticmethod
    def title_from(messages: list[dict[str, str]]) -> str:
        return next((" ".join(item["content"].split())[:100] for item in messages
                     if item["role"] == "user"), "Новый чат")

    def dto(self, row: sqlite3.Row, detail: bool = True) -> dict:
        messages = self.decode_messages(row["messages"], row["total_tokens"])
        metrics = decode_metrics(row["turn_metrics"], len(messages) // 2)
        result = {key: row[key] for key in ("id", "title", "created_at", "updated_at", "total_tokens")}
        result["message_count"] = len(messages)
        if detail:
            result["messages"] = messages
            result["turn_metrics"] = metrics
            result["compression"] = decode_compression(row["compression"], len(messages))
        return result

    def list_chats(self, owner_id: str) -> list[dict]:
        with self.database() as database:
            rows = database.execute(
                "SELECT * FROM chats WHERE owner_id = ? ORDER BY updated_at DESC, rowid DESC",
                (owner_id,),
            ).fetchall()
        return [self.dto(row, detail=False) for row in rows]

    def get_chat(self, owner_id: str, chat_id: str) -> dict | None:
        with self.database() as database:
            row = database.execute("SELECT * FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).fetchone()
        return self.dto(row) if row else None

    def create_chat(self, owner_id: str, title: str = "Новый чат", chat_id: str | None = None) -> dict:
        chat_id = chat_id or secrets.token_urlsafe(24)
        with self.database() as database:
            database.execute(
                "INSERT INTO chats (id, owner_id, title, messages, total_tokens, created_at, updated_at) VALUES (?, ?, ?, '[]', 0, unixepoch(), unixepoch())",
                (chat_id, owner_id, title),
            )
        return self.get_chat(owner_id, chat_id)

    def rename_chat(self, owner_id: str, chat_id: str, title: str) -> None:
        with self.database() as database:
            if not database.execute(
                "UPDATE chats SET title = ?, updated_at = unixepoch() WHERE owner_id = ? AND id = ?",
                (title, owner_id, chat_id),
            ).rowcount:
                raise KeyError(chat_id)

    def delete_chat(self, owner_id: str, chat_id: str) -> None:
        with self.database() as database:
            if not database.execute("DELETE FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).rowcount:
                raise KeyError(chat_id)
            database.execute("DELETE FROM requests WHERE owner_id = ? AND chat_id = ?", (owner_id, chat_id))
            if database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='compression'").fetchone():
                database.execute("DELETE FROM compression WHERE chat_id = ?", (chat_id,))

    def set_compression_mode(self, owner_id: str, chat_id: str, mode: str) -> None:
        if not isinstance(mode, str) or mode not in {"full", "compressed"}:
            raise ValueError("Invalid compression mode")
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute("SELECT * FROM chats WHERE owner_id=? AND id=?", (owner_id, chat_id)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            state = self.dto(row)["compression"]
            state["mode"] = mode
            database.execute("UPDATE chats SET compression=? WHERE owner_id=? AND id=?",
                             (json.dumps(state), owner_id, chat_id))

    def reserve_request(self, owner_id: str, chat_id: str, request_id: str, message: str) -> dict | None:
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT * FROM requests WHERE owner_id = ? AND request_id = ?", (owner_id, request_id)
            ).fetchone()
            if row:
                return dict(row)
            database.execute("INSERT INTO requests VALUES (?, ?, ?, ?, 'pending', NULL)",
                             (owner_id, request_id, chat_id, message))
        return None

    def get_request(self, owner_id: str, request_id: str) -> dict | None:
        with self.database() as database:
            row = database.execute("SELECT * FROM requests WHERE owner_id = ? AND request_id = ?",
                                   (owner_id, request_id)).fetchone()
        return dict(row) if row else None

    def fail_request(self, owner_id: str, request_id: str) -> None:
        with self.database() as database:
            database.execute("UPDATE requests SET state = 'failed' WHERE owner_id = ? AND request_id = ?",
                             (owner_id, request_id))

    def finish_request(self, owner_id: str, chat_id: str, request_id: str, messages: list[dict[str, str]], total_tokens: int, turn_metrics: list[dict], compression: dict | None = None, snapshot=None) -> dict:
        metrics_json = json.dumps(turn_metrics)
        decode_metrics(metrics_json, len(messages) // 2)
        self.decode_messages(json.dumps(messages), total_tokens)
        if compression is not None:
            decode_compression(json.dumps(compression), len(messages))
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            request = database.execute("SELECT * FROM requests WHERE owner_id = ? AND request_id = ?",
                                       (owner_id, request_id)).fetchone()
            if request is None or request["chat_id"] != chat_id or request["state"] != "pending":
                raise RuntimeError("Request is not pending")
            row = database.execute("SELECT * FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            title = self.title_from(messages) if row["title"] == "Новый чат" and row["messages"] == "[]" else row["title"]
            database.execute(
                "UPDATE chats SET messages = ?, total_tokens = ?, turn_metrics = ?, title = ?, updated_at = unixepoch() WHERE owner_id = ? AND id = ?",
                (json.dumps(messages, ensure_ascii=False), total_tokens, metrics_json, title, owner_id, chat_id),
            )
            if compression is not None:
                database.execute("UPDATE chats SET compression=? WHERE owner_id=? AND id=?",
                                 (json.dumps(compression, ensure_ascii=False), owner_id, chat_id))
            chat = self.dto(database.execute("SELECT * FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).fetchone())
            if snapshot is not None:
                chat = snapshot(chat)
            database.execute("UPDATE requests SET state = 'complete', response = ? WHERE owner_id = ? AND request_id = ?",
                             (json.dumps(chat, ensure_ascii=False), owner_id, request_id))
        return chat

    def load_agent(self, conversation_id: str) -> tuple[list[dict[str, str]], int] | None:
        chat = self.get_chat(conversation_id, conversation_id)
        return (chat["messages"], chat["total_tokens"]) if chat else None

    def save_agent(
        self,
        conversation_id: str,
        messages: list[dict[str, str]],
        total_tokens: int,
        turn_metrics: list[dict] | None = None,
    ) -> None:
        metrics_json = json.dumps(turn_metrics or [])
        decode_metrics(metrics_json, len(messages) // 2)
        with self.database() as database:
            database.execute(
                """
                INSERT INTO chats (id, owner_id, title, messages, total_tokens, turn_metrics, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, unixepoch(), unixepoch())
                ON CONFLICT(id) DO UPDATE SET
                    messages = excluded.messages,
                    total_tokens = excluded.total_tokens,
                    turn_metrics = excluded.turn_metrics,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, conversation_id, self.title_from(messages), json.dumps(messages, ensure_ascii=False), total_tokens, metrics_json),
            )

    def delete(self, conversation_id: str) -> None:
        with self.database() as database:
            database.execute("DELETE FROM chats WHERE owner_id = ? AND id = ?", (conversation_id, conversation_id))
            database.execute("DELETE FROM requests WHERE owner_id = ? AND chat_id = ?", (conversation_id, conversation_id))

@dataclass(frozen=True)
class AgentConfig:
    model: str = "deepseek-v4-flash"
    temperature: float = 0.5
    top_p: float = 1.0
    max_tokens: int = 250
    timeout: int = 60
    context_limit: int = 2048

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (self.max_tokens, self.context_limit)):
            raise ValueError("Token limits must be positive integers")
        if self.max_tokens >= self.context_limit:
            raise ValueError("Output reserve must be smaller than context limit")


def estimate_text_tokens(text: str) -> int:
    # ponytail: UTF-8 byte heuristic; use the provider tokenizer if exact preflight is required.
    return (len(text.encode("utf-8")) + 3) // 4


def estimate_context(messages: list[dict[str, str]], message: str = "", config: AgentConfig | None = None) -> dict:
    config = config or AgentConfig()
    message = message.strip()
    system = sum(estimate_text_tokens(item["content"]) for item in messages if item["role"] == "system")
    history = sum(estimate_text_tokens(item["content"]) for item in messages if item["role"] != "system")
    request = estimate_text_tokens(message)
    overhead = 3 + 4 * (len(messages) + bool(message))
    prompt = system + history + request + overhead
    required = prompt + config.max_tokens
    return {"system_tokens": system, "history_tokens": history, "request_tokens": request,
            "message_overhead_tokens": overhead, "prompt_tokens": prompt,
            "reserved_output_tokens": config.max_tokens, "required_tokens": required,
            "context_limit": config.context_limit, "remaining_tokens": config.context_limit - required,
            "overflow": required > config.context_limit, "estimator": "utf8_bytes_div4_v1"}


class ContextLimitError(ValueError):
    def __init__(self, estimate: dict) -> None:
        self.estimate = estimate
        super().__init__("Application context limit exceeded")


@dataclass(frozen=True)
class ProviderUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None

    @classmethod
    def parse(cls, raw: dict, *, stored: bool = False) -> "ProviderUsage":
        if not isinstance(raw, dict):
            raise ValueError("Invalid token usage")
        fields = cls.__dataclass_fields__
        if stored and set(raw) != set(fields):
            raise ValueError("Invalid stored usage fields")
        values = {name: raw.get(name) for name in fields}
        for name, value in values.items():
            if value is None and (stored or name not in raw):
                continue
            if type(value) is not int or value < 0:
                raise ValueError("Invalid token usage")
        usage = cls(**values)
        prompt, completion, total, hit, miss = (values[name] for name in fields)
        if prompt is not None and completion is not None and total is not None and prompt + completion != total:
            raise ValueError("Inconsistent total usage")
        if prompt is not None and hit is not None and miss is not None and hit + miss != prompt:
            raise ValueError("Inconsistent cache usage")
        if hit is not None and miss is not None:
            if total is not None and hit + miss > total:
                raise ValueError("Inconsistent cache usage")
            if total is not None and completion is not None and hit + miss + completion != total:
                raise ValueError("Inconsistent total usage")
        for part, whole in ((prompt, total), (completion, total), (hit, prompt), (miss, prompt), (hit, total), (miss, total)):
            if part is not None and whole is not None and part > whole:
                raise ValueError("Inconsistent token usage")
        return usage


PRICING_DATE = "2026-09-09"
PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"


def estimate_cost(usage: ProviderUsage, model: str) -> dict | None:
    counts = (usage.prompt_cache_hit_tokens, usage.prompt_cache_miss_tokens, usage.completion_tokens)
    if model != "deepseek-v4-flash" or any(value is None for value in counts):
        return None
    minimum = sum(Decimal(count) * Decimal(rate) for count, rate in zip(counts, ("0.007", "0.22", "0.66"))) / Decimal(1_000_000)
    return {"min_usd": format(minimum, "f"), "max_usd": format(minimum * 2, "f"),
            "currency": "USD", "pricing_date": PRICING_DATE, "source": PRICING_SOURCE}


def decode_metrics(raw: str, turn_count: int) -> list[dict]:
    try:
        metrics = json.loads(raw)
        if not isinstance(metrics, list):
            raise ValueError
        previous = 0
        counts = {"turn_index", "request_tokens", "history_tokens", "system_tokens", "prompt_tokens", "answer_tokens"}
        for metric in metrics:
            if not isinstance(metric, dict) or set(metric) != counts | {"provider_usage", "cost"}:
                raise ValueError
            if any(type(metric[name]) is not int or metric[name] < 0 for name in counts):
                raise ValueError
            if not previous < metric["turn_index"] <= turn_count:
                raise ValueError
            previous = metric["turn_index"]
            if metric["prompt_tokens"] < sum(metric[name] for name in ("request_tokens", "history_tokens", "system_tokens")):
                raise ValueError
            usage = ProviderUsage.parse(metric["provider_usage"], stored=True)
            cost = metric["cost"]
            if cost is not None:
                if not isinstance(cost, dict) or set(cost) != {"min_usd", "max_usd", "currency", "pricing_date", "source"}:
                    raise ValueError
                if cost["currency"] != "USD" or cost["source"] != PRICING_SOURCE:
                    raise ValueError
                date.fromisoformat(cost["pricing_date"])
                if any(not isinstance(cost[key], str) for key in ("min_usd", "max_usd")):
                    raise ValueError
                low, high = Decimal(cost["min_usd"]), Decimal(cost["max_usd"])
                if not low.is_finite() or not high.is_finite() or not 0 <= low <= high:
                    raise ValueError
                if any(value is None for value in (usage.prompt_cache_hit_tokens, usage.prompt_cache_miss_tokens, usage.completion_tokens)):
                    raise ValueError
    except (ValueError, TypeError, KeyError, InvalidOperation) as error:
        raise RuntimeError("Stored turn metrics are invalid") from error
    return metrics


class ChatAgent:
    api_url = "https://api.deepseek.com/chat/completions"
    system_prompt = (
        "You are a helpful conversational assistant. Reply in the user's language. "
        "Use a natural, direct tone. Be accurate and say clearly when you are uncertain."
    )

    def __init__(
        self,
        config: AgentConfig | None = None,
        store: ContextStore | None = None,
        conversation_id: str = "default",
    ) -> None:
        self.config = config or AgentConfig()
        self.api_key = load_api_key()
        self.store = store
        self.conversation_id = conversation_id
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.total_tokens = 0
        self.turn_metrics: list[dict] = []
        stored = store.get_chat(conversation_id, conversation_id) if store else None
        if stored:
            self.total_tokens = stored["total_tokens"]
            self.messages.extend(stored["messages"])
            self.turn_metrics = stored["turn_metrics"]

    def ask(self, user_request: str) -> str:
        if not isinstance(user_request, str) or not user_request.strip():
            raise ValueError("User request must not be empty")

        user_message = {"role": "user", "content": user_request.strip()}
        estimate = estimate_context(self.messages, user_request, self.config)
        if estimate["overflow"]:
            raise ContextLimitError(estimate)
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": [*self.messages, user_message],
                "thinking": {"type": "disabled"},
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "max_tokens": self.config.max_tokens,
            }
        ).encode()
        request = Request(
            self.api_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"DeepSeek API returned HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError("DeepSeek API network error") from error
        except (json.JSONDecodeError, UnicodeError) as error:
            raise RuntimeError("DeepSeek API returned an invalid response") from error

        try:
            answer = result["choices"][0]["message"]["content"]
            usage = ProviderUsage.parse(result.get("usage", {}))
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Missing answer")
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise RuntimeError("DeepSeek API returned an invalid response") from error
        answer = answer.strip()
        messages = [*self.messages, user_message, {"role": "assistant", "content": answer}]
        total_tokens = self.total_tokens + (usage.total_tokens or 0)
        metric = {name: estimate[name] for name in ("request_tokens", "history_tokens", "system_tokens", "prompt_tokens")}
        metric.update(turn_index=(len(messages) - 1) // 2, answer_tokens=estimate_text_tokens(answer),
                      provider_usage=asdict(usage), cost=estimate_cost(usage, self.config.model))
        turn_metrics = [*self.turn_metrics, metric]
        if self.store:
            self.store.save_agent(self.conversation_id, messages[1:], total_tokens, turn_metrics)
        self.messages = messages
        self.total_tokens = total_tokens
        self.turn_metrics = turn_metrics
        return answer

    def reset(self) -> None:
        if self.store:
            self.store.delete(self.conversation_id)
        self.messages = self.messages[:1]
        self.total_tokens = 0
        self.turn_metrics = []


def load_api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise RuntimeError("DEEPSEEK_API_KEY was not found in .env")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    agent = ChatAgent(store=ContextStore(DATA_DIR / "context.sqlite3"), conversation_id="cli")
    print("Chat Agent. Type exit to stop.")
    while True:
        message = input("\nYou: ").strip()
        if message.lower() == "exit":
            break
        if message:
            try:
                print(f"\nAgent:\n{agent.ask(message)}")
                print(json.dumps(agent.turn_metrics[-1], ensure_ascii=False))
            except ContextLimitError as error:
                print(f"Context limit: {error.estimate['required_tokens']} / {error.estimate['context_limit']}. Start a new chat.")
            except RuntimeError as error:
                print(f"Request failed: {error}")

    print(
        f"\nSession: {len(agent.messages) - 1} stored messages, "
        f"{agent.total_tokens} API tokens."
    )


if __name__ == "__main__":
    main()
