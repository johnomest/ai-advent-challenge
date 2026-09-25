from __future__ import annotations

import json
import time
from typing import Annotated, Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver import MCPServer
from pydantic import Field


API_URL = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "GOOST-MCP-Orchestrator/1.0 (https://github.com/johnomest/ai-advent-challenge)"

server = MCPServer(
    name="goost-musicbrainz",
    description="Read-only recording search in the public MusicBrainz catalog.",
)


def fetch_json(request: Request, attempts: int = 3) -> dict[str, Any]:
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 503} or attempt == attempts - 1:
                raise
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError("MusicBrainz request failed after retries")


@server.tool(
    name="search_recordings",
    description=(
        "Search MusicBrainz for recordings by artist and title. "
        "Returns canonical IDs, dates, scores, and release names."
    ),
    structured_output=True,
)
def search_recordings(
    artist: Annotated[str, Field(min_length=1, max_length=120, description="Artist name")],
    title: Annotated[str, Field(min_length=1, max_length=200, description="Recording title")],
    limit: Annotated[int, Field(ge=1, le=5, description="Maximum result count")] = 3,
) -> dict[str, Any]:
    query = f'artist:"{artist}" AND recording:"{title}"'
    url = f"{API_URL}?{urlencode({'query': query, 'fmt': 'json', 'limit': limit})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    payload = fetch_json(request)

    recordings = []
    for item in payload.get("recordings", []):
        releases = []
        for release in item.get("releases", []):
            name = release.get("title") if isinstance(release, dict) else None
            if name and name not in releases:
                releases.append(name)
        recordings.append(
            {
                "musicbrainz_id": item.get("id"),
                "title": item.get("title"),
                "first_release_date": item.get("first-release-date") or None,
                "score": item.get("score"),
                "releases": releases[:3],
            }
        )

    return {
        "source": "MusicBrainz",
        "artist": artist,
        "requested_title": title,
        "total_matches": payload.get("count", 0),
        "recordings": recordings,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
