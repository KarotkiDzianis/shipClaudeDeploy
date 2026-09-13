"""tests/test_registry.py — §36: central registry overrides project
request / wrong repo rejected / wrong service rejected / path traversal
rejected, plus the base allow/deny cases.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_registry -v
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import shiplib.registry as registry
from shiplib.registry import DeploymentRefused, authorize_deploy


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig_registry_dir = registry.REGISTRY_DIR
        registry.REGISTRY_DIR = self.tmp
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "projects/personal/demo", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service"},
            "locked": {"path": "projects/personal/locked", "repo": "me/locked", "deployment_allowed": False,
                      "target": "main-vm", "service": "locked.service"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": "/srv/apps",
                       "allowed_projects": ["demo"]},
        }))

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_request_authorized(self):
        result = authorize_deploy("demo", "main-vm", "me/demo", "demo.service", "/srv/apps/demo/releases")
        self.assertEqual(result["target"], "main-vm")

    def test_unknown_project_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("ghost", "main-vm", "me/ghost", "ghost.service", "/srv/apps/ghost")

    def test_deployment_allowed_false_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("locked", "main-vm", "me/locked", "locked.service", "/srv/apps/locked")

    def test_project_not_in_target_allowed_projects_refused(self):
        # "locked" is deployment_allowed=True at the project level, but
        # main-vm's own allowed_projects list doesn't include it --
        # the target's own allowlist must independently refuse it.
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "locked": {"path": "x", "repo": "me/locked", "deployment_allowed": True,
                      "target": "main-vm", "service": "locked.service"},
        }))
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("locked", "main-vm", "me/locked", "locked.service", "/srv/apps/locked")

    def test_wrong_target_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("demo", "some-other-vm", "me/demo", "demo.service", "/srv/apps/demo")

    def test_wrong_repo_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("demo", "main-vm", "attacker/fake-demo", "demo.service", "/srv/apps/demo")

    def test_wrong_service_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("demo", "main-vm", "me/demo", "some-other.service", "/srv/apps/demo")

    def test_path_traversal_release_root_refused(self):
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("demo", "main-vm", "me/demo", "demo.service", "/srv/apps/../etc")

    def test_unregistered_repo_placeholder_refused(self):
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "x", "repo": "TBD -- no git repository exists yet", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service"},
        }))
        with self.assertRaises(DeploymentRefused):
            authorize_deploy("demo", "main-vm", "TBD -- no git repository exists yet", "demo.service", "/srv/apps/demo")


if __name__ == "__main__":
    unittest.main()
