import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
MAX_TOKENS = 1200
EXPECTED_FACTS = {
    "Конверсия A = 3%": r"\b3(?:\.0+)?\s*%",
    "Конверсия B = 4%": r"\b4(?:\.0+)?\s*%",
    "Средний чек A = $300": r"\b300(?:\.0+)?\b",
    "Средний чек B = $280": r"\b280(?:\.0+)?\b",
    "ROAS A = 6": r"\b6(?:\.0+)?\s*(?:x|раз)?\b",
    "ROAS B = 4.48": r"\b4\.48\s*x?\b",
    "Прибыль A = $36,000": r"\b36000(?:\.0+)?\b",
    "Прибыль B = $24,800": r"\b24800(?:\.0+)?\b",
}
TASK = """Интернет-магазин провёл две рекламные кампании.
Кампания A: 12 000 посетителей, 360 заказов, выручка $108 000,
расходы на рекламу $18 000, себестоимость товаров $54 000.
Кампания B: 8 000 посетителей, 320 заказов, выручка $89 600,
расходы на рекламу $20 000, себестоимость товаров $44 800.

Для каждой кампании рассчитай конверсию, средний чек, ROAS и прибыль
после вычета расходов на рекламу и себестоимости. Порекомендуй кампанию,
если приоритетом являются максимальная прибыль и ROAS, и объясни компромисс."""


def api_key() -> str:
    if key := os.getenv("DEEPSEEK_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()

    raise SystemExit("DEEPSEEK_API_KEY was not found in .env")


def generate(system_prompt: str, user_prompt: str) -> str:
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
            "max_tokens": MAX_TOKENS,
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


def evaluate_response(response: str) -> dict[str, bool]:
    normalized = response.lower().replace("$", "")
    normalized = re.sub(r"(?<=\d)[\s\u00a0](?=\d)", "", normalized)
    normalized = re.sub(r"(?<=\d),(?=\d{1,2}(?:\D|$))", ".", normalized)
    normalized = normalized.replace(",", "")
    checks = {
        label: re.search(pattern, normalized, re.IGNORECASE) is not None
        for label, pattern in EXPECTED_FACTS.items()
    }
    recommendation = re.search(
        r"(?:рекоменд\w*|выб\w*|предпочт\w*|лучш\w*|выгодн\w*)"
        r"[^.\n]{0,80}кампани\w*\s+a\b|"
        r"кампани\w*\s+a[^.\n]{0,80}"
        r"(?:рекоменд\w*|выб\w*|предпочт\w*|лучш\w*|выгодн\w*)",
        normalized,
        re.IGNORECASE,
    )
    checks["Рекомендована кампания A"] = recommendation is not None
    return checks


def print_solution(title: str, response: str) -> None:
    print(f"\n{'=' * 12} {title} {'=' * 12}\n{response}")


def main() -> None:
    print(f"ЗАДАЧА\n{TASK}")

    solutions = {}
    solutions["Прямой ответ"] = generate(
        "Ты полезный ассистент. Отвечай только на русском языке.", TASK
    )
    print_solution("1. ПРЯМОЙ ОТВЕТ", solutions["Прямой ответ"])

    solutions["Пошаговое решение"] = generate(
        "Ты полезный ассистент. Отвечай только на русском языке.",
        f"{TASK}\n\nРешай пошагово.",
    )
    print_solution("2. ПОШАГОВОЕ РЕШЕНИЕ", solutions["Пошаговое решение"])

    generated_prompt = generate(
        "Ты промпт-инженер. Отвечай только на русском языке.",
        (
            "Составь точный промпт, который поможет другой языковой модели правильно "
            "решить задачу ниже. Включи полное условие, инструкции по проверке и чёткий "
            "формат ответа. Не решай задачу. Верни только новый промпт.\n\n"
            f"{TASK}"
        ),
    )
    print_solution("3A. ПРОМПТ, СОЗДАННЫЙ МОДЕЛЬЮ", generated_prompt)
    solutions["Сгенерированный промпт"] = generate(
        "Ты полезный ассистент. Отвечай только на русском языке.", generated_prompt
    )
    print_solution(
        "3B. ОТВЕТ ПО СОЗДАННОМУ ПРОМПТУ",
        solutions["Сгенерированный промпт"],
    )

    solutions["Группа экспертов"] = generate(
        (
            "Ты группа из трёх независимых экспертов. АНАЛИТИК ДАННЫХ рассчитывает "
            "все метрики. ФИНАНСОВЫЙ СПЕЦИАЛИСТ независимо проверяет формулы и вывод. "
            "КРИТИК ищет ошибки и скрытые компромиссы. Покажи ответ каждого эксперта, "
            "затем сформируй КОНСЕНСУС со всеми метриками и рекомендацией. "
            "Отвечай только на русском языке."
        ),
        TASK,
    )
    print_solution("4. ГРУППА ЭКСПЕРТОВ", solutions["Группа экспертов"])

    print(f"\n{'=' * 12} СРАВНЕНИЕ {'=' * 12}")
    evaluations = {}
    for name, response in solutions.items():
        checks = evaluate_response(response)
        evaluations[name] = sum(checks.values())
        missing = [label for label, matched in checks.items() if not matched]
        print(f"{name}: точность={evaluations[name]}/{len(checks)}, слов={len(response.split())}")
        if missing:
            print(f"  Не найдено или неверно: {', '.join(missing)}")

    answers_differ = len({response.strip() for response in solutions.values()}) > 1
    best_score = max(evaluations.values())
    best_methods = [name for name, score in evaluations.items() if score == best_score]
    print(f"Ответы отличаются: {'ДА' if answers_differ else 'НЕТ'}")
    print(f"Самые точные: {', '.join(best_methods)} ({best_score}/9)")
    print(
        "Эталон: A = 3%, $300, ROAS 6.0, прибыль $36 000; "
        "B = 4%, $280, ROAS 4.48, прибыль $24 800; "
        "по прибыли и ROAS рекомендована кампания A."
    )


if __name__ == "__main__":
    main()
