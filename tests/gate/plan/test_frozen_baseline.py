"""Tests for the baseline of a frozen reproduction test: the hash `frozen-seen` records when a frozen file is written
with a file tool, and the read-only `frozen-status` that compares it with the file now, so a change made outside the
file tools (a Bash `sed -i`, a formatter) shows up and a builder cannot hide it by editing `build.md`.

They feed the hook hand-written payloads. Whether Claude Code sends `agent_type` in a PostToolUse payload is not
shown here, and the hook does not need it: a PreToolUse denial means no write of a frozen file reaches PostToolUse
except qa-engineer's.

Run: python3 -I -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

from support.frozen_base import BUILDER, FrozenGateTest, QA
from support.paths import HOOKS, SCRIPT

READ_ONLY_REVIEWER = "sdlc:brutal-reviewer"


class FrozenBaselineTest(FrozenGateTest):
    def setUp(self):
        super().setUp()
        self.records = self.home / "sdlc-gate" / "frozen"

    def write_frozen(self, text="def test_bug(): assert False\n"):
        self.frozen.parent.mkdir(exist_ok=True)
        self.frozen.write_text(text)

    def seen(self, path, agent=QA):
        return self.run_hook("frozen-seen", {"tool_name": "Write", "tool_input": {"file_path": str(path)},
                                             "agent_type": agent})

    def status(self, env=None):
        return self.run_raw("frozen-status", "", env).stdout

    def test_a_write_of_a_frozen_test_records_its_hash_and_the_status_says_ok(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.assertIn("tests/test_bug.py ok", self.status())

    def test_a_change_made_outside_the_file_tools_shows_as_changed(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.frozen.write_text("def test_bug(): assert True\n")
        self.assertIn("tests/test_bug.py CHANGED", self.status())

    def test_a_frozen_test_that_was_deleted_shows_as_missing(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.frozen.unlink()
        self.assertIn("tests/test_bug.py missing", self.status())

    def test_a_write_of_a_file_that_is_not_frozen_records_nothing(self):
        self.approve_frozen()
        (self.project / "money.py").write_text("x = 1\n")
        self.seen(self.project / "money.py")
        self.assertNotIn("money.py", self.status())

    def test_with_no_approved_tests_nothing_is_recorded(self):
        self.write_frozen()
        self.seen(self.frozen)
        self.assertFalse(self.records.exists())

    def test_a_hard_link_written_later_is_recorded_under_the_frozen_name(self):
        self.approve_frozen()
        self.write_frozen()
        os.link(self.frozen, self.project / "alias.py")
        self.seen(self.project / "alias.py")
        self.assertIn("tests/test_bug.py ok", self.status())

    def test_the_status_of_a_project_with_no_record_says_none_recorded(self):
        self.assertIn("none recorded", self.status())

    def test_the_status_says_so_when_the_gate_is_off(self):
        self.assertIn("gate is off", self.status({"SDLC_GATE": "off"}))

    def damage_the_record(self):
        next(self.records.glob("*.json")).write_text("{not json")

    def test_a_write_by_an_agent_that_is_not_qa_records_nothing(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen, agent=BUILDER)
        self.assertIn("tests/test_bug.py NO BASELINE", self.status())

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_a_frozen_file_that_cannot_be_read_is_named_by_the_status(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.frozen.chmod(0)
        self.addCleanup(self.frozen.chmod, 0o600)
        self.assertIn("tests/test_bug.py unreadable", self.status())

    def test_two_writes_at_once_keep_both_baselines(self):
        other = self.project / "tests" / "test_other.py"
        self.approve_frozen("tests/test_bug.py", "tests/test_other.py")
        self.write_frozen()
        other.write_text("def test_other(): assert False\n")
        self.seen_at_once(self.frozen, other)
        status = self.status()
        self.assertTrue("tests/test_bug.py ok" in status and "tests/test_other.py ok" in status, status)

    def test_the_record_folder_holds_no_file_but_the_record(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.assertEqual([entry.suffix for entry in self.records.iterdir()], [".json"])

    def seen_at_once(self, *paths):
        env = {**os.environ, "SDLC_GATE": "", "SDLC_GATE_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.project)}
        running = [subprocess.Popen([sys.executable, "-I", str(SCRIPT), "frozen-seen"], stdin=subprocess.PIPE, env=env,
                                    text=True) for _ in paths]
        for process, path in zip(running, paths):
            process.stdin.write(json.dumps({"session_id": "s1", "cwd": str(self.project), "tool_name": "Write",
                                            "tool_input": {"file_path": str(path)}, "agent_type": QA}))
            process.stdin.close()
        self.assertEqual([process.wait(timeout=5) for process in running], [0] * len(paths))

    def test_a_record_that_cannot_be_read_is_reported_by_the_status(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.damage_the_record()
        self.assertIn("cannot be read", self.status())

    def test_a_record_that_cannot_be_read_locks_no_edit(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.damage_the_record()
        self.assertEqual(self.edit_as(self.project / "money.py", BUILDER).stdout, "")

    def test_the_next_write_of_a_frozen_test_replaces_a_record_that_cannot_be_read(self):
        self.approve_frozen()
        self.write_frozen()
        self.seen(self.frozen)
        self.damage_the_record()
        self.seen(self.frozen)
        self.assertIn("tests/test_bug.py ok", self.status())

    def test_approving_again_does_not_baseline_the_files_over_a_record_that_cannot_be_read(self):
        self.write_frozen()
        self.approve_frozen()
        self.damage_the_record()
        self.frozen.write_text("def test_bug(): assert True\n")
        self.approve_frozen()
        self.assertIn("cannot be read", self.status())

    def test_an_approved_frozen_test_that_does_not_exist_yet_says_no_baseline(self):
        self.approve_frozen()
        self.assertIn("tests/test_bug.py NO BASELINE", self.status())

    def test_a_frozen_test_that_exists_at_approval_has_its_content_as_the_baseline(self):
        self.write_frozen()
        self.approve_frozen()
        self.assertIn("tests/test_bug.py ok", self.status())

    def test_a_change_made_before_qa_wrote_the_test_shows_as_changed(self):
        self.write_frozen()
        self.approve_frozen()
        self.frozen.write_text("def test_bug(): assert True\n")
        self.assertIn("tests/test_bug.py CHANGED", self.status())

    def test_approving_again_keeps_the_baseline_an_earlier_approval_recorded(self):
        self.write_frozen()
        self.approve_frozen()
        self.frozen.write_text("def test_bug(): assert True\n")
        self.approve_frozen()
        self.assertIn("tests/test_bug.py CHANGED", self.status())

    def test_the_status_run_from_a_folder_below_the_project_finds_the_record(self):
        self.write_frozen()
        self.approve_frozen()
        env = {key: value for key, value in os.environ.items() if key != "CLAUDE_PROJECT_DIR"}
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "frozen-status"], cwd=self.frozen.parent,
                              capture_output=True, text=True, timeout=5, env={**env, "SDLC_GATE_HOME": str(self.home)})
        self.assertIn("tests/test_bug.py ok", done.stdout)

    def test_a_read_only_reviewer_may_run_the_status_command(self):
        self.approve_frozen()
        done = self.bash(f"python3 -I {SCRIPT} frozen-status", agent_type=READ_ONLY_REVIEWER)
        self.assertEqual(done.stdout, "")

    def test_the_approval_notice_gives_the_command_that_compares_the_frozen_tests(self):
        done = self.approve_frozen()
        self.assertIn("frozen-status", self.context(done))


class WiringTest(unittest.TestCase):
    def test_hooks_json_records_a_baseline_after_a_notebook_edit_too(self):
        entries = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PostToolUse"]
        matchers = [entry["matcher"] for entry in entries if "frozen-seen" in entry["hooks"][0]["command"]]
        self.assertEqual(matchers, ["Edit|Write|MultiEdit|NotebookEdit"])


if __name__ == "__main__":
    unittest.main()
