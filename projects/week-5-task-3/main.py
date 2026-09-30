import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


DAY_22_PATH = Path(__file__).resolve().parents[1] / "week-5-task-2" / "main.py"
SPEC = importlib.util.spec_from_file_location("week_5_day_22", DAY_22_PATH)
day22 = importlib.util.module_from_spec(SPEC)
if not SPEC or not SPEC.loader:
    raise RuntimeError("Could not load Day 22 module.")
sys.modules[SPEC.name] = day22
SPEC.loader.exec_module(day22)

STOP_WORDS = {
    "какие", "какой", "какая", "какое", "что", "как", "для", "или", "при",
    "это", "нужно", "можно", "должен", "должна", "должны", "релиза",
}


def rewrite_query(question: str, api_key: str) -> str:
    result = day22.post_json(
        day22.DEEPSEEK_URL,
        {
            "model": day22.DEFAULT_MODEL,
            "thinking": {"type": "disabled"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Перепиши вопрос в короткий поисковый запрос для русскоязычной "
                        "базы знаний. Добавь вероятные технические синонимы, названия полей, "
                        "форматы и единицы измерения. Верни только ключевые слова, без пояснений."
                    ),
                },
                {"role": "user", "content": question},
            ],
            "max_tokens": 80,
        },
        {"Authorization": f"Bearer {api_key}"},
    )
    choices = result.get("choices")
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek returned an empty rewritten query.")
    return content.strip()


def terms(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zа-яё0-9-]+", text.casefold())
        if len(word) >= 3 and word not in STOP_WORDS
    }


def source_authority(source: str) -> float:
    if source.startswith("managers/"):
        return 1.0
    if source.startswith(("domains/", "processes/", "runbooks/")):
        return 0.5
    if source.startswith("legacy/"):
        return 0.0
    return 0.25


def rerank(
    candidates: list[dict[str, object]],
    query: str,
    top_k: int,
    threshold: float,
) -> list[dict[str, object]]:
    query_terms = terms(query)
    rescored = []
    for item in candidates:
        vector_score = float(item["score"])
        if vector_score < threshold:
            continue
        searchable = f"{item.get('title', '')} {item.get('section', '')} {item.get('text', '')}"
        lexical_score = len(query_terms & terms(searchable)) / max(len(query_terms), 1)
        authority = source_authority(str(item.get("source", "")))
        final_score = 0.60 * vector_score + 0.30 * lexical_score + 0.10 * authority
        rescored.append(({**item, "vector_score": vector_score, "score": final_score}))
    rescored.sort(key=lambda item: float(item["score"]), reverse=True)

    selected = []
    seen = set()
    for item in rescored:
        key = (item.get("source"), item.get("section"))
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) == top_k:
            break
    return selected


def merge_candidates(*groups: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for group in groups:
        for item in group:
            key = str(item.get("chunk_id"))
            current = merged.get(key)
            if current is None or float(item["score"]) > float(current["score"]):
                merged[key] = item
    return sorted(merged.values(), key=lambda item: float(item["score"]), reverse=True)


def print_chunks(title: str, chunks: list[dict[str, object]]) -> None:
    print(title)
    for item in chunks:
        vector = item.get("vector_score", item["score"])
        print(
            f"final={float(item['score']):.3f} vector={float(vector):.3f} | "
            f"{item['source']} | {item['section']}"
        )
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare base and improved RAG retrieval.")
    parser.add_argument("--question", default=day22.DEFAULT_QUESTION)
    parser.add_argument("--index", type=Path, default=day22.DEFAULT_INDEX)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument("--ollama-url", default=day22.DEFAULT_OLLAMA_URL)
    parser.add_argument("--evaluate", action="store_true")
    return parser.parse_args()


def evaluate_improved(
    index: dict[str, object], api_key: str, args: argparse.Namespace
) -> tuple[int, int]:
    questions = json.loads(day22.CONTROL_QUESTIONS.read_text(encoding="utf-8"))
    hits = 0
    for number, item in enumerate(questions, start=1):
        rewritten = rewrite_query(item["question"], api_key)
        original_vector = day22.embed_question(
            item["question"], index.get("model", day22.DEFAULT_EMBED_MODEL), args.ollama_url
        )
        rewritten_vector = day22.embed_question(
            rewritten, index.get("model", day22.DEFAULT_EMBED_MODEL), args.ollama_url
        )
        candidates = merge_candidates(
            day22.retrieve(index, original_vector, args.top_n),
            day22.retrieve(index, rewritten_vector, args.top_n),
        )
        found = rerank(
            candidates, f"{item['question']} {rewritten}", args.top_k, args.threshold
        )
        expected_source = item["source"].split("#", 1)[0]
        hit = any(chunk.get("source") == expected_source for chunk in found)
        hits += int(hit)
        print(f"{number:02}. {'HIT ' if hit else 'MISS'} | {item['question']}")
    print(f"\nImproved retrieval hit@{args.top_k}: {hits}/{len(questions)}")
    return hits, len(questions)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    api_key = day22.os.getenv("DEEPSEEK_API_KEY") or day22.read_env_value(
        day22.ROOT_ENV, "DEEPSEEK_API_KEY"
    )
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY was not found.")
    index = day22.load_index(args.index)
    if args.evaluate:
        evaluate_improved(index, api_key, args)
        return

    original_vector = day22.embed_question(
        args.question, index.get("model", day22.DEFAULT_EMBED_MODEL), args.ollama_url
    )
    baseline = day22.retrieve(index, original_vector, args.top_k)

    rewritten = rewrite_query(args.question, api_key)
    rewritten_vector = day22.embed_question(
        rewritten, index.get("model", day22.DEFAULT_EMBED_MODEL), args.ollama_url
    )
    candidates = merge_candidates(
        day22.retrieve(index, original_vector, args.top_n),
        day22.retrieve(index, rewritten_vector, args.top_n),
    )
    improved = rerank(candidates, f"{args.question} {rewritten}", args.top_k, args.threshold)

    print(f"QUESTION\n{args.question}\n")
    print(f"REWRITTEN QUERY\n{rewritten}\n")
    print_chunks("BASE RETRIEVAL", baseline)
    print_chunks("FILTERED AND RERANKED", improved)
    print(f"BASE ANSWER\n{day22.ask_deepseek(args.question, api_key, baseline)}\n")
    print(f"IMPROVED ANSWER\n{day22.ask_deepseek(args.question, api_key, improved)}")


if __name__ == "__main__":
    main()
