#!/usr/bin/env python3
"""platform/ship/scripts/smoke_test_telegram.py — the FIRST real,
network-touching test of the Ship Telegram bot: calls `getMe` to confirm
the token is valid, then sends one real "Ship Control test" message to
confirm the chat_id actually receives it.

Reads SHIP_CLAUDE_DEPLOY_BOT (the dedicated Ship bot token) +
TELEGRAM_CHAT_ID_DZIANIS from ~/claude/.env (same wallet convention as
every other project here) -- never hardcode a token in this file.

    cd platform/ship
    PYTHONPATH=. .venv/bin/python scripts/smoke_test_telegram.py
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
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_DZIANIS") or _load_env_value("TELEGRAM_CHAT_ID_DZIANIS")

    if not token:
        print("ISSUE: SHIP_CLAUDE_DEPLOY_BOT not found in environment or ~/claude/.env")
        print("  -> create a dedicated bot via @BotFather, add the line")
        print("     SHIP_CLAUDE_DEPLOY_BOT=<token>  to ~/claude/.env")
        return 1
    if not chat_id:
        print("ISSUE: TELEGRAM_CHAT_ID_DZIANIS not found in environment or ~/claude/.env")
        return 1

    from telegram.approval_bot.client import TelegramClient
    client = TelegramClient(token)

    import requests
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
    except Exception as e:
        # Never let the raw exception (which embeds the token in the URL)
        # reach stdout/logs -- scrub it before printing anything.
        safe = str(e).replace(token, "***REDACTED***")
        print(f"ISSUE: could not reach api.telegram.org: {safe}")
        return 1
    if not me.get("ok"):
        print(f"ISSUE: getMe failed -- token is likely invalid: {me}")
        return 1
    print(f"OK: token is valid, bot is @{me['result']['username']}")

    try:
        sent = client.send_message(chat_id, "🚢 Ship Control -- smoke test message. If you see this, the bot/chat wiring works.")
    except Exception as e:
        safe = str(e).replace(token, "***REDACTED***")
        print(f"ISSUE: send_message failed: {safe}")
        return 1
    print(f"OK: message sent, message_id={sent['result']['message_id']}")
    print("\nNEXT: reply /start to this bot in Telegram if you haven't already "
         "(required once, or it can't message you), then confirm you received this message.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
