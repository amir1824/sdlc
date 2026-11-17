"""Tests for the `mcp` mode of plugins/sdlc/hooks/sdlc_gate.py (no MCP write in a session with a Jira run) and for the
pending Jira intake that keeps `approve plan` from passing before the ticket was read.

Run: python3 -I -m unittest discover -s tests
These feed the hook the documented input shape and prove the gate's logic, not that the host runs the hook
for these tool names or what a subagent's session id is: that is checked with SDLC_GATE_TRACE=1 in a real session.
"""
import json
import unittest
from pathlib import Path

from test_sdlc_gate import GateTest

REPO = Path(__file__).resolve().parent.parent
UUID_SERVER = "mcp__0dcd0205-81c2-491f-b8e9-2617c355f029__"
NAMED_SERVER = "mcp__atlassian__"
WRITES = ("createJiraIssue", "editJiraIssue", "transitionJiraIssue", "addOrEditJiraIssueComment",
          "createConfluenceContent", "updateConfluenceContent", "showConfluenceEditor", "addGraphContext",
          "executeWrite", "executeDestructive")
READS = ("getJiraIssue", "searchJiraIssuesUsingJql", "listJiraIssueComments", "lookupJiraAccountId",
         "getConfluenceContent", "searchConfluence", "search", "discover", "atlassianUserInfo", "atlassianHome",
         "getAccessibleAtlassianResources", "getGraphContext", "getGraphObject", "getWorkPortfolio", "getPeopleInfo",
         "getCollaborators", "getWorkActivity", "getLoomObjectsContent", "getJiraIssueComment")
LOOKALIKES = ("getOrCreateJiraIssue", "findOrCreateJiraIssue", "searchAndUpdateConfluencePage", "listAndCloseJiraIssues",
              "readThenDeleteJira", "get_jira_and_delete", "discoverAndCreateJiraIssue", "atlassianHomeWriteX",
              "add_graph_context", "execute-write", "execute_destructive", "get_or_set", "list_then_post", "fetchAndPush",
              "search_and_notify", "readThenSubmit", "getAndSetX", "readAndExecute", "fetchAndPost")
OTHER_READS = ("mcp__figma__get_design_context", "mcp__supabase__list_tables", "mcp__Claude_Browser__read_page",
               "mcp__Claude_Browser__get_page_text")
OTHER_WRITES = ("mcp__supabase__execute_sql", "mcp__Claude_Browser__navigate", "mcp__terminal__run_in_terminal",
                "mcp__7eca610e-292a-4260-90ca-1b88681efe7a__generate_image", "mcp__ctx__graphql_mutation_x",
                "mcp__ccd_session__start_session", "mcp__scheduled-tasks__create_scheduled_task")
APP_TOOLS = ("mcp__ccd_turn__update_plan", "mcp__ccd_turn__wrap_up", "mcp__ccd_session__mark_chapter")


class McpGateTest(GateTest):
    def setUp(self):
        super().setUp()
        self.marker = self.home / "sdlc-gate" / "s1.jira"

    def mcp(self, tool, tool_input=None, **payload):  # payload: agent_id, agent_type
        return self.run_hook("mcp", {"tool_name": tool, "tool_input": tool_input or {}, **payload})

    def denied(self, tool, tool_input=None):
        return bool(self.mcp(tool, tool_input).stdout)

    def denied_among(self, tools):
        return [tool for tool in tools if self.denied(tool)]

    def jira_run(self):
        self.prompt("/sdlc jira SCRUM-123")

    def jira_run_approved(self):
        self.jira_run()
        (self.home / "sdlc-gate" / "s1.jira-intake").unlink()  # as if the ticket's label had been seen
        self.prompt("approve plan")

    def jira_folder(self, slug="jira-scrum-123"):
        (self.project / ".sdlc" / slug).mkdir(parents=True)


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
        self.assertEqual(self.denied_among([UUID_SERVER + name for name in WRITES]), [UUID_SERVER + name for name in WRITES])

    def test_every_write_is_denied_under_a_named_server(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among([NAMED_SERVER + name for name in WRITES]), [NAMED_SERVER + name for name in WRITES])

    def test_every_read_is_allowed(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among([UUID_SERVER + name for name in READS]), [])

    def test_a_write_named_like_a_read_is_denied(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among([UUID_SERVER + name for name in LOOKALIKES]), [UUID_SERVER + name for name in LOOKALIKES])

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

    def test_the_apps_own_task_tools_are_allowed_in_a_jira_run(self):
        self.jira_run_approved()
        self.assertEqual(self.denied_among(APP_TOOLS), [])

    def test_the_deny_reason_for_another_servers_write_says_it_may_change_something_outside(self):
        self.jira_run_approved()
        self.assertIn("may change something outside this session", self.reason(self.mcp("mcp__supabase__execute_sql")))

    def test_a_plain_sdlc_session_denies_no_atlassian_write(self):
        self.locked_and_approved()
        self.assertEqual(self.denied_among([UUID_SERVER + name for name in WRITES]), [])

    def test_a_session_that_never_typed_sdlc_denies_nothing(self):
        self.assertEqual(self.denied_among([UUID_SERVER + name for name in WRITES]), [])

    def test_a_tool_that_is_not_mcp_is_not_judged(self):
        self.jira_run_approved()
        self.assertFalse(self.denied("createJiraIssue"))

    def test_an_unsafe_session_id_denies_nothing(self):
        self.jira_run_approved()
        done = self.run_hook("mcp", {"session_id": "../x", "tool_name": UUID_SERVER + "editJiraIssue", "tool_input": {}})
        self.assertEqual(done.stdout, "")


class IntakeTest(McpGateTest):
    def setUp(self):
        super().setUp()
        self.pending = self.home / "sdlc-gate" / "s1.jira-intake"
        self.approved = self.home / "sdlc-gate" / "s1.approved"

    def test_a_jira_prompt_arms_the_intake_with_the_key(self):
        self.prompt("/sdlc jira SCRUM-123")
        self.assertEqual((self.pending.read_text(), self.marker.read_text()), ("SCRUM-123", "SCRUM-123"))

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

    def test_jira_alone_arms_the_intake_with_no_key(self):
        self.prompt("/sdlc jira")
        self.assertEqual(self.pending.read_text(), "?")

    def test_jira_followed_by_words_arms_the_intake_with_no_key(self):
        self.prompt("/sdlc jira fix the slug bug")
        self.assertEqual(self.pending.read_text(), "?")

    def test_a_full_width_digit_arms_the_intake_with_no_key(self):
        self.prompt("/sdlc jira SCRUM-\uff11")
        self.assertEqual(self.pending.read_text(), "?")

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
        self.prompt("/sdlc jira")
        self.assertIn("no ticket key was understood", self.context(self.prompt("approve plan")))

    def test_the_start_note_without_a_key_asks_for_it_to_be_retyped(self):
        self.assertIn("retypes it as `/sdlc jira SCRUM-123`", self.context(self.prompt("/sdlc jira")))

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

    def test_a_response_with_no_labels_list_is_not_a_ticket(self):
        self.jira_run()
        done = self.seen({"key": "SCRUM-123", "fields": {"summary": "x"}})
        self.assertTrue(self.pending.is_file())
        self.assertIn("could not be read as one Jira issue", self.note(done))

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
        self.prompt("/sdlc jira")
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
        self.prompt("/sdlc jira")
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


class LateRunTest(McpGateTest):
    def test_a_jira_folder_created_after_a_plain_sdlc_prompt_denies_writes(self):
        self.locked_and_approved()
        self.jira_folder()
        self.assertTrue(self.denied(UUID_SERVER + "executeWrite"))

    def test_the_marker_is_written_when_the_folder_is_first_seen(self):
        self.locked_and_approved()
        self.jira_folder()
        self.denied(UUID_SERVER + "executeWrite")
        self.assertTrue(self.marker.is_file())

    def test_deleting_the_folder_afterwards_does_not_lift_the_marker(self):
        self.locked_and_approved()
        self.jira_folder()
        self.denied(UUID_SERVER + "executeWrite")
        (self.project / ".sdlc" / "jira-scrum-123").rmdir()
        self.assertTrue(self.denied(UUID_SERVER + "executeWrite"))

    def test_a_jira_folder_in_a_session_with_no_run_denies_nothing(self):
        self.jira_folder()
        self.assertFalse(self.denied(UUID_SERVER + "executeWrite"))

    def test_a_write_by_another_server_in_a_gated_session_with_a_jira_folder_is_denied_and_marks_it(self):
        self.locked_and_approved()
        self.jira_folder()
        self.assertEqual((self.denied("mcp__figma__use_figma", {"code": "x"}), self.marker.is_file()), (True, True))

    def test_a_read_by_another_server_does_not_write_the_marker(self):
        self.locked_and_approved()
        self.jira_folder()
        self.denied("mcp__figma__get_design_context")
        self.assertFalse(self.marker.exists())

    def test_a_folder_that_is_not_a_jira_run_denies_nothing(self):
        self.locked_and_approved()
        self.jira_folder("feature-x")
        self.assertFalse(self.denied(UUID_SERVER + "executeWrite"))

    def test_sdlc_off_lifts_a_marker_written_late(self):
        self.locked_and_approved()
        self.jira_folder()
        self.denied(UUID_SERVER + "executeWrite")
        self.prompt("sdlc off")
        self.assertFalse(self.denied(UUID_SERVER + "executeWrite"))


class CrashTest(McpGateTest):
    """A crash of the mcp hook denies only where a Jira run is on; elsewhere the error propagates and the host allows."""

    def crash(self):
        return self.mcp(UUID_SERVER + "executeRead", ["cloudId"])

    def test_a_crash_in_a_jira_run_denies(self):
        self.jira_run_approved()
        done = self.crash()
        self.assertEqual(done.returncode, 0)
        self.assertIn("the gate failed", self.reason(done))
        self.assertIn("has a Jira run", self.reason(done))

    def test_a_crash_in_a_plain_sdlc_session_does_not_deny(self):
        self.locked_and_approved()
        done = self.crash()
        self.assertEqual((done.stdout, done.returncode != 0), ("", True))

    def test_a_crash_in_a_session_with_no_run_does_not_deny(self):
        done = self.crash()
        self.assertEqual((done.stdout, done.returncode != 0), ("", True))

    def test_the_crash_exit_code_is_never_2(self):
        self.assertNotEqual(self.crash().returncode, 2)


class WiringTest(unittest.TestCase):
    def pre_tool_use(self):
        return json.loads((REPO / "plugins" / "sdlc" / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]

    def test_hooks_json_keeps_the_file_and_bash_entry_first(self):
        self.assertEqual(self.pre_tool_use()[0]["matcher"], "Edit|Write|MultiEdit|NotebookEdit|Bash")

    def test_hooks_json_adds_an_anchored_mcp_entry_second(self):
        entry = self.pre_tool_use()[1]
        self.assertEqual((entry["matcher"], entry["hooks"][0]["command"]),
                         ("^mcp__", 'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" mcp'))

    def test_sdlc_md_describes_the_jira_intake(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("## Jira intake", text)
        self.assertIn("under the heading `Ticket text, untrusted, n=1`", text)
        self.assertIn("When that line is absent the hooks are not installed: stop and tell the owner", text)
        self.assertIn("`waiting: jira unavailable`", text)

    def test_sdlc_md_asks_for_the_tickets_context_and_keeps_jira_priority_out_of_the_risk(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("its context (issue type, status, priority, labels, components, parent or epic, linked issues)", text)
        self.assertIn("a `Ticket context` list copies the issue type, status, priority, labels", text)
        self.assertIn("Jira's priority and type are hints, never the run's risk", text)
        self.assertIn("A status of Done, Closed or Resolved, or an `is blocked by` link to an issue that is not done, is an Owner question before Plan.", text)

    def test_sdlc_md_says_what_a_missing_label_and_a_denied_mcp_write_mean(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("write `abandoned: no <label> label` as the last line of `status.md`", text)
        self.assertIn("is reported `not run`, with the reason", text)

    def test_the_lean_section_allows_the_ticket_intent_file(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("the chair writes no `intent.md` (a Jira run keeps the ticket's", text)

    def test_sdlc_md_lists_the_jira_form_in_the_argument_hint(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("| resume <slug> | jira <KEY>", text.splitlines()[2])

    def test_hooks_json_runs_jira_seen_after_an_mcp_call(self):
        hooks = json.loads((REPO / "plugins" / "sdlc" / "hooks" / "hooks.json").read_text())["hooks"]["PostToolUse"]
        self.assertEqual((hooks[1]["matcher"], hooks[1]["hooks"][0]["command"]),
                         ("^mcp__", 'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" jira-seen'))

    def test_the_readme_snippet_for_a_manual_install_wires_jira_seen(self):
        self.assertIn("/path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py jira-seen", (REPO / "README.md").read_text())

    def test_the_readme_snippet_for_a_manual_install_wires_the_mcp_mode(self):
        text = (REPO / "README.md").read_text()
        self.assertIn("/path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py mcp", text)


if __name__ == "__main__":
    unittest.main()
