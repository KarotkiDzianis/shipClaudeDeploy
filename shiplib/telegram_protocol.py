"""shiplib/telegram_protocol.py — the approval STATE MACHINE (§18-25 of
the Ship spec), deliberately separated from any real Telegram HTTP call
(see telegram/approval_bot/bot.py for the thin client that actually talks
to api.telegram.org). Testable with zero network access.

Security invariants enforced here (§24):
  - approval payload is bound to (project, repo, git_sha, release_id, nonce)
  - only one PENDING approval per project at a time; a new release
    supersedes the old one BEFORE it's decided
  - an old/superseded release's callback can never approve a newer one
  - only allow-listed Telegram user ids can decide
  - duplicate clicks are idempotent (same result returned, no re-trigger)
  - a blocked release cannot later deploy without a brand new approval
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PendingApproval:
    project: str
    repo: str
    git_sha: str
    release_id: str
    nonce: str
    created_at: str = field(default_factory=_now)
    message_id: int = None
    decided: bool = False
    decision: str = None  # "approved" | "blocked"
    decided_by: int = None
    decided_at: str = None


class ApprovalStore:
    """In-memory store, one pending (or most-recently-decided) approval per
    project. A real deployment would back this with a small JSON/SQLite
    file next to state.json -- kept in-memory here so the state machine
    itself is trivially unit-testable; persistence is a thin wrapper any
    caller can add without touching this logic.
    """

    def __init__(self, allowed_approvers: set):
        self._pending: dict[str, PendingApproval] = {}
        self._allowed_approvers = set(allowed_approvers)

    def create_pending(self, project: str, repo: str, git_sha: str, release_id: str) -> PendingApproval:
        """§20: a NEW release always supersedes whatever was pending for
        this project before, even if that one was never decided --
        creating a new nonce means the old message's buttons can never
        approve anything again (checked in decide()). Nonce is
        deliberately short (token_urlsafe(12), ~16 chars): Telegram
        rejects a button whose callback_data exceeds 64 BYTES total, and
        a full 40-char git_sha release_id no longer needs to be echoed
        back in it (see decide()'s own docstring) -- confirmed failing
        for real (400 Bad Request) with the original token_urlsafe(16)
        PLUS release_id both embedded in the payload."""
        approval = PendingApproval(project=project, repo=repo, git_sha=git_sha, release_id=release_id,
                                   nonce=secrets.token_urlsafe(12))
        self._pending[project] = approval
        return approval

    def get_pending(self, project: str) -> PendingApproval | None:
        return self._pending.get(project)

    def set_message_id(self, project: str, message_id: int) -> None:
        approval = self._pending.get(project)
        if approval is not None:
            approval.message_id = message_id

    def decide(self, project: str, nonce: str, telegram_user_id: int, decision: str) -> dict:
        """Returns {"status": "ok", "decision": ..., "idempotent_repeat": bool}
        or {"status": "rejected", "reason": ...}. Never raises -- every
        rejection is a normal, expected outcome (wrong user, stale button,
        etc), not a bug.

        Takes `nonce` only, not `release_id` -- the nonce is generated
        fresh per release (create_pending) and is already unguessable/
        unique, so it alone is sufficient to bind this decision to the
        exact release that was announced; the release_id/git_sha it
        corresponds to is looked up here server-side, never trusted from
        the callback payload. This also keeps Telegram's inline button
        callback_data under its own 64-byte limit -- a full 40-char
        git_sha no longer needs to round-trip through it (confirmed
        failing for real with it included, see telegram/approval_bot/
        bot.py's own comment)."""
        if decision not in ("approved", "blocked"):
            return {"status": "rejected", "reason": f"unknown decision '{decision}'"}

        if telegram_user_id not in self._allowed_approvers:
            return {"status": "rejected", "reason": "telegram_user_id is not an allowed approver"}

        approval = self._pending.get(project)
        if approval is None:
            return {"status": "rejected", "reason": f"no pending approval for project '{project}'"}

        if approval.nonce != nonce:
            return {"status": "rejected",
                    "reason": "this button belongs to a superseded or unknown release -- refusing "
                             "(§24: old release callback rejected)"}

        if approval.decided:
            # idempotent: same button clicked twice (or two people clicking
            # in a race) returns the ALREADY-recorded decision, never
            # re-triggers a second deploy/rollback attempt.
            return {"status": "ok", "decision": approval.decision, "idempotent_repeat": True}

        approval.decided = True
        approval.decision = decision
        approval.decided_by = telegram_user_id
        approval.decided_at = _now()
        return {"status": "ok", "decision": decision, "idempotent_repeat": False}

    def is_superseded(self, project: str, release_id: str) -> bool:
        """True if `release_id` is no longer the current pending/decided
        release for this project (a later release replaced it)."""
        current = self._pending.get(project)
        return current is None or current.release_id != release_id
