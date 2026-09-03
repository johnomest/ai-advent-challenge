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
EXPECTED_PATH = "A-C-B-D-E-F"
EXPECTED_COST = 13
TASK = """An undirected weighted graph has these edges:
A-B: 4, A-C: 2, B-C: 1, B-D: 5, C-D: 8,
C-E: 10, D-E: 2, D-F: 6, E-F: 3.
Find the shortest path from A to F and its total cost."""


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


def evaluate_response(response: str) -> tuple[bool, bool, bool]:
    normalized = response.upper()
    for separator in ("->", "→", "—", "–", ">"):
        normalized = normalized.replace(separator, "-")
    normalized = re.sub(r"\s+", "", normalized)
    path_correct = EXPECTED_PATH in normalized
    cost_correct = re.search(rf"\b{EXPECTED_COST}\b", response) is not None
    return path_correct, cost_correct, path_correct and cost_correct


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
            "ANALYST derives a solution. ENGINEER verifies it with a suitable algorithm. "
            "CRITIC searches for mistakes and proposes a corrected solution if needed. "
            "Show each expert's answer, then produce a CONSENSUS with the final path "
            "and total cost."
        ),
        TASK,
    )
    print_solution("4. EXPERT PANEL", solutions["Expert panel"])

    print(f"\n{'=' * 12} COMPARISON {'=' * 12}")
    correct_methods = []
    for name, response in solutions.items():
        path_correct, cost_correct, correct = evaluate_response(response)
        if correct:
            correct_methods.append(name)
        print(
            f"{name}: path={'PASS' if path_correct else 'FAIL'}, "
            f"cost={'PASS' if cost_correct else 'FAIL'}, "
            f"words={len(response.split())}"
        )

    answers_differ = len({response.strip() for response in solutions.values()}) > 1
    print(f"Answers differ: {'YES' if answers_differ else 'NO'}")
    if correct_methods:
        print(f"Most accurate: {', '.join(correct_methods)}")
    else:
        print("Most accurate: none matched the known answer")
    print(f"Known answer: {EXPECTED_PATH}, cost {EXPECTED_COST}")


if __name__ == "__main__":
    main()
