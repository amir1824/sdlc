"""Tests for the `snyk-seen` mode and for the Snyk scans a Jira run may start.

Run: python3 -I -m unittest discover -s tests
"""
import stat
import subprocess
import unittest

from support.snyk_base import OTHER_SNYK_TOOLS, SCANS, SNYK, SnykGateTest


class SnykSeenTest(SnykGateTest):
    def test_a_scan_of_the_project_is_recorded(self):
        self.seen()
        record = self.state()["scans"]["code"]
        self.assertEqual((record["status"], len(record["findings"]), len(record["tree"])), ("completed", 1, 64))

    def test_the_finding_is_recorded_by_its_fingerprint_and_a_relative_file(self):
        self.seen()
        self.assertEqual(self.state()["scans"]["code"]["findings"][0]["id"], "fp-1")

    def test_a_scan_from_a_server_that_is_not_listed_records_nothing(self):
        self.seen(server="other")
        self.assertFalse(self.snyk_state.exists())

    def test_a_server_named_in_the_environment_is_recorded(self):
        self.seen(server="Other", env={"SDLC_SNYK_SERVERS": "Other"})
        self.assertEqual(self.state()["scans"]["code"]["status"], "completed")

    def test_a_failed_scan_is_recorded_as_an_error(self):
        self.seen(kind="PostToolUseFailure")
        self.assertEqual(self.state()["scans"]["code"]["status"], "error")

    def test_a_scan_of_a_subfolder_is_recorded_as_unusable(self):
        self.seen(tool_input={"path": str(self.project / "src")})
        self.assertEqual(self.state()["scans"]["code"]["status"], "unusable")

    def test_a_project_that_is_not_a_git_repo_records_an_unusable_scan(self):
        subprocess.run(["rm", "-rf", str(self.project / ".git")], check=True)
        self.seen()
        self.assertEqual(self.state()["scans"]["code"]["status"], "unusable")

    def test_the_unusable_scan_keeps_the_reason_the_code_could_not_be_hashed(self):
        subprocess.run(["rm", "-rf", str(self.project / ".git")], check=True)
        self.seen()
        self.assertIn("git rev-parse failed", self.state()["scans"]["code"]["note"])

    def test_a_later_scan_replaces_the_earlier_one_of_its_kind(self):
        self.seen()
        self.seen(kind="PostToolUseFailure")
        self.assertEqual(self.state()["scans"]["code"]["status"], "error")

    def test_a_dependency_scan_keeps_the_code_scan(self):
        self.seen()
        self.seen("snyk_sca_scan", issues=())
        self.assertEqual(sorted(self.state()["scans"]), ["code", "sca"])

    def test_the_record_is_readable_by_the_owner_only(self):
        self.seen()
        mode = stat.S_IMODE(next(iter(self.snyk_state.glob("*.json"))).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_an_event_with_nothing_in_it_changes_nothing_and_prints_nothing(self):
        done = self.run_raw("snyk-seen", "{}")
        self.assertEqual((done.returncode, done.stdout, self.snyk_state.exists()), (0, "", False))


class SnykInJiraRunTest(SnykGateTest):
    def setUp(self):
        super().setUp()
        self.prompt("sdlc snyk on")
        self.jira_run_approved()

    def test_a_scan_of_the_project_runs(self):
        self.assertFalse(self.scan_denied({"path": str(self.project)}))

    def test_a_scan_of_a_folder_in_the_project_runs(self):
        self.assertFalse(self.scan_denied({"path": str(self.project / "src")}))

    def test_all_three_scans_run(self):
        denied = [tool for tool in SCANS if self.scan_denied({"path": str(self.project)}, tool)]
        self.assertEqual(denied, [])

    def test_a_dependency_scan_may_name_python(self):
        self.assertFalse(self.scan_denied({"path": str(self.project), "all_projects": True, "command": "python3"},
                                          "snyk_sca_scan"))

    def test_a_scan_of_a_path_outside_the_project_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.home)}))

    def test_a_symlink_out_of_the_project_is_denied(self):
        (self.project / "out").symlink_to(self.home)
        self.assertTrue(self.scan_denied({"path": str(self.project / "out")}))

    def test_an_argument_outside_the_list_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.project), "org": "x"}))

    def test_a_dependency_scan_naming_a_shell_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.project), "command": "/bin/sh"}, "snyk_sca_scan"))

    def test_an_iac_scan_that_reports_to_snyk_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.project), "report": True}, "snyk_iac_scan"))

    def test_a_scan_from_a_server_that_is_not_listed_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.project)}, server="mcp__other__"))

    def test_a_server_named_in_the_environment_runs(self):
        self.assertFalse(self.scan_denied({"path": str(self.project)}, server="mcp__Other__",
                                          env={"SDLC_SNYK_SERVERS": "Other"}))

    def test_every_other_snyk_tool_is_still_denied(self):
        denied = [tool for tool in OTHER_SNYK_TOOLS if self.scan_denied({}, tool)]
        self.assertEqual(denied, list(OTHER_SNYK_TOOLS))

    def test_a_project_that_is_the_home_folder_is_denied(self):
        self.assertTrue(self.scan_denied({"path": str(self.project)}, env={"HOME": str(self.project)}))

    def test_the_reason_names_the_tool_and_what_is_allowed(self):
        done = self.run_hook("mcp", {"tool_name": SNYK + "snyk_auth", "tool_input": {}})
        self.assertIn("snyk_auth", self.reason(done))


class SnykConsentInJiraRunTest(SnykGateTest):
    def test_a_scan_is_denied_in_a_project_that_has_not_decided(self):
        self.jira_run_approved()
        self.assertTrue(self.scan_denied({"path": str(self.project)}))

    def test_a_scan_is_denied_in_a_project_that_turned_snyk_off(self):
        self.prompt("sdlc snyk off")
        self.jira_run_approved()
        self.assertTrue(self.scan_denied({"path": str(self.project)}))


class SnykOutsideJiraRunTest(SnykGateTest):
    def test_a_session_with_no_jira_run_is_not_limited(self):
        self.assertFalse(self.scan_denied({"path": str(self.home), "org": "x"}))

    def test_a_session_gated_only_by_a_jira_folder_denies_input_it_cannot_read(self):
        self.jira_folder()
        self.locked_and_approved()
        self.assertTrue(self.scan_denied(["not", "a", "mapping"]))


if __name__ == "__main__":
    unittest.main()
