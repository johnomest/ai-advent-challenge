import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"


def api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
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


print("WITHOUT CONTROLS")
name = input("Name: ").strip()
description = input("Description: ").strip()
if not name or not description:
    raise SystemExit("Name and description must not be empty")

user_prompt = f"Track name: {name}\nDescription: {description}"

uncontrolled = generate(
    "Write an English music pitch for this track.",
    user_prompt,
)
print(f"\nRESPONSE ({len(uncontrolled.split())} words)\n{uncontrolled}")

print("\nWITH CONTROLS")
controlled_name = input("Name: ").strip()
controlled_description = input("Description: ").strip()
controlled_user_prompt = (
    f"Track name: {controlled_name}\nDescription: {controlled_description}"
)
if controlled_user_prompt != user_prompt:
    raise SystemExit("Enter the same name and description for a valid comparison")

controlled = generate(
    (
        "Write an English music pitch using exactly this format: "
        "PITCH: <one paragraph>. Keep the pitch at 45 words or fewer. "
        "Use only the supplied details. End the response with <END>."
    ),
    controlled_user_prompt,
    max_tokens=100,
    stop=["<END>"],
)

print(f"\nRESPONSE ({len(controlled.split())} words)\n{controlled}")
