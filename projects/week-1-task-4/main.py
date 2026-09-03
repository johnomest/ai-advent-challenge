import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
TEMPERATURES = (0.0, 0.7, 1.2)
TRACKS = (
    (
        "Mira Vale",
        "Neon Static",
        "мрачный синтвейв с женским шёпотом и напряжённым настроением ночной поездки",
    ),
    (
        "Northbound",
        "Rusted Halo",
        "кинематографичный альтернативный рок с хриплым мужским вокалом и решительным настроением",
    ),
    (
        "Luma, Davi",
        "Mango Rush",
        "яркий бразильский фанк-поп с игривым дуэтным вокалом и настроением летней вечеринки",
    ),
)
SYSTEM_PROMPT = (
    "Напиши краткий музыкальный питч на русском языке ровно из трёх предложений. "
    "Сначала представь трек, исполнителей, жанр и характер. Затем опиши звучание, "
    "ритм, вокал и настроение, используя только переданные сведения. В конце предложи "
    "подходящий контент или плейлисты на основе настроения. Не выдумывай имена, "
    "исполнителей, происхождение, инструменты или жанровые детали. Выведи только питч."
)


def api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise SystemExit("DEEPSEEK_API_KEY was not found in .env")


def build_payload(
    artists: str, title: str, description: str, temperature: float
) -> bytes:
    return json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Исполнители: {artists}\nНазвание: {title}\n"
                        f"Описание: {description}"
                    ),
                },
            ],
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "top_p": 1.0,
            "max_tokens": 200,
        }
    ).encode()


def generate(
    artists: str, title: str, description: str, temperature: float
) -> str:
    request = Request(
        API_URL,
        data=build_payload(artists, title, description, temperature),
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


def main() -> None:
    for artists, title, description in TRACKS:
        print(f"\n{'#' * 12} {artists} - {title} {'#' * 12}")
        print(f"Описание: {description}")
        for temperature in TEMPERATURES:
            pitch = generate(artists, title, description, temperature)
            print(
                f"\n{'=' * 12} ТЕМПЕРАТУРА {temperature:g} {'=' * 12}\n{pitch}"
            )


if __name__ == "__main__":
    main()
