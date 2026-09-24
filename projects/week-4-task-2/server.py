from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver import MCPServer
from pydantic import Field


MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "GOOST-MCP-Demo/1.0 (https://github.com/johnomest/ai-advent-challenge)"

server = MCPServer(
    name="goost-musicbrainz",
    description="Searches the public MusicBrainz catalog for recording metadata.",
)


def normalize_recordings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for recording in payload.get("recordings", []):
        artists = "".join(
            f"{artist.get('name', '')}{artist.get('joinphrase', '')}"
            for artist in recording.get("artist-credit", [])
            if isinstance(artist, dict)
        ).strip()
        releases = []
        for release in recording.get("releases", []):
            title = release.get("title") if isinstance(release, dict) else None
            if title and title not in releases:
                releases.append(title)

        normalized.append(
            {
                "id": recording.get("id"),
                "title": recording.get("title"),
                "artist": artists or "Unknown artist",
                "first_release_date": recording.get("first-release-date") or None,
                "releases": releases[:3],
                "score": recording.get("score"),
            }
        )
    return normalized


@server.tool(
    name="search_recordings",
    description=(
        "Search the MusicBrainz catalog for recordings by title, artist, or free-text query. "
        "Use this instead of guessing music metadata."
    ),
    structured_output=True,
)
def search_recordings(
    query: Annotated[
        str,
        Field(
            min_length=2,
            max_length=200,
            description="MusicBrainz search query, for example: artist:Daft Punk AND recording:Aerodynamic",
        ),
    ],
    limit: Annotated[
        int,
        Field(ge=1, le=10, description="Maximum number of recordings to return"),
    ] = 5,
) -> dict[str, Any]:
    """Return normalized recording metadata from the public MusicBrainz API."""
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")

    url = f"{MUSICBRAINZ_URL}?{urlencode({'query': query, 'fmt': 'json', 'limit': limit})}"
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    return {
        "query": query,
        "count": payload.get("count", 0),
        "recordings": normalize_recordings(payload),
    }


if __name__ == "__main__":
    server.run(transport="stdio")
