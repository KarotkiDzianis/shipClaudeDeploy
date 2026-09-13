# SHIP V0 ARCHITECTURE

Generic release/deployment foundation for `~/claude` workspace projects.
TradePulse is only one future consumer — nothing here is TradePulse-
specific, and TradePulse itself is untouched by this pass (§34 of the
originating spec).

## Why this exists

Before this, deploying any project meant a human manually running
`scp`/`ssh`/`tar`/`systemctl`, or (TradePulse's own established process)
Claude building an archive locally and handing over one copy-paste
command. Ship replaces that with a deterministic pipeline: commit → tests
→ build → package → artifact SHA256 → Telegram approval → self-hosted
deploy runner → atomic install/switch → verify → health → auto-rollback
on any failure.

## Components

```
platform/ship/
├── schema/project.schema.json    JSON Schema for a project's project.yml (fail-closed)
├── registry/                     CENTRAL authority: projects.yml + targets.yml
├── shiplib/                      the actual logic, importable + unit-tested
│   ├── schema.py                 validate/load project.yml
│   ├── registry.py               authorize_deploy() -- the fail-closed gate
│   ├── project.py                context path resolution (`ship context`)
│   ├── release.py                install / verify / switch_current / rollback / run_deploy
│   ├── telegram_protocol.py      approval state machine (nonce binding, idempotency)
│   └── cli.py                    `ship status` / `ship context` logic
├── cli/ship                      thin executable wrapping shiplib.cli
├── deploy/                       CLIs the self-hosted runner actually invokes
│   ├── install_release.py, verify_release.py, rollback.py   (thin wrappers)
│   └── run_deploy_cli.py         full install→verify→switch→restart→health→rollback orchestration
├── telegram/approval_bot/
│   ├── client.py                 real Telegram Bot API HTTP calls (untested -- no token)
│   └── bot.py                    message/pin/edit orchestration (tested with a fake client)
├── .github/workflows/            reusable-ci.yml, reusable-release.yml, reusable-deploy.yml
├── tests/                        63/63 passing, see "Known gaps" for what ISN'T covered
└── docs/                         this file + 5 more (see index below)
```

## Docs index

- `SHIP_PROJECT_CONTRACT.md` — what a project.yml must contain, how a project adopts Ship
- `SHIP_RELEASE_MODEL.md` — the release object, on-disk layout, atomicity guarantees
- `SHIP_TELEGRAM_APPROVAL.md` — the approval protocol, message lifecycle, security invariants
- `SHIP_DEPLOYMENT.md` — the full deploy contract and auto-rollback conditions
- `SHIP_SECURITY.md` — the central-registry threat model, secrets policy

## What is genuinely BUILT and TESTED (2026-09-13, 63/63 passing)

- Schema validation (fail-closed, unknown fields rejected) — 10 tests
- Central registry authorization (wrong repo/service/target/path-traversal all rejected) — 8 tests
- Release mechanics: install, atomic symlink switch, verify, rollback
  (including a post-rollback restart+health recheck, reporting
  `ROLLBACK_UNHEALTHY` distinctly from a clean `ROLLED_BACK` — §17 "run
  health again"), full `run_deploy` orchestration including auto-rollback
  on restart OR health failure — 10 tests, run against a real local
  filesystem sandbox (real tar extraction, real symlinks, real state
  persistence — not mocked). Caught and fixed one real ordering bug in
  this pass: `run_deploy` was checking the `current` symlink before it
  had been switched.
- Telegram approval state machine: nonce binding, allowlist, idempotent
  duplicate clicks, superseded-release rejection, blocked-cannot-later-
  approve — 10 tests, zero network access
- Telegram bot orchestration (pin on announce, edit-not-recreate on
  decision, unpin on terminal state, persists the decision when
  `release_root` is configured) — 7 tests against a fake client
- The full deploy CLI (`deploy/run_deploy_cli.py`) end to end: registry
  authorization, the Telegram-approval check (refuses with no approval /
  a blocked decision / an approval for a mismatched git_sha), the PR-job
  guard (refuses under `GITHUB_EVENT_NAME=pull_request`), and a real
  `systemctl restart`/health-command call point (faked in tests, real
  subprocess code path exists) — 9 tests
- `ship status` / `ship context` — 3 tests, plus a real end-to-end
  `new-project.sh` run verified against the real schema (see git history
  / session transcript — a throwaway project was generated, its
  project.yml validated for real, then removed)

## Known gaps — genuinely NOT connected to anything real yet

These are not oversights; §34 of the originating spec explicitly scoped
this pass to foundation-only. Each is a deliberate stop point, documented
so a future session knows exactly where to pick up rather than guessing:

1. **RESOLVED 2026-09-13**: `platform/ship` is a real git repo
   (`https://github.com/KarotkiDzianis/shipClaudeDeploy`, SSH auth). A
   second, separate real repo, `https://github.com/KarotkiDzianis/
   ship-sandbox`, is the first project actually onboarded — a disposable
   app built specifically to prove the pipeline mechanically (see its own
   CLAUDE.md) before any real project goes through it. Each project is
   its OWN git repo, not a shared monorepo — `reusable-ci.yml`/
   `reusable-deploy.yml`/`reusable-release.yml` check platform/ship out
   into a `platform/ship` subdirectory at a pinned commit (env
   `SHIP_REF`), separately from the calling project's own default
   checkout; this was a real design gap found and fixed this session
   (the original versions assumed platform/ship was already present in
   the calling job's own checkout, which is only true in a monorepo).
   TradePulse's own directory is still NOT a git repository — unaffected
   either way, per §34.
2. **`shiplib.registry_check` and `shiplib.deploy_result_cli` are now
   written and tested** (`tests/test_registry_check_cli.py`,
   `tests/test_deploy_result_cli.py`) — thin, real CLIs, not just
   documented intent. `shiplib.release_ready_cli` (the Telegram
   announce-and-wait-for-approval step) is still NOT written — ship-sandbox
   deliberately skips it (`approval: automatic` in the registry, not
   project.yml — see `deploy/run_deploy_cli.py`), so the first real E2E
   test proves install/verify/switch/restart/health/rollback mechanics
   work on a real VM, independent of the still-unbuilt Telegram
   webhook/polling receiver that would turn a button tap into
   `ShipTelegramBot.handle_callback()`. That receiver, `release_ready_cli`,
   and wiring a real Telegram-gated project remain the next, separate step.
3. **A self-hosted runner is being registered on the real prod VM**
   (the same VM TradePulse and another bot already run on — Dzianis's
   explicit decision, confirmed 2026-09-13: one isolated systemd unit per
   project, restart always scoped to that one named service, never the
   VM itself; see `registry/targets.yml`'s own header and
   `deploy/ship-sandbox.service`). Setup is one script Dzianis runs
   himself on the VM (`deploy/setup_main_vm_runner.sh` — sudoers scoped
   to exactly `systemctl restart ship-sandbox.service`, nothing else;
   Claude never SSHes in, per Rule 10). Known limitation, not fixed here:
   the runner registers against the ship-sandbox REPO specifically — a
   future project in its own separate repo will need its own
   registration, or an org-level runner pool, when it actually onboards.
4. **RESOLVED 2026-09-13**: a real, dedicated Ship bot token exists
   (`SHIP_CLAUDE_DEPLOY_BOT` in `~/claude/.env`, distinct from
   TradePulse's own `TRAIDZ_BOT_TOKEN` and the unrelated
   `TELEGRAM_BOT_TOKEN` already used by 3 other projects — deliberately
   not reused, per §18) and is now VERIFIED WORKING: Dzianis ran
   `scripts/smoke_test_telegram.py` on his own machine (Claude's sandbox
   cannot reach `api.telegram.org` — confirmed separately, HTTP 000 on
   that one host only, unrelated to the token). Real result: `getMe`
   confirmed the token is valid (`@SHIP_CLAUDE_DEPLOY_BOT`), and a real
   message was sent successfully (`message_id=2`). Delivery into the
   actual Telegram chat still pending Dzianis's confirmation — the bot
   can only message a chat that has sent it `/start` at least once.
   Still not wired: no webhook/polling receiver exists yet to turn a real
   button tap into `ShipTelegramBot.handle_callback()` (see gap #2).
5. **`registry/projects.yml`'s `repo:` fields for tradepulse/stroytender-by
   are still literal `"TBD"` values** — `authorize_deploy()` explicitly
   refuses to authorize a deploy while this is true (see
   `test_unregistered_repo_placeholder_refused`), enforced, not just
   documented. `ship-sandbox`'s own entry now has a real repo.
6. **TradePulse has not adopted `project.yml`** — `ship status tradepulse`
   correctly reports `NOT_ADOPTED`, not an error. TradePulse's existing
   Rule 10 manual-deploy process is completely unaffected either way.

## Explicit non-goals for V0 (§41 "do not overengineer")

Kubernetes, AWS/multi-cloud, canary/blue-green, multi-region, an
enterprise policy engine, a plugin framework. If GitHub → approval → one
VM deploy → restart → health → rollback doesn't need it, it isn't here.
