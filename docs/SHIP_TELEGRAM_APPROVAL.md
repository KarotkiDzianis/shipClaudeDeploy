# SHIP TELEGRAM APPROVAL

## Status: protocol built + tested, real bot NOT connected

`shiplib/telegram_protocol.py` (the state machine) and
`telegram/approval_bot/bot.py` (the message orchestration) are real,
tested code — 15 tests total, zero network access, using a fake Telegram
client. `telegram/approval_bot/client.py` (the real HTTP calls) has never
been exercised against api.telegram.org — there is no bot token yet.

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

## What's left to actually connect this (not done in this pass, §34)

1. A real bot token + chat id (Telegram secrets, never in `project.yml`
   or git — see `SHIP_SECURITY.md`).
2. A real webhook/polling receiver wiring Telegram's actual callback
   payloads into `ShipTelegramBot.handle_callback()` — the bot and
   persistence logic above are both real and tested; only the "receive an
   HTTP update from Telegram and call this function" glue is missing,
   because there's no real bot to receive updates from yet.
3. `shiplib.release_ready_cli` / `shiplib.deploy_result_cli` (referenced
   by the reusable GitHub workflows, not yet written — see
   `SHIP_V0_ARCHITECTURE.md` "Known gaps").
4. The persistent Ship dashboard (§21) and pending-release reminders
   (§22) — designed, not built; they're thin extensions of the same
   edit-not-recreate pattern already proven in `bot.py`.
