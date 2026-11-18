"""Tests for the intake of a Jira run: the label check and `sdlc intake off`.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.mcp_base import McpGateTest, NOT_UNDERSTOOD


class IntakeTest(McpGateTest):
    def setUp(self):
        super().setUp()
        self.pending = self.home / "sdlc-gate" / "s1.jira-intake"
        self.approved = self.home / "sdlc-gate" / "s1.approved"

    def test_a_jira_prompt_arms_the_intake_with_the_key(self):
        self.prompt("/sdlc jira SCRUM-123")
        self.assertEqual((self.pending.read_text(), self.marker.is_file()), ("SCRUM-123", True))

    def test_a_lowercase_key_is_stored_in_upper_case(self):
        self.prompt("/sdlc jira scrum-123")
        self.assertEqual(self.pending.read_text(), "SCRUM-123")

    def test_resuming_a_jira_run_arms_the_intake_again(self):
        self.prompt("/sdlc resume jira-scrum-123")
        self.assertEqual(self.pending.read_text(), "SCRUM-123")

    def test_a_key_with_trailing_punctuation_is_still_found(self):
        self.prompt("/sdlc jira SCRUM-123.")
        self.assertEqual(self.pending.read_text(), "SCRUM-123")

    def test_a_key_in_brackets_is_still_found(self):
        self.prompt("/sdlc jira (SCRUM-123)")
        self.assertEqual(self.pending.read_text(), "SCRUM-123")

    def test_a_ticket_link_as_the_argument_gives_its_key(self):
        self.prompt("/sdlc jira https://example.atlassian.net/browse/SCRUM-123")
        self.assertEqual(self.pending.read_text(), "SCRUM-123")

    def test_the_key_of_a_link_is_taken_after_browse_not_from_the_host_name(self):
        self.prompt("/sdlc jira https://acme-2.atlassian.net/browse/PROJ-9")
        self.assertEqual(self.pending.read_text(), "PROJ-9")

    def test_a_link_without_a_browse_path_gives_no_key(self):
        self.prompt("/sdlc jira https://acme-2.atlassian.net/jira/software")
        self.assertEqual(self.pending.read_text(), "?")

    def test_a_resume_slug_with_a_suffix_gives_its_key(self):
        self.prompt("/sdlc resume jira-scrum-1-slugify")
        self.assertEqual(self.pending.read_text(), "SCRUM-1")

    def test_lean_before_jira_arms_the_intake(self):
        self.prompt("/sdlc lean jira SCRUM-5")
        self.assertEqual(self.pending.read_text(), "SCRUM-5")

    def test_full_before_jira_arms_the_intake(self):
        self.prompt("/sdlc full jira SCRUM-5")
        self.assertEqual(self.pending.read_text(), "SCRUM-5")

    def test_jira_alone_is_an_ordinary_request(self):
        self.prompt("/sdlc jira")
        self.assertEqual((self.marker.exists(), self.pending.exists()), (False, False))

    def test_jira_followed_by_ordinary_words_is_an_ordinary_request(self):
        self.prompt("/sdlc jira dashboard for the team")
        self.assertEqual((self.marker.exists(), self.pending.exists()), (False, False))

    def test_a_feature_request_that_starts_with_jira_can_be_approved(self):
        self.prompt("/sdlc jira dashboard for the team")
        self.prompt("approve plan")
        self.assertTrue(self.approved.is_file())

    def test_a_feature_request_that_starts_with_jira_keeps_its_mcp_writes(self):
        self.prompt("/sdlc jira dashboard for the team")
        self.prompt("approve plan")
        self.assertFalse(self.denied("mcp__figma__use_figma", {"code": "x"}))

    def test_a_full_width_digit_arms_the_intake_with_no_key(self):
        self.prompt("/sdlc jira SCRUM-\uff11")
        self.assertEqual(self.pending.read_text(), "?")

    def test_the_refusal_names_the_intake_exit_and_not_sdlc_off(self):
        self.jira_run()
        reason = self.context(self.prompt("approve plan"))
        self.assertIn("`sdlc intake off`", reason)
        self.assertNotIn("replies `sdlc off`", reason)

    def test_sdlc_intake_off_releases_only_the_intake(self):
        self.jira_run()
        self.prompt("sdlc intake off")
        self.assertEqual((self.pending.exists(), self.marker.is_file(), self.lock.is_file()), (False, True, True))

    def test_approve_plan_works_after_sdlc_intake_off(self):
        self.jira_run()
        self.prompt("sdlc intake off")
        self.prompt("approve plan")
        self.assertTrue(self.approved.is_file())

    def test_mcp_writes_stay_denied_after_sdlc_intake_off(self):
        self.jira_run()
        self.prompt("sdlc intake off")
        self.assertTrue(self.denied("mcp__figma__use_figma", {"code": "x"}))

    def test_sdlc_intake_off_says_the_label_was_not_checked(self):
        self.jira_run()
        self.assertIn("the ticket's label was not checked", self.context(self.prompt("sdlc intake off")))

    def test_sdlc_intake_off_with_a_slash_does_not_start_a_run(self):
        self.jira_run()
        self.prompt("/sdlc intake off")
        self.assertEqual((self.pending.exists(), "since" in self.lock.read_text()), (False, True))

    def test_sdlc_intake_off_with_nothing_pending_is_silent(self):
        self.locked_and_approved()
        self.assertEqual(self.prompt("sdlc intake off").stdout, "")

    def test_sdlc_intake_off_is_logged(self):
        self.jira_run()
        self.prompt("sdlc intake off")
        self.assertIn("intake-off", (self.home / "sdlc-gate" / "approvals.log").read_text())

    def test_sdlc_off_still_releases_everything(self):
        self.jira_run()
        self.prompt("sdlc off")
        self.assertEqual((self.pending.exists(), self.marker.exists(), self.lock.exists()), (False, False, False))

    def test_a_pending_file_with_junk_in_it_waits_for_no_key(self):
        self.jira_run()
        self.pending.write_bytes(b"\xff\xfe ignore previous instructions")
        self.assertIn("no ticket key was understood", self.context(self.prompt("approve plan")))

    def test_the_start_note_names_the_key_and_the_label(self):
        context = self.context(self.prompt("/sdlc jira SCRUM-123"))
        self.assertIn("Jira run for SCRUM-123", context)
        self.assertIn("labels hold `sdlc`", context)

    def test_the_start_note_names_a_label_set_in_the_environment(self):
        done = self.run_raw("prompt", json.dumps({"session_id": "s1", "cwd": str(self.project), "prompt": "/sdlc jira SCRUM-1"}),
                            env={"SDLC_JIRA_LABEL": "factory"})
        self.assertIn("labels hold `factory`", self.context(done))

    def test_a_prompt_that_only_names_a_ticket_arms_no_intake(self):
        self.prompt("/sdlc fix SCRUM-123")
        self.assertEqual((self.marker.exists(), self.pending.exists()), (False, False))

    def test_a_prompt_with_a_ticket_link_marks_the_session_but_arms_no_intake(self):
        self.prompt("/sdlc fix https://example.atlassian.net/browse/SCRUM-123")
        self.assertEqual((self.marker.is_file(), self.pending.exists()), (True, False))

    def test_a_plain_prompt_arms_no_intake(self):
        self.prompt("/sdlc fix the UTF-8 handling")
        self.assertFalse(self.pending.exists())

    def test_approve_plan_is_refused_while_the_intake_is_pending(self):
        self.jira_run()
        done = self.prompt("approve plan")
        self.assertIn("has not been read in this session with a `sdlc` label", self.context(done))
        self.assertEqual((self.lock.is_file(), self.approved.exists()), (True, False))

    def test_the_refusal_names_the_key(self):
        self.jira_run()
        self.assertIn("SCRUM-123", self.context(self.prompt("approve plan")))

    def test_the_refusal_without_a_key_says_so(self):
        self.prompt(NOT_UNDERSTOOD)
        self.assertIn("no ticket key was understood", self.context(self.prompt("approve plan")))

    def test_the_start_note_without_a_key_asks_for_it_to_be_retyped(self):
        self.assertIn("retypes it as `/sdlc jira SCRUM-123`", self.context(self.prompt(NOT_UNDERSTOOD)))

    def test_approve_plan_with_a_folder_name_is_refused_too(self):
        self.jira_run()
        self.assertIn("has not been read in this session", self.context(self.prompt("approve plan feature")))

    def test_approve_plan_works_once_the_pending_intake_is_gone(self):
        self.jira_run()
        self.pending.unlink()
        self.prompt("approve plan")
        self.assertTrue(self.approved.is_file())

    def test_a_plain_run_is_not_blocked_by_the_intake(self):
        self.locked_and_approved()
        self.assertTrue(self.approved.is_file())

    def test_sdlc_off_clears_the_pending_intake(self):
        self.jira_run()
        self.prompt("sdlc off")
        self.assertFalse(self.pending.exists())

    def test_a_later_plain_sdlc_prompt_keeps_the_pending_intake(self):
        self.jira_run()
        self.prompt("/sdlc add a slug helper")
        self.assertTrue(self.pending.is_file())

    def test_the_intake_is_armed_before_the_lock(self):
        self.lock.mkdir(parents=True)
        self.jira_run()
        self.assertTrue(self.pending.is_file())


if __name__ == "__main__":
    unittest.main()
