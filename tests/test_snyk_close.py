"""Tests for plugins/sdlc/hooks/snyk/close.py: spotting a write to status.md that closes a run or starts Ship,
working out the text a file tool would leave, and reading the owner's `sdlc snyk ...` words.

Run: python3 -I -m unittest discover -s tests
"""
import importlib.util
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "plugins" / "sdlc" / "hooks"
SPEC = importlib.util.spec_from_file_location("snyk_close", HOOKS / "snyk" / "close.py")
close = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(close)

OPEN_RUN = "run: x\n6 Verify: done\nwaiting: owner\n"


class ClosingTest(unittest.TestCase):
    def test_a_last_line_of_closed_closes_the_run(self):
        self.assertTrue(close.is_closing("run: x\nclosed\n"))

    def test_closed_with_a_reason_closes_the_run(self):
        self.assertTrue(close.is_closing("run: x\nclosed - shipped\n"))

    def test_a_ship_stage_that_is_running_starts_ship(self):
        self.assertTrue(close.is_closing("6 Verify: done\n7 Ship: running\nwaiting: x\n"))

    def test_a_ship_stage_that_is_done_starts_ship(self):
        self.assertTrue(close.is_closing("7 Ship: done\nwaiting: x\n"))

    def test_an_abandoned_run_does_not_need_the_gate(self):
        self.assertFalse(close.is_closing("run: x\nabandoned: not wanted\n"))

    def test_an_open_run_is_not_closing(self):
        self.assertFalse(close.is_closing(OPEN_RUN))

    def test_a_ship_stage_line_with_leading_space_starts_ship(self):
        self.assertTrue(close.is_closing("6 Verify: done\n  7 Ship: running\nwaiting: x\n"))

    def test_a_ship_stage_after_an_odd_line_break_starts_ship(self):
        self.assertTrue(close.is_closing("6 Verify: done\x0b7 Ship: done\nwaiting: x\n"))

    def test_a_ship_stage_that_is_only_pending_is_not_closing(self):
        self.assertFalse(close.is_closing("7 Ship: pending\nwaiting: x\n"))

    def test_the_word_closed_inside_a_line_is_not_closing(self):
        self.assertFalse(close.is_closing("run: x\nwaiting: the closed beta\n"))

    def test_an_empty_text_is_not_closing(self):
        self.assertFalse(close.is_closing(""))


class StatusPathTest(unittest.TestCase):
    def test_a_status_md_of_a_run_is_one(self):
        self.assertTrue(close.is_status_relative(".sdlc/feature/status.md"))

    def test_another_file_of_a_run_is_not(self):
        self.assertFalse(close.is_status_relative(".sdlc/feature/plan.md"))

    def test_another_spelling_of_the_case_is_one_too(self):
        self.assertTrue(close.is_status_relative(".SDLC/Feature/STATUS.MD"))

    def test_a_status_md_deeper_down_is_not(self):
        self.assertFalse(close.is_status_relative(".sdlc/feature/runs/status.md"))

    def test_a_status_md_outside_the_run_folder_is_not(self):
        self.assertFalse(close.is_status_relative("docs/feature/status.md"))


class ResultingTextTest(unittest.TestCase):
    def test_a_write_leaves_its_content(self):
        self.assertEqual(close.resulting_text("Write", {"content": "closed\n"}, OPEN_RUN), "closed\n")

    def test_an_edit_replaces_the_first_match(self):
        sent = {"old_string": "waiting: owner", "new_string": "closed"}
        self.assertEqual(close.resulting_text("Edit", sent, OPEN_RUN), "run: x\n6 Verify: done\nclosed\n")

    def test_an_edit_with_replace_all_replaces_every_match(self):
        sent = {"old_string": "x", "new_string": "y", "replace_all": True}
        self.assertEqual(close.resulting_text("Edit", sent, "x x"), "y y")

    def test_a_multi_edit_applies_its_edits_in_order(self):
        sent = {"edits": [{"old_string": "a", "new_string": "b"}, {"old_string": "b", "new_string": "closed"}]}
        self.assertEqual(close.resulting_text("MultiEdit", sent, "a"), "closed")

    def test_an_edit_that_cannot_apply_leaves_nothing(self):
        self.assertIsNone(close.resulting_text("Edit", {"old_string": "zzz", "new_string": "q"}, OPEN_RUN))

    def test_an_edit_of_a_file_that_does_not_exist_leaves_nothing(self):
        self.assertIsNone(close.resulting_text("Edit", {"old_string": "a", "new_string": "b"}, None))

    def test_a_write_with_no_content_is_malformed(self):
        with self.assertRaises(ValueError):
            close.resulting_text("Write", {}, OPEN_RUN)

    def test_an_edit_whose_strings_are_not_text_is_malformed(self):
        with self.assertRaises(ValueError):
            close.resulting_text("Edit", {"old_string": 1, "new_string": 2}, OPEN_RUN)

    def test_an_edit_with_an_empty_old_string_creates_the_file(self):
        sent = {"old_string": "", "new_string": "run: x\nclosed\n"}
        self.assertEqual(close.resulting_text("Edit", sent, None), "run: x\nclosed\n")

    def test_an_edit_with_curly_quotes_for_straight_ones_still_applies(self):
        sent = {"old_string": "waiting: owner\u2019s call", "new_string": "closed"}
        self.assertEqual(close.resulting_text("Edit", sent, "waiting: owner's call"), "closed")

    def test_a_tool_that_is_not_a_file_edit_is_malformed(self):
        with self.assertRaises(ValueError):
            close.resulting_text("Read", {}, OPEN_RUN)


class ClosingAfterTest(unittest.TestCase):
    def test_an_applied_edit_is_judged_by_the_text_it_leaves(self):
        sent = {"old_string": "waiting: owner", "new_string": "closed"}
        self.assertTrue(close.closing_after("Edit", sent, OPEN_RUN))

    def test_an_edit_that_cannot_apply_to_an_existing_file_is_held_whatever_it_says(self):
        sent = {"old_string": "zzz", "new_string": "waiting: qa"}
        self.assertTrue(close.closing_after("Edit", sent, OPEN_RUN))

    def test_a_multi_edit_that_cannot_apply_to_an_existing_file_is_held(self):
        sent = {"edits": [{"old_string": "zzz", "new_string": ""}]}
        self.assertTrue(close.closing_after("MultiEdit", sent, OPEN_RUN))

    def test_an_edit_of_a_file_that_is_not_there_is_judged_by_its_new_text(self):
        sent = {"old_string": "zzz", "new_string": "closed"}
        self.assertTrue(close.closing_after("Edit", sent, None))

    def test_an_edit_of_a_file_that_is_not_there_and_closes_nothing_is_not_closing(self):
        sent = {"old_string": "zzz", "new_string": "waiting: qa"}
        self.assertFalse(close.closing_after("Edit", sent, None))

    def test_a_write_is_judged_by_its_content(self):
        self.assertTrue(close.closing_after("Write", {"content": "closed\n"}, OPEN_RUN))


class OwnerWordsTest(unittest.TestCase):
    def test_on_is_read(self):
        self.assertEqual(close.parse_command("sdlc snyk on"), ("on", ""))

    def test_off_is_read(self):
        self.assertEqual(close.parse_command("sdlc snyk off"), ("off", ""))

    def test_waive_is_read_with_its_reason(self):
        self.assertEqual(close.parse_command("sdlc snyk waive snyk is down"), ("waive", "snyk is down"))

    def test_upper_case_is_read(self):
        self.assertEqual(close.parse_command("SDLC Snyk ON"), ("on", ""))

    def test_the_slash_form_is_not_the_command(self):
        self.assertIsNone(close.parse_command("/sdlc snyk on"))

    def test_the_words_after_the_verb_are_kept(self):
        self.assertEqual(close.parse_command("sdlc snyk accept F2 not reachable from input"),
                         ("accept", "F2 not reachable from input"))

    def test_words_around_the_command_are_not_a_command(self):
        self.assertIsNone(close.parse_command("please run sdlc snyk on now"))

    def test_another_verb_is_not_a_command(self):
        self.assertIsNone(close.parse_command("sdlc snyk delete"))

    def test_accept_needs_a_finding_and_a_reason(self):
        self.assertEqual(close.accept_args("F12 it is a test fixture"), ("F12", "it is a test fixture"))

    def test_accept_without_a_reason_is_refused(self):
        self.assertIsNone(close.accept_args("F1"))

    def test_accept_of_something_that_is_not_a_short_id_is_refused(self):
        self.assertIsNone(close.accept_args("python/PT because"))


if __name__ == "__main__":
    unittest.main()
