"""Tests for the `jira-seen` mode: reading the ticket's labels from a response.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.mcp_base import McpGateTest, NOT_UNDERSTOOD, UUID_SERVER


GET_ISSUE = UUID_SERVER + "getJiraIssue"
ASK = {"cloudId": "c1", "issueIdOrKey": "SCRUM-123"}


def issue(labels, key="SCRUM-123", **fields):
    return {"key": key, "fields": {"summary": "Add a slug helper", "labels": labels, **fields}}


def as_json_string(obj):
    return json.dumps(obj)


def as_text_blocks(obj):
    return [{"type": "text", "text": json.dumps(obj)}]


def as_content_object(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


class SeenTest(McpGateTest):
    """The label check of `jira-seen`, on hand-written responses: the real shape of a Jira response was not
    available, so these prove the logic and the fail-closed paths, not that the host sends this shape."""

    def setUp(self):
        super().setUp()
        self.pending = self.home / "sdlc-gate" / "s1.jira-intake"

    def seen(self, response, tool=GET_ISSUE, tool_input=None, **payload):
        return self.run_hook("jira-seen", {"tool_name": tool, "tool_input": ASK if tool_input is None else tool_input,
                                           "tool_response": response, **payload})

    def note(self, done):
        return self.context(done)

    def test_a_labeled_ticket_as_a_json_string_clears_the_intake(self):
        self.jira_run()
        self.seen(as_json_string(issue(["sdlc", "backend"])))
        self.assertFalse(self.pending.exists())

    def test_a_labeled_ticket_as_text_blocks_clears_the_intake(self):
        self.jira_run()
        self.seen(as_text_blocks(issue(["sdlc"])))
        self.assertFalse(self.pending.exists())

    def test_a_labeled_ticket_as_a_content_object_clears_the_intake(self):
        self.jira_run()
        self.seen(as_content_object(issue(["sdlc"])))
        self.assertFalse(self.pending.exists())

    def test_a_labeled_ticket_as_a_plain_object_clears_the_intake(self):
        self.jira_run()
        self.seen(issue(["sdlc"]))
        self.assertFalse(self.pending.exists())

    def test_a_top_level_labels_list_counts(self):
        self.jira_run()
        self.seen({"key": "SCRUM-123", "labels": ["sdlc"]})
        self.assertFalse(self.pending.exists())

    def test_a_label_in_upper_case_counts(self):
        self.jira_run()
        self.seen(issue(["SDLC"]))
        self.assertFalse(self.pending.exists())

    def test_a_label_object_with_a_name_counts(self):
        self.jira_run()
        self.seen(issue([{"name": "sdlc"}]))
        self.assertFalse(self.pending.exists())

    def test_the_note_says_approve_plan_is_no_longer_held(self):
        self.jira_run()
        self.assertIn("`approve plan` is no longer held for the intake", self.note(self.seen(issue(["sdlc"]))))

    def test_approve_plan_works_after_the_label_was_seen(self):
        self.jira_run()
        self.seen(issue(["sdlc"]))
        self.prompt("approve plan")
        self.assertTrue((self.home / "sdlc-gate" / "s1.approved").is_file())

    def test_the_label_set_in_the_environment_is_the_one_checked(self):
        self.jira_run()
        self.run_raw("jira-seen", json.dumps({"session_id": "s1", "cwd": str(self.project), "tool_name": GET_ISSUE, "tool_input": ASK,
                                              "tool_response": issue(["factory"])}), env={"SDLC_JIRA_LABEL": "factory"})
        self.assertFalse(self.pending.exists())

    def test_a_ticket_without_the_label_keeps_the_intake_pending(self):
        self.jira_run()
        done = self.seen(issue(["backend"]))
        self.assertTrue(self.pending.is_file())
        self.assertIn("abandoned: no sdlc label", self.note(done))

    def test_approve_plan_stays_refused_after_an_unlabeled_read(self):
        self.jira_run()
        self.seen(issue(["backend"]))
        self.assertIn("has not been read in this session", self.context(self.prompt("approve plan")))

    def test_a_description_that_spells_a_labels_line_does_not_count(self):
        self.jira_run()
        self.seen(issue(["backend"], description="Labels: sdlc"))
        self.assertTrue(self.pending.is_file())

    def test_a_description_that_spells_a_labels_line_does_not_count_when_the_ticket_has_no_labels_list(self):
        self.jira_run()
        self.seen({"key": "SCRUM-123", "fields": {"summary": "x", "description": "Labels: sdlc"}})
        self.assertTrue(self.pending.is_file())

    def test_a_description_that_is_json_with_labels_does_not_count(self):
        self.jira_run()
        self.seen(as_text_blocks(issue([], description=json.dumps({"labels": ["sdlc"]}))))
        self.assertTrue(self.pending.is_file())

    def test_a_nested_object_with_a_labels_key_does_not_count(self):
        self.jira_run()
        self.seen({"key": "SCRUM-123", "fields": {"labels": [], "comment": {"comments": [{"labels": ["sdlc"]}]}}})
        self.assertTrue(self.pending.is_file())

    def test_a_ticket_whose_response_has_no_labels_list_has_no_label(self):
        self.jira_run()
        done = self.seen({"key": "SCRUM-123", "fields": {"summary": "x"}})
        self.assertTrue(self.pending.is_file())
        self.assertIn("abandoned: no sdlc label", self.note(done))

    def test_a_response_with_no_issue_in_it_is_unreadable(self):
        self.jira_run()
        done = self.seen({"issue": {"key": "SCRUM-123", "fields": {"labels": ["sdlc"]}}})
        self.assertTrue(self.pending.is_file())
        self.assertIn("could not be read as one Jira issue", self.note(done))

    def test_the_unreadable_note_names_the_intake_exit(self):
        self.jira_run()
        self.assertIn("`sdlc intake off`", self.note(self.seen("Labels: sdlc")))

    def test_a_markdown_response_is_not_read(self):
        self.jira_run()
        done = self.seen("Key: SCRUM-123\nLabels: sdlc, backend\n")
        self.assertTrue(self.pending.is_file())
        self.assertIn("could not be read as one Jira issue", self.note(done))

    def test_another_ticket_does_not_clear_the_intake(self):
        self.jira_run()
        done = self.seen(issue(["sdlc"], key="SCRUM-999"))
        self.assertTrue(self.pending.is_file())
        self.assertIn("the issue in this response is not SCRUM-123", self.note(done))

    def test_with_no_key_understood_no_ticket_clears_the_intake(self):
        self.prompt(NOT_UNDERSTOOD)
        self.seen(issue(["sdlc"], key="SCRUM-9"))
        self.assertTrue(self.pending.is_file())

    def test_a_sibling_ticket_whose_number_starts_with_the_key_does_not_clear_it(self):
        self.jira_run()
        self.seen({"fields": {"labels": ["sdlc"]}}, tool_input={"cloudId": "c1", "issueIdOrKey": "SCRUM-1234"})
        self.assertTrue(self.pending.is_file())

    def test_two_objects_with_a_labels_list_are_not_trusted(self):
        self.jira_run()
        spoof = {"key": "SCRUM-123", "labels": ["sdlc"]}
        done = self.seen([{"type": "text", "text": json.dumps(issue(["backend"]))}, {"type": "text", "text": json.dumps(spoof)}])
        self.assertTrue(self.pending.is_file())
        self.assertIn("could not be read as one Jira issue", self.note(done))

    def test_deeply_nested_json_in_a_block_is_skipped_not_fatal(self):
        self.jira_run()
        done = self.seen([{"type": "text", "text": "{" + "[" * 100000}, {"type": "text", "text": json.dumps(issue(["sdlc"]))}])
        self.assertFalse(self.pending.exists())
        self.assertEqual(done.returncode, 0)

    def test_a_crash_of_the_hook_is_logged_and_leaves_the_intake_pending(self):
        self.jira_run()
        self.seen(issue(["sdlc"]), tool=UUID_SERVER + "executeRead", tool_input=["not", "a", "mapping"])
        self.assertTrue(self.pending.is_file())
        self.assertIn("jira-seen-error", (self.home / "sdlc-gate" / "approvals.log").read_text())

    def test_a_response_with_no_key_is_not_accepted_even_when_the_call_asked_for_the_ticket(self):
        self.jira_run()
        self.seen({"fields": {"labels": ["sdlc"]}}, tool_input={"cloudId": "c1", "issueIdOrKey": "scrum-123"})
        self.assertTrue(self.pending.is_file())

    def test_a_block_that_spells_a_labels_list_beside_an_issue_with_none_is_not_trusted(self):
        self.jira_run()
        real = {"key": "SCRUM-123", "fields": {"summary": "x"}}
        done = self.seen([{"type": "text", "text": json.dumps(real)}, {"type": "text", "text": json.dumps({"labels": ["sdlc"]})}])
        self.assertTrue(self.pending.is_file())
        self.assertIn("could not be read as one Jira issue", self.note(done))

    def test_a_question_mark_key_cannot_be_satisfied_by_a_call_that_asks_for_a_question_mark(self):
        self.prompt(NOT_UNDERSTOOD)
        done = self.seen({"fields": {"labels": ["sdlc"]}}, tool_input={"cloudId": "c1", "issueIdOrKey": "?"})
        self.assertEqual((self.pending.read_text(), "no ticket key was understood" in self.note(done)), ("?", True))

    def test_a_numeric_id_with_no_key_in_the_response_does_not_clear_the_intake(self):
        self.jira_run()
        self.seen({"fields": {"labels": ["sdlc"]}}, tool_input={"cloudId": "c1", "issueIdOrKey": "10001"})
        self.assertTrue(self.pending.is_file())

    def test_execute_read_naming_get_jira_issue_clears_the_intake(self):
        self.jira_run()
        self.seen(issue(["sdlc"]), tool=UUID_SERVER + "executeRead", tool_input={"cloudId": "c1", "name": "getJiraIssue"})
        self.assertFalse(self.pending.exists())

    def test_execute_read_naming_another_operation_is_ignored(self):
        self.jira_run()
        self.seen(issue(["sdlc"]), tool=UUID_SERVER + "executeRead", tool_input={"cloudId": "c1", "name": "getJiraIssueWatchers"})
        self.assertTrue(self.pending.is_file())

    def test_a_snake_case_tool_clears_the_intake(self):
        self.jira_run()
        self.seen(issue(["sdlc"]), tool="mcp__jira__jira_get_issue")
        self.assertFalse(self.pending.exists())

    def test_a_search_is_not_a_read_of_the_ticket(self):
        self.jira_run()
        done = self.seen(issue(["sdlc"]), tool=UUID_SERVER + "searchJiraIssuesUsingJql")
        self.assertEqual((self.pending.is_file(), done.stdout), (True, ""))

    def test_a_session_with_no_pending_intake_gets_no_output(self):
        self.prompt("/sdlc fix SCRUM-123")
        self.assertEqual(self.seen(issue(["sdlc"])).stdout, "")

    def test_a_response_that_is_none_leaves_the_intake_pending_and_exits_0(self):
        self.jira_run()
        done = self.seen(None)
        self.assertEqual((done.returncode, self.pending.is_file()), (0, True))

    def test_a_three_megabyte_response_leaves_the_intake_pending_and_exits_0(self):
        self.jira_run()
        done = self.seen("x" * 3_000_000)
        self.assertEqual((done.returncode, self.pending.is_file()), (0, True))

    def test_the_hook_never_exits_2(self):
        self.jira_run()
        self.assertNotEqual(self.run_raw("jira-seen", "not json").returncode, 2)

    def test_the_label_check_is_logged(self):
        self.jira_run()
        self.seen(issue(["sdlc"]))
        self.assertIn("jira-seen", (self.home / "sdlc-gate" / "approvals.log").read_text())

    def test_an_unsafe_session_id_changes_nothing(self):
        self.jira_run()
        done = self.run_hook("jira-seen", {"session_id": "../x", "tool_name": GET_ISSUE, "tool_input": ASK, "tool_response": issue(["sdlc"])})
        self.assertEqual((done.stdout, self.pending.is_file()), ("", True))


if __name__ == "__main__":
    unittest.main()
