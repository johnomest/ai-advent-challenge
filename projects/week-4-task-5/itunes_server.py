from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver import MCPServer
from pydantic import Field


API_URL = "https://itunes.apple.com/search"
USER_AGENT = "GOOST-MCP-Orchestrator/1.0"

server = MCPServer(
    name="goost-itunes",
    description="Read-only music search in the iTunes Store catalog.",
)


@server.tool(
    name="search_tracks",
    description=(
        "Search the iTunes Store for music tracks. Returns store IDs, album, genre, "
        "release date, duration, price, and a public store URL."
    ),
    structured_output=True,
)
def search_tracks(
    artist: Annotated[str, Field(min_length=1, max_length=120, description="Artist name")],
    title: Annotated[str, Field(min_length=1, max_length=200, description="Track title")],
    country: Annotated[
        str,
        Field(min_length=2, max_length=2, pattern="^[A-Za-z]{2}$", description="Store country code"),
    ] = "US",
    limit: Annotated[int, Field(ge=1, le=5, description="Maximum result count")] = 3,
) -> dict[str, Any]:
    params = {
        "term": f"{artist} {title}",
        "country": country.upper(),
        "media": "music",
        "entity": "song",
        "limit": limit,
        "explicit": "Yes",
    }
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    tracks = []
    for item in payload.get("results", []):
        tracks.append(
            {
                "track_id": item.get("trackId"),
                "artist": item.get("artistName"),
                "title": item.get("trackName"),
                "album": item.get("collectionName"),
                "release_date": item.get("releaseDate"),
                "duration_ms": item.get("trackTimeMillis"),
                "genre": item.get("primaryGenreName"),
                "price": item.get("trackPrice"),
                "currency": item.get("currency"),
                "store_url": item.get("trackViewUrl"),
            }
        )

    return {
        "source": "iTunes Store",
        "country": country.upper(),
        "artist": artist,
        "requested_title": title,
        "result_count": payload.get("resultCount", 0),
        "tracks": tracks,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
