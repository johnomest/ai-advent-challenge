import json
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DATA_DIR = Path(__file__).resolve().parent / "data"


class ContextStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.database() as database:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute("BEGIN IMMEDIATE")
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
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
                            "INSERT OR IGNORE INTO chats VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (chat_id, row["id"], self.title_from(messages), row["messages"],
                             row["total_tokens"], row["updated_at"], row["updated_at"]),
                        )
                database.execute("PRAGMA user_version=1")

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
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Stored conversation is invalid") from error
        return messages

    @staticmethod
    def title_from(messages: list[dict[str, str]]) -> str:
        return next((" ".join(item["content"].split())[:100] for item in messages
                     if item["role"] == "user"), "Новый чат")

    def dto(self, row: sqlite3.Row, detail: bool = True) -> dict:
        messages = self.decode_messages(row["messages"], row["total_tokens"])
        result = {key: row[key] for key in ("id", "title", "created_at", "updated_at", "total_tokens")}
        result["message_count"] = len(messages)
        if detail:
            result["messages"] = messages
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
                "INSERT INTO chats VALUES (?, ?, ?, '[]', 0, unixepoch(), unixepoch())",
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

    def fail_request(self, owner_id: str, request_id: str) -> None:
        with self.database() as database:
            database.execute("UPDATE requests SET state = 'failed' WHERE owner_id = ? AND request_id = ?",
                             (owner_id, request_id))

    def finish_request(self, owner_id: str, chat_id: str, request_id: str, messages: list[dict[str, str]], total_tokens: int) -> dict:
        with self.database() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute("SELECT * FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            title = self.title_from(messages) if row["title"] == "Новый чат" and row["messages"] == "[]" else row["title"]
            database.execute(
                "UPDATE chats SET messages = ?, total_tokens = ?, title = ?, updated_at = unixepoch() WHERE owner_id = ? AND id = ?",
                (json.dumps(messages, ensure_ascii=False), total_tokens, title, owner_id, chat_id),
            )
            chat = self.dto(database.execute("SELECT * FROM chats WHERE owner_id = ? AND id = ?", (owner_id, chat_id)).fetchone())
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
    ) -> None:
        with self.database() as database:
            database.execute(
                """
                INSERT INTO chats (id, owner_id, title, messages, total_tokens, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, unixepoch(), unixepoch())
                ON CONFLICT(id) DO UPDATE SET
                    messages = excluded.messages,
                    total_tokens = excluded.total_tokens,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, conversation_id, self.title_from(messages), json.dumps(messages, ensure_ascii=False), total_tokens),
            )

    def delete(self, conversation_id: str) -> None:
        with self.database() as database:
            database.execute("DELETE FROM chats WHERE owner_id = ? AND id = ?", (conversation_id, conversation_id))

@dataclass(frozen=True)
class AgentConfig:
    model: str = "deepseek-v4-flash"
    temperature: float = 0.5
    top_p: float = 1.0
    max_tokens: int = 250
    timeout: int = 60


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
        stored = store.load_agent(conversation_id) if store else None
        if stored:
            messages, self.total_tokens = stored
            self.messages.extend(messages)

    def ask(self, user_request: str) -> str:
        if not isinstance(user_request, str) or not user_request.strip():
            raise ValueError("User request must not be empty")

        user_message = {"role": "user", "content": user_request.strip()}
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
            raise RuntimeError(f"Network error: {error.reason}") from error
        except (json.JSONDecodeError, UnicodeError) as error:
            raise RuntimeError("DeepSeek API returned an invalid response") from error

        try:
            answer = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Missing answer")
            if type(tokens) is not int or tokens < 0:
                raise ValueError("Invalid token usage")
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise RuntimeError("DeepSeek API returned an invalid response") from error
        answer = answer.strip()
        messages = [*self.messages, user_message, {"role": "assistant", "content": answer}]
        total_tokens = self.total_tokens + tokens
        if self.store:
            self.store.save_agent(self.conversation_id, messages[1:], total_tokens)
        self.messages = messages
        self.total_tokens = total_tokens
        return answer

    def reset(self) -> None:
        if self.store:
            self.store.delete(self.conversation_id)
        self.messages = self.messages[:1]
        self.total_tokens = 0


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
            print(f"\nAgent:\n{agent.ask(message)}")

    print(
        f"\nSession: {len(agent.messages) - 1} stored messages, "
        f"{agent.total_tokens} API tokens."
    )


if __name__ == "__main__":
    main()
