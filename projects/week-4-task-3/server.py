from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver import MCPServer
from pydantic import Field


PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "data" / "scheduler.db"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "GOOST-MCP-Scheduler/1.0 (https://github.com/johnomest/ai-advent-challenge)"

server = MCPServer(
    name="goost-music-scheduler",
    description="Schedules periodic MusicBrainz catalog summaries and stores them in SQLite.",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect_database() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    connection = connect_database()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database() -> None:
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                next_run_at REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS digest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                item_count INTEGER NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id)
            );
            """
        )


def fetch_artist_recordings(artist: str, limit: int = 5) -> list[dict[str, Any]]:
    query = f'artist:"{artist}"'
    url = f"{MUSICBRAINZ_URL}?{urlencode({'query': query, 'fmt': 'json', 'limit': limit})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    return [
        {
            "title": item.get("title"),
            "first_release_date": item.get("first-release-date") or None,
            "score": item.get("score"),
        }
        for item in payload.get("recordings", [])
    ]


def build_digest(artist: str, recordings: list[dict[str, Any]]) -> str:
    if not recordings:
        return f"{artist}: no matching recordings found."
    entries = ", ".join(
        f"{item.get('title') or 'Untitled'} ({item.get('first_release_date') or 'date unknown'})"
        for item in recordings
    )
    return f"{artist}: {len(recordings)} catalog matches. Top results: {entries}."


def process_due_schedules() -> int:
    now = time.time()
    with database() as connection:
        due = connection.execute(
            "SELECT id, artist, interval_seconds FROM schedules "
            "WHERE active = 1 AND next_run_at <= ? ORDER BY id",
            (now,),
        ).fetchall()

    processed = 0
    for schedule in due:
        try:
            recordings = fetch_artist_recordings(schedule["artist"])
            summary = build_digest(schedule["artist"], recordings)
        except Exception as error:
            recordings = []
            summary = f"{schedule['artist']}: collection failed: {type(error).__name__}: {error}"

        with database() as connection:
            connection.execute(
                "INSERT INTO digest_runs "
                "(schedule_id, created_at, item_count, summary, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    schedule["id"],
                    utc_now(),
                    len(recordings),
                    summary,
                    json.dumps(recordings, ensure_ascii=False),
                ),
            )
            connection.execute(
                "UPDATE schedules SET next_run_at = ? WHERE id = ?",
                (time.time() + schedule["interval_seconds"], schedule["id"]),
            )
        processed += 1
    return processed


def scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(0.5):
        process_due_schedules()


@server.tool(
    name="schedule_artist_digest",
    description="Create a recurring MusicBrainz digest job. The background worker runs it automatically.",
    structured_output=True,
)
def schedule_artist_digest(
    artist: Annotated[
        str,
        Field(min_length=1, max_length=120, description="Artist name to monitor"),
    ],
    interval_seconds: Annotated[
        int,
        Field(ge=5, le=86400, description="Run interval in seconds; use 5 for a short demo"),
    ] = 3600,
) -> dict[str, Any]:
    if not 5 <= interval_seconds <= 86400:
        raise ValueError("interval_seconds must be between 5 and 86400")
    init_database()
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO schedules (artist, interval_seconds, next_run_at, active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (artist.strip(), interval_seconds, time.time(), utc_now()),
        )
        schedule_id = cursor.lastrowid
    return {
        "schedule_id": schedule_id,
        "artist": artist.strip(),
        "interval_seconds": interval_seconds,
        "status": "scheduled",
    }


@server.tool(
    name="get_latest_digest",
    description="Return the newest stored result for a scheduled artist digest.",
    structured_output=True,
)
def get_latest_digest(
    schedule_id: Annotated[int, Field(ge=1, description="ID returned by schedule_artist_digest")],
) -> dict[str, Any]:
    init_database()
    with database() as connection:
        row = connection.execute(
            "SELECT id, created_at, item_count, summary, payload_json FROM digest_runs "
            "WHERE schedule_id = ? ORDER BY id DESC LIMIT 1",
            (schedule_id,),
        ).fetchone()
    if row is None:
        return {"schedule_id": schedule_id, "status": "pending"}
    return {
        "schedule_id": schedule_id,
        "status": "ready",
        "run_id": row["id"],
        "created_at": row["created_at"],
        "item_count": row["item_count"],
        "summary": row["summary"],
        "recordings": json.loads(row["payload_json"]),
    }


@server.tool(
    name="cancel_schedule",
    description="Stop future executions of a scheduled digest without deleting stored results.",
    structured_output=True,
)
def cancel_schedule(
    schedule_id: Annotated[int, Field(ge=1, description="Schedule ID to stop")],
) -> dict[str, Any]:
    init_database()
    with database() as connection:
        cursor = connection.execute(
            "UPDATE schedules SET active = 0 WHERE id = ? AND active = 1",
            (schedule_id,),
        )
    return {"schedule_id": schedule_id, "cancelled": cursor.rowcount == 1}


if __name__ == "__main__":
    init_database()
    stop = threading.Event()
    worker = threading.Thread(target=scheduler_loop, args=(stop,), daemon=True)
    worker.start()
    try:
        server.run(transport="stdio")
    finally:
        stop.set()
        worker.join(timeout=2)
