import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")


def api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.split("=", 1)[1].strip()

    raise SystemExit("DEEPSEEK_API_KEY was not found in .env")


name = input("Name: ").strip()
description = input("Description: ").strip()
if not name or not description:
    raise SystemExit("Name and description must not be empty")

payload = json.dumps(
    {
        "model": "deepseek-v4-flash",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write a concise English music pitch in exactly three sentences. "
                    "First introduce the track, credited artists if provided, genre, and character. "
                    "Then describe its sound, rhythm, vocals, and mood using only supplied details. "
                    "Finally suggest suitable content or playlists based on that mood. "
                    "Do not invent names, credits, origins, instruments, or genre details. "
                    "Output only the pitch."
                ),
            },
            {
                "role": "user",
                "content": f"Track name: {name}\nDescription: {description}",
            },
        ],
        "thinking": {"type": "disabled"},
        "temperature": 0.5,
        "top_p": 1.0,
        "max_tokens": 200,
    }
).encode()

request = Request(
    "https://api.deepseek.com/chat/completions",
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

print(result["choices"][0]["message"]["content"])
