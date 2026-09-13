"""shiplib/approval_persistence.py — persists the Telegram approval
decision so the deploy runner can verify it (§24: a blocked or never-
decided release must never deploy). Deliberately separate from
`telegram_protocol.ApprovalStore` (which stays in-memory/pure for unit
testing) -- this is the thin, JSON-file-backed bridge a real webhook
handler calls after `ApprovalStore.decide()` returns "ok".

One file per project, next to that project's own release state.json --
NOT a history of every decision ever made, only the most recent one
(matching ApprovalStore's own "one pending/decided release per project"
model: an older decision is moot the moment a newer release supersedes it).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _approval_path(release_root, project: str) -> Path:
    return Path(release_root) / project / "approval.json"


def record_decision(release_root, project: str, release_id: str, git_sha: str, decision: str,
                    decided_by: int, decided_at: str) -> None:
    path = _approval_path(release_root, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"release_id": release_id, "git_sha": git_sha, "decision": decision,
              "decided_by": decided_by, "decided_at": decided_at}
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_approval_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_decision(release_root, project: str) -> dict | None:
    path = _approval_path(release_root, project)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def is_approved_for(release_root, project: str, git_sha: str) -> tuple[bool, str]:
    """§24/§36: the ONE check the deploy runner must make before deploying
    anything. Returns (True, "") only if the most recent recorded decision
    is 'approved' AND matches the exact git_sha being deployed -- a
    decision for a different (older or newer) sha, a 'blocked' decision,
    or no decision at all, all refuse with a specific reason."""
    decision = load_decision(release_root, project)
    if decision is None:
        return False, "no approval decision recorded for this project yet"
    if decision["git_sha"] != git_sha:
        return False, (f"the recorded approval is for git_sha '{decision['git_sha']}', "
                       f"not '{git_sha}' -- stale or mismatched approval")
    if decision["decision"] != "approved":
        return False, f"the recorded decision for this release is '{decision['decision']}', not 'approved'"
    return True, ""
