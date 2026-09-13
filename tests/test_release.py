"""tests/test_release.py — §36: artifact SHA mismatch rejected / release
SHA mismatch rejected / healthy deploy succeeds / restart failure triggers
rollback / health failure triggers rollback / rollback health check.

Runs entirely against a local temp directory standing in for
`/srv/apps/<project>` -- no real VM/service anywhere.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_release -v
"""
import hashlib
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

from shiplib import release


_artifact_counter = 0


def _make_artifact(tmp: Path, content: str = "hello ship") -> tuple[Path, str]:
    global _artifact_counter
    _artifact_counter += 1
    src_dir = tmp / f"artifact_src_{_artifact_counter}"
    src_dir.mkdir()
    (src_dir / "app.txt").write_text(content)
    artifact_path = tmp / f"artifact_{_artifact_counter}.tar.gz"
    with tarfile.open(artifact_path, "w:gz") as tf:
        tf.add(src_dir / "app.txt", arcname="app.txt")
    sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    return artifact_path, sha256


class TestRelease(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.release_root = self.tmp / "srv_apps"
        self.project = "demo"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_and_verify_succeeds_with_correct_sha(self):
        artifact_path, sha256 = _make_artifact(self.tmp)
        manifest = {"release_id": "r1", "project": self.project, "git_sha": "abc123", "artifact_sha256": sha256}
        release.install_release(self.release_root, self.project, "abc123", artifact_path, manifest)
        release.switch_current(self.release_root, self.project, "abc123")
        result = release.verify_release(self.release_root, self.project, "abc123", sha256)
        self.assertTrue(result["ok"], result)
        self.assertTrue(all(result["checks"].values()))

    def test_verify_fails_on_artifact_sha_mismatch(self):
        artifact_path, sha256 = _make_artifact(self.tmp)
        manifest = {"release_id": "r1", "project": self.project, "git_sha": "abc123", "artifact_sha256": sha256}
        release.install_release(self.release_root, self.project, "abc123", artifact_path, manifest)
        release.switch_current(self.release_root, self.project, "abc123")
        result = release.verify_release(self.release_root, self.project, "abc123", "0" * 64)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["artifact_sha256_matches"])

    def test_verify_fails_on_corrupted_release_sha_file(self):
        """Distinct from 'not installed at all' -- the release DIRECTORY
        exists (correctly named), but its RELEASE_SHA file's own content
        has been tampered with/corrupted, no longer matching the directory
        name it lives in."""
        artifact_path, sha256 = _make_artifact(self.tmp)
        manifest = {"release_id": "r1", "git_sha": "abc123", "artifact_sha256": sha256}
        release.install_release(self.release_root, self.project, "abc123", artifact_path, manifest)
        (self.release_root / self.project / "releases" / "abc123" / "RELEASE_SHA").write_text("corrupted-value")
        result = release.verify_release(self.release_root, self.project, "abc123", sha256)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["release_sha_matches"])

    def test_verify_fails_when_release_sha_not_installed(self):
        result = release.verify_release(self.release_root, self.project, "never-installed", "irrelevant")
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["release_dir_exists"])

    def test_healthy_deploy_succeeds(self):
        artifact_path, sha256 = _make_artifact(self.tmp)
        manifest = {"release_id": "r1", "project": self.project, "git_sha": "sha1", "artifact_sha256": sha256}
        result = release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                                    restart_fn=lambda: True, health_fn=lambda: True)
        self.assertEqual(result["status"], "DEPLOYED")
        state = release.load_state(self.release_root, self.project)
        self.assertEqual(state["current_release"], "sha1")
        self.assertEqual(state["previous_successful_release"], "sha1")

    def test_restart_failure_triggers_rollback_to_previous_and_rollback_itself_is_healthy(self):
        """§17: rollback isn't just the symlink swap -- it restarts and
        re-checks health against the RESTORED release too. A realistic
        `restart_fn` doesn't know or care which release is symlinked (it's
        just `systemctl restart <service>`) -- only the BROKEN v2 fails to
        start; v1 restarts fine once rolled back to, same as it did on its
        own original deploy."""
        artifact_path, sha256 = _make_artifact(self.tmp, "v1")
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        first = release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                                   restart_fn=lambda: True, health_fn=lambda: True)
        self.assertEqual(first["status"], "DEPLOYED")

        artifact2, sha2 = _make_artifact(self.tmp, "v2-broken")
        manifest2 = {"release_id": "r2", "git_sha": "sha2", "artifact_sha256": sha2}
        calls = {"n": 0}

        def flaky_restart():
            calls["n"] += 1
            return calls["n"] > 1  # fails on the v2 attempt, succeeds on the post-rollback re-check

        second = release.run_deploy(self.release_root, self.project, "sha2", artifact2, sha2, manifest2,
                                    restart_fn=flaky_restart, health_fn=lambda: True)
        self.assertEqual(second["status"], "FAILED")
        self.assertEqual(second["failed_stage"], "restart")
        self.assertEqual(second["rollback"]["status"], "ROLLED_BACK")
        self.assertEqual(second["rollback"]["restored_sha"], "sha1")
        self.assertTrue(second["rollback"]["rollback_restarted"])
        self.assertTrue(second["rollback"]["rollback_health"])

        current = self.release_root / self.project / "current"
        self.assertEqual(current.resolve().name, "sha1")

    def test_health_failure_triggers_rollback(self):
        artifact_path, sha256 = _make_artifact(self.tmp, "v1")
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                           restart_fn=lambda: True, health_fn=lambda: True)

        artifact2, sha2 = _make_artifact(self.tmp, "v2-unhealthy")
        manifest2 = {"release_id": "r2", "git_sha": "sha2", "artifact_sha256": sha2}
        calls = {"n": 0}

        def flaky_health():
            calls["n"] += 1
            return calls["n"] > 1  # v2 unhealthy, v1 healthy again once restored

        second = release.run_deploy(self.release_root, self.project, "sha2", artifact2, sha2, manifest2,
                                    restart_fn=lambda: True, health_fn=flaky_health)
        self.assertEqual(second["failed_stage"], "health")
        self.assertEqual(second["rollback"]["restored_sha"], "sha1")
        self.assertTrue(second["rollback"]["rollback_health"])

    def test_rollback_that_is_itself_unhealthy_is_reported_not_hidden(self):
        """If the whole target is broken regardless of release (e.g. the
        VM/service itself is down), rollback must say so distinctly --
        never silently report a clean 'ROLLED_BACK' when the restored
        release isn't actually healthy either."""
        artifact_path, sha256 = _make_artifact(self.tmp, "v1")
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                           restart_fn=lambda: True, health_fn=lambda: True)

        artifact2, sha2 = _make_artifact(self.tmp, "v2-broken")
        manifest2 = {"release_id": "r2", "git_sha": "sha2", "artifact_sha256": sha2}
        second = release.run_deploy(self.release_root, self.project, "sha2", artifact2, sha2, manifest2,
                                    restart_fn=lambda: True, health_fn=lambda: False)  # NEVER healthy, even post-rollback
        self.assertEqual(second["rollback"]["status"], "ROLLBACK_UNHEALTHY")
        self.assertFalse(second["rollback"]["rollback_health"])

    def test_first_ever_deploy_failure_has_no_previous_to_roll_back_to(self):
        artifact_path, sha256 = _make_artifact(self.tmp, "v1-broken")
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        result = release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                                    restart_fn=lambda: False, health_fn=lambda: True)
        self.assertEqual(result["rollback"]["status"], "NO_PREVIOUS_RELEASE")

    def test_rollback_health_check_is_the_callers_responsibility_and_reflected_in_result(self):
        artifact_path, sha256 = _make_artifact(self.tmp, "v1")
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        release.run_deploy(self.release_root, self.project, "sha1", artifact_path, sha256, manifest,
                           restart_fn=lambda: True, health_fn=lambda: True)
        result = release.rollback(self.release_root, self.project)
        self.assertEqual(result["status"], "ROLLED_BACK")
        state = release.load_state(self.release_root, self.project)
        self.assertEqual(state["last_rollback"]["result"], "success")

    def test_current_symlink_never_missing_between_deploys(self):
        """§15: switching current is atomic -- there should never be a
        moment where `current` doesn't exist once a first release lands."""
        artifact_path, sha256 = _make_artifact(self.tmp)
        manifest = {"release_id": "r1", "git_sha": "sha1", "artifact_sha256": sha256}
        release.install_release(self.release_root, self.project, "sha1", artifact_path, manifest)
        release.switch_current(self.release_root, self.project, "sha1")
        current = self.release_root / self.project / "current"
        self.assertTrue(current.is_symlink())
        release.switch_current(self.release_root, self.project, "sha1")  # idempotent re-switch
        self.assertTrue(current.is_symlink())


if __name__ == "__main__":
    unittest.main()
