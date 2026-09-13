"""tests/test_schema.py — §36: project schema valid / unknown field
rejected / deploy disabled default.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_schema -v
"""
import copy
import unittest

from shiplib.schema import ProjectConfigError, validate_project_config

VALID = {
    "schema_version": 1,
    "project": {"slug": "demo-project", "name": "Demo Project", "type": "personal", "repo": "example/demo"},
    "context": {"claude_rules": "CLAUDE.md", "memory_index": "memory/MEMORY.md"},
    "skills": {"preferred": [], "domains": []},
    "ci": {"test": "scripts/ship/test", "build": "scripts/ship/build"},
    "deploy": {"enabled": False, "approval": "manual"},
    "health": {"command": "scripts/ship/health"},
}


class TestSchema(unittest.TestCase):
    def test_valid_config_passes(self):
        validate_project_config(copy.deepcopy(VALID))  # must not raise

    def test_unknown_top_level_field_rejected(self):
        cfg = copy.deepcopy(VALID)
        cfg["totally_unexpected_field"] = "value"
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_unknown_nested_field_rejected(self):
        cfg = copy.deepcopy(VALID)
        cfg["project"]["secret_api_key"] = "sk-should-never-be-here"
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_missing_required_field_rejected(self):
        cfg = copy.deepcopy(VALID)
        del cfg["project"]["slug"]
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_deploy_disabled_is_valid_without_target_or_service(self):
        cfg = copy.deepcopy(VALID)
        cfg["deploy"] = {"enabled": False, "approval": "manual"}
        validate_project_config(cfg)  # must not raise

    def test_deploy_enabled_requires_target_and_service(self):
        cfg = copy.deepcopy(VALID)
        cfg["deploy"] = {"enabled": True, "approval": "telegram"}  # missing target/service
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_deploy_enabled_with_target_and_service_is_valid(self):
        cfg = copy.deepcopy(VALID)
        cfg["deploy"] = {"enabled": True, "approval": "telegram", "target": "main-vm", "service": "demo.service"}
        validate_project_config(cfg)  # must not raise

    def test_invalid_approval_enum_rejected(self):
        cfg = copy.deepcopy(VALID)
        cfg["deploy"]["approval"] = "yolo"
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_invalid_slug_pattern_rejected(self):
        cfg = copy.deepcopy(VALID)
        cfg["project"]["slug"] = "Not Valid Slug!"
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)

    def test_wrong_schema_version_rejected(self):
        cfg = copy.deepcopy(VALID)
        cfg["schema_version"] = 2
        with self.assertRaises(ProjectConfigError):
            validate_project_config(cfg)


if __name__ == "__main__":
    unittest.main()
