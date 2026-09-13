"""shiplib/schema.py — validates a project.yml against
schema/project.schema.json. Fail-closed: unknown fields and invalid
values both raise, never silently pass through (§5 of the Ship spec).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "project.schema.json"


class ProjectConfigError(ValueError):
    """Raised for any schema violation -- unknown field, wrong type,
    missing required field, or an invalid enum/pattern value."""


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_project_config(config: dict) -> None:
    """Raises ProjectConfigError with a readable message on any
    violation. Returns None (no value) on success."""
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
    if errors:
        messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
        raise ProjectConfigError("project.yml failed schema validation:\n  " + "\n  ".join(messages))


def load_project_config(path: Path) -> dict:
    """Loads and validates a project.yml file. Raises ProjectConfigError
    on any validation failure -- never returns a partially-valid config."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    validate_project_config(raw)
    return raw
