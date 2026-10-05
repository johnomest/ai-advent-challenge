"""Build page-aware local PDF indexes using the existing Day 21 pipeline."""

import argparse
import hashlib
import json
import math
import re
import statistics
from dataclasses import replace
from pathlib import Path

import pdfplumber

from main import build_index, fixed_chunks, print_comparison, structured_chunks, write_json


def extract_page(page) -> str:
    words = page.extract_words()
    midpoint = page.width / 2
    left = [word for word in words if word["x1"] < midpoint]
    right = [word for word in words if word["x0"] >= midpoint]
    crossing = [word for word in words if word["x0"] < midpoint < word["x1"]]
    # This book uses two columns. Preserve full-width headings above the body.
    if len(left) > 30 and len(right) > 30:
        if crossing and max(word["bottom"] for word in crossing) > page.height * 0.3:
            return page.extract_text() or ""
        top = max((word["bottom"] + 2 for word in crossing), default=0)
        header = page.crop((0, 0, page.width, top)).extract_text() if top else ""
        columns = [
            page.crop((0, top, midpoint, page.height)).extract_text() or "",
            page.crop((midpoint, top, page.width, page.height)).extract_text() or "",
        ]
        return "\n\n".join(part for part in [header, *columns] if part)
    return page.extract_text() or ""


def validate_index(index: dict) -> None:
    assert index["chunks"], "No chunks were indexed."
    assert len({chunk["chunk_id"] for chunk in index["chunks"]}) == len(index["chunks"])
    for chunk in index["chunks"]:
        assert chunk["text"].strip() and chunk["page"] >= 1
        vector = chunk["embedding"]
        assert len(vector) == index["dimensions"]
        assert all(math.isfinite(value) for value in vector)
        assert any(value != 0 for value in vector)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="embeddinggemma")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text_dir = args.output_dir / "pages"
    text_dir.mkdir(exist_ok=True)
    if list(text_dir.glob("*.md")):
        raise SystemExit("Output already contains extracted pages; choose a new directory.")
    title = args.pdf.stem
    pages = []
    with pdfplumber.open(args.pdf) as pdf:
        total_pages = len(pdf.pages)
        for number, page in enumerate(pdf.pages, 1):
            text = extract_page(page).strip()
            pages.append({"page": number, "words": len(text.split()), "has_text": bool(text)})
            if text:
                (text_dir / f"page-{number:03}.md").write_text(
                    f"# {title} — PDF page {number}\n\n{text}\n", encoding="utf-8"
                )
    report = {
        "source": str(args.pdf.resolve()),
        "sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        "pages": total_pages,
        "text_pages": sum(page["has_text"] for page in pages),
        "words": sum(page["words"] for page in pages),
        "empty_pages": [page["page"] for page in pages if not page["has_text"]],
        "ocr_performed": False,
        "page_details": pages,
        "indexes": {},
    }
    print(json.dumps({key: report[key] for key in ["pages", "text_pages", "words", "empty_pages"]}))
    for strategy, chunker in [("fixed", fixed_chunks), ("structure", structured_chunks)]:
        chunks = chunker(text_dir, 180, 30)
        page_by_id = {}
        mapped = []
        for chunk in chunks:
            number = int(re.search(r"page-(\d+)", chunk.source).group(1))
            page_by_id[chunk.chunk_id] = number
            mapped.append(replace(chunk, source=args.pdf.name, title=title, section=f"PDF page {number}"))
        print_comparison(strategy, mapped)
        index = build_index(mapped, args.model, "http://127.0.0.1:11434")
        index["source_sha256"] = report["sha256"]
        for chunk in index["chunks"]:
            chunk["page"] = page_by_id[chunk["chunk_id"]]
        validate_index(index)
        path = args.output_dir / f"index-{strategy}.json"
        write_json(path, index)
        validate_index(json.loads(path.read_text(encoding="utf-8")))
        sizes = [len(chunk.text.split()) for chunk in mapped]
        report["indexes"][strategy] = {
            "chunks": len(mapped),
            "dimensions": index["dimensions"],
            "min_words": min(sizes),
            "max_words": max(sizes),
            "avg_words": round(statistics.mean(sizes), 1),
            "chunk_words": 180,
            "overlap_words": 30,
            "boundary": "page file",
        }
        print(f"Saved and validated: {path}", flush=True)
    write_json(args.output_dir / "extraction-report.json", report)
    print("COMPARISON")
    print(json.dumps(report["indexes"], indent=2))


if __name__ == "__main__":
    main()
