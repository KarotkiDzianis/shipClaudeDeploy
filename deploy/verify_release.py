#!/usr/bin/env python3
"""deploy/verify_release.py — thin CLI over shiplib.release.verify_release
(the FULL post-switch §16 contract, including the `current` symlink
check).

    PYTHONPATH=.. .venv/bin/python deploy/verify_release.py \\
        --project demo --git-sha abc123 --artifact-sha256 <sha>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shiplib import release
from shiplib.registry import load_projects, load_targets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--artifact-sha256", required=True)
    args = ap.parse_args()

    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"ok": False, "reason": f"'{args.project}' is not in the central registry"}, indent=2))
        return 1
    targets = load_targets()
    release_root = targets.get(projects[args.project].get("target"), {}).get("release_root")
    if not release_root:
        print(json.dumps({"ok": False, "reason": "no target/release_root configured for this project"}, indent=2))
        return 1

    result = release.verify_release(release_root, args.project, args.git_sha, args.artifact_sha256)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
