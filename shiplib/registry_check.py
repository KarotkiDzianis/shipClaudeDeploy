"""shiplib/registry_check.py — thin CLI wrapper around
shiplib.registry.authorize_deploy(), run as an early, fail-fast step by
the self-hosted deploy runner (§27) before any release mechanics are
attempted. `--repo` is read from GITHUB_REPOSITORY (set by the Actions
runtime itself for the repo the job is actually running in), never taken
as a caller-supplied flag -- there is nothing else for a workflow to
claim it with.

    PYTHONPATH=.. .venv/bin/python -m shiplib.registry_check \\
        --project demo --git-sha abc123
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from shiplib.registry import DeploymentRefused, authorize_deploy, load_projects, load_targets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--git-sha", required=True)
    args = ap.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"status": "REFUSED", "reason": f"'{args.project}' not in registry"}, indent=2))
        return 1

    entry = projects[args.project]
    targets = load_targets()
    release_root = targets.get(entry.get("target"), {}).get("release_root", "")

    try:
        auth = authorize_deploy(args.project, entry.get("target"), repo, entry.get("service"), release_root)
    except DeploymentRefused as e:
        print(json.dumps({"status": "REFUSED", "reason": str(e)}, indent=2))
        return 1

    print(json.dumps({"status": "OK", "git_sha": args.git_sha, **auth}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
