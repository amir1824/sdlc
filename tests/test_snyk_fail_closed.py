"""Tests that the Snyk close gate holds a write when it cannot be checked (a module that does not load, a record that
cannot be parsed, a repo git cannot read) and that it never touches a project where Snyk is off or undecided.

Run: python3 -I -m unittest discover -s tests
Some tests call plugins/sdlc/hooks/sdlc_gate.py in this process so that an error can be made in it that no input to
the script could make.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_sdlc_gate import SCRIPT
from test_sdlc_gate_snyk import GATE_TAG, SnykCloseTest


class FailClosedInProcessTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("sdlc_gate_under_test", SCRIPT)
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name, "project")
        self.project.mkdir()
        patched = mock.patch.dict(os.environ, {"SDLC_GATE_HOME": str(Path(self.tmp.name, "home")),
                                               "CLAUDE_PROJECT_DIR": str(self.project)})
        patched.start()
        self.addCleanup(patched.stop)
        self.event = {"cwd": str(self.project), "session_id": "s1"}
        self.status = str(self.project / ".sdlc" / "x" / "status.md")

    def policy(self, value):
        path = self.gate.snyk_state_path(self.project)
        self.gate.write_snyk_state(path, {**self.gate.read_snyk_state(path), "policy": value})

    def check(self):
        return self.gate.snyk_close_reason(self.event, "Write", {"file_path": self.status, "content": "closed\n"})

    def test_an_error_while_building_the_host_holds_the_write_with_snyk_on(self):
        self.policy("on")
        with mock.patch.object(self.gate, "snyk_host", side_effect=RuntimeError("boom")):
            self.assertTrue(self.check().startswith(self.gate.SNYK_TAG))

    def test_the_same_error_changes_nothing_with_snyk_off(self):
        self.policy("off")
        with mock.patch.object(self.gate, "snyk_host", side_effect=RuntimeError("boom")):
            self.assertEqual(self.check(), "")

    def test_a_record_that_cannot_be_parsed_counts_as_unreadable_and_not_as_off(self):
        self.policy("on")
        path = self.gate.snyk_state_path(self.project)
        path.write_text("[" * 100000)
        self.assertEqual(self.gate.read_snyk_state(path)["policy"], self.gate.POLICY_UNREADABLE)

    def test_a_module_that_cannot_be_loaded_holds_the_gate_with_snyk_on(self):
        self.policy("on")
        with mock.patch.object(self.gate, "load_sibling", side_effect=OSError("gone")):
            self.assertTrue(self.check().startswith(self.gate.SNYK_TAG))

    def test_a_module_that_cannot_be_loaded_changes_nothing_with_snyk_undecided(self):
        with mock.patch.object(self.gate, "load_sibling", side_effect=OSError("gone")):
            self.assertEqual(self.check(), "")

    def test_a_crash_of_the_older_file_check_does_not_lift_the_snyk_check(self):
        self.policy("on")
        sent = {**self.event, "tool_name": "Write", "tool_input": {"file_path": self.status, "content": "closed\n"}}
        printed = io.StringIO()
        with mock.patch.object(self.gate, "file_tool_reason", side_effect=RuntimeError("boom")):
            with contextlib.redirect_stdout(printed):
                self.gate.on_tool(sent)
        self.assertIn("Snyk gate", printed.getvalue())

    def test_the_run_folder_has_the_same_name_in_every_module_that_names_it(self):
        names = [self.gate.load_sibling(module).RUN_FOLDER for module in ("security_gate", "snyk/close", "snyk/tree")]
        self.assertEqual(names, [".sdlc"] * 3)

    def test_the_policy_names_are_the_same_here_and_in_the_verdict(self):
        gate = self.gate.load_sibling("security_gate")
        self.assertEqual((self.gate.POLICY_ON, self.gate.POLICY_OFF, self.gate.POLICY_UNREADABLE),
                         (gate.POLICY_ON, gate.POLICY_OFF, gate.POLICY_UNREADABLE))

    def test_the_owner_verbs_are_the_same_in_the_bash_check_and_in_the_prompt_reader(self):
        close = self.gate.load_sibling("snyk/close")
        words = ["on", "off", "accept", "waive", "delete"]
        in_bash = [bool(self.gate.SNYK_OWNER_WORDS.search(f"sdlc snyk {word}")) for word in words]
        in_prompt = [close.parse_command(f"sdlc snyk {word}") is not None for word in words]
        self.assertEqual((in_bash, in_prompt), ([True] * 4 + [False], [True] * 4 + [False]))


class FailClosedTest(SnykCloseTest):
    def test_a_project_with_no_pinned_base_cannot_close(self):
        self.prompt("sdlc snyk on")
        record = next(iter(self.snyk_state.glob("*.json")))
        record.write_text(json.dumps({**self.state(), "base": None}))
        self.edit_code()
        self.assertIn("changed files: unknown", self.denial())

    def test_the_reason_there_is_no_base_is_in_the_denial(self):
        self.prompt("sdlc snyk on")
        record = next(iter(self.snyk_state.glob("*.json")))
        record.write_text(json.dumps({**self.state(), "base": None}))
        self.edit_code()
        self.assertIn("no base commit is pinned", self.denial())

    def test_a_crash_of_the_older_bash_check_does_not_lift_the_snyk_check_in_a_session_with_no_lock(self):
        self.prompt("sdlc snyk on")
        unreadable = self.project / "message.txt"
        unreadable.write_text("fix: x\n")
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o600)
        done = self.bash(f"git commit -F {unreadable} -q; echo closed >> .sdlc/feature/status.md")
        self.assertIn(GATE_TAG, done.stdout)

    def test_a_state_file_that_cannot_be_read_cannot_close(self):
        self.prompt("sdlc snyk on")
        next(iter(self.snyk_state.glob("*.json"))).write_text("not json")
        self.assertTrue(self.closing_denied())

    def test_a_repo_that_git_cannot_read_cannot_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        subprocess.run(["rm", "-rf", str(self.project / ".git")], check=True)
        self.assertTrue(self.closing_denied())

    def test_a_write_input_that_is_not_the_shape_of_the_tool_cannot_close(self):
        self.snyk_on_and_approved()
        done = self.run_hook("tool", {"tool_name": "Write", "tool_input": {"file_path": str(self.status)}})
        self.assertIn(GATE_TAG, done.stdout)


if __name__ == "__main__":
    unittest.main()
