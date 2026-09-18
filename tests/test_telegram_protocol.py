"""tests/test_telegram_protocol.py — §36: Telegram pending message
pinned (bot-level, see test_telegram_bot.py) / wrong user rejected /
duplicate click idempotent / old release callback rejected / superseded
release rejected / blocked release cannot later deploy without new
approval.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_telegram_protocol -v
"""
import unittest

from shiplib.telegram_protocol import ApprovalStore


class TestApprovalStore(unittest.TestCase):
    def setUp(self):
        self.store = ApprovalStore(allowed_approvers={111, 222})

    def test_valid_approval_succeeds(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        result = self.store.decide("demo", approval.nonce, 111, "approved")
        self.assertEqual(result, {"status": "ok", "decision": "approved", "idempotent_repeat": False})

    def test_wrong_user_rejected(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        result = self.store.decide("demo", approval.nonce, 999, "approved")
        self.assertEqual(result["status"], "rejected")

    def test_duplicate_click_is_idempotent_not_a_re_trigger(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        first = self.store.decide("demo", approval.nonce, 111, "approved")
        second = self.store.decide("demo", approval.nonce, 111, "approved")
        self.assertFalse(first["idempotent_repeat"])
        self.assertTrue(second["idempotent_repeat"])
        self.assertEqual(second["decision"], "approved")

    def test_duplicate_click_by_a_different_allowed_user_still_returns_original_decision(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        self.store.decide("demo", approval.nonce, 111, "approved")
        race = self.store.decide("demo", approval.nonce, 222, "blocked")
        # the FIRST decision wins -- a second click (even "blocked" from a
        # different user) never flips an already-decided release
        self.assertTrue(race["idempotent_repeat"])
        self.assertEqual(race["decision"], "approved")

    def test_old_release_callback_rejected_after_new_one_supersedes_it(self):
        first = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        self.store.create_pending("demo", "me/demo", "sha2", "r2")  # supersedes r1, never decided
        result = self.store.decide("demo", first.nonce, 111, "approved")
        self.assertEqual(result["status"], "rejected")

    def test_stale_nonce_for_current_release_rejected(self):
        self.store.create_pending("demo", "me/demo", "sha1", "r1")
        result = self.store.decide("demo", "totally-wrong-nonce", 111, "approved")
        self.assertEqual(result["status"], "rejected")

    def test_unknown_decision_value_rejected(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        result = self.store.decide("demo", approval.nonce, 111, "maybe")
        self.assertEqual(result["status"], "rejected")

    def test_blocked_release_cannot_later_approve_without_a_new_approval(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        self.store.decide("demo", approval.nonce, 111, "blocked")
        # clicking "approved" on the SAME (already blocked) release must
        # NOT flip it -- it's idempotent to the recorded "blocked" decision
        retry = self.store.decide("demo", approval.nonce, 111, "approved")
        self.assertEqual(retry["decision"], "blocked")
        self.assertTrue(retry["idempotent_repeat"])

        # a genuinely NEW release (new nonce/release_id) can still be approved
        new_approval = self.store.create_pending("demo", "me/demo", "sha1-fixed", "r2")
        fresh = self.store.decide("demo", new_approval.nonce, 111, "approved")
        self.assertEqual(fresh, {"status": "ok", "decision": "approved", "idempotent_repeat": False})

    def test_decide_on_project_with_no_pending_approval_rejected(self):
        result = self.store.decide("never-created", "any-nonce", 111, "approved")
        self.assertEqual(result["status"], "rejected")

    def test_is_superseded(self):
        approval = self.store.create_pending("demo", "me/demo", "sha1", "r1")
        self.assertFalse(self.store.is_superseded("demo", "r1"))
        self.store.create_pending("demo", "me/demo", "sha2", "r2")
        self.assertTrue(self.store.is_superseded("demo", "r1"))


if __name__ == "__main__":
    unittest.main()
