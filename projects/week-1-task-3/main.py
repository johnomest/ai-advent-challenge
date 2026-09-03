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
    "A conversion = 3%": r"\b3(?:\.0+)?\s*%",
    "B conversion = 4%": r"\b4(?:\.0+)?\s*%",
    "A average order value = $300": r"\b300(?:\.0+)?\b",
    "B average order value = $280": r"\b280(?:\.0+)?\b",
    "A ROAS = 6": r"\b6(?:\.0+)?\s*(?:x|times)?\b",
    "B ROAS = 4.48": r"\b4\.48\s*x?\b",
    "A profit = $36,000": r"\b36000(?:\.0+)?\b",
    "B profit = $24,800": r"\b24800(?:\.0+)?\b",
}
TASK = """An online store ran two advertising campaigns.
Campaign A: 12,000 visitors, 360 orders, $108,000 revenue,
$18,000 ad spend, and $54,000 cost of goods sold.
Campaign B: 8,000 visitors, 320 orders, $89,600 revenue,
$20,000 ad spend, and $44,800 cost of goods sold.

For each campaign, calculate conversion rate, average order value, ROAS,
and profit after advertising and cost of goods sold. Recommend a campaign
when the priority is maximum profit and ROAS, and explain the trade-off."""


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
    normalized = response.lower().replace(",", "").replace("$", "")
    checks = {
        label: re.search(pattern, normalized, re.IGNORECASE) is not None
        for label, pattern in EXPECTED_FACTS.items()
    }
    recommendation = re.search(
        r"(?:recommend|choose|prefer|better|winner|most effective)"
        r"[^.\n]{0,80}campaign\s+a\b|"
        r"campaign\s+a[^.\n]{0,80}"
        r"(?:recommend|choose|prefer|better|winner|most effective)",
        normalized,
        re.IGNORECASE,
    )
    checks["Recommend campaign A"] = recommendation is not None
    return checks


def print_solution(title: str, response: str) -> None:
    print(f"\n{'=' * 12} {title} {'=' * 12}\n{response}")


def main() -> None:
    print(f"TASK\n{TASK}")

    solutions = {}
    solutions["Direct"] = generate("You are a helpful assistant.", TASK)
    print_solution("1. DIRECT ANSWER", solutions["Direct"])

    solutions["Step by step"] = generate(
        "You are a helpful assistant.",
        f"{TASK}\n\nSolve step by step.",
    )
    print_solution("2. STEP BY STEP", solutions["Step by step"])

    generated_prompt = generate(
        "You are a prompt engineer.",
        (
            "Create a precise prompt that will help another language model solve "
            "the task below accurately. Include the complete task, useful verification "
            "instructions, and a clear expected answer format. Do not solve the task. "
            f"Return only the new prompt.\n\n{TASK}"
        ),
    )
    print_solution("3A. MODEL-GENERATED PROMPT", generated_prompt)
    solutions["Generated prompt"] = generate(
        "You are a helpful assistant.", generated_prompt
    )
    print_solution("3B. GENERATED PROMPT ANSWER", solutions["Generated prompt"])

    solutions["Expert panel"] = generate(
        (
            "You are a panel of three independent experts solving the user's task. "
            "DATA ANALYST calculates every requested metric. FINANCE SPECIALIST "
            "independently verifies the formulas and business conclusion. CRITIC "
            "searches for calculation errors and hidden trade-offs. Show each expert's "
            "answer, then produce a CONSENSUS with all metrics and a recommendation."
        ),
        TASK,
    )
    print_solution("4. EXPERT PANEL", solutions["Expert panel"])

    print(f"\n{'=' * 12} COMPARISON {'=' * 12}")
    evaluations = {}
    for name, response in solutions.items():
        checks = evaluate_response(response)
        evaluations[name] = sum(checks.values())
        missing = [label for label, matched in checks.items() if not matched]
        print(f"{name}: accuracy={evaluations[name]}/{len(checks)}, words={len(response.split())}")
        if missing:
            print(f"  Missing or incorrect: {', '.join(missing)}")

    answers_differ = len({response.strip() for response in solutions.values()}) > 1
    best_score = max(evaluations.values())
    best_methods = [name for name, score in evaluations.items() if score == best_score]
    print(f"Answers differ: {'YES' if answers_differ else 'NO'}")
    print(f"Most accurate: {', '.join(best_methods)} ({best_score}/9)")
    print(
        "Known answer: A = 3%, $300, 6.0 ROAS, $36,000 profit; "
        "B = 4%, $280, 4.48 ROAS, $24,800 profit; recommend A for profit and ROAS."
    )


if __name__ == "__main__":
    main()
