"""Compare basic PDF RAG with query rewriting, filtering and heuristic reranking."""

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path


DAY22 = Path(__file__).resolve().parents[1] / "week-5-task-2/main.py"
SPEC = importlib.util.spec_from_file_location("day22_rag", DAY22)
day22 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = day22
SPEC.loader.exec_module(day22)
STOP_WORDS = set("the and for are how what when with from this that their your someone they does have has can should would about studio studios candidate candidates hiring hired work works book advice".split())


def rewrite(question: str, key: str, model: str) -> str:
    return day22.complete(
        "Rewrite the question into a short English search query for How to Get Hired. "
        "Preserve proper names present in the question exactly; do not add new studio names. Preserve the intent, "
        "add a few English synonyms, but do not answer or invent facts. "
        "Do not turn unrelated questions into recruitment questions. Return only the query.",
        question, key, model, 160,
    )


def studio_labels(chunks: list[dict]) -> dict[int, str]:
    first_on_page = {}
    for chunk in chunks:
        first_on_page.setdefault(chunk["page"], chunk["text"])
    labels, current = {}, ""
    for page, text in sorted(first_on_page.items()):
        header = re.match(r"^([A-Z][A-Z &'\-]+)\s+([a-z0-9.-]+\.[a-z]{2,})(?:\s|/)", text)
        if header:
            current = " ".join(header[1].split())
        labels[page] = current
    return labels


def enrich(index: dict) -> dict:
    # ponytail: header inheritance is specific to this book's sequential interviews.
    # For other layouts use explicit section metadata from the extraction stage.
    labels = studio_labels(index["chunks"])
    return {**index, "chunks": [
        {**chunk, "studio": labels[chunk["page"]],
         "section": f"{chunk['section']} | {labels[chunk['page']]}" if labels[chunk["page"]] else chunk["section"]}
        for chunk in index["chunks"]
    ]}


def tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-zа-яё0-9]+", text.casefold()) if len(word) > 2 and word not in STOP_WORDS}


def named_studios(question: str, chunks: list[dict]) -> set[str]:
    return {chunk.get("studio", "") for chunk in chunks if chunk.get("studio") and
            re.search(r"(?<!\w)" + re.escape(chunk["studio"]) + r"(?!\w)", question, re.IGNORECASE)}


def rerank(groups: list[list[dict]], index: dict, question: str, rewritten: str,
           threshold: float, top_k: int) -> tuple[list[dict], dict]:
    merged = {}
    for group in groups:
        for item in group:
            previous = merged.get(item["chunk_id"])
            if previous is None or item["vector_score"] > previous["vector_score"]:
                merged[item["chunk_id"]] = item
    allowed_studios = named_studios(question, index["chunks"])
    query_tokens = tokens(rewritten)
    corpus_tokens = [tokens(item["text"]) for item in index["chunks"]]
    weights = {term: math.log(1 + len(corpus_tokens) / (1 + sum(term in document for document in corpus_tokens)))
               for term in query_tokens}
    total_weight = sum(weights.values()) or 1
    qualified = [item for item in merged.values() if item["vector_score"] >= threshold]
    scoped = [item for item in qualified if not allowed_studios or item.get("studio") in allowed_studios]
    ranked = []
    for item in scoped:
        lexical = sum(weights[term] for term in query_tokens & tokens(item["text"])) / total_weight
        ranked.append({**item, "lexical_score": lexical,
                       "rerank_score": 0.65 * item["vector_score"] + 0.35 * lexical})
    ranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    selected, seen = [], set()
    for item in ranked:
        text = " ".join(item["text"].split())
        if text in seen:
            continue
        seen.add(text)
        selected.append(item)
        if len(selected) == top_k:
            break
    return selected, {
        "merged_candidates": len(merged), "after_threshold": len(qualified),
        "after_studio_filter": len(scoped), "final_chunks": len(selected),
        "studio_filter": sorted(allowed_studios),
    }


def compare(question: str, index: dict, key: str, args) -> dict:
    rewritten = rewrite(question, key, args.model)
    vectors = day22.day21.embed_batch([question, rewritten], index["model"], args.ollama_url)
    baseline = day22.search(index, vectors[0], args.top_k)
    improved, counts = rerank(
        [day22.search(index, vectors[0], args.top_n), day22.search(index, vectors[1], args.top_n)],
        index, question, rewritten, args.threshold, args.top_k,
    )
    return {
        "question": question, "rewritten": rewritten,
        "settings": {"top_n_per_query": args.top_n, "top_k": args.top_k, "threshold": args.threshold},
        "counts": counts, "baseline": day22.compact(baseline), "improved": day22.compact(improved),
    }


def show(result: dict) -> None:
    print(f"\nQUESTION\n{result['question']}\n\nREWRITTEN QUERY\n{result['rewritten']}")
    print("SETTINGS:", result["settings"])
    print("FILTERING:", result["counts"])
    for mode in ("baseline", "improved"):
        print(f"\n{mode.upper()} RETRIEVAL ({len(result[mode])} chunks)")
        for chunk in result[mode]:
            extra = f" rerank={chunk['rerank_score']:.3f} lexical={chunk['lexical_score']:.3f}" if "rerank_score" in chunk else ""
            print(f"vector={chunk['vector_score']:.3f}{extra} | {chunk['section']} | {chunk['chunk_id']}")
            print(" ".join(chunk["text"].split())[:160])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Как студия IV относится к художественному образованию кандидата?")
    parser.add_argument("--index", type=Path, default=day22.DEFAULT_INDEX)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.40)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--with-answers", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data/comparison.json")
    args = parser.parse_args()
    if not 1 <= args.top_k <= args.top_n or not 0 <= args.threshold <= 1:
        parser.error("Require 1 <= top-k <= top-n and 0 <= threshold <= 1.")
    if not args.index.is_file():
        parser.error("Index not found. Build Day 21 or pass --index.")
    index = enrich(json.loads(args.index.read_text(encoding="utf-8")))
    key = day22.api_key()
    print("Query rewriting sends questions to DeepSeek. Embeddings and reranking are local.")
    if args.with_answers:
        print("Selected PDF excerpts are also sent for two answers per question.")
    cases = json.loads(DAY22.with_name("control_questions.json").read_text(encoding="utf-8")) if args.evaluate else [{"question": args.question}]
    report = {"index": str(args.index), "source_sha256": index.get("source_sha256"),
              "model": args.model, "results": []}
    for case in cases:
        result = compare(case["question"], index, key, args)
        show(result)
        if args.evaluate:
            result["expected"] = case
            result["checks"] = {mode: day22.evaluate_retrieval_case(case, result[mode]) for mode in ("baseline", "improved")}
            print("CHECKS:", result["checks"], flush=True)
        if args.with_answers:
            for mode in ("baseline", "improved"):
                result[f"{mode}_answer"] = day22.ask(case["question"], result[mode], key, args.model)
                print(f"\n{mode.upper()} ANSWER\n{result[f'{mode}_answer']}", flush=True)
        report["results"].append(result)
        day22.day21.write_json(args.output, report)
    if args.evaluate:
        report["summary"] = {mode: {
            "questions": len(cases),
            "page_hit": sum(result["checks"][mode]["page_hit"] for result in report["results"]),
            "evidence_hit": sum(result["checks"][mode]["evidence_hit"] for result in report["results"]),
        } for mode in ("baseline", "improved")}
        print("\nSUMMARY\n" + json.dumps(report["summary"], indent=2))
        day22.day21.write_json(args.output, report)
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
