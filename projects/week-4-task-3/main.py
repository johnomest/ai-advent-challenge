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


async def wait_for_new_digest(client: Client, schedule_id: int, previous_run_id: int = 0) -> dict[str, Any]:
    for _ in range(40):
        result = result_data(await client.call_tool("get_latest_digest", {"schedule_id": schedule_id}))
        if result.get("status") == "ready" and result.get("run_id", 0) > previous_run_id:
            return result
        await anyio.sleep(0.5)
    raise RuntimeError("Timed out while waiting for the scheduled digest")


async def run_demo(artist: str, interval_seconds: int) -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    async with Client(params) as client:
        tools = await client.list_tools()
        print(f"MCP connected: {client.protocol_version}")
        print(f"Available tools: {', '.join(tool.name for tool in tools.tools)}")

        scheduled = result_data(
            await client.call_tool(
                "schedule_artist_digest",
                {"artist": artist, "interval_seconds": interval_seconds},
            )
        )
        schedule_id = scheduled["schedule_id"]
        print(f"Scheduled: #{schedule_id}, artist={artist}, every {interval_seconds}s")

        try:
            first = await wait_for_new_digest(client, schedule_id)
            print(f"Run #{first['run_id']}: {first['summary']}")

            second = await wait_for_new_digest(client, schedule_id, first["run_id"])
            print(f"Run #{second['run_id']}: {second['summary']}")
            print("Two automatic executions completed and were read from SQLite.")
        finally:
            cancelled = result_data(
                await client.call_tool("cancel_schedule", {"schedule_id": schedule_id})
            )
            print(f"Schedule cancelled: {cancelled['cancelled']}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="MCP background scheduler demo")
    parser.add_argument("--artist", default="Daft Punk")
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    try:
        anyio.run(run_demo, args.artist, args.interval)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
