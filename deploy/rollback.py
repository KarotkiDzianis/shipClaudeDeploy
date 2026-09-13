#!/usr/bin/env python3
"""deploy/rollback.py — thin CLI over shiplib.release.rollback. Switches
`current` back to the previous_successful_release (or an explicit
--target-sha) and records the attempt (§17).

    PYTHONPATH=.. .venv/bin/python deploy/rollback.py --project demo
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
    ap.add_argument("--target-sha", default=None, help="defaults to the recorded previous_successful_release")
    args = ap.parse_args()

    projects = load_projects()
    if args.project not in projects:
        print(json.dumps({"status": "ROLLBACK_FAILED", "reason": f"'{args.project}' is not in the central registry"}, indent=2))
        return 1
    targets = load_targets()
    release_root = targets.get(projects[args.project].get("target"), {}).get("release_root")
    if not release_root:
        print(json.dumps({"status": "ROLLBACK_FAILED", "reason": "no target/release_root configured"}, indent=2))
        return 1

    result = release.rollback(release_root, args.project, target_sha=args.target_sha)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ROLLED_BACK" else 1


if __name__ == "__main__":
    sys.exit(main())
