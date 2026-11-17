"""Tests for plugins/sdlc/hooks/repeat_guard.py, run as Claude Code runs it: JSON on stdin.

Run: python3 -I -m unittest discover -s tests
These feed the hook the documented input shapes, so they prove its counting and its failure handling, not
what the host sends. Set REPEAT_GUARD_TRACE=<file> in a real session to record what the host sends.
Test bodies hold no loops or branches; the helpers do the repeating.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "plugins" / "sdlc" / "hooks"
SCRIPT = HOOKS / "repeat_guard.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "repeat_loop.json"
A, B = "python tests/a.py", "python tests/b.py"
KEY_A = "main|tests/a.py"
THREE = (0, 60, 120)
QUIET = ["", "", ""]


def failure(command, agent=None):
    return {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "session_id": "s1",
            "tool_input": {"command": command}, "error": "Exit code 1", **({"agent_id": agent} if agent else {})}


def finished(command, stdout):
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "s1",
            "tool_input": {"command": command}, "tool_response": {"stdout": stdout, "stderr": ""}}


class RepeatGuardTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.folder = self.home / "sdlc-gate"

    def run_raw(self, stdin, now=0, env=None):
        full_env = {**os.environ, "SDLC_GATE_HOME": str(self.home), "REPEAT_GUARD_NOW": str(now), **(env or {})}
        return subprocess.run([sys.executable, "-I", str(SCRIPT)], input=stdin, capture_output=True,
                              text=True, env=full_env, timeout=5)

    def hook(self, payload, now=0, env=None):
        return self.run_raw(json.dumps(payload), now, env)

    def note(self, payload, now=0):
        out = self.hook(payload, now).stdout
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def notes(self, payload, times):
        return [self.note(payload, t) for t in times]

    def notes_for(self, steps):
        return [self.note(payload, t) for payload, t in steps]

    def write_state(self, text):
        self.folder.mkdir(parents=True)
        (self.folder / "s1.repeat").write_text(text)

    def test_three_failures_of_one_test_file_add_the_note(self):
        notes = self.notes(failure(A), THREE)
        self.assertEqual(notes[:2], ["", ""])
        self.assertIn("tests/a.py failed 3 times", notes[2])

    def test_a_failed_run_hidden_by_a_pipe_counts(self):
        notes = self.notes(finished(A + " | tail -3", "2 failed, 8 passed"), THREE)
        self.assertIn("failed 3 times", notes[2])

    def test_a_pass_in_between_does_not_reset_the_count(self):
        self.note(failure(A), 0)
        self.note(finished(A, "10 passed"), 30)
        self.note(failure(A), 60)
        self.assertIn("failed 3 times", self.note(failure(A), 120))

    def test_a_zero_failed_summary_is_not_a_failure(self):
        self.assertEqual(self.notes(finished(A, "10 passed, 0 failed"), THREE), QUIET)

    def test_failures_older_than_the_window_drop_out(self):
        self.note(failure(A), 0)
        self.note(failure(A), 1000)
        self.assertEqual(self.note(failure(A), 2000), "")

    def test_another_test_file_counts_separately(self):
        steps = ((failure(A), 0), (failure(B), 10), (failure(A), 20), (failure(B), 30))
        self.assertEqual(self.notes_for(steps), ["", "", "", ""])

    def test_another_agent_counts_separately(self):
        steps = ((failure(A, "x"), 0), (failure(A, "y"), 10), (failure(A, "x"), 20), (failure(A, "y"), 30))
        self.assertEqual(self.notes_for(steps), ["", "", "", ""])

    def test_a_command_without_a_test_path_is_ignored(self):
        self.assertEqual(self.notes(failure("npm test"), THREE), QUIET)
        self.assertFalse(self.folder.exists())

    def test_reading_a_test_file_is_not_a_failure(self):
        self.assertEqual(self.notes(finished("cat tests/a.py", "2 failed, 8 passed"), THREE), QUIET)

    def test_a_failed_read_of_a_test_file_is_not_a_failure(self):
        self.assertEqual(self.notes(failure("sed -n 1,5p tests/a.py"), THREE), QUIET)

    def test_grepping_for_a_runner_word_in_a_test_file_is_not_a_failure(self):
        self.assertEqual(self.notes(finished("grep -n unittest tests/a.py", "FAILED"), THREE), QUIET)

    def test_a_read_followed_by_a_run_counts_the_run(self):
        notes = self.notes(failure("sed -n 1,5p tests/a.py; python tests/a.py"), THREE)
        self.assertIn("tests/a.py failed 3 times", notes[2])

    def test_the_note_is_logged(self):
        self.notes(failure(A), THREE)
        self.assertIn("3 tests/a.py", (self.folder / "repeat.log").read_text())

    def test_other_tools_are_ignored(self):
        self.assertEqual(self.notes({**failure(A), "tool_name": "Edit"}, THREE), QUIET)

    def test_a_command_that_is_not_text_is_ignored(self):
        payload = {**failure(A), "tool_input": {"command": 5}}
        run = self.hook(payload)
        self.assertEqual((run.returncode, run.stdout), (0, ""))

    def test_a_broken_state_file_fails_open(self):
        self.write_state("{not json")
        run = self.hook(failure(A))
        self.assertEqual((run.returncode, run.stdout), (0, ""))

    def test_a_state_file_of_the_wrong_shape_is_replaced(self):
        self.write_state(json.dumps({KEY_A: "abc", "x": 5}))
        notes = self.notes(failure(A), THREE)
        self.assertIn("failed 3 times", notes[2])

    def test_a_state_folder_that_cannot_be_made_fails_open(self):
        blocker = self.home / "blocker"
        blocker.write_text("a file, not a folder")
        run = self.hook(failure(A), env={"SDLC_GATE_HOME": str(blocker)})
        self.assertEqual((run.returncode, run.stdout), (0, ""))

    def test_input_that_is_not_json_fails_open(self):
        run = self.run_raw("not json")
        self.assertEqual((run.returncode, run.stdout), (0, ""))

    def test_a_session_id_that_is_not_a_name_writes_nothing(self):
        run = self.hook({**failure(A), "session_id": "../escape"})
        self.assertEqual((run.returncode, run.stdout, self.folder.exists()), (0, "", False))

    def names(self, folder):
        return sorted(p.name for p in folder.iterdir())

    def test_an_agent_id_cannot_move_the_state_file(self):
        self.hook(failure(A, "../../x"))
        self.assertEqual((self.names(self.folder), self.names(self.home)), (["s1.repeat"], ["sdlc-gate"]))

    def test_the_log_stops_growing_at_its_cap_but_the_note_still_goes_out(self):
        self.folder.mkdir(parents=True)
        log = self.folder / "repeat.log"
        log.write_text("x" * 100_001)
        notes = self.notes(failure(A), THREE)
        self.assertEqual((log.stat().st_size, "failed 3 times" in notes[2]), (100_001, True))

    def test_a_temp_file_a_day_old_is_removed(self):
        self.folder.mkdir(parents=True)
        old = self.folder / "s1.99.tmp"
        old.write_text("{}")
        two_days_ago = time.time() - 2 * 24 * 3600
        os.utime(old, (two_days_ago, two_days_ago))
        self.hook(failure(A), now=time.time())
        self.assertFalse(old.exists())

    def test_a_file_the_guard_does_not_own_is_left_alone(self):
        self.folder.mkdir(parents=True)
        other = self.folder / "s1.locked"
        other.write_text("")
        two_days_ago = time.time() - 2 * 24 * 3600
        os.utime(other, (two_days_ago, two_days_ago))
        self.hook(failure(A), now=time.time())
        self.assertTrue(other.exists())

    def test_the_state_file_is_private(self):
        self.hook(failure(A))
        mode = stat.S_IMODE(os.stat(self.folder / "s1.repeat").st_mode)
        self.assertEqual(mode, 0o600)

    def test_a_key_keeps_only_its_last_ten_times(self):
        self.notes(failure(A), range(12))
        times = json.loads((self.folder / "s1.repeat").read_text())[KEY_A]
        self.assertEqual(len(times), 10)

    def test_a_state_file_a_day_old_is_removed(self):
        self.folder.mkdir(parents=True)
        old = self.folder / "old.repeat"
        old.write_text("{}")
        two_days_ago = time.time() - 2 * 24 * 3600
        os.utime(old, (two_days_ago, two_days_ago))
        self.hook(failure(A), now=time.time())
        self.assertFalse(old.exists())

    def test_the_trace_records_field_names_and_no_content(self):
        trace = self.home / "trace.txt"
        self.hook(failure("python tests/a.py --token SECRET-VALUE"), env={"REPEAT_GUARD_TRACE": str(trace)})
        text = trace.read_text()
        self.assertIn("PostToolUseFailure Bash", text)
        self.assertNotIn("SECRET-VALUE", text)

    def replay(self, events):
        fired = []
        for event in events:
            path = event["paths"][0]
            command = f"sed -n 1,5p {path}; python {path}"
            payload = failure(command) if event["failed"] else finished(command, "ok")
            fired.append(bool(self.hook(payload, event["t"]).stdout))
        return fired

    def test_the_real_loop_fires_where_the_agent_was_looping(self):
        """Replays the failure times of a real 14 Nov end-to-end loop (fixture): the first note comes at
        the third failure of one file within 30 minutes. It replays failure times, not output text."""
        data = json.loads(FIXTURE.read_text())
        first = data["first_fire_index"]
        fired = self.replay(data["events"][: first + 1])
        self.assertEqual(fired, [False] * first + [True])


if __name__ == "__main__":
    unittest.main()
