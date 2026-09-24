from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_PROMPT = (
    "Find up to three MusicBrainz recordings matching Aerodynamic by Daft Punk "
    "and summarize what the catalog returns."
)
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
SERVER_SCRIPT = Path(__file__).with_name("server.py")


def read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{name}="
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'") or None
    return None


def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or read_env_value(ROOT_ENV, "DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY was not found in the environment or root .env")
    return key


def request_deepseek(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": 700,
        }
    ).encode("utf-8")
    request = Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.load(response)["choices"][0]["message"]
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"DeepSeek API returned HTTP {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error


def mcp_tools_to_deepseek(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def tool_result_text(result: Any) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    texts = [item.text for item in result.content if getattr(item, "text", None)]
    return "\n".join(texts)


async def run_agent(prompt: str) -> None:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
    )
    async with Client(server_params) as client:
        listed = await client.list_tools()
        tools = mcp_tools_to_deepseek(listed.tools)
        print(f"MCP connected: {client.protocol_version}")
        print(f"Available tools: {', '.join(tool.name for tool in listed.tools)}")
        print(f"User: {prompt}\n")

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a music research assistant. For every request to find recordings, "
                    "always call the provided MCP tool exactly once. Set limit to the number "
                    "of recordings requested, or 3 when no number is given. "
                    "Never invent catalog metadata and use only the returned rows. "
                    "Answer concisely in the user's language."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        for _ in range(3):
            assistant = await anyio.to_thread.run_sync(request_deepseek, messages, tools)
            messages.append(assistant)
            calls = assistant.get("tool_calls") or []
            if not calls:
                print(f"Assistant: {assistant.get('content', '')}")
                return

            for call in calls:
                function = call["function"]
                arguments = json.loads(function.get("arguments") or "{}")
                print(f"Tool call: {function['name']}({json.dumps(arguments, ensure_ascii=False)})")
                result = await client.call_tool(function["name"], arguments)
                if result.is_error:
                    raise RuntimeError(f"MCP tool failed: {tool_result_text(result)}")
                content = tool_result_text(result)
                parsed = json.loads(content)
                print(f"Tool result: {len(parsed.get('recordings', []))} recordings\n")
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
    parser = argparse.ArgumentParser(description="DeepSeek agent with a local MusicBrainz MCP tool")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Question for the music research agent")
    args = parser.parse_args()
    try:
        anyio.run(run_agent, args.prompt)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
