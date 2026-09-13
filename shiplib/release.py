"""shiplib/release.py — immutable release install, atomic current-symlink
switch, verification, and auto-rollback (§14-§17 of the Ship spec).

Layout under `<release_root>/<project>/`:
    releases/<git_sha>/RELEASE_SHA      -- plain text, == git_sha
    releases/<git_sha>/MANIFEST.json    -- the full release object
    releases/<git_sha>/...              -- extracted artifact contents
    current -> releases/<git_sha>       -- atomic symlink, never edited in place
    state.json                          -- current_release / previous_successful_release / history

Callers must run this ONLY after `shiplib.registry.authorize_deploy()` has
already granted the (project, target, service, release_root) combination
-- this module trusts its caller on authorization and focuses purely on
the release mechanics themselves.
"""
from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root(release_root, project: str) -> Path:
    return Path(release_root) / project


def _releases_dir(release_root, project: str) -> Path:
    return _project_root(release_root, project) / "releases"


def _state_path(release_root, project: str) -> Path:
    return _project_root(release_root, project) / "state.json"


def load_state(release_root, project: str) -> dict:
    path = _state_path(release_root, project)
    if not path.exists():
        return {"current_release": None, "previous_successful_release": None,
                "last_deploy": None, "last_health": None, "last_rollback": None}
    return json.loads(path.read_text())


def _write_state(release_root, project: str, **updates) -> dict:
    path = _state_path(release_root, project)
    state = load_state(release_root, project)
    state.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_state_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return state


def install_release(release_root, project: str, git_sha: str, artifact_path, manifest: dict) -> Path:
    """§14/§15: extracts the artifact into releases/<git_sha>/ (never
    touches `current` in place) and writes RELEASE_SHA + MANIFEST.json.
    Idempotent: re-installing the same git_sha overwrites only that
    release's own directory, never `current`."""
    release_dir = _releases_dir(release_root, project) / git_sha
    release_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact_path, "r:gz") as tf:
        # `filter="data"` (PEP 706, Python 3.12+) rejects path-traversal/
        # absolute-path members -- use it where available; older
        # interpreters fall back to a plain extract (these are Ship's own
        # just-built artifacts, not third-party uploads, at this stage).
        try:
            tf.extractall(release_dir, filter="data")
        except TypeError:
            tf.extractall(release_dir)
    (release_dir / "RELEASE_SHA").write_text(git_sha)
    (release_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, default=str))
    return release_dir


def switch_current(release_root, project: str, git_sha: str) -> None:
    """§15: atomic symlink swap via a temp-symlink + os.replace (POSIX
    atomic rename) -- `current` is never briefly missing or half-updated."""
    project_root = _project_root(release_root, project)
    project_root.mkdir(parents=True, exist_ok=True)
    current = project_root / "current"
    target = Path("releases") / git_sha
    tmp_link = project_root / f".current.tmp.{os.getpid()}"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(target, tmp_link)
    os.replace(tmp_link, current)


def verify_artifact(release_root, project: str, expected_git_sha: str, expected_artifact_sha256: str) -> dict:
    """Pre-switch half of §16's contract: artifact SHA256 matches and the
    installed RELEASE_SHA matches -- deliberately does NOT check the
    `current` symlink (it hasn't been switched yet at this point in
    `run_deploy`; see `verify_release` for the full post-switch check)."""
    release_dir = _releases_dir(release_root, project) / expected_git_sha
    checks = {"release_dir_exists": release_dir.exists()}
    if not checks["release_dir_exists"]:
        return {"ok": False, "checks": checks, "reason": f"{release_dir} does not exist"}

    release_sha_file = release_dir / "RELEASE_SHA"
    checks["release_sha_matches"] = release_sha_file.exists() and release_sha_file.read_text() == expected_git_sha

    manifest_path = release_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    checks["artifact_sha256_matches"] = manifest.get("artifact_sha256") == expected_artifact_sha256

    ok = all(checks.values())
    result = {"ok": ok, "checks": checks}
    if not ok:
        result["reason"] = "one or more artifact verification checks failed -- see 'checks'"
    return result


def verify_release(release_root, project: str, expected_git_sha: str, expected_artifact_sha256: str) -> dict:
    """§16 (full release-layer contract, run AFTER switch_current): artifact
    SHA256 matches, installed RELEASE_SHA matches, AND `current` resolves
    to the expected release. Hash alone is not treated as sufficient --
    all three checks must pass."""
    result = verify_artifact(release_root, project, expected_git_sha, expected_artifact_sha256)
    current = _project_root(release_root, project) / "current"
    result["checks"]["current_symlink_correct"] = (
        current.is_symlink() and os.readlink(current) == str(Path("releases") / expected_git_sha))
    result["ok"] = all(result["checks"].values())
    if not result["ok"]:
        result["reason"] = "one or more release verification checks failed -- see 'checks'"
    elif "reason" in result:
        del result["reason"]
    return result


def rollback(release_root, project: str, target_sha: str = None) -> dict:
    """§17: switches `current` back to `target_sha` (defaults to the
    recorded previous_successful_release) and records the attempt. Does
    NOT itself run a health check -- callers (run_deploy, or `ship
    rollback`) are expected to health-check afterward and report that
    separately, matching §17's own 'Telegram result' + 'rollback health
    check' as two distinct facts."""
    state = load_state(release_root, project)
    sha = target_sha or state.get("previous_successful_release")
    if sha is None:
        result = {"status": "ROLLBACK_FAILED", "reason": "no previous_successful_release recorded"}
        _write_state(release_root, project, last_rollback={"at": _now(), "result": "failed", "reason": result["reason"]})
        return result

    release_dir = _releases_dir(release_root, project) / sha
    if not release_dir.exists():
        result = {"status": "ROLLBACK_FAILED", "reason": f"release {sha} no longer exists on disk"}
        _write_state(release_root, project, last_rollback={"at": _now(), "result": "failed", "reason": result["reason"]})
        return result

    switch_current(release_root, project, sha)
    _write_state(release_root, project, current_release=sha,
                 last_rollback={"at": _now(), "result": "success", "restored_sha": sha})
    return {"status": "ROLLED_BACK", "restored_sha": sha}


def run_deploy(release_root, project: str, git_sha: str, artifact_path, artifact_sha256: str,
              manifest: dict, restart_fn, health_fn) -> dict:
    """Implements the full §16 success contract + §17 auto-rollback in one
    place. `restart_fn`/`health_fn` are zero-arg callables returning bool
    -- injected so this is testable without a real service or VM (§36:
    'restart failure triggers rollback', 'health failure triggers
    rollback', 'healthy deploy succeeds'). Never leaves a half-deployed
    release: every path ends in DEPLOYED, or FAILED with a rollback
    attempt recorded -- and per §17 ('restart service / run health again'),
    rollback itself re-runs restart_fn/health_fn against the RESTORED
    release, not just the symlink switch, recording that outcome as
    `rollback["rollback_health"]` (matches the Telegram result examples'
    own 'Rollback health: PASS' field)."""
    state = load_state(release_root, project)
    previous = state.get("current_release")

    install_release(release_root, project, git_sha, artifact_path, manifest)
    pre_verify = verify_artifact(release_root, project, git_sha, artifact_sha256)
    if not pre_verify["ok"]:
        return _fail_and_rollback(release_root, project, previous, "verify", pre_verify, restart_fn, health_fn)

    switch_current(release_root, project, git_sha)

    post_verify = verify_release(release_root, project, git_sha, artifact_sha256)
    if not post_verify["ok"]:
        return _fail_and_rollback(release_root, project, previous, "verify", post_verify, restart_fn, health_fn)

    if not restart_fn():
        return _fail_and_rollback(release_root, project, previous, "restart", {}, restart_fn, health_fn)

    if not health_fn():
        return _fail_and_rollback(release_root, project, previous, "health", {}, restart_fn, health_fn)

    _write_state(release_root, project, current_release=git_sha, previous_successful_release=git_sha,
                 last_deploy={"git_sha": git_sha, "result": "success", "at": _now()})
    return {"status": "DEPLOYED", "git_sha": git_sha}


def _fail_and_rollback(release_root, project: str, previous: str, failed_stage: str, detail: dict,
                       restart_fn=None, health_fn=None) -> dict:
    result = {"status": "FAILED", "failed_stage": failed_stage, "detail": detail}
    if previous is None:
        result["rollback"] = {"status": "NO_PREVIOUS_RELEASE"}
    else:
        rb = rollback(release_root, project, target_sha=previous)
        if rb["status"] == "ROLLED_BACK":
            # §17: rollback isn't just the symlink swap -- restart and
            # re-check health against the RESTORED release too, so a
            # rollback that lands on an equally-broken previous release
            # (e.g. the service itself won't start at all) is visible,
            # not silently reported as a clean recovery.
            restarted = restart_fn() if restart_fn else None
            healthy = health_fn() if health_fn else None
            rb["rollback_restarted"] = restarted
            rb["rollback_health"] = healthy
            if restarted is False or healthy is False:
                rb["status"] = "ROLLBACK_UNHEALTHY"
        result["rollback"] = rb
    _write_state(release_root, project,
                 last_deploy={"git_sha": None, "result": "failed", "failed_stage": failed_stage, "at": _now()})
    return result
