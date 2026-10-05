"""Run three local-only Ollama prompts of increasing complexity."""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

CASES = [
    {"id": "simple", "question": "Ответь одним словом: какая столица Франции?"},
    {"id": "structured", "question": 'Верни только JSON с ключами artist, release_date, budget_rub. '
     'Без пояснений и Markdown. Данные: артист Astin Ray; дата релиза 2026-10-12; бюджет 108000 рублей.'},
    {"id": "analytical", "question": 'Выбери проекты с максимальной суммарной прибылью при бюджете времени '
     '8 часов. Проекты неделимы, каждый можно выбрать один раз: A — 3 часа, прибыль 90; '
     'B — 5 часов, прибыль 120; C — 4 часа, прибыль 110; D — 2 часа, прибыль 40. '
     'Верни только JSON с ключами projects (массив букв), hours (число), profit (число), '
     'explanation (краткая проверка выбора на русском). Не превышай 8 часов.'},
]


def local_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Only a loopback HTTP Ollama URL is allowed.")
    return url.rstrip("/")


def request(base: str, endpoint: str, payload: dict | None = None) -> dict:
    url = local_url(base) + endpoint
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    try:
        # Ignore environment proxies: local prompts must stay on the local machine.
        with build_opener(ProxyHandler({})).open(req, timeout=300) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Ollama returned HTTP {error.code}.") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Local Ollama is unavailable. Start Ollama and retry.") from None
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Ollama returned an invalid or error response.")
    return result


def check(identifier: str, answer: str) -> bool:
    if identifier == "simple":
        return answer.strip().strip(".! ").casefold() == "париж"
    try:
        data = json.loads(answer)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    if identifier == "structured":
        return data == {"artist": "Astin Ray", "release_date": "2026-10-12", "budget_rub": 108000}
    if identifier == "analytical":
        return (isinstance(data.get("projects"), list) and all(isinstance(item, str) for item in data["projects"])
                and sorted(data["projects"]) == ["A", "B"]
                and data.get("hours") == 8 and data.get("profit") == 210
                and isinstance(data.get("explanation"), str) and bool(data["explanation"].strip()))
    raise ValueError("Unknown check identifier.")


def generate(question: str, args) -> dict:
    started = time.perf_counter()
    result = request(args.url, "/api/chat", {
        "model": args.model, "stream": False, "think": False, "keep_alive": "10m",
        "messages": [{"role": "user", "content": question}],
        "options": {"num_ctx": args.num_ctx, "num_predict": args.max_tokens, "temperature": 0},
    })
    message = result.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not result.get("done") or not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty or incomplete answer.")
    count, duration = result.get("eval_count", 0), result.get("eval_duration", 0)
    return {"answer": content.strip(), "done_reason": result.get("done_reason"),
            "truncated": result.get("done_reason") == "length",
            "wall_seconds": round(time.perf_counter() - started, 3),
            "generated_tokens": count, "tokens_per_second": round(count * 1e9 / duration, 2) if duration else None,
            "load_seconds": round(result.get("load_duration", 0) / 1e9, 3)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma4:12b-it-qat")
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=768)
    parser.add_argument("--question", help="One custom prompt instead of the three control prompts.")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data/results.json")
    args = parser.parse_args()
    local_url(args.url)
    if args.num_ctx < 1 or args.max_tokens < 1 or args.question is not None and not args.question.strip():
        parser.error("Context and token limit must be positive; question must not be empty.")
    models = request(args.url, "/api/tags")["models"]
    installed = next((model for model in models if model["name"] == args.model), None)
    if installed is None:
        parser.error("Model is not installed. Run ollama pull with the exact model tag first.")
    report = {"endpoint": args.url, "ollama": request(args.url, "/api/version"),
              "installed_model": installed, "settings": {"num_ctx": args.num_ctx, "max_tokens": args.max_tokens,
              "temperature": 0, "think": False}, "results": []}
    print(f"LOCAL MODEL: {args.model}\nENDPOINT: {args.url}\nCONTEXT: {args.num_ctx}", flush=True)
    cases = [{"id": "custom", "question": args.question}] if args.question else CASES
    for case in cases:
        print(f"\nQUESTION [{case['id']}]\n{case['question']}", flush=True)
        result = {**case, **generate(case["question"], args)}
        if case["id"] != "custom":
            result["check_passed"] = not result["truncated"] and check(case["id"], result["answer"])
        report["results"].append(result)
        print(f"\nANSWER\n{result['answer']}\nMETRICS: " + json.dumps({key: value for key, value in result.items() if key not in ("id", "question", "answer")}, ensure_ascii=False), flush=True)
        report["running_models"] = request(args.url, "/api/ps")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.output}")
    if not args.question:
        passed = sum(result["check_passed"] for result in report["results"])
        print(f"CHECKS: {passed}/{len(cases)}")
        if passed != len(cases):
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
