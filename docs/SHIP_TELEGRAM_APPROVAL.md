# SHIP TELEGRAM APPROVAL

## Status: fully wired (2026-09-16), not yet exercised with a real click

`shiplib/telegram_protocol.py` (the state machine), `telegram/
approval_bot/bot.py` (the message orchestration), `telegram/
approval_bot/daemon.py` (the persistent process that owns both), `shiplib/
release_ready_cli.py` (enqueues an announce request) and `shiplib/
wait_for_approval_cli.py` (the deploy job's gate) are all real, tested
code. `telegram/approval_bot/client.py`'s `send_message`/`getMe` were
proven working against the real API by `scripts/smoke_test_telegram.py`;
`get_updates()` (long-polling) has not yet received a real button tap —
that's the next real-world verification, once the daemon is running on
the VM (see "Running it for real" below).

## One bot, one chat, all projects (§18)

Approval traffic is deliberately never mixed into a project's own
Telegram chat (e.g. TradePulse's trade-signal chat stays untouched). One
"Ship Control" bot/chat serves every project's release approvals.

## Message lifecycle (§19/§20 — edited, never recreated)

1. `announce_release_ready()` creates a `PendingApproval` (fresh
   `secrets.token_urlsafe` nonce), sends ONE message with 3 buttons
   (🚀 РАСКАТИТЬ / ⛔ БЛОКИРОВАТЬ / ℹ️ ИНФО), and pins it immediately.
2. `handle_callback()` on a valid, non-repeat decision EDITS that exact
   message to its terminal text and unpins it. It never sends a second
   message for the same release.
3. A NEW release for the same project (`announce_release_ready()` called
   again) creates a brand-new `PendingApproval` with its own nonce and
   sends its own new message — it does not touch the old one, but the old
   one's nonce is no longer the "current" one, so its buttons stop working
   (see security invariants below).

## Security invariants (§24, all enforced by `ApprovalStore.decide()`, all tested)

- **Payload binding**: a callback is only honored if its `(release_id,
  nonce)` exactly matches the CURRENT pending approval for that project.
- **Old/superseded release rejected**: once a new release is announced,
  the previous one's buttons can never approve or block anything, even if
  the previous one was never decided.
- **Allowlist**: only Telegram user ids in `ApprovalStore`'s
  `allowed_approvers` set can decide anything.
- **Idempotent duplicate clicks**: clicking an already-decided button
  again (by the same or a different allowed user) returns the SAME
  original decision — it never re-triggers a deploy or flips a decision.
- **Blocked release cannot later deploy**: a `blocked` decision is
  terminal for that `(release_id, nonce)`; only a genuinely new
  `announce_release_ready()` call (a new release/nonce) can be approved.

## Closing the loop: the deploy runner actually checks the decision

`ShipTelegramBot(client, store, chat_id, release_root=...)` — when
`release_root` is set, a valid non-repeat decision is persisted via
`shiplib/approval_persistence.py` (one `approval.json` per project, next
to that project's own `state.json`). `deploy/run_deploy_cli.py` calls
`is_approved_for(release_root, project, git_sha)` BEFORE doing anything
else — refusing if no decision was ever recorded, if the recorded
decision is for a different `git_sha` (stale/mismatched approval), or if
it's `"blocked"`. This is what actually enforces §24's invariants at
deploy time, not just at the Telegram-button level — tested end to end in
`tests/test_deploy_cli.py` (refused-without-approval, refused-when-
blocked, refused-when-sha-mismatched, succeeds-when-approved).

## Running it for real: one daemon per VM, not one process per deploy

A human's decision is asynchronous — it can arrive minutes or hours after
a release is announced, long after the GitHub Actions job that announced
it has finished. So the bot is a SEPARATE, always-running process
(`telegram/approval_bot/daemon.py`, installed via `deploy/
setup_approval_daemon.sh` as `ship-approval-bot.service`), not something
spun up per job:

1. `reusable-release.yml`'s `release-ready` job (now `runs-on:
   [self-hosted, ...]`, not GitHub-hosted) calls `shiplib.
   release_ready_cli`, which drops a JSON "please announce this" request
   into `<release_root>/_telegram_queue/` — a plain file, because this
   job and the daemon share the SAME VM's filesystem.
2. The daemon picks up the file, calls `announce_release_ready()` for
   real, deletes the file.
3. The daemon also long-polls `getUpdates()` in the same loop; a
   `callback_query` with `data` matching `ship:{project}:{release_id}:
   {nonce}:{decision}` calls `handle_callback()`, which persists the
   decision (`shiplib/approval_persistence.py`) if it's valid.
4. `reusable-deploy.yml`'s deploy job calls `shiplib.
   wait_for_approval_cli` (polls that persisted file, 30 min default
   timeout) before `run_deploy_cli.py` — which re-checks the same
   decision itself anyway (§27 defense in depth).

**The real bot token never becomes a GitHub secret.** Only the daemon's
own systemd `EnvironmentFile` (`/etc/ship/telegram.env`, created by hand
on the VM, never in git) holds `SHIP_CLAUDE_DEPLOY_BOT`/
`TELEGRAM_CHAT_ID_DZIANIS`/`SHIP_ALLOWED_APPROVER_IDS` — a smaller secret
surface than the original plan (see `SHIP_SECURITY.md`).

## What's still not done

- **A real button tap has never been clicked** — the daemon has not run
  on the VM yet, so `get_updates()`/`handle_callback()` are tested only
  against a fake client (`tests/test_approval_daemon.py`,
  `tests/test_telegram_bot.py`).
- `SHIP_ALLOWED_APPROVER_IDS` needs Dzianis's real numeric Telegram user
  id (not the chat id) — obtained once from `getUpdates` after messaging
  the bot, from his own machine (see the setup script's own header).
- The persistent Ship dashboard (§21) and pending-release reminders
  (§22) — designed, not built; thin extensions of the same
  edit-not-recreate pattern already proven in `bot.py`.
- `shiplib.deploy_result_cli` still posts the final deploy outcome via
  its OWN direct Telegram call (a GitHub Actions secret, if configured)
  rather than through the daemon's queue — inconsistent with the
  "daemon is the only thing holding the token" principle above, but
  harmless (no-ops if unconfigured) and not required for the approval
  flow itself; unifying it is a small follow-up, not done here.
