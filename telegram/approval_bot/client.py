"""telegram/approval_bot/client.py — thin wrapper over the Telegram Bot
API HTTP methods this bot needs. Real network calls only; no
protocol/business logic here (see shiplib/telegram_protocol.py for that).
Never imported by anything that runs in tests -- tests use a fake client
implementing the same method signatures (see tests/test_telegram_bot.py).
"""
from __future__ import annotations

import requests


class TelegramClient:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org"):
        self._base = f"{base_url}/bot{token}"

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

    def _post(self, method: str, payload: dict) -> dict:
        clean = {k: v for k, v in payload.items() if v is not None}
        resp = requests.post(f"{self._base}/{method}", json=clean, timeout=10)
        resp.raise_for_status()
        return resp.json()
