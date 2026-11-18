"""Tests for what the `snyk-seen` hook says after it records a scan: with Snyk required, the Security gate's verdict
on the code as it is now, so the chair sees it when Verify runs the scans. They run plugins/sdlc/hooks/sdlc_gate.py as
Claude Code runs it (JSON on stdin). Whether Claude Code passes a PostToolUse reply for an MCP tool on to the model is
not shown here; the close denial carries the same text.

Run: python3 -m unittest discover -s tests
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support.paths import HOOKS
from support.snyk_base import HIGH, SnykCloseTest

sys.path.append(str(HOOKS))


class ScanVerdictTest(SnykCloseTest):
    def spoken(self, done):
        return json.loads(done.stdout)

    def test_a_blocking_finding_in_the_change_is_reported_to_the_model_and_the_owner(self):
        self.snyk_on_and_approved()
        self.edit_code()
        said = self.spoken(self.seen(issues=(HIGH,)))
        self.assertIn("Security gate: BLOCK", said["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Security gate: BLOCK", said["systemMessage"])

    def test_the_reply_names_the_event_it_answers(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertEqual(self.spoken(self.seen(issues=(HIGH,)))["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_a_scan_that_finds_nothing_in_a_changed_file_reports_a_pass(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertIn("Security gate: PASS", self.context(self.seen(issues=())))

    def test_while_a_required_scan_has_not_run_yet_the_hook_names_it_without_a_verdict(self):
        self.snyk_on_and_approved()
        self.edit_code()
        (self.project / "requirements.txt").write_text("flask==1\n")
        said = self.context(self.seen(issues=()))
        self.assertIn("Security gate: waiting - sca: not run", said)
        self.assertNotIn("INCOMPLETE", said)

    def test_the_last_required_scan_reports_the_verdict(self):
        self.snyk_on_and_approved()
        self.edit_code()
        (self.project / "requirements.txt").write_text("flask==1\n")
        self.seen(issues=())
        whole = {"path": str(self.project), "all_projects": True}
        self.assertIn("Security gate: PASS", self.context(self.seen(tool="snyk_sca_scan", tool_input=whole, issues=())))

    def test_the_scan_is_recorded_whatever_the_reply_says(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        self.assertEqual(self.state()["scans"]["code"]["status"], "completed")

    def test_with_snyk_undecided_the_hook_says_nothing(self):
        self.assertEqual(self.seen(issues=(HIGH,)).stdout, "")

    def test_with_snyk_off_the_hook_says_nothing(self):
        self.prompt("sdlc snyk off")
        self.assertEqual(self.seen(issues=(HIGH,)).stdout, "")


class RecordedBeforeTheVerdictTest(unittest.TestCase):
    """In this process, so that an error can be made inside the verdict that no input to the script could make. They
    call `record_scan` with a real host, so they show the order of the steps and not what the live host sends."""

    def setUp(self):
        self.gate = importlib.import_module("sdlc_hooks.snyk_gate")
        self.state = importlib.import_module("sdlc_hooks.snyk_state")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name, "project")
        self.project.mkdir()
        patched = mock.patch.dict(os.environ, {"SDLC_GATE_HOME": str(Path(self.tmp.name, "home")),
                                               "CLAUDE_PROJECT_DIR": str(self.project)})
        patched.start()
        self.addCleanup(patched.stop)
        (self.project / "app.py").write_text("x = 1\n")
        for args in (("init", "-q"), ("add", "app.py"), ("commit", "-q", "-m", "first")):
            subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=n", *args], cwd=self.project, check=True,
                           capture_output=True)
        self.path = self.state.snyk_state_path(self.project)
        self.state.write_snyk_state(self.path, {**self.state.read_snyk_state(self.path), "policy": "on"})
        reply = {"success": True, "issueCount": 0, "issues": []}
        self.event = {"cwd": str(self.project), "session_id": "s1", "hook_event_name": "PostToolUse",
                      "mcp_server": {"name": "Snyk Security", "source": "sdk"},
                      "tool_name": "mcp__Snyk_Security__snyk_code_scan", "tool_input": {"path": str(self.project)},
                      "tool_response": [{"type": "text", "text": json.dumps(reply)}]}

    def record(self):
        return self.gate.load_sibling("snyk/record").record_scan(self.gate.snyk_host(), self.event)

    def test_a_verdict_that_fails_leaves_the_scan_recorded_and_says_nothing(self):
        with mock.patch.object(self.gate.load_sibling("security_gate"), "evaluate", side_effect=RuntimeError("boom")):
            line = self.record()
        self.assertEqual((line, self.state.read_snyk_state(self.path)["scans"]["code"]["status"]), ("", "completed"))

    def test_with_no_base_pinned_the_verdict_says_the_changed_files_are_unknown(self):
        self.assertIn("changed files: no base commit is pinned", self.record())

    def test_a_failed_clear_at_an_approval_tells_the_owner_the_old_acceptances_still_stand(self):
        with mock.patch.object(self.gate.load_sibling("snyk/record"), "reset_accepted", side_effect=RuntimeError("boom")):
            note = self.gate.clear_snyk_accepted(self.project)
        self.assertIn("still stand", note)


if __name__ == "__main__":
    unittest.main()
