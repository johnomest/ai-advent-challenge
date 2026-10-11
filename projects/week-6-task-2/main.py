"""Day 27: local Qwen via llama.cpp with bounded in-memory history."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("day26_local", ROOT / "projects/week-6-task-1/main.py")
day26 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(day26)
SYSTEM = "Answer in Russian in a natural, concise tone. Admit uncertainty."


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(base, endpoint, payload=None, timeout=300):
    url = day26.local_url(base) + endpoint
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers={"Content-Type": "application/json"},
                  method="POST" if data is not None else "GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open(req, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Local model server returned HTTP {error.code}.") from None
    except (OSError, ValueError):
        raise RuntimeError("Local model server is unavailable or returned invalid JSON.") from None
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Local model server returned an error response.")
    return result


def ensure_local_model(base, model):
    details = request(base, "/api/show", {"model": model})
    if "cloud" in model.casefold() or details.get("remote_host") or details.get("remote_model"):
        raise ValueError("Cloud-backed Ollama models are not allowed.")


def generate(messages, args):
    started = time.perf_counter()
    timeout = getattr(args, "request_timeout", 300)
    payload = {
        "model": args.model, "messages": messages, "stream": False,
        "max_tokens": args.max_tokens, "temperature": getattr(args, "temperature", 0),
        "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
        "reasoning_budget_tokens": 0,
    }
    for option in ("seed", "cache_prompt"):
        if hasattr(args, option):
            payload[option] = getattr(args, option)
    if hasattr(args, "context_limit"):
        formatted = request(args.url, "/apply-template", {
            "messages": messages, "chat_template_kwargs": payload["chat_template_kwargs"]}, timeout=timeout)
        if not isinstance(formatted.get("prompt"), str):
            raise RuntimeError("Server returned an invalid chat template.")
        tokens = request(args.url, "/tokenize", {"content": formatted["prompt"],
                                                 "add_special": True, "parse_special": True}, timeout=timeout).get("tokens")
        if not isinstance(tokens, list):
            raise RuntimeError("Server returned invalid tokenization.")
        if len(tokens) + args.max_tokens > args.context_limit:
            raise ValueError("Context limit exceeded. Reset history or shorten the question.")
    result = request(args.url, "/v1/chat/completions", payload, timeout=timeout)
    choices = result.get("choices")
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    if not isinstance(choice, dict):
        raise RuntimeError("Local model server returned invalid choices.")
    if choice.get("finish_reason") == "length":
        raise RuntimeError("Answer truncated. Increase --max-tokens; history unchanged.")
    message = choice.get("message")
    answer = message.get("content") if isinstance(message, dict) else None
    if choice.get("finish_reason") != "stop" or not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Local model server returned an empty or incomplete answer.")
    usage = result.get("usage")
    return {"answer": answer.strip(), "seconds": round(time.perf_counter() - started, 3),
            "tokens": usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0,
            "prompt_tokens": usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0,
            "timings": result.get("timings") if isinstance(result.get("timings"), dict) else {}}


def turn(question, history, args, system=SYSTEM):
    if not question.strip() or len(question) > 4000:
        raise ValueError("Question must contain 1-4000 characters.")
    messages = [{"role": "system", "content": system}, *history[-10:],
                {"role": "user", "content": question}]
    result = generate(messages, args)
    history.extend([{"role": "user", "content": question},
                    {"role": "assistant", "content": result["answer"][:2000]}])
    del history[:-10]
    return result


def chat_loop(answer):
    history = []
    print("Commands: /reset, /exit. History: last 5 turns, current process only.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if question == "/exit":
            return
        if question == "/reset":
            history.clear()
            print("History cleared.")
            continue
        if not question:
            continue
        try:
            result = answer(question, history)
            print(f"\nGOOST: {result['answer']}\nTime: {result['seconds']} s | Tokens: {result['tokens']}")
        except (RuntimeError, ValueError) as error:
            print(f"Error: {error}")


def arguments(description=__doc__):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--model", default="Qwen3.5-9B-Q8_0")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--max-tokens", type=int, default=1536)
    parser.add_argument("--question", help="One request instead of interactive chat")
    return parser


def validate(args):
    day26.local_url(args.url)
    if not 1 <= args.max_tokens <= 4096:
        raise ValueError("max-tokens must be between 1 and 4096.")
    models = request(args.url, "/v1/models").get("data")
    if not isinstance(models, list) or not any(
        isinstance(model, dict) and model.get("id") == args.model for model in models
    ):
        raise ValueError("Requested model is not loaded in the local llama.cpp server.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = arguments().parse_args()
    validate(args)
    print(f"LOCAL ONLY | {args.model} | {args.url}")
    if args.question is not None:
        print(json.dumps(turn(args.question, [], args), ensure_ascii=False, indent=2))
    else:
        chat_loop(lambda question, history: turn(question, history, args))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
