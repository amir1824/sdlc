"""Tests for the denial of a write to a run's status.md that closes the run or starts Ship while the Snyk gate is
not PASS, through the file tools, run through plugins/sdlc/hooks/sdlc_gate.py as Claude Code runs it.

Run: python3 -I -m unittest discover -s tests
"""
import os
import unittest

from test_sdlc_gate_snyk import CLOSED_RUN, GATE_TAG, HIGH, SnykCloseTest


class CloseGateTest(SnykCloseTest):
    def test_a_project_that_has_not_decided_may_close(self):
        self.locked_and_approved()
        self.edit_code()
        self.assertFalse(self.closing_denied())

    def test_a_project_that_turned_snyk_off_may_close(self):
        self.prompt("sdlc snyk off")
        self.locked_and_approved()
        self.edit_code()
        self.assertFalse(self.closing_denied())

    def test_with_snyk_on_a_change_with_no_scan_cannot_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertTrue(self.closing_denied())
        self.assertIn("code: not run", self.denial())

    def test_the_denial_says_what_the_owner_can_type(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertIn("sdlc snyk waive", self.denial())

    def test_a_clean_scan_of_this_code_lets_it_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        self.assertFalse(self.closing_denied())

    def test_a_scan_before_the_last_edit_is_stale_and_cannot_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        self.edit_code("x = 3\n")
        self.assertIn("code: stale", self.denial())

    def test_a_high_in_a_changed_file_cannot_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        self.assertIn("F1 high app.py", self.denial())

    def test_an_accepted_high_lets_it_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        self.prompt("sdlc snyk accept F1 reviewed by the owner")
        self.assertFalse(self.closing_denied())

    def test_a_waiver_lets_an_incomplete_gate_close(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.prompt("sdlc snyk waive snyk is down today")
        self.assertFalse(self.closing_denied())

    def test_a_waiver_does_not_survive_a_change_to_the_code(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.prompt("sdlc snyk waive snyk is down today")
        self.edit_code("x = 3\n")
        self.assertTrue(self.closing_denied())

    def test_a_waiver_does_not_cover_a_high(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=(HIGH,))
        self.prompt("sdlc snyk waive snyk is down today")
        self.assertTrue(self.closing_denied())

    def test_a_change_that_is_only_docs_may_close_with_no_scan(self):
        self.snyk_on_and_approved()
        (self.project / "README.md").write_text("hello\n")
        self.assertFalse(self.closing_denied())

    def test_starting_ship_is_held_like_closing(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertTrue(self.closing_denied("run: feature\n7 Ship: running\nwaiting: devops\n"))

    def test_a_write_that_does_not_close_is_allowed(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertFalse(self.closing_denied("run: feature\n6 Verify: running\nwaiting: qa\n"))

    def test_an_abandoned_run_is_not_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertFalse(self.closing_denied("run: feature\nabandoned: not wanted\n"))

    def test_an_edit_that_closes_the_run_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertTrue(self.edit_status("Edit", {"old_string": "waiting: owner", "new_string": "closed"}))

    def test_a_multi_edit_that_closes_the_run_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        edits = [{"old_string": "waiting: owner", "new_string": "waiting: x"},
                 {"old_string": "waiting: x", "new_string": "closed"}]
        self.assertTrue(self.edit_status("MultiEdit", {"edits": edits}))

    def test_an_edit_the_gate_cannot_match_is_held_while_the_gate_is_not_closable(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertTrue(self.edit_status("Edit", {"old_string": "not in the file", "new_string": "waiting: qa"}))

    def test_an_edit_the_gate_cannot_match_is_allowed_once_the_gate_passes(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        self.assertFalse(self.edit_status("Edit", {"old_string": "not in the file", "new_string": "waiting: qa"}))

    def test_a_deletion_the_gate_cannot_match_in_a_file_with_windows_line_breaks_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.status.write_bytes(b"run: x\r\n7 Ship: pending\r\nclosed\r\nwaiting: Verify\r\n")
        self.assertTrue(self.edit_status("Edit", {"old_string": "waiting: Verify\n", "new_string": ""}))

    def test_an_edit_of_a_status_md_over_the_size_limit_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        self.status.write_text("run: x\n" + "x" * 1_100_000 + "\nwaiting: owner\n")
        self.assertTrue(self.edit_status("Edit", {"old_string": "waiting: owner", "new_string": "waiting: qa"}))

    def test_an_edit_of_a_status_md_that_is_a_pipe_is_held_and_does_not_hang(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.seen(issues=())
        self.status.unlink()
        os.mkfifo(self.status)
        sent = {"old_string": "waiting: owner", "new_string": "waiting: qa"}
        done = self.run_hook("tool", {"tool_name": "Edit", "tool_input": {"file_path": str(self.status), **sent}})
        self.assertIn("could not be checked", done.stdout)

    def test_a_denial_is_logged_with_the_path_of_the_file(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.closing_denied()
        log = (self.home / "sdlc-gate" / "approvals.log").read_text()
        self.assertIn(' deny-snyk session=s1 ', log)
        self.assertIn('prompt=".sdlc/feature/status.md"', log)

    def test_an_edit_that_matches_a_file_with_windows_line_breaks_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.status.write_bytes(b"run: feature\r\n6 Verify: done\r\nwaiting: owner\r\n")
        sent = {"old_string": "done\r\nwaiting: owner", "new_string": "done\r\nclosed"}
        self.assertTrue(self.edit_status("Edit", sent))

    def test_a_ship_stage_with_leading_space_is_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        self.assertTrue(self.closing_denied("run: feature\n   7 Ship: running\nwaiting: devops\n"))

    def test_another_file_of_the_run_is_not_held(self):
        self.snyk_on_and_approved()
        self.edit_code()
        done = self.run_hook("tool", {"tool_name": "Write", "tool_input": {
            "file_path": str(self.project / ".sdlc" / "feature" / "review.md"), "content": "closed\n"}})
        self.assertEqual(done.stdout, "")


class SpellingTest(SnykCloseTest):
    """The same file under another spelling of its path is held too."""

    def setUp(self):
        super().setUp()
        self.snyk_on_and_approved()
        self.edit_code()

    def test_a_path_in_other_case_is_held(self):
        self.assertTrue(self.closing_denied(path=self.project / ".SDLC" / "feature" / "Status.md"))

    def test_a_path_through_a_symlinked_folder_is_held(self):
        (self.project / "alias").symlink_to(self.project / ".sdlc" / "feature")
        self.assertTrue(self.closing_denied(path=self.project / "alias" / "status.md"))

    def test_a_path_that_is_a_symlink_to_the_file_is_held(self):
        (self.project / "link.txt").symlink_to(self.status)
        self.assertTrue(self.closing_denied(path=self.project / "link.txt"))

    def test_a_path_that_is_a_hard_link_to_the_file_is_held(self):
        os.link(self.status, self.project / "notes.txt")
        self.assertTrue(self.closing_denied(path=self.project / "notes.txt"))

    def test_an_edit_that_creates_a_missing_status_md_is_held(self):
        self.status.unlink()
        self.assertTrue(self.edit_status("Edit", {"old_string": "", "new_string": CLOSED_RUN}))

    def test_an_edit_whose_quotes_differ_from_the_files_is_held(self):
        self.status.write_text("run: feature\nwaiting: owner's call\n")
        self.assertTrue(self.edit_status("Edit", {"old_string": "waiting: owner\u2019s call", "new_string": "closed"}))

    def test_a_symlink_to_a_device_that_never_ends_does_not_hang_the_check(self):
        (self.project / "pad.bin").symlink_to("/dev/zero")
        self.seen(issues=())
        self.assertFalse(self.closing_denied())


if __name__ == "__main__":
    unittest.main()
