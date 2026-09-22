import os
import sys
from pathlib import Path

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


MCP_URL = "https://mcp.airtable.com/mcp"
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


def read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{name}="
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'") or None
    return None


def load_airtable_pat() -> str:
    token = os.getenv("AIRTABLE_PAT") or read_env_value(ROOT_ENV, "AIRTABLE_PAT")
    if not token:
        raise RuntimeError("AIRTABLE_PAT was not found in the environment or root .env")
    if not token.startswith("pat"):
        raise RuntimeError("AIRTABLE_PAT does not look like an Airtable personal access token")
    return token


async def fetch_tools() -> None:
    token = load_airtable_pat()
    timeout = httpx2.Timeout(30.0, read=300.0)
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    ) as http_client:
        transport = streamable_http_client(MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            result = await client.list_tools()
            print(f"Connected: {MCP_URL}")
            print(f"Protocol: {client.protocol_version}")
            print(f"Tools: {len(result.tools)}\n")
            for index, tool in enumerate(result.tools, start=1):
                description = " ".join((tool.description or "No description").split())
                if len(description) > 140:
                    description = description[:137].rstrip() + "..."
                print(f"{index:02}. {tool.name}")
                print(f"    {description}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        anyio.run(fetch_tools)
    except RuntimeError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    except Exception as error:
        raise SystemExit(f"MCP connection failed: {type(error).__name__}: {error}") from error


if __name__ == "__main__":
    main()
