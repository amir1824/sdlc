"""Tests for the Snyk parts of plugins/sdlc/hooks/sdlc_gate.py, run as Claude Code runs it (JSON on stdin):
the `snyk-seen` mode that records a scan, and the exception that lets a scan of the project run in a Jira run.

Run: python3 -I -m unittest discover -s tests
These feed the hook the shape a probe recorded from a real Snyk MCP server on 2026-11-18. They prove the gate's
logic, not that the host runs the hook for every Snyk tool name, and not what a very large reply looks like.
"""
import json
import re
import stat
import subprocess
import unittest
from pathlib import Path

from test_sdlc_gate_mcp import McpGateTest

REPO = Path(__file__).resolve().parent.parent

SNYK = "mcp__Snyk_Security__"
SCANS = ("snyk_code_scan", "snyk_sca_scan", "snyk_iac_scan")
OTHER_SNYK_TOOLS = ("snyk_auth", "snyk_trust", "snyk_logout", "snyk_send_feedback", "snyk_sbom_scan", "snyk_aibom",
                    "snyk_container_scan", "snyk_package_health_check", "snyk_breakability_check", "snyk_version")
ISSUE = {"id": "python/PT", "title": "Path Traversal", "severity": "Low", "fingerPrint": "fp-1",
         "filePath": "src/app.py", "line": 5, "dataflow": [{"position": 0, "filePath": "src/app.py"}]}


class SnykGateTest(McpGateTest):
    def setUp(self):
        super().setUp()
        self.snyk_state = self.home / "sdlc-gate" / "snyk"
        self.git("init", "-q")
        (self.project / "app.py").write_text("x = 1\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "first")

    def git(self, *args):
        subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=n", *args], cwd=self.project, check=True,
                       capture_output=True)

    def seen(self, tool="snyk_code_scan", tool_input=None, issues=(ISSUE,), server="Snyk_Security", env=None,
             kind="PostToolUse"):
        reply = {"success": True, "issueCount": len(issues), "issues": list(issues)}
        payload = {"hook_event_name": kind, "mcp_server": {"name": server.replace("_", " "), "source": "sdk"},
                   "tool_name": f"mcp__{server}__{tool}",
                   "tool_input": {"path": str(self.project)} if tool_input is None else tool_input,
                   "tool_response": [{"type": "text", "text": json.dumps(reply)}]}
        return self.run_hook("snyk-seen", payload, env)

    def state(self):
        return json.loads(next(iter(self.snyk_state.glob("*.json"))).read_text())

    def scan_denied(self, tool_input, tool="snyk_code_scan", server=SNYK, env=None):
        done = self.run_hook("mcp", {"tool_name": server + tool, "tool_input": tool_input}, env)
        return bool(done.stdout)


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


class SnykOutsideJiraRunTest(SnykGateTest):
    def test_a_session_with_no_jira_run_is_not_limited(self):
        self.assertFalse(self.scan_denied({"path": str(self.home), "org": "x"}))

    def test_a_session_gated_only_by_a_jira_folder_denies_input_it_cannot_read(self):
        self.jira_folder()
        self.locked_and_approved()
        self.assertTrue(self.scan_denied(["not", "a", "mapping"]))


class WiringTest(unittest.TestCase):
    MATCHER = "^mcp__.*__snyk_(code|sca|iac)_scan$"
    COMMAND = 'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" snyk-seen'

    def hooks(self):
        return json.loads((REPO / "plugins" / "sdlc" / "hooks" / "hooks.json").read_text())["hooks"]

    def test_a_scan_is_recorded_after_it_succeeds(self):
        entry = self.hooks()["PostToolUse"][2]
        self.assertEqual((entry["matcher"], entry["hooks"][0]["command"]), (self.MATCHER, self.COMMAND))

    def test_a_scan_is_recorded_after_it_fails(self):
        entry = self.hooks()["PostToolUseFailure"][0]
        self.assertEqual((entry["matcher"], entry["hooks"][0]["command"]), (self.MATCHER, self.COMMAND))

    def test_the_matcher_covers_each_scan_of_a_named_or_a_uuid_server(self):
        names = [f"{server}{tool}" for server in (SNYK, "mcp__0dcd0205-81c2-491f-b8e9-2617c355f029__") for tool in SCANS]
        self.assertEqual([name for name in names if re.search(self.MATCHER, name)], names)

    def test_the_matcher_skips_every_other_snyk_tool(self):
        self.assertEqual([tool for tool in OTHER_SNYK_TOOLS if re.search(self.MATCHER, SNYK + tool)], [])


if __name__ == "__main__":
    unittest.main()
