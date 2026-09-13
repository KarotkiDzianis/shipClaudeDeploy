# SHIP RELEASE MODEL

## The release object (immutable)

Every deploy attempt creates one release object:

```
release_id           usually == git_sha, unless explicitly set
project               slug
repo
git_sha
artifact_sha256
created_at
```

(`ship_version`/`test_summary`/`change_summary`/`project_config_hash`
from the originating spec's §14 are carried by the CI/release GitHub
workflows, not by `shiplib.release` itself, which only needs the fields
above to install/verify/switch/rollback.)

## On-disk layout

```
<release_root>/<project>/
├── releases/
│   └── <git_sha>/
│       ├── RELEASE_SHA        plain text, == git_sha
│       ├── MANIFEST.json      the release object
│       └── ...                extracted artifact contents
├── current -> releases/<git_sha>     symlink, atomically switched
└── state.json                current_release / previous_successful_release / last_deploy / last_health / last_rollback
```

`<release_root>` comes ONLY from `registry/targets.yml` (e.g. `/srv/apps`
on `main-vm`) — never from a caller-supplied path. See `SHIP_SECURITY.md`.

## Atomicity (§15: never overwrite `current` in place)

`switch_current()` never edits the existing `current` symlink in place.
It creates a new temp symlink pointing at `releases/<git_sha>` and calls
`os.replace()` on it — a single atomic rename at the filesystem level.
`current` is either the old release or the new one at every instant,
never briefly missing or half-pointing.

## The two-phase verify (why there are two functions, not one)

`run_deploy()` calls `verify_artifact()` (SHA256 + RELEASE_SHA checks
only) BEFORE switching `current`, then `verify_release()` (the same two
checks PLUS "does `current` actually resolve to this release") AFTER
switching. Checking the symlink before it's ever been switched would
always fail — an actual bug this project's own test suite caught in this
pass (`test_healthy_deploy_succeeds` failed until `run_deploy()` was
reordered — see `shiplib/release.py`'s own history).

## Deploy success contract (§16 — hash alone is not enough)

`run_deploy()` only reports `DEPLOYED` if, in order:
1. the artifact SHA256 matches
2. the installed RELEASE_SHA matches
3. `current` resolves to the new release
4. the service restart succeeds (`restart_fn()` returns True)
5. the project's own health command passes (`health_fn()` returns True)

Any single failure at steps 1-5 triggers rollback (see below) — the
function never returns anything other than `DEPLOYED` or `FAILED` (with a
rollback attempt already made and recorded).

## Auto-rollback (§17 — never leaves a half-deployed release)

Before installing anything, `run_deploy()` reads
`state.json.current_release` as `previous`. On ANY failure (steps 1-5
above), it calls `rollback(release_root, project, target_sha=previous)`,
which switches `current` back and records `last_rollback` in `state.json`.
If there was no previous release (first-ever deploy fails), the result
says `rollback: {"status": "NO_PREVIOUS_RELEASE"}` — explicit, not silent.

When `run_deploy()` itself triggers the rollback (not a manual `ship
rollback`), it also re-runs the SAME `restart_fn`/`health_fn` against the
now-restored release and records the outcome as `rollback["rollback_
restarted"]`/`rollback["rollback_health"]` (§17: "restart service / run
health again", matching the Telegram result examples' own "Rollback
health: PASS" field). If the restored release is itself unhealthy or
won't restart, the rollback's own `status` becomes `ROLLBACK_UNHEALTHY`
rather than a falsely-reassuring `ROLLED_BACK` — "the symlink pointed back
successfully" and "the previous release is actually healthy" are kept as
two distinct, both-checked facts, never conflated.

A standalone `ship rollback` (via `deploy/rollback.py`, not triggered by
a failed `run_deploy`) does NOT automatically re-run health — that command
switches the symlink and records the attempt; the caller is expected to
run `deploy/verify_release.py` and the project's own health check
afterward as separate, explicit steps.
