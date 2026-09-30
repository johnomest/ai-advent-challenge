import argparse
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_MODEL = "embeddinggemma"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_SOURCE = Path(__file__).resolve().parents[3] / "goost-tools" / "documentation"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    title: str
    section: str
    strategy: str
    text: str


def markdown_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"Documentation directory does not exist: {root}")
    return sorted(path for path in root.rglob("*.md") if not path.name.startswith("."))


def document_title(path: Path, text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else path.stem.replace("-", " ").title()


def word_windows(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than size.")
    words = text.split()
    step = size - overlap
    return [" ".join(words[start : start + size]) for start in range(0, len(words), step)]


def fixed_chunks(root: Path, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8").strip()
        title = document_title(path, text)
        source = path.relative_to(root).as_posix()
        for part in word_windows(text, size, overlap):
            chunks.append(
                Chunk(
                    chunk_id=f"fixed-{len(chunks) + 1:05d}",
                    source=source,
                    title=title,
                    section=title,
                    strategy="fixed",
                    text=part,
                )
            )
    return chunks


def markdown_sections(text: str, fallback: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = fallback
    body: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            content = "\n".join(body).strip()
            if content:
                sections.append((heading, content))
            heading = match.group(1).strip()
            body = []
        else:
            body.append(line)
    content = "\n".join(body).strip()
    if content:
        sections.append((heading, content))
    return sections


def structured_chunks(root: Path, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8").strip()
        title = document_title(path, text)
        source = path.relative_to(root).as_posix()
        for section, body in markdown_sections(text, title):
            parts = word_windows(body, size, overlap) if len(body.split()) > size else [body]
            for part in parts:
                chunks.append(
                    Chunk(
                        chunk_id=f"structure-{len(chunks) + 1:05d}",
                        source=source,
                        title=title,
                        section=section,
                        strategy="structure",
                        text=part,
                    )
                )
    return chunks


def embed_batch(texts: list[str], model: str, base_url: str) -> list[list[float]]:
    payload = json.dumps(
        {"model": model, "input": texts, "truncate": False}, ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Ollama is unavailable at {base_url}. Start Ollama and pull {model}."
        ) from error
    embeddings = result.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError("Ollama returned an invalid embeddings response.")
    return embeddings


def build_index(
    chunks: list[Chunk], model: str, base_url: str, batch_size: int = 16
) -> dict[str, object]:
    records = []
    dimensions: int | None = None
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embed_batch([chunk.text for chunk in batch], model, base_url)
        for chunk, vector in zip(batch, vectors, strict=True):
            if not vector or not all(isinstance(value, (int, float)) for value in vector):
                raise RuntimeError("Ollama returned an invalid vector.")
            dimensions = dimensions or len(vector)
            if len(vector) != dimensions:
                raise RuntimeError("Embedding dimensions are inconsistent.")
            records.append({**asdict(chunk), "embedding": vector})
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": model,
        "dimensions": dimensions or 0,
        "strategy": chunks[0].strategy if chunks else "unknown",
        "chunks": records,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def print_comparison(name: str, chunks: list[Chunk]) -> None:
    average = round(sum(len(chunk.text.split()) for chunk in chunks) / max(len(chunks), 1))
    sources = len({chunk.source for chunk in chunks})
    print(f"{name:10} chunks={len(chunks):4} sources={sources:3} avg_words={average:3}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build two local RAG indexes.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--model", default=os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_MODEL))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--chunk-words", type=int, default=180)
    parser.add_argument("--overlap-words", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fixed = fixed_chunks(args.source, args.chunk_words, args.overlap_words)
    structured = structured_chunks(args.source, args.chunk_words, args.overlap_words)
    if not fixed or not structured:
        raise SystemExit("No Markdown content found.")

    print(f"Source: {args.source.resolve()}")
    print(f"Model:  {args.model}\n")
    print_comparison("fixed", fixed)
    print_comparison("structure", structured)

    for name, chunks in (("fixed", fixed), ("structure", structured)):
        output = args.output_dir / f"index-{name}.json"
        write_json(output, build_index(chunks, args.model, args.ollama_url))
        print(f"Saved: {output.resolve()}")


if __name__ == "__main__":
    main()
