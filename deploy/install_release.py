#!/usr/bin/env python3
"""deploy/install_release.py — thin CLI over shiplib.release.install_release.
Extracts an artifact into releases/<git_sha>/ without touching `current`
(§15). Re-validates the request against the central registry first (§27)
-- target/release_root are always resolved from the registry itself, the
CLI cannot be pointed at an arbitrary path.

    PYTHONPATH=.. .venv/bin/python deploy/install_release.py \\
        --project demo --repo me/demo --service demo.service \\
        --git-sha abc123 --artifact-sha256 <sha> --artifact-path artifact.tar.gz
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shiplib import release
from shiplib.registry import DeploymentRefused, authorize_deploy, load_projects, load_targets


def resolve_and_authorize(project: str, repo: str, service: str):
    projects = load_projects()
    if project not in projects:
        raise DeploymentRefused(f"'{project}' is not in the central registry")
    target_name = projects[project].get("target")
    targets = load_targets()
    release_root = targets.get(target_name, {}).get("release_root", "")
    return authorize_deploy(project, target_name, repo, service, release_root)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--artifact-sha256", required=True)
    ap.add_argument("--artifact-path", required=True)
    ap.add_argument("--release-id", default=None)
    args = ap.parse_args()

    try:
        auth = resolve_and_authorize(args.project, args.repo, args.service)
    except DeploymentRefused as e:
        print(json.dumps({"status": "REFUSED", "reason": str(e)}, indent=2))
        return 1

    manifest = {
        "release_id": args.release_id or args.git_sha,
        "project": args.project,
        "git_sha": args.git_sha,
        "artifact_sha256": args.artifact_sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    release_dir = release.install_release(auth["release_root"], args.project, args.git_sha,
                                          args.artifact_path, manifest)
    print(json.dumps({"status": "INSTALLED", "release_dir": str(release_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
