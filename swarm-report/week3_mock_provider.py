"""Validation-only mock; isolated database, no outbound API request."""
import io
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects" / f"week-3-task-{sys.argv[1]}"))
import main
from web import ChatServer


def provider(request, **kwargs):
    payload = json.loads(request.data)
    message = payload["messages"][-1]["content"]
    if "ASYNC" in message:
        time.sleep(4)
    content = "MOCK PAYLOAD: " + json.dumps(payload["messages"][1], ensure_ascii=False)
    if "LONG" in message:
        content = "START OF LONG REPLY\n" + "Readable line with a useful explanation.\n" * 150
    if payload.get("response_format"):
        content = json.dumps({"language": "Python", "architecture": "monolith", "budget": 500, "answer": content})
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


main.load_api_key = lambda: "validation-mock"
main.urlopen = provider
with tempfile.TemporaryDirectory(prefix="week3-validation-") as temporary:
    with ChatServer(int(sys.argv[2]), database_path=Path(temporary) / "context.sqlite3") as server:
        print("MOCK READY", flush=True)
        server.serve_forever()
