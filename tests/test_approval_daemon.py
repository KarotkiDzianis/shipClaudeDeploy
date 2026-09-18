"""tests/test_approval_daemon.py — the daemon's two pure responsibilities
(process_queue, process_updates), tested against a fake Telegram client
and a real temp filesystem for the queue -- no network, no sleep loop.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_approval_daemon -v
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "telegram" / "approval_bot"))

from shiplib.approval_persistence import load_decision
from shiplib.telegram_protocol import ApprovalStore
from telegram.approval_bot import daemon  # noqa: E402
from telegram.approval_bot.bot import ShipTelegramBot  # noqa: E402


class FakeTelegramClient:
    def __init__(self, updates_to_return=None):
        self.calls = []
        self._next_message_id = 1000
        self._updates_to_return = updates_to_return or []

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

    def get_updates(self, offset=0, timeout=10):
        return {"result": self._updates_to_return}


class TestProcessQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.client = FakeTelegramClient()
        self.store = ApprovalStore(allowed_approvers={111})
        self.bot = ShipTelegramBot(self.client, self.store, chat_id=-100, release_root=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_announces_a_queued_request_and_removes_the_file(self):
        queue_dir = self.tmp / "_telegram_queue"
        queue_dir.mkdir()
        (queue_dir / "demo-sha1.json").write_text(json.dumps({
            "project": "demo", "repo": "me/demo", "git_sha": "sha1", "release_id": "sha1",
            "current_sha": None, "test_summary": "ok", "change_summary": ["x"],
        }))

        daemon.process_queue(self.bot, queue_dir)

        methods = [c[0] for c in self.client.calls]
        self.assertEqual(methods, ["send_message", "pin_chat_message"])
        self.assertEqual(list(queue_dir.glob("*.json")), [])

    def test_a_bad_request_file_is_removed_not_left_to_retry_forever(self):
        queue_dir = self.tmp / "_telegram_queue"
        queue_dir.mkdir()
        (queue_dir / "broken.json").write_text("{not valid json")

        daemon.process_queue(self.bot, queue_dir)  # must not raise

        self.assertEqual(list(queue_dir.glob("*.json")), [])


class TestProcessUpdates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = ApprovalStore(allowed_approvers={111})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_valid_callback_records_the_decision(self):
        client = FakeTelegramClient()
        bot = ShipTelegramBot(client, self.store, chat_id=-100, release_root=self.tmp)
        announced = bot.announce_release_ready("demo", "me/demo", "sha1", "sha1", None, "ok", [])

        client._updates_to_return = [{
            "update_id": 5,
            "callback_query": {
                "id": "cbq1", "from": {"id": 111},
                "data": f"ship:demo:{announced['nonce']}:approved",
            },
        }]
        offset_file = self.tmp / "offset.txt"
        daemon.process_updates(bot, client, offset_file)

        recorded = load_decision(self.tmp, "demo")
        self.assertEqual(recorded["decision"], "approved")
        self.assertEqual(offset_file.read_text(), "6")

    def test_a_non_ship_callback_is_ignored(self):
        client = FakeTelegramClient()
        bot = ShipTelegramBot(client, self.store, chat_id=-100, release_root=self.tmp)
        client._updates_to_return = [{
            "update_id": 1,
            "callback_query": {"id": "cbq1", "from": {"id": 111}, "data": "not-ours:whatever"},
        }]
        offset_file = self.tmp / "offset.txt"
        daemon.process_updates(bot, client, offset_file)  # must not raise
        self.assertEqual(offset_file.read_text(), "2")

    def test_offset_persists_and_resumes_across_calls(self):
        client = FakeTelegramClient()
        bot = ShipTelegramBot(client, self.store, chat_id=-100, release_root=self.tmp)
        offset_file = self.tmp / "offset.txt"
        offset_file.write_text("42")

        captured = {}
        orig_get_updates = client.get_updates
        def spy(offset=0, timeout=10):
            captured["offset"] = offset
            return orig_get_updates(offset=offset, timeout=timeout)
        client.get_updates = spy

        daemon.process_updates(bot, client, offset_file)
        self.assertEqual(captured["offset"], 42)


class TestResolveApproverIds(unittest.TestCase):
    def test_parses_a_single_id(self):
        self.assertEqual(daemon.resolve_approver_ids("12345"), {12345})

    def test_parses_multiple_comma_separated_ids(self):
        self.assertEqual(daemon.resolve_approver_ids("111,222, 333"), {111, 222, 333})


if __name__ == "__main__":
    unittest.main()
