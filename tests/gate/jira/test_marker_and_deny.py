"""Tests for the Jira-run marker and for the MCP tools the gate denies in a Jira run.

Run: python3 -I -m unittest discover -s tests
"""
import unittest

from support.mcp_base import APP_TOOLS, McpGateTest, NAMED_WRITES, OTHER_READS, OTHER_WRITES, READS_WITHOUT_A_VERB, UUID_LOOKALIKES, UUID_READS, UUID_SERVER, UUID_WRITES


class MarkerTest(McpGateTest):
    def test_a_jira_prompt_writes_the_marker(self):
        self.jira_run()
        self.assertTrue(self.marker.is_file())

    def test_a_lowercase_key_still_writes_the_marker(self):
        self.prompt("/sdlc jira scrum-123")
        self.assertTrue(self.marker.is_file())

    def test_jira_followed_by_a_newline_writes_the_marker(self):
        self.prompt("/sdlc jira\nSCRUM-123")
        self.assertTrue(self.marker.is_file())

    def test_a_namespaced_jira_prompt_writes_the_marker(self):
        self.prompt("/my-agents:sdlc jira SCRUM-123")
        self.assertTrue(self.marker.is_file())

    def test_resuming_a_jira_run_writes_the_marker(self):
        self.prompt("/sdlc resume jira-scrum-123")
        self.assertTrue(self.marker.is_file())

    def test_a_newline_between_sdlc_and_jira_writes_the_marker(self):
        self.prompt("/sdlc\njira SCRUM-1")
        self.assertTrue(self.marker.is_file())

    def test_a_newline_in_a_resume_of_a_jira_run_writes_the_marker(self):
        self.prompt("/sdlc resume\njira-scrum-1")
        self.assertTrue(self.marker.is_file())

    def test_a_start_prompt_that_only_names_a_ticket_writes_no_marker(self):
        self.prompt("/sdlc fix SCRUM-123")
        self.assertFalse(self.marker.exists())

    def test_a_start_prompt_with_a_ticket_link_writes_the_marker(self):
        self.prompt("/sdlc https://example.atlassian.net/browse/SCRUM-123")
        self.assertTrue(self.marker.is_file())

    def test_resuming_by_a_bare_ticket_key_writes_no_marker(self):
        self.prompt("/sdlc resume SCRUM-123")
        self.assertFalse(self.marker.exists())

    def test_lean_before_jira_writes_the_marker(self):
        self.prompt("/sdlc lean jira SCRUM-1")
        self.assertTrue(self.marker.is_file())

    def test_full_before_jira_writes_the_marker(self):
        self.prompt("/sdlc full jira SCRUM-1")
        self.assertTrue(self.marker.is_file())

    def test_a_start_prompt_that_only_looks_like_a_key_writes_no_marker(self):
        self.prompt("/sdlc fix the UTF-8 handling")
        self.assertFalse(self.marker.exists())

    def test_a_plain_run_that_mentions_utf8_keeps_its_mcp_writes(self):
        self.prompt("/sdlc fix the UTF-8 handling")
        self.prompt("approve plan")
        self.assertFalse(self.denied("mcp__figma__use_figma", {"code": "x"}))

    def test_a_plain_sdlc_prompt_writes_no_marker(self):
        self.prompt("/sdlc add a slug helper")
        self.assertFalse(self.marker.exists())

    def test_a_word_that_only_starts_like_jira_writes_no_marker(self):
        self.prompt("/sdlc jiraffe tracker")
        self.assertFalse(self.marker.exists())

    def test_the_marker_is_written_before_the_lock(self):
        self.lock.mkdir(parents=True)  # a lock that cannot be written: the run fails after the marker, not before
        self.jira_run()
        self.assertTrue(self.marker.is_file())

    def test_approve_plan_keeps_the_marker(self):
        self.jira_run_approved()
        self.assertTrue(self.marker.is_file())

    def test_a_later_plain_sdlc_prompt_keeps_the_marker(self):
        self.jira_run_approved()
        self.prompt("/sdlc add a slug helper")
        self.assertTrue(self.marker.is_file())

    def test_sdlc_off_removes_the_marker_and_says_so(self):
        self.jira_run_approved()
        done = self.prompt("sdlc off")
        self.assertFalse(self.marker.exists())
        self.assertIn("MCP writes are no longer blocked", self.context(done))

    def test_sdlc_off_without_a_marker_does_not_mention_atlassian(self):
        self.locked_and_approved()
        self.assertNotIn("Atlassian", self.context(self.prompt("sdlc off")))

    def test_a_jira_key_in_a_reply_of_a_gated_session_writes_no_marker(self):
        self.locked_and_approved()
        self.prompt("now work on SCRUM-123 please")
        self.assertFalse(self.marker.exists())

    def test_a_reply_that_says_sha_256_in_a_gated_session_writes_no_marker(self):
        self.locked_and_approved()
        self.prompt("use SHA-256 for the digest")
        self.assertFalse(self.marker.exists())

    def test_an_atlassian_link_in_a_reply_of_a_gated_session_writes_the_marker(self):
        self.locked_and_approved()
        self.prompt("see https://example.atlassian.net/browse/SCRUM-9")
        self.assertTrue(self.marker.is_file())

    def test_a_jira_key_in_a_session_with_no_run_writes_no_marker(self):
        self.prompt("work on SCRUM-123 please")
        self.assertFalse(self.marker.exists())


class DenyTest(McpGateTest):
    def test_every_write_is_denied_under_a_uuid_server_id(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(UUID_WRITES), list(UUID_WRITES))

    def test_every_write_is_denied_under_a_named_server(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(NAMED_WRITES), list(NAMED_WRITES))

    def test_every_read_is_allowed(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(UUID_READS), [])

    def test_a_write_named_like_a_read_is_denied(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(UUID_LOOKALIKES), list(UUID_LOOKALIKES))

    def test_execute_read_naming_a_write_that_starts_like_a_read_is_denied(self):
        self.jira_run_approved()
        self.assertTrue(self.denied(UUID_SERVER + "executeRead", {"cloudId": "c1", "name": "getOrCreateJiraIssue"}))

    def test_a_write_by_a_subagent_is_denied(self):
        self.jira_run_approved()
        done = self.mcp(UUID_SERVER + "editJiraIssue", agent_type="backend-developer", agent_id="a1")
        self.assertEqual(self.reason(done).startswith("sdlc-gate: editJiraIssue"), True)

    def test_a_write_by_a_server_named_jira_is_denied_and_a_read_is_allowed(self):
        self.jira_run_approved()
        self.assertEqual((self.denied("mcp__jira__create_issue"), self.denied("mcp__jira__get_issue")), (True, False))

    def test_a_write_by_a_server_named_atlassian_is_denied(self):
        self.jira_run_approved()
        self.assertTrue(self.denied("mcp__atlassian__createIssue"))

    def test_the_deny_reason_names_the_tool_and_sdlc_off(self):
        self.jira_run_approved()
        reason = self.reason(self.mcp(UUID_SERVER + "addOrEditJiraIssueComment"))
        self.assertIn("addOrEditJiraIssueComment", reason)
        self.assertIn("`sdlc off`", reason)

    def test_an_unknown_snake_case_jira_tool_is_denied(self):
        self.jira_run_approved()
        self.assertTrue(self.denied("mcp__other__jira_foo"))

    def test_a_snake_case_jira_read_is_allowed(self):
        self.jira_run_approved()
        self.assertFalse(self.denied("mcp__other__jira_get_issue"))

    def test_execute_read_naming_a_read_is_allowed(self):
        self.jira_run_approved()
        self.assertFalse(self.denied(UUID_SERVER + "executeRead", {"cloudId": "c1", "name": "getJiraIssue"}))

    def test_execute_read_naming_a_write_is_denied(self):
        self.jira_run_approved()
        self.assertTrue(self.denied(UUID_SERVER + "executeRead", {"cloudId": "c1", "name": "createJiraIssue"}))

    def test_other_servers_reads_are_allowed_in_a_jira_run(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(OTHER_READS), [])

    def test_other_servers_writes_are_denied_in_a_jira_run(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(OTHER_WRITES), list(OTHER_WRITES))

    def test_a_read_without_a_read_verb_is_denied_too(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(READS_WITHOUT_A_VERB), list(READS_WITHOUT_A_VERB))

    def test_the_apps_own_task_tools_are_allowed_in_a_jira_run(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(APP_TOOLS), [])

    def test_the_deny_reason_for_another_servers_write_says_it_may_change_something_outside(self):
        self.jira_run_approved()
        self.assertIn("may change something outside this session", self.reason(self.mcp("mcp__supabase__execute_sql")))

    def test_a_plain_sdlc_session_denies_no_atlassian_write(self):
        self.locked_and_approved()
        self.assertEqual(self.denied_among(UUID_WRITES), [])

    def test_a_session_that_never_typed_sdlc_denies_nothing(self):
        self.assertEqual(self.denied_among(UUID_WRITES), [])

    def test_a_tool_that_is_not_mcp_is_not_judged(self):
        self.jira_run_approved()
        self.assertFalse(self.denied("createJiraIssue"))

    def test_an_unsafe_session_id_denies_nothing(self):
        self.jira_run_approved()
        done = self.run_hook("mcp", {"session_id": "../x", "tool_name": UUID_SERVER + "editJiraIssue", "tool_input": {}})
        self.assertEqual(done.stdout, "")


if __name__ == "__main__":
    unittest.main()
