"""tests/test_registry_check_cli.py — shiplib.registry_check is the
early fail-fast step the self-hosted runner takes before attempting any
release mechanics (§27): authorized project/repo prints OK, anything the
central registry refuses exits non-zero with the reason, and the repo
comes only from GITHUB_REPOSITORY (never a caller-supplied flag).

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_registry_check_cli -v
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import shiplib.registry as registry
import shiplib.registry_check as registry_check


class TestRegistryCheckCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig_registry_dir = registry.REGISTRY_DIR
        registry.REGISTRY_DIR = self.tmp
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "projects/personal/demo", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": str(self.tmp / "srv_apps"),
                       "allowed_projects": ["demo"]},
        }))
        self._orig_repo_env = os.environ.pop("GITHUB_REPOSITORY", None)

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        if self._orig_repo_env is not None:
            os.environ["GITHUB_REPOSITORY"] = self._orig_repo_env
        else:
            os.environ.pop("GITHUB_REPOSITORY", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_authorized_project_and_matching_repo_ok(self):
        os.environ["GITHUB_REPOSITORY"] = "me/demo"
        argv = ["registry_check.py", "--project", "demo", "--git-sha", "sha1"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(registry_check.main(), 0)

    def test_repo_mismatch_refused(self):
        os.environ["GITHUB_REPOSITORY"] = "attacker/fake"
        argv = ["registry_check.py", "--project", "demo", "--git-sha", "sha1"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(registry_check.main(), 1)

    def test_unknown_project_refused(self):
        os.environ["GITHUB_REPOSITORY"] = "me/demo"
        argv = ["registry_check.py", "--project", "ghost", "--git-sha", "sha1"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(registry_check.main(), 1)


if __name__ == "__main__":
    unittest.main()
