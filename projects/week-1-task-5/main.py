import json
import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

MAX_TOKENS = 8000
CONFIGURATIONS = (
    {
        "level": "Слабая",
        "provider": "DeepSeek",
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key_name": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "thinking": "disabled",
        "reasoning_effort": None,
    },
    {
        "level": "Средняя",
        "provider": "DeepSeek",
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key_name": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "thinking": "enabled",
        "reasoning_effort": "low",
    },
    {
        "level": "Сильная",
        "provider": "DeepSeek",
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key_name": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-pro",
        "thinking": "enabled",
        "reasoning_effort": "max",
    },
    {
        "level": "Zen слабая",
        "provider": "OpenCode Zen",
        "api_url": "https://opencode.ai/zen/v1/chat/completions",
        "api_key_name": "OPENCODE_API_KEY",
        "model": "nemotron-3.5-lightning-free",
    },
    {
        "level": "Zen средняя",
        "provider": "OpenCode Zen",
        "api_url": "https://opencode.ai/zen/v1/chat/completions",
        "api_key_name": "OPENCODE_API_KEY",
        "model": "mimo-v2.5-free",
    },
    {
        "level": "Zen сильная",
        "provider": "OpenCode Zen",
        "api_url": "https://opencode.ai/zen/v1/chat/completions",
        "api_key_name": "OPENCODE_API_KEY",
        "model": "nemotron-3-ultra-free",
    },
)
PRICES_PER_MILLION = {
    "deepseek-v4-flash": {
        "off_peak": {"cache_hit": 0.007, "cache_miss": 0.22, "output": 0.66},
        "peak": {"cache_hit": 0.014, "cache_miss": 0.44, "output": 1.32},
    },
    "deepseek-v4-pro": {
        "off_peak": {"cache_hit": 0.022, "cache_miss": 0.66, "output": 1.98},
        "peak": {"cache_hit": 0.044, "cache_miss": 1.32, "output": 3.96},
    },
}
SYSTEM_PROMPT = (
    "Ты финансовый аналитик музыкального лейбла. Реши задачу самостоятельно, "
    "проверь арифметику и соблюдай требуемый формат. Не меняй исходные условия."
)
ANALYTICAL_TASK = """Лейбл должен распределить ровно $15,000 рекламного бюджета между каналами A, B и C. Деньги выделяются блоками по $1,000. На каждый канал нужно выделить минимум один блок. Максимумы: A — 8 блоков, B — 7, C — 6.

Предельный прирост новых слушателей от каждого следующего блока:
- A: блоки 1–4 дают по 450 слушателей; блоки 5–8 — по 220.
- B: блоки 1–3 дают по 600 слушателей; блоки 4–7 — по 180.
- C: блоки 1–2 дают по 750 слушателей; блоки 3–6 — по 250.

Каждый новый слушатель приносит $4 ожидаемой валовой маржи до рекламных расходов. Для канала B существует вероятность 20%, что он даст только 50% заявленного результата; в остальных 80% он даст полный результат. Для основного расчёта используй математическое ожидание.

Нужно:
1. Найти распределение блоков, которое максимизирует ожидаемую чистую прибыль при обязательном расходовании всех $15,000.
2. Показать по каждому каналу: число блоков, ожидаемых слушателей, валовую маржу и чистую прибыль.
3. Показать общий итог и отдельно худший сценарий, когда B даёт 50% результата.
4. Кратко объяснить, почему распределение оптимально.

Формат ответа: компактная Markdown-таблица, затем расчёт общего итога и вывод. Не более 350 слов."""


def api_key(name: str) -> str:
    if key := os.getenv(name):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()

    raise SystemExit(f"{name} was not found in .env")


def build_payload(configuration: dict) -> bytes:
    payload = {
        "model": configuration["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ANALYTICAL_TASK},
        ],
        "max_tokens": MAX_TOKENS,
    }
    if configuration.get("thinking"):
        payload["thinking"] = {"type": configuration["thinking"]}
    if configuration.get("reasoning_effort"):
        payload["reasoning_effort"] = configuration["reasoning_effort"]
    return json.dumps(payload).encode()


def is_peak(moment: datetime) -> bool:
    current = moment.astimezone(timezone.utc).time()
    return time(1) <= current < time(4) or time(6) <= current < time(10)


def calculate_cost(model: str, usage: dict, peak: bool) -> float:
    prices = PRICES_PER_MILLION[model]["peak" if peak else "off_peak"]
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get(
        "prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - cache_hit
    )
    output = usage.get("completion_tokens", 0)
    return (
        cache_hit * prices["cache_hit"]
        + cache_miss * prices["cache_miss"]
        + output * prices["output"]
    ) / 1_000_000


def run_configuration(configuration: dict) -> dict:
    requested_at = datetime.now(timezone.utc)
    request = Request(
        configuration["api_url"],
        data=build_payload(configuration),
        headers={
            "Authorization": f"Bearer {api_key(configuration['api_key_name'])}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Advent-Challenge/1.0",
        },
        method="POST",
    )

    started = perf_counter()
    try:
        with urlopen(request, timeout=300) as response:
            result = json.load(response)
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(
            f"{configuration['provider']} API returned HTTP {error.code}: {details}"
        ) from error
    except URLError as error:
        raise SystemExit(f"Network error: {error.reason}") from error

    elapsed = perf_counter() - started
    usage = result.get("usage", {})
    peak = is_peak(requested_at) if configuration["provider"] == "DeepSeek" else False
    details = usage.get("completion_tokens_details") or {}
    message = result["choices"][0]["message"]
    cost = (
        calculate_cost(configuration["model"], usage, peak)
        if configuration["provider"] == "DeepSeek"
        else usage.get("cost", 0)
    )
    return {
        "level": configuration["level"],
        "provider": configuration["provider"],
        "model": configuration["model"],
        "thinking": configuration.get("thinking", "provider default"),
        "reasoning_effort": configuration.get("reasoning_effort") or "provider default",
        "answer": (message.get("content") or "[Финальный ответ не сформирован]").strip(),
        "finish_reason": result["choices"][0].get("finish_reason", "unknown"),
        "elapsed": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
        "cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "reasoning_tokens": details.get("reasoning_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "price_period": (
            "peak"
            if peak
            else "off-peak"
            if configuration["provider"] == "DeepSeek"
            else "free"
        ),
        "cost": cost,
    }


def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 28 + " СРАВНЕНИЕ " + "=" * 28)
    print(
        f"{'Уровень':<10} {'Провайдер':<14} {'Модель':<32} {'Время':>9} "
        f"{'Токены':>8} {'Reasoning':>10} {'Стоимость':>12}"
    )
    for result in results:
        print(
            f"{result['level']:<10} {result['provider']:<14} {result['model']:<32} "
            f"{result['elapsed']:>7.2f} с {result['total_tokens']:>8} "
            f"{result['reasoning_tokens']:>10} ${result['cost']:>10.6f}"
        )
    print("\nРесурсоёмкость оценивается по токенам и стоимости: cloud API не раскрывает GPU/RAM.")


def main() -> None:
    results = []
    print("Один аналитический запрос, конфигурации DeepSeek и модели OpenCode Zen")
    for configuration in CONFIGURATIONS:
        print(
            f"\n{'#' * 16} {configuration['level'].upper()}: "
            f"{configuration['provider']} / {configuration['model']} {'#' * 16}"
        )
        result = run_configuration(configuration)
        results.append(result)
        print(result["answer"])
        print(
            f"\nМетрики: {result['elapsed']:.2f} с; "
            f"input={result['prompt_tokens']} "
            f"(cache hit={result['cache_hit_tokens']}, miss={result['cache_miss_tokens']}); "
            f"output={result['completion_tokens']}; reasoning={result['reasoning_tokens']}; "
            f"total={result['total_tokens']}; {result['price_period']}; "
            f"cost=${result['cost']:.6f}; finish={result['finish_reason']}"
        )
    print_summary(results)


if __name__ == "__main__":
    main()
