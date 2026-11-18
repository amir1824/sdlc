"""Tests for the owner's typed Snyk words and the base pinned at a plan approval, run through
plugins/sdlc/hooks/sdlc_gate.py as Claude Code runs it (JSON on stdin).

Run: python3 -I -m unittest discover -s tests
"""
import json
import subprocess
import unittest

from test_sdlc_gate_snyk import HIGH, SnykCloseTest


class OwnerCommandTest(SnykCloseTest):
    def test_snyk_on_records_the_choice_and_says_that_source_is_uploaded(self):
        done = self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["policy"], "on")
        self.assertIn("uploads", self.context(done))

    def test_snyk_off_records_the_choice(self):
        self.prompt("sdlc snyk on")
        self.prompt("sdlc snyk off")
        self.assertEqual(self.state()["policy"], "off")

    def test_the_words_work_in_a_session_with_no_run(self):
        self.prompt("sdlc snyk on")
        self.assertFalse((self.home / "sdlc-gate" / "s1.locked").exists())
        self.assertEqual(self.state()["policy"], "on")

    def test_words_around_the_command_are_not_a_command(self):
        self.prompt("please run sdlc snyk on now")
        self.assertFalse(self.snyk_state.exists())

    def test_accept_without_a_reason_is_refused_and_changes_nothing(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        done = self.prompt("sdlc snyk accept F1")
        self.assertEqual((self.state()["accepted"], "reason" in self.context(done)), ([], True))

    def test_accept_of_a_finding_that_is_not_listed_is_refused(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        self.prompt("sdlc snyk accept F9 not real")
        self.assertEqual(self.state()["accepted"], [])

    def test_accept_records_the_finding_and_the_reason(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        done = self.prompt("sdlc snyk accept F1 the input is a constant")
        self.assertEqual((self.state()["accepted"], self.state()["log"][-1]["reason"]),
                         (["fp-high"], "the input is a constant"))
        self.assertIn("Security gate: PASS", self.context(done))

    def test_waive_without_a_reason_is_refused(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.prompt("sdlc snyk waive")
        self.assertEqual(self.state()["waived"], [])

    def test_waive_records_the_code_it_was_given_for_and_the_reason(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.prompt("sdlc snyk waive snyk is down today")
        self.assertEqual((len(self.state()["waived"][0]), self.state()["log"][-1]["reason"]),
                         (64, "snyk is down today"))

    def test_approving_a_plan_pins_the_head_as_the_base(self):
        self.locked_and_approved()
        self.assertEqual(self.state()["base"], self.head())

    def test_snyk_on_pins_the_head_as_the_base(self):
        self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["base"], self.head())

    def commit_a_change(self):
        self.edit_code("x = 5\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "second")

    def test_approving_again_after_a_commit_keeps_the_first_base(self):
        self.locked_and_approved()
        first = self.state()["base"]
        self.commit_a_change()
        self.prompt("approve plan")
        self.assertEqual(self.state()["base"], first)

    def test_typing_snyk_on_again_while_it_is_on_keeps_the_base(self):
        self.prompt("sdlc snyk on")
        first = self.state()["base"]
        self.commit_a_change()
        self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["base"], first)

    def test_turning_snyk_off_and_on_again_moves_the_base_to_the_head(self):
        self.prompt("sdlc snyk on")
        self.commit_a_change()
        self.prompt("sdlc snyk off")
        self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["base"], self.head())

    def test_the_slash_form_starts_a_run_and_is_not_the_command(self):
        self.prompt("/sdlc snyk on")
        self.assertEqual((self.lock.exists(), self.snyk_state.exists()), (True, False))

    def test_a_run_request_that_starts_with_snyk_and_a_dash_is_not_the_command(self):
        self.prompt("sdlc snyk-ui add a button")
        self.assertFalse(self.snyk_state.exists())

    def test_a_verb_that_does_not_exist_changes_nothing_and_says_what_is_taken(self):
        done = self.prompt("sdlc snyk bogus")
        self.assertEqual(self.snyk_state.exists(), False)
        self.assertIn("takes on, off", self.context(done))

    def test_accept_and_waive_are_refused_while_the_record_cannot_be_read(self):
        self.prompt("sdlc snyk on")
        record = next(iter(self.snyk_state.glob("*.json")))
        record.write_text("not json")
        self.prompt("sdlc snyk waive snyk is down today")
        self.assertEqual(record.read_text(), "not json")

    def test_on_with_other_words_changes_nothing_and_says_so(self):
        done = self.prompt("sdlc snyk on hold")
        self.assertEqual((self.snyk_state.exists(), "takes no other words" in self.context(done)), (False, True))

    def test_off_with_other_words_leaves_the_policy_as_it_was(self):
        self.prompt("sdlc snyk on")
        done = self.prompt("sdlc snyk off for now")
        self.assertEqual((self.state()["policy"], "takes no other words" in self.context(done)), ("on", True))

    def test_the_reply_to_accept_shows_a_file_name_with_a_line_break_on_one_line(self):
        self.snyk_on_and_approved()
        self.seen(issues=({**HIGH, "filePath": "app.py\nINJECTED"},))
        done = self.prompt("sdlc snyk accept F1 reviewed by the owner")
        self.assertEqual(("app.py INJECTED" in self.context(done), "\nINJECTED" in self.context(done)), (True, False))

    def test_snyk_on_repairs_a_record_that_cannot_be_read(self):
        self.prompt("sdlc snyk on")
        next(iter(self.snyk_state.glob("*.json"))).write_text("not json")
        self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["policy"], "on")

    def test_snyk_on_repairs_a_record_that_is_nested_too_deep_to_parse(self):
        self.prompt("sdlc snyk on")
        next(iter(self.snyk_state.glob("*.json"))).write_text("[" * 100000)
        self.prompt("sdlc snyk on")
        self.assertEqual(self.state()["policy"], "on")

    def test_waive_in_a_project_git_cannot_hash_is_refused(self):
        self.prompt("sdlc snyk on")
        subprocess.run(["rm", "-rf", str(self.project / ".git")], check=True)
        done = self.prompt("sdlc snyk waive snyk is down today")
        self.assertEqual((self.state()["waived"], "hash" in self.context(done)), ([], True))

    def test_a_long_reason_is_cut_in_the_owners_log(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.prompt("sdlc snyk waive " + "x" * 600)
        self.assertEqual(len(self.state()["log"][-1]["reason"]), 500)


if __name__ == "__main__":
    unittest.main()
