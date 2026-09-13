"""telegram/approval_bot/bot.py — orchestrates shiplib.telegram_protocol
(state machine) + a TelegramClient (real or fake) to implement the
pinned/edited-not-recreated approval message and dashboard (§18-23 of the
Ship spec). One bot instance, one chat, serves ALL projects -- approval
traffic is deliberately never mixed into a project's own Telegram
chat (§18).
"""
from __future__ import annotations

from shiplib.telegram_protocol import ApprovalStore


def _release_ready_text(project: str, repo: str, git_sha: str, current_sha: str, test_summary: str,
                        change_summary: list) -> str:
    changes = "\n".join(f"• {c}" for c in change_summary) or "(no summary provided)"
    return (
        "🟡 НУЖНО РЕШЕНИЕ ПО РЕЛИЗУ\n\n"
        f"Проект: {project}\n"
        f"Версия: {git_sha[:8]}\n"
        f"Репозиторий: {repo}\n\n"
        f"{test_summary}\n\n"
        f"Изменения:\n{changes}\n\n"
        f"Сейчас PROD: {(current_sha or '(нет)')[:8]}\n"
        f"Новая: {git_sha[:8]}"
    )


def _terminal_text(base_text: str, decision: str, decided_by: int) -> str:
    label = "✅ РАСКАТАНО (одобрено)" if decision == "approved" else "⛔ ЗАБЛОКИРОВАНО"
    return f"{base_text}\n\n---\n{label} пользователем {decided_by}"


class ShipTelegramBot:
    def __init__(self, client, store: ApprovalStore, chat_id, release_root=None):
        self.client = client
        self.store = store
        self.chat_id = chat_id
        self.release_root = release_root  # if set, decisions are persisted for the deploy runner to check (§24)
        self._base_texts: dict[str, str] = {}

    def announce_release_ready(self, project: str, repo: str, git_sha: str, release_id: str,
                               current_sha: str, test_summary: str, change_summary: list) -> dict:
        """§19/§20: sends ONE message, pins it immediately. Creating a new
        pending approval automatically supersedes whatever was pending
        before for this project (see ApprovalStore.create_pending)."""
        approval = self.store.create_pending(project, repo, git_sha, release_id)
        text = _release_ready_text(project, repo, git_sha, current_sha, test_summary, change_summary)
        self._base_texts[project] = text
        buttons = self._buttons(project, release_id, approval.nonce)
        sent = self.client.send_message(self.chat_id, text, reply_markup=buttons)
        message_id = sent["result"]["message_id"]
        self.store.set_message_id(project, message_id)
        self.client.pin_chat_message(self.chat_id, message_id)
        return {"message_id": message_id, "nonce": approval.nonce, "release_id": release_id}

    def handle_callback(self, project: str, release_id: str, nonce: str, telegram_user_id: int,
                        decision: str, callback_query_id: str) -> dict:
        """§20/§24: on a valid, non-repeat decision -- EDIT the same
        message to its terminal state and unpin it. A repeat click
        (idempotent_repeat=True) or a rejection edits nothing (§24:
        duplicate click idempotent, old/superseded button rejected)."""
        result = self.store.decide(project, release_id, nonce, telegram_user_id, decision)
        if result["status"] == "ok" and not result["idempotent_repeat"]:
            approval = self.store.get_pending(project)
            base_text = self._base_texts.get(project, "")
            new_text = _terminal_text(base_text, decision, telegram_user_id)
            self.client.edit_message_text(self.chat_id, approval.message_id, new_text)
            self.client.unpin_chat_message(self.chat_id, approval.message_id)
            if self.release_root is not None:
                from shiplib.approval_persistence import record_decision
                record_decision(self.release_root, project, approval.release_id, approval.git_sha,
                               result["decision"], telegram_user_id, approval.decided_at)
        self.client.answer_callback_query(callback_query_id, text=result.get("reason") or "OK")
        return result

    @staticmethod
    def _buttons(project: str, release_id: str, nonce: str) -> dict:
        def payload(decision):
            return f"ship:{project}:{release_id}:{nonce}:{decision}"
        return {"inline_keyboard": [[
            {"text": "🚀 РАСКАТИТЬ", "callback_data": payload("approved")},
            {"text": "⛔ БЛОКИРОВАТЬ", "callback_data": payload("blocked")},
            {"text": "ℹ️ ИНФО", "callback_data": f"ship:{project}:{release_id}:{nonce}:info"},
        ]]}
