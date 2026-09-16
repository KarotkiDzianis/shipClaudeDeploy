# SHIP SECURITY

## Rule 10, redefined (per the originating spec's own §1)

Rule 10 no longer means "deploy is manual forever." It now means:

- Claude Code never SSHes into a production VM itself.
- Claude never runs ad-hoc `systemctl`/deploy commands directly.
- The user never has to manually copy-paste deploy commands.
- Deploy only ever happens through the deterministic Ship/GitHub pipeline.
- Production deploy requires the project's configured approval policy
  (Telegram/automatic/manual per `project.yml`'s `deploy.approval`).
- Claude MAY: write code, open PRs, analyze test/deploy logs, write
  release summaries.
- Claude MUST NOT: bypass a failing test, self-approve a release, bypass
  the deploy policy, or directly deploy to a protected production target.

This governs Ship itself; it does not retroactively change TradePulse's
own already-established Rule 10 behavior (Dzianis deploys manually, one
command) until TradePulse explicitly onboards to Ship as a separate,
later decision.

## The central registry is the authority, not project.yml (§8/§27)

A project's own `project.yml` can ASK for a deploy target/service. Only
`registry/projects.yml` + `registry/targets.yml` can GRANT it.
`shiplib.registry.authorize_deploy()` is the single fail-closed
gate — checked, not just documented:

- unknown project → refused
- `deployment_allowed: false` → refused
- project not in the target's own `allowed_projects` → refused (the
  project-level flag and the target-level allowlist are two independent
  checks; both must agree)
- requested repo != registry's repo for that project → refused
- requested service != registry's service for that project → refused
- requested target != the project's own registered target → refused
- requested `release_root` escapes the target's own `release_root` (path
  traversal) → refused
- registry `repo:` is still a `"TBD"` placeholder → refused (a project
  cannot deploy before it even has a real git remote registered)

A compromised or stale `project.yml`, or a forged/tampered workflow
input, cannot grant itself new production permission — the deploy runner
re-validates every one of these against the registry itself, every time
(§27), never trusting the calling workflow's own claims.

## No secrets, anywhere, ever

Not in `project.yml`, not in git, not in `CLAUDE.md`, not in a release
artifact. The schema (`schema/project.schema.json`) has
`additionalProperties: false` at every level specifically so a secret
accidentally added as an "extra field" fails validation loudly instead of
silently shipping.

**Where real secrets live:**
- Telegram bot token + chat id + allowed approver ids → **not a GitHub
  secret at all** (revised 2026-09-16 from the original plan below): only
  `telegram/approval_bot/daemon.py`'s own systemd `EnvironmentFile`
  (`/etc/ship/telegram.env` on the VM, created by hand, never in git)
  holds them. The daemon is the ONE long-running process that announces
  releases and receives button taps (see `SHIP_TELEGRAM_APPROVAL.md`) —
  GitHub Actions jobs only ever drop/read plain JSON files on the shared
  VM filesystem, never touching the token. Smaller secret surface than
  routing it through CI at all.
- GitHub authentication → prefer a GitHub App with minimum permissions
  over a personal access token (§25); the app requests/dispatches only
  the specific approved deployment.
- Self-hosted runner registration token → generated per-registration by
  GitHub, never stored in this repo.

## Telegram bot security (see SHIP_TELEGRAM_APPROVAL.md for the full protocol)

The bot itself never SSHes, never runs a shell command, never deploys
directly — it only records an approval/block decision bound to one exact
`(project, repo, git_sha, release_id, nonce)`. See that doc for the 5
invariants (payload binding, allowlist, idempotency, old-release
rejection, blocked-cannot-later-deploy) — all independently unit-tested.

## What the self-hosted runner itself must enforce (§26/§27)

All four of these are actually checked by `deploy/run_deploy_cli.py`
(tested in `tests/test_deploy_cli.py`), not just documented conventions:

- Never accept a deploy workflow triggered from a PR/untrusted-code
  context — `_refuse_if_untrusted_job_context()` checks `GITHUB_EVENT_NAME`
  and refuses on `pull_request`/`pull_request_target` before anything else
  runs.
- Never deploy a release Telegram never approved, or approved a
  DIFFERENT sha for — `shiplib.approval_persistence.is_approved_for()` is
  checked before `authorize_deploy()` even runs.
- Never run arbitrary `systemctl <anything>` — only the exact,
  registry-authorized service name for the exact, registry-authorized
  project (`authorize_deploy()`'s own `service` check).
- Never write outside the registry-authorized `release_root` — the
  path-traversal check in `authorize_deploy()`.
- Re-run `authorize_deploy()` itself rather than trusting any input it
  was invoked with.
