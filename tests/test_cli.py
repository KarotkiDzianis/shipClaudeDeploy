"""tests/test_cli.py — sanity coverage for `ship status`/`ship context`
against the real registry (read-only, no side effects) plus the missing-
project-yml graceful-failure path.

    PYTHONPATH=.. .venv/bin/python -m unittest tests.test_cli -v
"""
import unittest

from shiplib.cli import cmd_context, cmd_status


class TestCli(unittest.TestCase):
    def test_status_unknown_project_reports_cleanly(self):
        result = cmd_status("definitely-not-a-real-project")
        self.assertEqual(result["status"], "UNKNOWN_PROJECT")

    def test_status_known_project_without_project_yml_does_not_crash(self):
        # tradepulse is registered but (per §34) has deliberately not
        # adopted project.yml yet -- must degrade gracefully, not raise.
        result = cmd_status("tradepulse")
        self.assertIn("project_yml", result)
        self.assertIn("NOT_ADOPTED", result["project_yml"])

    def test_context_missing_project_yml_raises_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError):
            cmd_context("tradepulse")


if __name__ == "__main__":
    unittest.main()
