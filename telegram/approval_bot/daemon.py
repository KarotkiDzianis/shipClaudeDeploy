"""telegram/approval_bot/daemon.py — the ONE persistent process that
owns the shared ApprovalStore (shiplib/telegram_protocol.py) and the
real Telegram bot token, for ALL projects on this VM. Installed as its
own systemd service (ship-approval-bot.service) -- separate from any
single deploy job, since a human's decision is asynchronous and can
arrive minutes or hours after a release-ready announcement, long after
the GitHub Actions job that triggered it has moved on to waiting
(shiplib/wait_for_approval_cli.py polls the FILE this daemon writes, not
this process directly).

Two responsibilities, one loop:
  1. Watch <release_root>/_telegram_queue/*.json for "please announce
     this release" requests (written by shiplib.release_ready_cli,
     running on the SAME self-hosted VM -- see reusable-release.yml's
     `runs-on`) -- call announce_release_ready(), then delete the file.
  2. Long-poll Telegram getUpdates for callback_query events -- parse
     "ship:{project}:{release_id}:{nonce}:{decision}", call
     handle_callback(). The offset is persisted so a restart never
     replays old updates.

Real secrets (bot token, chat id, allowed approver ids) come from THIS
PROCESS'S OWN ENVIRONMENT (systemd EnvironmentFile, see
deploy/setup_main_vm_runner.sh) -- never passed through GitHub Actions,
never a GitHub secret. Smaller secret surface than originally documented
in SHIP_SECURITY.md (updated to match).
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shiplib.telegram_protocol import ApprovalStore
from telegram.approval_bot.bot import ShipTelegramBot
from telegram.approval_bot.client import TelegramClient

POLL_INTERVAL_SECONDS = 3
GETUPDATES_LONGPOLL_SECONDS = 10


def _load_offset(offset_file: Path) -> int:
    if offset_file.exists():
        text = offset_file.read_text().strip()
        if text:
            return int(text)
    return 0


def _save_offset(offset_file: Path, offset: int) -> None:
    offset_file.write_text(str(offset))


def process_queue(bot: ShipTelegramBot, queue_dir: Path) -> None:
    for path in sorted(glob.glob(str(queue_dir / "*.json"))):
        p = Path(path)
        try:
            req = json.loads(p.read_text())
            bot.announce_release_ready(
                req["project"], req["repo"], req["git_sha"], req["release_id"],
                req.get("current_sha"), req.get("test_summary", ""), req.get("change_summary", []),
            )
            print(f"announced {req['project']} @ {req['git_sha'][:8]}", flush=True)
        except Exception as e:
            print(f"failed to process queued request {p}: {e}", flush=True)
        finally:
            p.unlink(missing_ok=True)


def process_updates(bot: ShipTelegramBot, client: TelegramClient, offset_file: Path) -> None:
    offset = _load_offset(offset_file)
    updates = client.get_updates(offset=offset, timeout=GETUPDATES_LONGPOLL_SECONDS)
    for update in updates.get("result", []):
        offset = max(offset, update["update_id"] + 1)
        cq = update.get("callback_query")
        if not cq:
            continue
        parts = (cq.get("data") or "").split(":")
        if len(parts) != 5 or parts[0] != "ship":
            continue
        _, project, release_id, nonce, decision = parts
        result = bot.handle_callback(project, release_id, nonce, cq["from"]["id"], decision, cq["id"])
        print(f"callback: project={project} decision={decision} -> {result}", flush=True)
    _save_offset(offset_file, offset)


def main() -> int:
    token = os.environ["SHIP_CLAUDE_DEPLOY_BOT"]
    chat_id = os.environ["TELEGRAM_CHAT_ID_DZIANIS"]
    approvers = {int(x) for x in os.environ["SHIP_ALLOWED_APPROVER_IDS"].split(",") if x.strip()}
    release_root = Path(os.environ["SHIP_RELEASE_ROOT"])

    client = TelegramClient(token)
    store = ApprovalStore(approvers)
    bot = ShipTelegramBot(client, store, chat_id, release_root=str(release_root))

    queue_dir = release_root / "_telegram_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    offset_file = release_root / "_telegram_bot_offset.txt"

    print(f"Ship approval bot daemon started (release_root={release_root}, "
         f"{len(approvers)} allowed approver(s))", flush=True)
    while True:
        process_queue(bot, queue_dir)
        try:
            process_updates(bot, client, offset_file)
        except Exception as e:
            print(f"poll error (continuing): {e}", flush=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
