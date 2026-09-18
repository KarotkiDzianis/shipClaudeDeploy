"""telegram/approval_bot/client.py — thin wrapper over the Telegram Bot
API HTTP methods this bot needs. Real network calls only; no
protocol/business logic here (see shiplib/telegram_protocol.py for that).
Never imported by anything that runs in tests -- tests use a fake client
implementing the same method signatures (see tests/test_telegram_bot.py).
"""
from __future__ import annotations

import json

import requests


class TelegramClient:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org"):
        self._token = token
        self._base = f"{base_url}/bot{token}"

    def _scrub(self, exc: Exception) -> Exception:
        """The token lives IN the request URL (Telegram's own API shape
        -- there's no way around that), so any raised exception --
        connection errors, HTTPError from a 4xx/5xx, anything -- embeds
        it unless caught here. Confirmed leaking into a systemd journal
        (readable via `journalctl`, no special privilege) via a 400 from
        a malformed sendMessage call before this existed -- never again:
        every real HTTP call in this class goes through this."""
        safe_message = str(exc).replace(self._token, "***REDACTED***")
        try:
            return type(exc)(safe_message)
        except Exception:
            return RuntimeError(safe_message)

    def send_message(self, chat_id, text, reply_markup=None) -> dict:
        return self._post("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None) -> dict:
        return self._post("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                              "text": text, "reply_markup": reply_markup})

    def pin_chat_message(self, chat_id, message_id) -> dict:
        return self._post("pinChatMessage", {"chat_id": chat_id, "message_id": message_id})

    def unpin_chat_message(self, chat_id, message_id) -> dict:
        return self._post("unpinChatMessage", {"chat_id": chat_id, "message_id": message_id})

    def answer_callback_query(self, callback_query_id, text: str = None) -> dict:
        return self._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

    def get_updates(self, offset: int = 0, timeout: int = 10, allowed_updates: list = None) -> dict:
        """Long-poll for new updates. `timeout` is Telegram's own
        long-poll wait (seconds), not just an HTTP client timeout -- the
        request itself blocks server-side until an update arrives or this
        elapses. `allowed_updates` defaults to None (Telegram's own
        default: all update types) -- restricting it to just
        ["callback_query"] would also make Telegram STOP delivering
        plain messages on every later call, including ones from a
        different script/purpose (confirmed: this is what silently broke
        scripts/get_telegram_user_id.py, which needs plain messages, not
        button taps)."""
        clean = {"offset": offset, "timeout": timeout}
        if allowed_updates is not None:
            clean["allowed_updates"] = json.dumps(allowed_updates)
        try:
            resp = requests.get(f"{self._base}/getUpdates", params=clean, timeout=timeout + 10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise self._scrub(e) from None

    def _post(self, method: str, payload: dict) -> dict:
        clean = {k: v for k, v in payload.items() if v is not None}
        try:
            resp = requests.post(f"{self._base}/{method}", json=clean, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise self._scrub(e) from None
