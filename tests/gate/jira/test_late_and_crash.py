"""Tests for a Jira run found late and for a crash of the `mcp` hook.

Run: python3 -I -m unittest discover -s tests
"""
import unittest

from support.mcp_base import McpGateTest, UUID_SERVER


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


if __name__ == "__main__":
    unittest.main()
