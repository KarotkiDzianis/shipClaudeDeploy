#!/usr/bin/env python3
"""deploy/run_deploy_cli.py — the real deploy entrypoint the self-hosted
runner invokes (§16/§17 full contract). Combines:
  1. a GitHub Actions job-context guard (§26/§36: "prod runner cannot run
     a PR job") -- refuses if GITHUB_EVENT_NAME looks like untrusted code
  2. shiplib.approval_persistence.is_approved_for() -- refuses unless
     Telegram recorded an "approved" decision for this EXACT git_sha
     (§24: a blocked or never-decided release must never deploy)
  3. shiplib.registry.authorize_deploy() -- fail-closed re-validation
  4. shiplib.release.run_deploy() -- install/verify/switch/restart/health
     with automatic rollback (and rollback-health-recheck) on any failure
  5. a real `systemctl restart <service>` as restart_fn, where <service>
     is ONLY ever the registry-authorized name, never a caller-supplied one
  6. the project's own `scripts/ship/health` as health_fn (§10: Ship core
     does not know what "healthy" means for any given project)

    PYTHONPATH=.. .venv/bin/python deploy/run_deploy_cli.py \\
        --project demo --repo me/demo --git-sha abc123 \\
        --artifact-sha256 <sha> --artifact-path artifact.tar.gz
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shiplib import release
from shiplib.approval_persistence import is_approved_for
from shiplib.registry import DeploymentRefused, authorize_deploy, load_projects, load_targets

UNTRUSTED_GITHUB_EVENTS = {"pull_request", "pull_request_target"}


def _refuse_if_untrusted_job_context() -> str | None:
    """§26/§36: the deploy runner must never execute a job triggered by a
    PR/untrusted-code event, even if somehow scheduled onto it. Returns a
    refusal reason, or None if the context is trusted (or this isn't
    running under GitHub Actions at all, e.g. local testing)."""
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name in UNTRUSTED_GITHUB_EVENTS:
        return f"refusing to deploy from a '{event_name}' job context -- deploy only runs for trusted main/release contexts"
    return None


def _systemctl_restart(service: str) -> bool:
    try:
        subprocess.run(["sudo", "systemctl", "restart", service], check=True, timeout=60)
        return True
    except Exception:
        return False


def _run_health_command(project_dir: Path) -> bool:
    try:
        result = subprocess.run(["bash", "scripts/ship/health"], cwd=project_dir, timeout=60)
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--artifact-sha256", required=True)
    ap.add_argument("--artifact-path", required=True)
    args = ap.parse_args()

    untrusted_reason = _refuse_if_untrusted_job_context()
    if untrusted_reason:
        print(json.dumps({"status": "REFUSED", "reason": untrusted_reason}, indent=2))
        return 1

    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"status": "REFUSED", "reason": f"'{args.project}' not in registry"}, indent=2))
        return 1
    entry = projects[args.project]
    targets = load_targets()
    release_root = targets.get(entry.get("target"), {}).get("release_root", "")

    try:
        auth = authorize_deploy(args.project, entry.get("target"), args.repo, entry.get("service"), release_root)
    except DeploymentRefused as e:
        print(json.dumps({"status": "REFUSED", "reason": str(e)}, indent=2))
        return 1

    approved, reason = is_approved_for(auth["release_root"], args.project, args.git_sha)
    if not approved:
        print(json.dumps({"status": "REFUSED", "reason": f"no valid Telegram approval: {reason}"}, indent=2))
        return 1

    manifest = {"release_id": args.git_sha, "project": args.project, "git_sha": args.git_sha,
               "artifact_sha256": args.artifact_sha256}
    project_dir = Path(__file__).resolve().parent.parent.parent.parent / entry["path"]

    result = release.run_deploy(
        auth["release_root"], args.project, args.git_sha, args.artifact_path, args.artifact_sha256, manifest,
        restart_fn=lambda: _systemctl_restart(auth["service"]),
        health_fn=lambda: _run_health_command(project_dir),
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "DEPLOYED" else 1


if __name__ == "__main__":
    sys.exit(main())
