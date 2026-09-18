#!/usr/bin/env python3
"""platform/ship/scripts/get_telegram_user_id.py — finds YOUR numeric
Telegram user id (not the chat id, not the bot token) by reading the
bot's recent updates. Needed for SHIP_ALLOWED_APPROVER_IDS in
/etc/ship/telegram.env -- the approval daemon allow-lists exactly this
id as who may tap 🚀/⛔ on a release.

BEFORE running this: send /start (or any message) to the Ship bot in
Telegram at least once, so it has a message from you to read back.

Run on your own machine (Claude's sandbox cannot reach api.telegram.org):
    cd platform/ship
    PYTHONPATH=. .venv/bin/python scripts/get_telegram_user_id.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WALLET = Path.home() / "claude" / ".env"


def _load_env_value(key: str) -> str | None:
    if not WALLET.exists():
        return None
    for line in WALLET.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    token = os.environ.get("SHIP_CLAUDE_DEPLOY_BOT") or _load_env_value("SHIP_CLAUDE_DEPLOY_BOT")
    if not token:
        print("ISSUE: SHIP_CLAUDE_DEPLOY_BOT not found in environment or ~/claude/.env")
        return 1

    from telegram.approval_bot.client import TelegramClient
    client = TelegramClient(token)

    try:
        # Explicitly ask for "message" -- an earlier bug in this script
        # made one real call with allowed_updates=["callback_query"],
        # which Telegram appears to "stick" server-side across later
        # calls that don't pass the parameter at all. Passing a wider
        # list here forces it back open.
        updates = client.get_updates(offset=0, timeout=0, allowed_updates=["message", "callback_query"])
    except Exception as e:
        safe = str(e).replace(token, "***REDACTED***")
        print(f"ISSUE: could not reach api.telegram.org: {safe}")
        return 1

    if not updates.get("ok"):
        print(f"ISSUE: getUpdates failed: {updates}")
        return 1

    seen = {}
    for update in updates.get("result", []):
        msg = update.get("message") or update.get("callback_query")
        if msg and "from" in msg:
            user = msg["from"]
            seen[user["id"]] = user

    if not seen:
        print("No messages found yet. Send /start (or anything) to the bot in Telegram, then run this again.")
        return 1

    print("Telegram users seen in this bot's recent updates:")
    for user_id, user in seen.items():
        name = user.get("username") or user.get("first_name", "?")
        print(f"  id={user_id}  ({name})")
    print("\nUse the id that's YOU as SHIP_ALLOWED_APPROVER_IDS in /etc/ship/telegram.env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
