"""tests/test_release_ready_cli.py — shiplib.release_ready_cli enqueues a
JSON request for the daemon to pick up; it never talks to Telegram
itself (zero network access in this test).

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_release_ready_cli -v
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import shiplib.registry as registry
import shiplib.release_ready_cli as release_ready_cli


class TestReleaseReadyCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.release_root = self.tmp / "srv_apps"
        self._orig_registry_dir = registry.REGISTRY_DIR
        registry.REGISTRY_DIR = self.tmp
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "projects/personal/demo", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service", "approval": "telegram"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": str(self.release_root),
                       "allowed_projects": ["demo"]},
        }))

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_queues_a_request_file_with_the_right_fields(self):
        argv = ["release_ready_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", "abc", "--change-summary", "fixed the thing"]
        with mock.patch.object(sys, "argv", argv):
            exit_code = release_ready_cli.main()
        self.assertEqual(exit_code, 0)

        queued = list((self.release_root / "_telegram_queue").glob("*.json"))
        self.assertEqual(len(queued), 1)
        request = json.loads(queued[0].read_text())
        self.assertEqual(request["project"], "demo")
        self.assertEqual(request["git_sha"], "sha1")
        self.assertEqual(request["release_id"], "sha1")
        self.assertEqual(request["change_summary"], ["fixed the thing"])

    def test_unregistered_project_refused(self):
        argv = ["release_ready_cli.py", "--project", "ghost", "--repo", "me/ghost", "--git-sha", "sha1",
               "--artifact-sha256", "abc"]
        with mock.patch.object(sys, "argv", argv):
            exit_code = release_ready_cli.main()
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
