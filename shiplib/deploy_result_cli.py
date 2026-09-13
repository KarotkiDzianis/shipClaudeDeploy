"""shiplib/deploy_result_cli.py — thin CLI that reports a deploy's
outcome (already recorded by shiplib.release.run_deploy() in state.json)
back to Telegram. Posts only if a bot token is actually configured for
this project's workflow (SHIP_TELEGRAM_BOT_TOKEN/SHIP_TELEGRAM_CHAT_ID
env vars) -- an automatic-approval project (see registry/projects.yml's
`approval` field) has no Telegram wiring at all, and that is not an
error: this CLI then just prints the result and exits 0.

    PYTHONPATH=.. .venv/bin/python -m shiplib.deploy_result_cli --project demo
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from shiplib.registry import load_projects, load_targets
from shiplib.release import load_state


def _format_message(project: str, state: dict) -> str:
    last = state.get("last_deploy") or {}
    if last.get("result") == "success":
        return f"✅ {project}: deployed {last.get('git_sha')}"
    rollback = state.get("last_rollback") or {}
    lines = [f"⛔ {project}: deploy FAILED at stage '{last.get('failed_stage')}'"]
    if rollback:
        lines.append(f"rollback: {rollback.get('result')} (restored {rollback.get('restored_sha', '?')})")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    args = ap.parse_args()

    projects = load_projects()
    entry = projects.get(args.project, {})
    targets = load_targets()
    release_root = targets.get(entry.get("target"), {}).get("release_root", "")

    state = load_state(release_root, args.project)
    message = _format_message(args.project, state)
    print(message)

    token = os.environ.get("SHIP_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("SHIP_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("(no SHIP_TELEGRAM_BOT_TOKEN/SHIP_TELEGRAM_CHAT_ID configured for this project -- not posting)")
        return 0

    from telegram.approval_bot.client import TelegramClient
    try:
        TelegramClient(token).send_message(chat_id, message)
    except Exception as e:
        safe = str(e).replace(token, "***REDACTED***")
        print(f"(failed to post result to Telegram: {safe})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
