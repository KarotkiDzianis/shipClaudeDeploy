"""shiplib/wait_for_approval_cli.py — the deploy job's first real step
for a Telegram-gated project: blocks until a human decision is recorded
for this EXACT git_sha (via the approval daemon writing approval.json,
see shiplib/approval_persistence.py), or a timeout elapses. A project
the central registry marks `approval: automatic` is skipped entirely --
this is a REGISTRY decision (never project.yml's own claim), matching
deploy/run_deploy_cli.py's own approval-mode check.

    PYTHONPATH=.. .venv/bin/python -m shiplib.wait_for_approval_cli \\
        --project demo --git-sha abc123 --timeout-seconds 1800
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from shiplib.approval_persistence import is_approved_for, load_decision
from shiplib.registry import load_projects, load_targets

POLL_SECONDS = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    args = ap.parse_args()

    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"status": "REFUSED", "reason": f"'{args.project}' not in registry"}, indent=2))
        return 1
    entry = projects[args.project]

    if entry.get("approval", "telegram") == "automatic":
        print(json.dumps({"status": "SKIPPED", "reason": "registry approval mode is automatic"}, indent=2))
        return 0

    targets = load_targets()
    release_root = targets.get(entry.get("target"), {}).get("release_root", "")

    deadline = time.time() + args.timeout_seconds
    while True:
        approved, reason = is_approved_for(release_root, args.project, args.git_sha)
        if approved:
            print(json.dumps({"status": "APPROVED"}, indent=2))
            return 0

        decision = load_decision(release_root, args.project)
        if decision and decision.get("git_sha") == args.git_sha and decision.get("decision") == "blocked":
            print(json.dumps({"status": "BLOCKED", "decided_by": decision.get("decided_by")}, indent=2))
            return 1

        if time.time() >= deadline:
            print(json.dumps({"status": "TIMEOUT",
                              "reason": f"no decision within {args.timeout_seconds}s"}, indent=2))
            return 1

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
