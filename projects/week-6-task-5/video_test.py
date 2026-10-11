"""Real HTTP checks for Day 30; run while main.py is serving on port 8090."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

spec = importlib.util.spec_from_file_location("service30_video", Path(__file__).with_name("main.py"))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    key = service.environment().get("LOCAL_AI_API_TOKEN")
    if not key:
        raise SystemExit("Start Day 30 first; LOCAL_AI_API_TOKEN will be generated in .env.")
    prefix = "api:video-" + uuid4().hex
    opener = build_opener(ProxyHandler({}), service.opt.rag.day27.NoRedirects())
    checks, results = [], []

    def request(path, payload=None, auth=True):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + key
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        started = time.perf_counter()
        try:
            with opener.open(Request("http://127.0.0.1:8090" + path, data, headers), timeout=130) as response:
                status, body = response.status, json.load(response)
        except HTTPError as error:
            status, body = error.code, json.load(error)
        return {"status": status, "body": body, "http_seconds": round(time.perf_counter() - started, 3)}

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        print(f"{'PASS' if condition else 'FAIL'}: {name}", flush=True)

    health = request("/health")
    check("Authenticated health and selected Q4 context 8192", health["status"] == 200
          and health["body"].get("context_tokens") == 8192 and "Q4_K_M-requant" in health["body"].get("model", ""))
    check("No token: HTTP 401", request("/health", auth=False)["status"] == 401)
    check("Input over 1200 characters: HTTP 400", request("/chat", {
        "question": "x" * 1201, "session": prefix})["status"] == 400)
    check("Client cannot override model limits: HTTP 400", request("/chat", {
        "question": "Q", "max_tokens": 99999})["status"] == 400)

    for session, question in [(prefix, "Нужен ли диплом, чтобы устроиться в Framestore?"),
                              (prefix, "Какие соцсети эта студия проверяет?"),
                              (prefix + "-iv", "Нужен ли студии IV отдельный resume или достаточно portfolio?")]:
        result = {"question": question, **request("/chat", {"session": session, "question": question})}
        results.append(result)
        print(f"\n{question}\n{result['body'].get('answer', result['body'])}", flush=True)
        check("Chat request completed", result["status"] == 200)
    check("Follow-up preserves Framestore", "LinkedIn" in results[1]["body"].get("answer", "")
          and "FRAMESTORE" in results[1]["body"].get("answer", "").upper())
    check("Separate IV session", "Студия: IV" in results[2]["body"].get("answer", ""))
    check("Reset via HTTP", request("/reset", {"session": prefix})["status"] == 200)

    barrier = threading.Barrier(3)
    def parallel(number):
        barrier.wait(timeout=5)
        question = ["Как студия IV относится к художественному образованию кандидата?",
                    "Как попасть в поле зрения GIANT ANT?",
                    "Как новичку расти в Framestore: вопросы, наставник и заметки?"][number]
        return {"question": question, **request("/chat", {"session": prefix + f"-parallel-{number}", "question": question})}
    with ThreadPoolExecutor(max_workers=3) as pool:
        concurrent = list(pool.map(parallel, range(3)))
    results.extend(concurrent)
    check("Three simultaneous HTTP requests completed", all(x["status"] == 200 for x in concurrent))
    check("GPU queue used", sum(x["body"].get("queue_seconds", 0) > .1 for x in concurrent) >= 2)
    for result in concurrent:
        print(f"\n{result['question']}\n{result['body'].get('answer', result['body'])}\n"
              f"HTTP {result['http_seconds']} s; queue {result['body'].get('queue_seconds')} s", flush=True)

    rates = [request("/chat", {"session": prefix + "-rate", "question": "Как приготовить борщ?"}) for _ in range(7)]
    check("First six questions admitted", all(x["status"] == 200 for x in rates[:6]))
    check("Seventh question: HTTP 429", rates[-1]["status"] == 429)
    check("Unrelated question declined with empty sources", not rates[0]["body"].get("sources")
          and "Не знаю" in rates[0]["body"].get("answer", ""))
    check("Service remains healthy", request("/health")["status"] == 200)
    report = {"model": health["body"].get("model"), "checks": checks, "answers": results,
              "rate_statuses": [x["status"] for x in rates],
              "quality": "These checks cover transport and expected markers; semantic review remains manual.",
              "telegram": "Demonstrate real messages from your phone separately."}
    service.DATA.mkdir(parents=True, exist_ok=True)
    (service.DATA / "http-video-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# День 30 — HTTP проверка", f"Модель: {report['model']}"]
    lines += [f"- {'PASS' if item['passed'] else 'FAIL'}: {item['name']}" for item in checks]
    for result in results:
        lines += [f"\n## {result['question']}", result["body"].get("answer", str(result["body"])),
                  f"HTTP {result['status']}; {result['http_seconds']} с; очередь {result['body'].get('queue_seconds')} с"]
    lines += ["\nПроверки ключевых слов не доказывают точность всех утверждений.",
              "Telegram и доступ с другого устройства показать отдельно."]
    (service.DATA / "http-video-test.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nChecks passed: {sum(item['passed'] for item in checks)}/{len(checks)}", flush=True)
    if not all(item["passed"] for item in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError):
        raise SystemExit("HTTP test failed: check the Day 30 service on port 8090.") from None
