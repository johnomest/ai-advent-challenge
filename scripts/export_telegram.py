"""Export one existing Telegram group without sending or marking messages read."""

import argparse
import asyncio
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def serialize_message(message):
    return {
        "id": message.id,
        "type": "message" if message.action is None else "service",
        "date": message.date.isoformat(),
        "edited": message.edit_date.isoformat() if message.edit_date else None,
        "from_id": str(message.sender_id) if message.sender_id else None,
        "reply_to_message_id": message.reply_to_msg_id,
        "text": message.message or "",
        "has_media": message.media is not None,
        "grouped_id": str(message.grouped_id) if message.grouped_id else None,
    }


def save_export(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def export_chat(chat):
    from telethon import TelegramClient

    api_id = int(os.getenv("TELEGRAM_API_ID") or input("Telegram API ID: ").strip())
    api_hash = os.getenv("TELEGRAM_API_HASH") or getpass("Telegram API hash: ")
    if api_id <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise ValueError("Invalid API credentials.")
    session_dir = ROOT / ".local-archive" / "telegram"
    session_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(
        str(session_dir / "reader"), api_id, api_hash, receive_updates=False
    )
    try:
        await client.start(
            phone=lambda: input("Phone number (international format): ").strip(),
            code_callback=lambda: getpass("Telegram login code: "),
            password=lambda: getpass("Telegram 2FA password: "),
        )
        matches = []
        async for dialog in client.iter_dialogs():
            if (dialog.is_group or dialog.is_channel) and (
                str(dialog.id) == chat or dialog.name == chat
            ):
                matches.append(dialog)
        if len(matches) != 1:
            raise ValueError("Chat not found or name ambiguous. Use an exact title or ID.")
        dialog = matches[0]
        print(f"Selected chat: {dialog.name} ({dialog.id})")
        if input("Export this chat? Type YES: ").strip() != "YES":
            print("Cancelled.")
            return
        messages = []
        async for message in client.iter_messages(dialog.entity, limit=None):
            messages.append(serialize_message(message))
            if len(messages) % 1000 == 0:
                print(f"Read {len(messages)} messages...")
        messages.reverse()
        output = ROOT / "chat" / "telegram" / str(dialog.id) / "result.json"
        save_export(output, {
            "name": dialog.name,
            "type": "telegram_api_export",
            "id": dialog.id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "messages": messages,
        })
        print(f"Saved {len(messages)} messages: {output}")
    finally:
        await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", required=True, help="Exact group title or numeric ID")
    args = parser.parse_args()
    try:
        asyncio.run(export_chat(args.chat))
    except KeyboardInterrupt:
        print("Cancelled. Previous export unchanged.")
        raise SystemExit(130)
    except Exception as error:
        print(f"Export failed ({type(error).__name__}). Previous export unchanged.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
