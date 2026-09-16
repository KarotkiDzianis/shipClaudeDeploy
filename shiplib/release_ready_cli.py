"""shiplib/release_ready_cli.py — enqueues a "please announce this
release for approval" request for the Telegram approval daemon
(telegram/approval_bot/daemon.py) to pick up.

Deliberately does NOT talk to Telegram itself: the daemon is the ONE
long-running process that owns the shared ApprovalStore (nonce binding,
one-pending-per-project, idempotent decisions -- see
shiplib/telegram_protocol.py) and the real bot token. This CLI and the
daemon share a filesystem because both run on the SAME self-hosted VM
(see reusable-release.yml's `runs-on`) -- the queue is just a JSON file
dropped into <release_root>/_telegram_queue/, which keeps the real bot
token out of GitHub Actions entirely (it never needs to be a GitHub
secret at all -- see SHIP_SECURITY.md).

    PYTHONPATH=.. .venv/bin/python -m shiplib.release_ready_cli \\
        --project demo --repo me/demo --git-sha abc123 \\
        --artifact-sha256 <sha> --change-summary "fixed the thing"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from shiplib.registry import load_projects, load_targets
from shiplib.release import load_state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--artifact-sha256", required=True)
    ap.add_argument("--change-summary", default="")
    args = ap.parse_args()

    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"status": "REFUSED", "reason": f"'{args.project}' not in registry"}, indent=2))
        return 1
    entry = projects[args.project]
    targets = load_targets()
    release_root = Path(targets.get(entry.get("target"), {}).get("release_root", ""))

    state = load_state(str(release_root), args.project)
    request = {
        "project": args.project,
        "repo": args.repo,
        "git_sha": args.git_sha,
        "release_id": args.git_sha,
        "artifact_sha256": args.artifact_sha256,
        "current_sha": state.get("current_release"),
        "test_summary": "CI passed: validate + test + build",
        "change_summary": [args.change_summary] if args.change_summary else [],
        "requested_at": time.time(),
    }

    queue_dir = release_root / "_telegram_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    req_path = queue_dir / f"{args.project}-{args.git_sha}.json"
    req_path.write_text(json.dumps(request, indent=2))

    print(json.dumps({"status": "QUEUED", "path": str(req_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
