from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anyio
import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


AIRTABLE_URL = "https://mcp.airtable.com/mcp"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_PROMPT = (
    "Find the GOOST MUSIC base in Airtable and list its table names. "
    "Then research Aerodynamic by Daft Punk in MusicBrainz and the US iTunes Store. "
    "Compare the catalog results and state which facts each source confirms."
)
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
PROJECT_DIR = Path(__file__).resolve().parent
AIRTABLE_TOOLS = {"search_bases", "list_tables_for_base"}


def read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{name}="
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'") or None
    return None


def load_secret(name: str) -> str:
    value = os.getenv(name) or read_env_value(ROOT_ENV, name)
    if not value:
        raise RuntimeError(f"{name} was not found in the environment or root .env")
    return value


def request_deepseek(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "thinking": {"type": "disabled"},
            "temperature": 0.1,
            "max_tokens": 1200,
        }
    ).encode("utf-8")
    request = Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {load_secret('DEEPSEEK_API_KEY')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.load(response)["choices"][0]["message"]
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"DeepSeek API returned HTTP {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error


def tool_result_text(result: Any) -> str:
    if result.is_error:
        details = "\n".join(item.text for item in result.content if getattr(item, "text", None))
        raise RuntimeError(details or "MCP tool failed")
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    return "\n".join(item.text for item in result.content if getattr(item, "text", None))


def compact_tool_result(public_name: str, content: str) -> str:
    if public_name != "airtable_list_tables_for_base":
        return content
    payload = json.loads(content)
    tables = payload.get("tables", [])
    return json.dumps(
        {
            "table_count": len(tables),
            "tables": [
                {"id": table.get("id"), "name": table.get("name")}
                for table in tables
            ],
        },
        ensure_ascii=False,
    )


async def register_server(
    server_name: str,
    client: Client,
    routes: dict[str, tuple[str, Client]],
    schemas: list[dict[str, Any]],
    allowed_tools: set[str] | None = None,
) -> list[str]:
    listed = await client.list_tools()
    names = []
    for tool in listed.tools:
        if allowed_tools is not None and tool.name not in allowed_tools:
            continue
        public_name = f"{server_name}_{tool.name}"
        routes[public_name] = (tool.name, client)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": public_name,
                    "description": f"[{server_name} MCP] {tool.description or ''}",
                    "parameters": tool.input_schema,
                },
            }
        )
        names.append(public_name)
    return names


async def run_agent(prompt: str) -> None:
    routes: dict[str, tuple[str, Client]] = {}
    schemas: list[dict[str, Any]] = []
    timeout = httpx2.Timeout(30.0, read=300.0)

    async with AsyncExitStack() as stack:
        musicbrainz = await stack.enter_async_context(
            Client(
                StdioServerParameters(
                    command=sys.executable,
                    args=[str(PROJECT_DIR / "musicbrainz_server.py")],
                )
            )
        )
        itunes = await stack.enter_async_context(
            Client(
                StdioServerParameters(
                    command=sys.executable,
                    args=[str(PROJECT_DIR / "itunes_server.py")],
                )
            )
        )
        http_client = await stack.enter_async_context(
            httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {load_secret('AIRTABLE_PAT')}"},
                timeout=timeout,
            )
        )
        airtable = await stack.enter_async_context(
            Client(streamable_http_client(AIRTABLE_URL, http_client=http_client))
        )

        registered = {
            "airtable": await register_server(
                "airtable", airtable, routes, schemas, AIRTABLE_TOOLS
            ),
            "musicbrainz": await register_server(
                "musicbrainz", musicbrainz, routes, schemas
            ),
            "itunes": await register_server("itunes", itunes, routes, schemas),
        }
        print("Registered MCP servers:")
        for server_name, tools in registered.items():
            print(f"- {server_name}: {', '.join(tools)}")
        print(f"\nUser: {prompt}\n")

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You orchestrate several independent MCP servers. Choose tools from their "
                    "descriptions and complete the user's entire request. Use Airtable tools only "
                    "for Airtable facts, MusicBrainz only for MusicBrainz catalog facts, and iTunes "
                    "only for iTunes Store facts. Resolve IDs returned by one tool before calling a "
                    "dependent tool. Never invent tool results. Answer concisely in the user's language."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        for round_number in range(1, 9):
            assistant = await anyio.to_thread.run_sync(request_deepseek, messages, schemas)
            messages.append(assistant)
            calls = assistant.get("tool_calls") or []
            if not calls:
                print(f"Assistant:\n{assistant.get('content', '')}")
                return

            for call in calls:
                function = call["function"]
                public_name = function["name"]
                arguments = json.loads(function.get("arguments") or "{}")
                if public_name not in routes:
                    raise RuntimeError(f"Model selected an unknown tool: {public_name}")
                raw_name, client = routes[public_name]
                print(
                    f"Round {round_number}: {public_name}"
                    f"({json.dumps(arguments, ensure_ascii=False)})"
                )
                result = await client.call_tool(raw_name, arguments)
                content = compact_tool_result(public_name, tool_result_text(result))
                print(f"  Result received: {len(content.encode('utf-8'))} bytes")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": content,
                    }
                )

        raise RuntimeError("The agent exceeded the maximum number of tool-call rounds")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DeepSeek orchestrator for three MCP servers")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Task for the MCP orchestrator")
    args = parser.parse_args()
    try:
        anyio.run(run_agent, args.prompt)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
