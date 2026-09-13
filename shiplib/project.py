"""shiplib/project.py — resolves one project's own project.yml plus the
context paths it points at (CLAUDE.md, memory/, graphify-out/, ...).
Pure path/config discovery -- no LLM framework, no interpretation of the
content (§32 of the Ship spec: "just context discovery").
"""
from __future__ import annotations

from pathlib import Path

from shiplib.schema import load_project_config

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # .../claude/


def project_dir(slug: str) -> Path:
    from shiplib.registry import load_projects
    projects = load_projects()
    if slug not in projects:
        raise KeyError(f"'{slug}' is not a known project (not in registry/projects.yml)")
    return WORKSPACE_ROOT / projects[slug]["path"]


def load_project(slug: str) -> dict:
    """Loads and validates <project_dir>/project.yml."""
    path = project_dir(slug) / "project.yml"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- this project has not adopted the Ship contract yet")
    return load_project_config(path)


def resolve_context(slug: str) -> dict:
    """§32: returns absolute paths for every context field a project.yml
    declares, plus the two ALWAYS-global files (workspace CLAUDE.md and
    this project's own CLAUDE.md), and skill hints. Missing optional
    fields are simply absent from the result -- never fabricated."""
    pdir = project_dir(slug)
    config = load_project(slug)
    context_cfg = config["context"]

    result = {
        "project_dir": str(pdir),
        "global_claude_md": str(WORKSPACE_ROOT / "CLAUDE.md"),
        "project_claude_md": str(pdir / context_cfg["claude_rules"]),
        "memory_index": str(pdir / context_cfg["memory_index"]),
        "skills_preferred": config["skills"]["preferred"],
        "skills_domains": config["skills"]["domains"],
    }
    for optional in ("project_goals", "decisions", "blockers", "graph"):
        if optional in context_cfg:
            result[optional] = str(pdir / context_cfg[optional])
    return result
