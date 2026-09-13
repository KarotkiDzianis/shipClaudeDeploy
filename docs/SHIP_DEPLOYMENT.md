# SHIP DEPLOYMENT

## Where deploy actually runs

Only on a self-hosted runner with labels `[self-hosted, linux,
ship-prod]` (see `registry/targets.yml`) — never on a GitHub-hosted
runner, and never for a PR/untrusted-code job (§11/§26). Test/build jobs
run on GitHub-hosted runners; only the deploy job needs the self-hosted
one.

## The deploy sequence (`deploy/run_deploy_cli.py`)

1. Look up the project in `registry/projects.yml` → its `target`/`service`.
2. Look up `release_root` from `registry/targets.yml`.
3. `authorize_deploy()` — re-validates repo/target/service/release_root
   against the registry, fail-closed. This happens even though the
   calling GitHub workflow already "knows" these values — a compromised
   or stale workflow input must never be trusted on its own (§27).
4. `shiplib.release.run_deploy()` — install → verify (pre-switch) →
   switch `current` → verify (post-switch) → `systemctl restart
   <authorized-service-name>` → the project's own `scripts/ship/health` →
   auto-rollback on any failure. See `SHIP_RELEASE_MODEL.md` for the full
   contract.

## Result reporting

`deploy/run_deploy_cli.py` prints one JSON object: `{"status": "DEPLOYED",
"git_sha": ...}` on success, or `{"status": "FAILED", "failed_stage":
"verify"|"restart"|"health", "rollback": {...}}` on failure. The Telegram
result message (§30, not yet built — see `SHIP_TELEGRAM_APPROVAL.md`) is
a thin formatter over this same JSON.

## Manual rollback

`deploy/rollback.py --project <slug> [--target-sha <sha>]` — defaults to
`state.json`'s own `previous_successful_release`. Does not itself
re-check health; run `deploy/verify_release.py` and the project's own
`scripts/ship/health` afterward to confirm the rollback landed cleanly.

## Log collection (§29 — not yet built)

Designed but not implemented in this pass: after a deploy, collect
`systemctl status`/`journalctl` output, health output, and deploy
duration into `deploy_report.json`/`.md`, uploaded as a GitHub Actions
artifact. Straightforward once a real runner exists to generate real logs
from — building it against nothing would be speculative.

## Status CLI

`ship status <project>` (see `cli/ship`) reports: registry entry, whether
`project.yml` has been adopted, and — once a target is configured —
`current_deployed_sha`, `previous_successful_release`, `last_deploy`,
`last_health`, `last_rollback` straight from `state.json`. Reports
`NOT_ADOPTED`/`NO_TARGET_CONFIGURED` explicitly rather than guessing or
crashing when a project hasn't set any of this up yet.
