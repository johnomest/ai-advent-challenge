import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

@dataclass(frozen=True)
class AgentConfig:
    model: str = "deepseek-v4-flash"
    temperature: float = 0.5
    top_p: float = 1.0
    max_tokens: int = 250
    timeout: int = 60


class PitchAgent:
    api_url = "https://api.deepseek.com/chat/completions"
    system_prompt = (
        "Write concise music pitches in English. Use only facts supplied by the user. "
        "Do not invent names, credits, origins, instruments, or genre details. "
        "Return only the pitch unless the user asks for a revision."
    )

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self.api_key = load_api_key()
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.total_tokens = 0

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
        self.messages.extend(
            [user_message, {"role": "assistant", "content": answer}]
        )
        self.total_tokens += tokens
        return answer


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
    agent = PitchAgent()
    print("Pitch Agent. Enter track data, then request revisions. Type exit to stop.")

    name = input("Name: ").strip()
    description = input("Description: ").strip()
    if not name or not description:
        raise SystemExit("Name and description must not be empty")

    request = (
        "Write a music pitch in exactly three sentences.\n"
        f"Track name: {name}\nDescription: {description}"
    )
    print(f"\nAgent:\n{agent.ask(request)}")

    while True:
        follow_up = input("\nRevision request (or exit): ").strip()
        if follow_up.lower() == "exit":
            break
        if follow_up:
            print(f"\nAgent:\n{agent.ask(follow_up)}")

    print(
        f"\nSession: {len(agent.messages) - 1} stored messages, "
        f"{agent.total_tokens} API tokens."
    )


if __name__ == "__main__":
    main()
