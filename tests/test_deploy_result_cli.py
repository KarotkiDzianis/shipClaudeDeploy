"""tests/test_deploy_result_cli.py — shiplib.deploy_result_cli reports
the outcome shiplib.release.run_deploy() already recorded in state.json.
No SHIP_TELEGRAM_BOT_TOKEN configured (e.g. an automatic-approval sandbox
project with no Telegram wiring) must be a silent no-op, never a failure
-- only when a token IS configured does it attempt to actually send.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_deploy_result_cli -v
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import shiplib.deploy_result_cli as deploy_result_cli
import shiplib.registry as registry
from shiplib.release import _write_state


class TestDeployResultCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.release_root = self.tmp / "srv_apps"
        self._orig_registry_dir = registry.REGISTRY_DIR
        registry.REGISTRY_DIR = self.tmp
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "projects/personal/demo", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": str(self.release_root),
                       "allowed_projects": ["demo"]},
        }))
        self._orig_env = {k: os.environ.pop(k, None) for k in
                          ("SHIP_TELEGRAM_BOT_TOKEN", "SHIP_TELEGRAM_CHAT_ID")}

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        for k, v in self._orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_token_configured_is_a_silent_noop_not_a_failure(self):
        _write_state(self.release_root, "demo", last_deploy={"git_sha": "sha1", "result": "success"})
        argv = ["deploy_result_cli.py", "--project", "demo"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(deploy_result_cli.main(), 0)

    def test_token_configured_attempts_a_real_send(self):
        _write_state(self.release_root, "demo", last_deploy={"git_sha": "sha1", "result": "success"})
        os.environ["SHIP_TELEGRAM_BOT_TOKEN"] = "fake-token"
        os.environ["SHIP_TELEGRAM_CHAT_ID"] = "12345"
        argv = ["deploy_result_cli.py", "--project", "demo"]
        with mock.patch("telegram.approval_bot.client.TelegramClient") as MockClient:
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(deploy_result_cli.main(), 0)
            MockClient.return_value.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
