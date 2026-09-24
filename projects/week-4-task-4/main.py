from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters


SERVER_SCRIPT = Path(__file__).with_name("server.py")


def result_data(result: Any) -> dict[str, Any]:
    if result.is_error:
        details = "\n".join(item.text for item in result.content if getattr(item, "text", None))
        raise RuntimeError(details or "MCP tool failed")
    if result.structured_content is not None:
        return result.structured_content
    text = "\n".join(item.text for item in result.content if getattr(item, "text", None))
    return json.loads(text)


async def run_pipeline(artist: str, title: str, limit: int) -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    async with Client(params) as client:
        listed = await client.list_tools()
        print(f"MCP connected: {client.protocol_version}")
        print(f"Pipeline tools: {' -> '.join(tool.name for tool in listed.tools)}\n")

        search = result_data(
            await client.call_tool(
                "search_recordings",
                {"artist": artist, "title": title, "limit": limit},
            )
        )
        print(
            f"1. search_recordings -> {len(search['recordings'])} rows "
            f"from {search['total_matches']} matches"
        )

        summary = result_data(
            await client.call_tool(
                "summarize_recordings",
                {
                    "artist": search["artist"],
                    "requested_title": search["requested_title"],
                    "total_matches": search["total_matches"],
                    "recordings": search["recordings"],
                },
            )
        )
        print(f"2. summarize_recordings -> {summary['row_count']} Markdown rows")

        saved = result_data(
            await client.call_tool(
                "save_report",
                {
                    "filename": f"{artist}-{title}",
                    "markdown": summary["markdown"],
                },
            )
        )
        print(f"3. save_report -> {saved['path']} ({saved['bytes']} bytes)")
        print("\nPipeline completed: search -> summarize -> save.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Automatic three-tool MCP pipeline")
    parser.add_argument("--artist", default="Daft Punk")
    parser.add_argument("--title", default="Aerodynamic")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    try:
        anyio.run(run_pipeline, args.artist, args.title, args.limit)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
