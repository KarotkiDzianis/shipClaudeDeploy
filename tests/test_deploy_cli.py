"""tests/test_deploy_cli.py — §36: prod runner cannot run an unauthorized
deploy (wrong repo refused before touching release mechanics) / prod
runner cannot run a PR job / a release without a matching Telegram
approval is refused / a full authorized+approved deploy succeeds end to
end with a faked systemctl+health.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_deploy_cli -v
"""
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import yaml

import deploy.run_deploy_cli as run_deploy_cli
import shiplib.registry as registry
from shiplib import release
from shiplib.approval_persistence import record_decision


def _make_artifact(tmp: Path) -> tuple[Path, str]:
    src = tmp / "src"
    src.mkdir()
    (src / "app.txt").write_text("hello")
    artifact = tmp / "artifact.tar.gz"
    with tarfile.open(artifact, "w:gz") as tf:
        tf.add(src / "app.txt", arcname="app.txt")
    return artifact, hashlib.sha256(artifact.read_bytes()).hexdigest()


class TestRunDeployCli(unittest.TestCase):
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
        self._orig_github_event = os.environ.pop("GITHUB_EVENT_NAME", None)

    def tearDown(self):
        registry.REGISTRY_DIR = self._orig_registry_dir
        if self._orig_github_event is not None:
            os.environ["GITHUB_EVENT_NAME"] = self._orig_github_event
        else:
            os.environ.pop("GITHUB_EVENT_NAME", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _approve(self, git_sha: str, decision: str = "approved"):
        record_decision(self.release_root, "demo", release_id=git_sha, git_sha=git_sha,
                        decision=decision, decided_by=111, decided_at=datetime.now(timezone.utc).isoformat())

    def test_wrong_repo_refused_before_touching_release_mechanics(self):
        artifact, sha256 = _make_artifact(self.tmp)
        self._approve("sha1")
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "attacker/fake", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)
        self.assertFalse((self.release_root / "demo" / "releases").exists())

    def test_deploy_refused_without_any_recorded_approval(self):
        artifact, sha256 = _make_artifact(self.tmp)
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)
        self.assertFalse((self.release_root / "demo" / "releases").exists())

    def test_deploy_refused_when_decision_is_blocked(self):
        artifact, sha256 = _make_artifact(self.tmp)
        self._approve("sha1", decision="blocked")
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)

    def test_deploy_refused_when_approval_is_for_a_different_git_sha(self):
        artifact, sha256 = _make_artifact(self.tmp)
        self._approve("some-other-sha")  # approved a DIFFERENT release
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)

    def test_deploy_refused_when_triggered_from_a_pull_request_job(self):
        artifact, sha256 = _make_artifact(self.tmp)
        self._approve("sha1")
        os.environ["GITHUB_EVENT_NAME"] = "pull_request"
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)
        self.assertFalse((self.release_root / "demo" / "releases").exists())

    def test_automatic_approval_project_deploys_without_any_recorded_decision(self):
        """§'approval mode is a central registry decision, not project.yml's
        own claim': a project the REGISTRY marks approval: automatic must
        deploy with zero recorded approval decisions -- and a project NOT
        marked automatic (the `demo` project used by every other test in
        this file) must still be refused without one (already covered
        above), proving this is opt-in per project, not a global bypass."""
        (self.tmp / "projects.yml").write_text(yaml.dump({
            "demo": {"path": "projects/personal/demo", "repo": "me/demo", "deployment_allowed": True,
                    "target": "main-vm", "service": "demo.service"},
            "auto-demo": {"path": "projects/personal/auto-demo", "repo": "me/auto-demo",
                         "deployment_allowed": True, "target": "main-vm", "service": "auto-demo.service",
                         "approval": "automatic"},
        }))
        (self.tmp / "targets.yml").write_text(yaml.dump({
            "main-vm": {"runner_labels": ["self-hosted"], "release_root": str(self.release_root),
                       "allowed_projects": ["demo", "auto-demo"]},
        }))
        artifact, sha256 = _make_artifact(self.tmp)
        argv = ["run_deploy_cli.py", "--project", "auto-demo", "--repo", "me/auto-demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(run_deploy_cli, "_systemctl_restart", return_value=True), \
             mock.patch.object(run_deploy_cli, "_run_health_command", return_value=True), \
             mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 0)
        state = release.load_state(self.release_root, "auto-demo")
        self.assertEqual(state["current_release"], "sha1")

    def test_authorized_and_approved_deploy_succeeds_with_faked_systemctl_and_health(self):
        artifact, sha256 = _make_artifact(self.tmp)
        self._approve("sha1")
        argv = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
               "--artifact-sha256", sha256, "--artifact-path", str(artifact)]
        with mock.patch.object(run_deploy_cli, "_systemctl_restart", return_value=True), \
             mock.patch.object(run_deploy_cli, "_run_health_command", return_value=True), \
             mock.patch.object(sys, "argv", argv):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 0)
        state = release.load_state(self.release_root, "demo")
        self.assertEqual(state["current_release"], "sha1")

    def test_failed_health_check_triggers_rollback_via_cli(self):
        artifact1, sha1 = _make_artifact(self.tmp)
        self._approve("sha1")
        argv1 = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha1",
                "--artifact-sha256", sha1, "--artifact-path", str(artifact1)]
        with mock.patch.object(run_deploy_cli, "_systemctl_restart", return_value=True), \
             mock.patch.object(run_deploy_cli, "_run_health_command", return_value=True), \
             mock.patch.object(sys, "argv", argv1):
            self.assertEqual(run_deploy_cli.main(), 0)

        tmp2 = self.tmp / "second"
        tmp2.mkdir()
        artifact2, sha2 = _make_artifact(tmp2)
        self._approve("sha2")
        argv2 = ["run_deploy_cli.py", "--project", "demo", "--repo", "me/demo", "--git-sha", "sha2",
                "--artifact-sha256", sha2, "--artifact-path", str(artifact2)]
        with mock.patch.object(run_deploy_cli, "_systemctl_restart", return_value=True), \
             mock.patch.object(run_deploy_cli, "_run_health_command", return_value=False), \
             mock.patch.object(sys, "argv", argv2):
            exit_code = run_deploy_cli.main()
        self.assertEqual(exit_code, 1)
        state = release.load_state(self.release_root, "demo")
        self.assertEqual(state["current_release"], "sha1")  # rolled back


if __name__ == "__main__":
    unittest.main()
