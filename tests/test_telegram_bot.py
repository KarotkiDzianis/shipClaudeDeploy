"""tests/test_telegram_bot.py — §36: Telegram pending message pinned /
same message edited on state change (not a new message) / terminal
release unpinned. Uses a FAKE client recording calls -- no network.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_telegram_bot -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "telegram" / "approval_bot"))

from shiplib.telegram_protocol import ApprovalStore

from telegram.approval_bot.bot import ShipTelegramBot  # noqa: E402


class FakeTelegramClient:
    def __init__(self):
        self.calls = []
        self._next_message_id = 1000

    def send_message(self, chat_id, text, reply_markup=None):
        self._next_message_id += 1
        self.calls.append(("send_message", chat_id, text, reply_markup))
        return {"result": {"message_id": self._next_message_id}}

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.calls.append(("edit_message_text", chat_id, message_id, text, reply_markup))
        return {"ok": True}

    def pin_chat_message(self, chat_id, message_id):
        self.calls.append(("pin_chat_message", chat_id, message_id))
        return {"ok": True}

    def unpin_chat_message(self, chat_id, message_id):
        self.calls.append(("unpin_chat_message", chat_id, message_id))
        return {"ok": True}

    def answer_callback_query(self, callback_query_id, text=None):
        self.calls.append(("answer_callback_query", callback_query_id, text))
        return {"ok": True}


class TestShipTelegramBot(unittest.TestCase):
    def setUp(self):
        self.client = FakeTelegramClient()
        self.store = ApprovalStore(allowed_approvers={111})
        self.bot = ShipTelegramBot(self.client, self.store, chat_id=-100)

    def test_announce_sends_one_message_and_pins_it(self):
        result = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", ["fixed x"])
        methods = [c[0] for c in self.client.calls]
        self.assertEqual(methods, ["send_message", "pin_chat_message"])
        self.assertEqual(self.client.calls[1][2], result["message_id"])

    def test_approval_edits_the_same_message_and_unpins_it(self):
        announced = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        self.client.calls.clear()

        result = self.bot.handle_callback("demo", "r1", announced["nonce"], 111, "approved", "cbq1")
        self.assertEqual(result["decision"], "approved")
        methods = [c[0] for c in self.client.calls]
        self.assertEqual(methods, ["edit_message_text", "unpin_chat_message", "answer_callback_query"])
        # edited the SAME message_id that was originally sent, never a new one
        self.assertEqual(self.client.calls[0][2], announced["message_id"])

    def test_rejected_callback_never_edits_or_unpins(self):
        announced = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        self.client.calls.clear()

        result = self.bot.handle_callback("demo", "r1", announced["nonce"], 999, "approved", "cbq1")
        self.assertEqual(result["status"], "rejected")
        methods = [c[0] for c in self.client.calls]
        self.assertEqual(methods, ["answer_callback_query"])  # only acknowledges the tap, nothing else

    def test_duplicate_click_does_not_edit_a_second_time(self):
        announced = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        self.bot.handle_callback("demo", "r1", announced["nonce"], 111, "approved", "cbq1")
        self.client.calls.clear()

        self.bot.handle_callback("demo", "r1", announced["nonce"], 111, "approved", "cbq2")
        methods = [c[0] for c in self.client.calls]
        self.assertEqual(methods, ["answer_callback_query"])  # idempotent repeat: no second edit/unpin

    def test_new_release_gets_its_own_new_message_not_a_reused_one(self):
        first = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        second = self.bot.announce_release_ready("demo", "me/demo", "sha2", "r2", "sha1", "✅ tests", [])
        self.assertNotEqual(first["message_id"], second["message_id"])

    def test_approval_is_persisted_when_release_root_is_configured(self):
        """§24/§36: this is what closes the loop between the Telegram
        protocol (tested in isolation above) and the deploy CLI's own
        is_approved_for() check (see test_deploy_cli.py) -- without this,
        an 'approved' click would never actually be checkable by anything."""
        import tempfile
        from pathlib import Path

        from shiplib.approval_persistence import load_decision

        release_root = Path(tempfile.mkdtemp())
        bot = ShipTelegramBot(self.client, self.store, chat_id=-100, release_root=release_root)
        announced = bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        bot.handle_callback("demo", "r1", announced["nonce"], 111, "approved", "cbq1")

        recorded = load_decision(release_root, "demo")
        self.assertIsNotNone(recorded)
        self.assertEqual(recorded["git_sha"], "sha1")
        self.assertEqual(recorded["decision"], "approved")

    def test_no_persistence_when_release_root_not_configured(self):
        """Existing bot usage (no release_root) must keep working exactly
        as before -- persistence is opt-in, not a silent new requirement."""
        announced = self.bot.announce_release_ready("demo", "me/demo", "sha1", "r1", "72ac110d", "✅ tests", [])
        result = self.bot.handle_callback("demo", "r1", announced["nonce"], 111, "approved", "cbq1")
        self.assertEqual(result["decision"], "approved")  # no crash, no persistence attempted


if __name__ == "__main__":
    unittest.main()
