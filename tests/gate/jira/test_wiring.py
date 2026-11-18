"""Tests for how hooks.json and the README wire the `mcp` and `jira-seen` modes.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.mcp_base import JIRA_SEEN_MATCHER, NAMED_SERVER, UUID_SERVER
from support.paths import REPO


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

    def test_sdlc_md_lists_tickets_for_a_jira_request_with_no_key_and_starts_no_run(self):
        text = (REPO / "plugins" / "sdlc" / "commands" / "sdlc.md").read_text()
        self.assertIn("## Jira picker", text)
        self.assertIn("`searchJiraIssuesUsingJql`", text)
        self.assertIn("Write no `.sdlc/` file and start no stage", text)

    def test_hooks_json_runs_jira_seen_after_an_mcp_call(self):
        hooks = json.loads((REPO / "plugins" / "sdlc" / "hooks" / "hooks.json").read_text())["hooks"]["PostToolUse"]
        self.assertEqual((hooks[1]["matcher"], hooks[1]["hooks"][0]["command"]),
                         (JIRA_SEEN_MATCHER, 'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" jira-seen'))

    def test_the_jira_seen_matcher_covers_a_uuid_server_and_a_named_one(self):
        self.assertRegex(UUID_SERVER + "getJiraIssue", JIRA_SEEN_MATCHER)
        self.assertRegex(NAMED_SERVER + "jira_get_issue", JIRA_SEEN_MATCHER)

    def test_the_jira_seen_matcher_covers_the_execute_read_wrapper(self):
        self.assertRegex(UUID_SERVER + "executeRead", JIRA_SEEN_MATCHER)

    def test_the_jira_seen_matcher_skips_other_servers_tools(self):
        self.assertNotRegex("mcp__figma__get_design_context", JIRA_SEEN_MATCHER)

    def test_the_readme_snippet_uses_the_same_jira_seen_matcher(self):
        self.assertIn('"matcher": "%s"' % JIRA_SEEN_MATCHER, (REPO / "README.md").read_text())

    def test_the_readme_snippet_for_a_manual_install_wires_jira_seen(self):
        self.assertIn("/path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py jira-seen", (REPO / "README.md").read_text())

    def test_the_readme_snippet_for_a_manual_install_wires_the_mcp_mode(self):
        text = (REPO / "README.md").read_text()
        self.assertIn("/path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py mcp", text)


if __name__ == "__main__":
    unittest.main()
