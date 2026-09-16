"""tests/test_wait_for_approval_cli.py — the deploy job's approval gate:
skips immediately for a registry `approval: automatic` project, returns
APPROVED as soon as the daemon's approval.json says so, returns BLOCKED
on a recorded block, and times out (fast, using a short timeout) if
nothing is ever decided. No sleeping through the real POLL_SECONDS --
patched down for the test.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_wait_for_approval_cli -v
"""
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import yaml

import shiplib.registry as registry
import shiplib.wait_for_approval_cli as wait_for_approval_cli
from shiplib.approval_persistence import record_decision


class TestWaitForApprovalCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.release_root = self.tmp / "srv_apps"
        self._orig_registry_dir = registry.REGISTRY_DIR
        registry.REGISTRY_DIR = self.tmp
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "x", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service", "approval": "telegram"},
            "auto-demo": {"path": "x", "repo": "me/auto-demo", "deployment_allowed": True,
                         "target": "main-vm", "service": "auto-demo.service", "approval": "automatic"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": str(self.release_root),
                       "allowed_projects": ["demo", "auto-demo"]},
        }))

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_automatic_approval_project_skips_immediately(self):
        argv = ["wait_for_approval_cli.py", "--project", "auto-demo", "--git-sha", "sha1"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(wait_for_approval_cli.main(), 0)

    def test_already_approved_returns_immediately(self):
        record_decision(self.release_root, "demo", release_id="sha1", git_sha="sha1",
                        decision="approved", decided_by=111, decided_at=datetime.now(timezone.utc).isoformat())
        argv = ["wait_for_approval_cli.py", "--project", "demo", "--git-sha", "sha1"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(wait_for_approval_cli.main(), 0)

    def test_blocked_decision_returns_nonzero_without_waiting_out_the_timeout(self):
        record_decision(self.release_root, "demo", release_id="sha1", git_sha="sha1",
                        decision="blocked", decided_by=111, decided_at=datetime.now(timezone.utc).isoformat())
        argv = ["wait_for_approval_cli.py", "--project", "demo", "--git-sha", "sha1",
               "--timeout-seconds", "9999"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(wait_for_approval_cli.main(), 1)

    def test_times_out_when_nothing_is_ever_decided(self):
        argv = ["wait_for_approval_cli.py", "--project", "demo", "--git-sha", "sha1",
               "--timeout-seconds", "0"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(wait_for_approval_cli.time, "sleep"):
            self.assertEqual(wait_for_approval_cli.main(), 1)


if __name__ == "__main__":
    unittest.main()
