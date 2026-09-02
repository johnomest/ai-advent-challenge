import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
RUNS = 20
PITCH_WORD_LIMIT = 30
EXPECTED_KEYS = {"track", "pitch", "content_uses"}
CONTROLLED_SYSTEM_PROMPT = f"""Return only valid JSON using exactly this structure:
{{
  "track": "<track name exactly as provided>",
  "pitch": "<English music pitch with {PITCH_WORD_LIMIT} words or fewer>",
  "content_uses": ["<use 1>", "<use 2>", "<use 3>"]
}}
Use only supplied details. Include every key and no additional keys.
The pitch must contain no more than {PITCH_WORD_LIMIT} words. Count before answering.
The content_uses array must contain exactly three short strings.
After the closing brace, emit <END> and stop."""


def api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise SystemExit("DEEPSEEK_API_KEY was not found in .env")


def generate(system_prompt: str, user_prompt: str, **controls: object) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "thinking": {"type": "disabled"},
            "temperature": 0.5,
            "top_p": 1.0,
            **controls,
        }
    ).encode()

    request = Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        raise SystemExit(f"DeepSeek API returned HTTP {error.code}") from error
    except URLError as error:
        raise SystemExit(f"Network error: {error.reason}") from error

    return result["choices"][0]["message"]["content"].strip()


def read_prompt(label: str) -> str:
    print(f"\n{label}")
    name = input("Name: ").strip()
    description = input("Description: ").strip()
    if not name or not description:
        raise SystemExit("Name and description must not be empty")
    return f"Track name: {name}\nDescription: {description}"


def validate_controlled_response(text: str) -> tuple[bool, str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False, "invalid JSON"

    if not isinstance(data, dict) or set(data) != EXPECTED_KEYS:
        return False, "wrong keys"
    if not isinstance(data["track"], str) or not data["track"].strip():
        return False, "track must be a non-empty string"
    if not isinstance(data["pitch"], str) or not data["pitch"].strip():
        return False, "pitch must be a non-empty string"
    if len(data["pitch"].split()) > PITCH_WORD_LIMIT:
        return False, f"pitch exceeds {PITCH_WORD_LIMIT} words"
    if not isinstance(data["content_uses"], list) or len(data["content_uses"]) != 3:
        return False, "content_uses must contain three items"
    if not all(isinstance(item, str) and item.strip() for item in data["content_uses"]):
        return False, "content_uses items must be non-empty strings"

    return True, "schema matched"


def run_uncontrolled(user_prompt: str) -> None:
    response = generate("Write an English music pitch for this track.", user_prompt)
    print(f"\nRESPONSE ({len(response.split())} words)\n{response}")


def run_controlled(user_prompt: str) -> bool:
    first_response = ""
    passed = 0

    print(f"\nRUNNING {RUNS} CONTROLLED REQUESTS")
    for number in range(1, RUNS + 1):
        response = generate(
            CONTROLLED_SYSTEM_PROMPT,
            user_prompt,
            response_format={"type": "json_object"},
            max_tokens=200,
            stop=["<END>"],
        )
        first_response = first_response or response
        valid, reason = validate_controlled_response(response)
        passed += valid
        print(f"{number:02d}/{RUNS} {'PASS' if valid else 'FAIL'}: {reason}")

    print(f"\nFIRST CONTROLLED RESPONSE\n{first_response}")
    print(f"\nSCHEMA RESULT: {passed}/{RUNS} responses matched")
    return passed == RUNS


def main() -> None:
    mode = input(
        "Mode [1 = without controls, 2 = with controls, 3 = compare]: "
    ).strip()
    if mode not in {"1", "2", "3"}:
        raise SystemExit("Mode must be 1, 2, or 3")

    uncontrolled_prompt = ""
    if mode in {"1", "3"}:
        uncontrolled_prompt = read_prompt("WITHOUT CONTROLS")
        run_uncontrolled(uncontrolled_prompt)

    if mode in {"2", "3"}:
        controlled_prompt = read_prompt("WITH CONTROLS")
        if mode == "3" and controlled_prompt != uncontrolled_prompt:
            raise SystemExit("Enter the same name and description for a valid comparison")
        if not run_controlled(controlled_prompt):
            raise SystemExit("Not every controlled response matched the schema")


if __name__ == "__main__":
    main()
