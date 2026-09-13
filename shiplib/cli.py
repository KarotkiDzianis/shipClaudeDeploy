"""shiplib/cli.py — status + context discovery logic (§31/§32 of the Ship
spec). No LLM framework, no deploy side effects -- pure read-only
discovery over project.yml/registry/release state. `cli/ship` is a thin
executable wrapper around `main()` below, kept separate so this logic is
directly importable and testable.
"""
from __future__ import annotations

import argparse
import json

from shiplib import project as project_mod
from shiplib import release as release_mod
from shiplib.registry import load_projects, load_targets


def cmd_status(slug: str) -> dict:
    projects = load_projects()
    if slug not in projects:
        return {"project": slug, "status": "UNKNOWN_PROJECT",
                "reason": "not listed in registry/projects.yml"}

    entry = projects[slug]
    result = {"project": slug, "repo": entry.get("repo"), "deployment_allowed": entry.get("deployment_allowed", False)}

    try:
        config = project_mod.load_project(slug)
        result["ci"] = config["ci"]
        result["deploy_enabled"] = config["deploy"]["enabled"]
    except FileNotFoundError:
        result["project_yml"] = "NOT_ADOPTED (no project.yml yet)"
        return result
    except Exception as e:
        result["project_yml"] = f"ISSUE: {type(e).__name__}: {e}"
        return result

    target_name = entry.get("target")
    targets = load_targets()
    release_root = targets.get(target_name, {}).get("release_root") if target_name else None
    if not release_root:
        result["release_state"] = "NO_TARGET_CONFIGURED"
        return result

    state = release_mod.load_state(release_root, slug)
    result["current_deployed_sha"] = state.get("current_release")
    result["previous_successful_release"] = state.get("previous_successful_release")
    result["last_deploy"] = state.get("last_deploy")
    result["last_health"] = state.get("last_health")
    result["last_rollback"] = state.get("last_rollback")
    if state.get("current_release") is None:
        result["note"] = "no deploy has ever run for this project through Ship yet"
    return result


def cmd_context(slug: str) -> dict:
    return project_mod.resolve_context(slug)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ship")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status", help="show a project's deploy status")
    status_p.add_argument("project")

    context_p = sub.add_parser("context", help="show a project's context file paths")
    context_p.add_argument("project")

    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = cmd_status(args.project)
        else:
            result = cmd_context(args.project)
    except (KeyError, FileNotFoundError) as e:
        print(json.dumps({"status": "ISSUE", "reason": str(e)}, indent=2))
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0
