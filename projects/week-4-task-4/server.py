from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver import MCPServer
from pydantic import Field


MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "GOOST-MCP-Pipeline/1.0 (https://github.com/johnomest/ai-advent-challenge)"
REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"

server = MCPServer(
    name="goost-music-pipeline",
    description="Searches MusicBrainz, summarizes normalized results, and saves a Markdown report.",
)


def normalize_filename(filename: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", filename.strip()).strip("-").lower()
    if not safe:
        raise ValueError("filename must contain at least one letter or number")
    return f"{safe}.md"


@server.tool(
    name="search_recordings",
    description="Search MusicBrainz by artist and recording title and return normalized rows.",
    structured_output=True,
)
def search_recordings(
    artist: Annotated[str, Field(min_length=1, max_length=120, description="Artist name")],
    title: Annotated[str, Field(min_length=1, max_length=200, description="Recording title")],
    limit: Annotated[int, Field(ge=1, le=10, description="Maximum result count")] = 5,
) -> dict[str, Any]:
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    query = f'artist:"{artist}" AND recording:"{title}"'
    url = f"{MUSICBRAINZ_URL}?{urlencode({'query': query, 'fmt': 'json', 'limit': limit})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    recordings = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "first_release_date": item.get("first-release-date") or None,
            "score": item.get("score"),
        }
        for item in payload.get("recordings", [])
    ]
    return {
        "artist": artist,
        "requested_title": title,
        "total_matches": payload.get("count", 0),
        "recordings": recordings,
    }


@server.tool(
    name="summarize_recordings",
    description="Convert normalized MusicBrainz rows into a compact Markdown report.",
    structured_output=True,
)
def summarize_recordings(
    artist: Annotated[str, Field(description="Artist from the search step")],
    requested_title: Annotated[str, Field(description="Requested title from the search step")],
    total_matches: Annotated[int, Field(ge=0, description="Total match count from MusicBrainz")],
    recordings: Annotated[list[dict[str, Any]], Field(description="Normalized rows from search_recordings")],
) -> dict[str, Any]:
    lines = [
        f"# MusicBrainz report: {artist} — {requested_title}",
        "",
        f"Total catalog matches: {total_matches}",
        "",
        "| Title | First release | Score | MusicBrainz ID |",
        "|---|---:|---:|---|",
    ]
    for item in recordings:
        lines.append(
            "| {title} | {date} | {score} | {recording_id} |".format(
                title=item.get("title") or "Untitled",
                date=item.get("first_release_date") or "Unknown",
                score=item.get("score") if item.get("score") is not None else "Unknown",
                recording_id=item.get("id") or "Unknown",
            )
        )
    if not recordings:
        lines.append("| No results | — | — | — |")

    return {
        "artist": artist,
        "requested_title": requested_title,
        "row_count": len(recordings),
        "markdown": "\n".join(lines) + "\n",
    }


@server.tool(
    name="save_report",
    description="Save Markdown content inside the project's protected reports directory.",
    structured_output=True,
)
def save_report(
    filename: Annotated[
        str,
        Field(min_length=1, max_length=120, description="Safe report name without a directory path"),
    ],
    markdown: Annotated[str, Field(min_length=1, description="Markdown produced by summarize_recordings")],
) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / normalize_filename(filename)
    path.write_text(markdown, encoding="utf-8")
    return {
        "saved": True,
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
