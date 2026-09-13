"""shiplib/registry.py — the CENTRAL authority (registry/projects.yml +
registry/targets.yml), not project.yml. A project's own project.yml can
ASK for a deploy target/service; this module is what actually GRANTS or
REFUSES it. Fail closed throughout: anything not explicitly listed here
is refused, never defaulted to allow (§8/§27 of the Ship spec).
"""
from __future__ import annotations

from pathlib import Path

import yaml

REGISTRY_DIR = Path(__file__).resolve().parent.parent / "registry"


class DeploymentRefused(ValueError):
    """Raised whenever a requested (project, target, service, repo)
    combination is not explicitly allowed by the central registry."""


def load_projects() -> dict:
    return yaml.safe_load((REGISTRY_DIR / "projects.yml").read_text()) or {}


def load_targets() -> dict:
    return yaml.safe_load((REGISTRY_DIR / "targets.yml").read_text()) or {}


def authorize_deploy(project_slug: str, requested_target: str, requested_repo: str,
                     requested_service: str, release_root: str) -> dict:
    """Validates a deploy request against the central registry. Even if a
    project's own project.yml is compromised/misconfigured, this is the
    server-side check the deploy runner must always re-run (§27) --
    returns the authorized {target, release_root} dict on success, or
    raises DeploymentRefused with the specific reason on any mismatch.
    Never partially authorizes: any single mismatch refuses the whole
    request.
    """
    projects = load_projects()
    targets = load_targets()

    if project_slug not in projects:
        raise DeploymentRefused(f"project '{project_slug}' is not listed in the central registry -- refusing")

    entry = projects[project_slug]
    if not entry.get("deployment_allowed", False):
        raise DeploymentRefused(f"project '{project_slug}' has deployment_allowed=false in the central registry")

    if entry.get("target") != requested_target:
        raise DeploymentRefused(
            f"project '{project_slug}' is only authorized for target '{entry.get('target')}', "
            f"not '{requested_target}'")

    if entry.get("service") != requested_service:
        raise DeploymentRefused(
            f"project '{project_slug}' is only authorized to manage service '{entry.get('service')}', "
            f"not '{requested_service}'")

    if requested_target not in targets:
        raise DeploymentRefused(f"target '{requested_target}' is not defined in registry/targets.yml")

    target_entry = targets[requested_target]
    if project_slug not in target_entry.get("allowed_projects", []):
        raise DeploymentRefused(
            f"target '{requested_target}' does not list '{project_slug}' in its allowed_projects")

    registry_repo = entry.get("repo", "")
    if registry_repo.startswith("TBD"):
        raise DeploymentRefused(
            f"project '{project_slug}' has no real repo registered yet (registry value: {registry_repo!r}) "
            f"-- refusing until the registry is updated with a real repo")
    if requested_repo != registry_repo:
        raise DeploymentRefused(
            f"requested repo '{requested_repo}' does not match the registry's repo for "
            f"'{project_slug}' ('{registry_repo}')")

    allowed_release_root = target_entry.get("release_root", "")
    requested_root = Path(release_root).resolve()
    allowed_root = Path(allowed_release_root).resolve()
    try:
        requested_root.relative_to(allowed_root)
    except ValueError:
        raise DeploymentRefused(
            f"requested release_root '{release_root}' escapes the target's allowed release_root "
            f"'{allowed_release_root}' -- refusing (path traversal guard)")

    return {"target": requested_target, "release_root": str(allowed_root), "service": requested_service}
