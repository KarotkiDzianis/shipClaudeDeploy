"""tests/test_telegram_client.py — the real HTTP client (unlike
everywhere else in this test suite, which uses a fake). Confirms the
callback_data length that broke a real deploy stays fixed, and that the
bot token can never leak through an exception message -- it did, for
real, into a systemd journal (a 400 from a too-long callback_data,
before either fix existed).

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_telegram_client -v
"""
import unittest
from unittest import mock

from telegram.approval_bot.bot import ShipTelegramBot
from telegram.approval_bot.client import TelegramClient
from shiplib.telegram_protocol import ApprovalStore


class TestCallbackDataFitsTelegramsLimit(unittest.TestCase):
    def test_buttons_stay_under_64_bytes_for_a_realistic_project_slug(self):
        """Confirmed failing for real: the original format embedded a
        full 40-char git_sha release_id alongside the nonce, well past
        Telegram's 64-byte callback_data limit, and Telegram rejected
        the whole sendMessage call (400) -- no message ever arrived."""
        store = ApprovalStore(allowed_approvers={111})
        approval = store.create_pending("stroytender-by", "me/stroytender-by", "a" * 40, "a" * 40)
        buttons = ShipTelegramBot._buttons("stroytender-by", approval.nonce)
        for row in buttons["inline_keyboard"]:
            for button in row:
                self.assertLessEqual(len(button["callback_data"].encode()), 64,
                                     f"callback_data too long: {button['callback_data']!r}")


class TestTokenNeverLeaksThroughAnException(unittest.TestCase):
    def test_a_failed_post_never_reveals_the_token_in_its_exception(self):
        token = "123456:AAsupersecrettoken"
        client = TelegramClient(token)
        with mock.patch("requests.post", side_effect=Exception(f"boom at {client._base}/sendMessage")):
            with self.assertRaises(Exception) as ctx:
                client.send_message(-100, "hi")
        self.assertNotIn(token, str(ctx.exception))
        self.assertIn("REDACTED", str(ctx.exception))

    def test_a_failed_get_updates_never_reveals_the_token_in_its_exception(self):
        token = "123456:AAsupersecrettoken"
        client = TelegramClient(token)
        with mock.patch("requests.get", side_effect=Exception(f"boom at {client._base}/getUpdates")):
            with self.assertRaises(Exception) as ctx:
                client.get_updates()
        self.assertNotIn(token, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
