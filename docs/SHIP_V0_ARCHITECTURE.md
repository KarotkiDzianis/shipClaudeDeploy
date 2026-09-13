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
├── tests/                        57/57 passing, see "Known gaps" for what ISN'T covered
└── docs/                         this file + 5 more (see index below)
```

## Docs index

- `SHIP_PROJECT_CONTRACT.md` — what a project.yml must contain, how a project adopts Ship
- `SHIP_RELEASE_MODEL.md` — the release object, on-disk layout, atomicity guarantees
- `SHIP_TELEGRAM_APPROVAL.md` — the approval protocol, message lifecycle, security invariants
- `SHIP_DEPLOYMENT.md` — the full deploy contract and auto-rollback conditions
- `SHIP_SECURITY.md` — the central-registry threat model, secrets policy

## What is genuinely BUILT and TESTED (2026-09-13, 57/57 passing)

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

1. **No git repository exists anywhere in this workspace** (confirmed:
   `git rev-parse --is-inside-work-tree` fails at both `~/claude` and
   `~/claude/projects/commercial/tradepulse`). Nothing in `.github/
   workflows/` has ever run — GitHub Actions requires an actual GitHub
   repo. `gh` CLI is also not installed on this machine.
2. **`shiplib.release_ready_cli`, `shiplib.registry_check`,
   `shiplib.deploy_result_cli`** are referenced by the reusable workflows
   but not written — they're thin glue around already-built-and-tested
   logic (`ShipTelegramBot.announce_release_ready`, `authorize_deploy`,
   a result-formatting call), deliberately not built because there is no
   real Telegram bot token or real workflow run to test them against yet;
   writing them now would be untested glue, not a build. What IS built and
   tested: the approval decision itself is now persisted
   (`shiplib/approval_persistence.py`) and actually checked by
   `deploy/run_deploy_cli.py` before it will deploy anything — the only
   missing piece is the real webhook/polling receiver that turns an
   incoming Telegram button tap into a call to `ShipTelegramBot.
   handle_callback()`.
3. **No self-hosted runner is registered anywhere** (targets.yml's
   `main-vm` is a design placeholder, see that file's own header).
4. **No real Telegram bot token / chat exists.** `telegram/approval_bot/
   client.py` is real, correct-looking code but has never made a real
   HTTP call to api.telegram.org.
5. **`registry/projects.yml`'s `repo:` fields are literal `"TBD"` values**
   — `authorize_deploy()` explicitly refuses to authorize a deploy while
   this is true (see `test_unregistered_repo_placeholder_refused`) — this
   is enforced, not just documented.
6. **TradePulse has not adopted `project.yml`** — `ship status tradepulse`
   correctly reports `NOT_ADOPTED`, not an error. TradePulse's existing
   Rule 10 manual-deploy process is completely unaffected either way.

## Explicit non-goals for V0 (§41 "do not overengineer")

Kubernetes, AWS/multi-cloud, canary/blue-green, multi-region, an
enterprise policy engine, a plugin framework. If GitHub → approval → one
VM deploy → restart → health → rollback doesn't need it, it isn't here.
