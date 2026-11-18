"""Tests for plugins/sdlc/hooks/snyk_events.py: reading one Snyk MCP event into a scan record, the check on a
scan's arguments and path, and the hash of the code a scan saw.

The events here have the shape the probe recorded from a real Snyk MCP server on 2026-11-18: a PostToolUse
payload whose tool_response is a list of text blocks holding the reply as a JSON string, and a
PostToolUseFailure payload with an `error` and no tool_response. They do not prove other servers or a reply
cut short by the host.

Run: python3 -I -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "plugins" / "sdlc" / "hooks"
SPEC = importlib.util.spec_from_file_location("snyk_events", HOOKS / "snyk_events.py")
events = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(events)

SERVERS = frozenset({"Snyk_Security"})
TREE = "tree-now"


def code_issue(fingerprint="fp-1", severity="Low", file="plugins/a.py", flow=("plugins/a.py",)):
    return {"id": "python/PT", "title": "Path Traversal", "severity": severity, "fingerPrint": fingerprint,
            "filePath": file, "line": 5, "dataflow": [{"position": n, "filePath": step} for n, step in enumerate(flow)]}


def sca_issue(file="video/package.json"):
    return {"id": "SNYK-JS-OPEN-1", "severity": "high", "packageName": "open", "version": "8.4.2", "filePath": file}


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "project"
        self.root.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()

    def absolute(self, relative):
        return str(self.root / relative)


class ArgumentsTest(unittest.TestCase):
    def test_a_code_scan_may_set_the_path_and_the_high_threshold(self):
        self.assertTrue(events.arguments_ok("code", {"path": "/p", "severity_threshold": "high"}))

    def test_a_threshold_that_hides_findings_is_refused(self):
        self.assertFalse(events.arguments_ok("code", {"path": "/p", "severity_threshold": "critical"}))

    def test_an_argument_that_reaches_another_path_or_org_is_refused(self):
        self.assertFalse(events.arguments_ok("code", {"path": "/p", "org": "x"}))

    def test_a_dependency_scan_may_name_python_and_all_projects(self):
        self.assertTrue(events.arguments_ok("sca", {"path": "/p", "all_projects": True, "command": "python3"}))

    def test_a_dependency_scan_may_not_name_another_program(self):
        self.assertFalse(events.arguments_ok("sca", {"path": "/p", "command": "/bin/sh"}))

    def test_all_projects_must_be_a_real_boolean(self):
        self.assertFalse(events.arguments_ok("sca", {"path": "/p", "all_projects": "yes"}))

    def test_an_iac_scan_may_not_report_to_snyk_or_read_a_var_file(self):
        self.assertFalse(events.arguments_ok("iac", {"path": "/p", "report": True}))

    def test_an_input_that_is_not_a_mapping_is_refused(self):
        self.assertFalse(events.arguments_ok("code", ["path"]))

    def test_a_scan_nobody_listed_is_refused(self):
        self.assertFalse(events.arguments_ok("container", {"path": "/p"}))


class PathTest(TempDirTest):
    def inside(self, path, root=None):
        return events.path_inside(path, str(root or self.root), os.path.realpath, str(self.home))

    def test_the_project_root_and_a_folder_in_it_are_inside(self):
        (self.root / "src").mkdir()
        self.assertEqual((self.inside(str(self.root)), self.inside(str(self.root / "src"))), (True, True))

    def test_a_folder_outside_is_not(self):
        self.assertFalse(self.inside(str(self.home)))

    def test_a_sibling_that_shares_the_prefix_is_not(self):
        sibling = self.tmp / "project-evil"
        sibling.mkdir()
        self.assertFalse(self.inside(str(sibling)))

    def test_a_dotdot_that_leaves_the_project_is_not(self):
        self.assertFalse(self.inside(str(self.root / ".." / "home")))

    def test_a_symlink_that_leaves_the_project_is_not(self):
        (self.root / "out").symlink_to(self.home)
        self.assertFalse(self.inside(str(self.root / "out")))

    def test_a_relative_path_is_not(self):
        self.assertFalse(self.inside("src"))

    def test_a_path_with_a_nul_is_not(self):
        self.assertFalse(self.inside(str(self.root) + "\x00"))

    def test_a_value_that_is_not_text_is_not(self):
        self.assertFalse(self.inside(5))

    def test_a_project_root_that_is_the_home_folder_is_not(self):
        self.assertFalse(self.inside(str(self.home), self.home))

    def test_a_project_root_that_is_the_filesystem_root_is_not(self):
        self.assertFalse(self.inside("/", "/"))


class JiraCallTest(TempDirTest):
    def allowed(self, server, name, tool_input):
        return events.jira_call_allowed(server, name, tool_input, str(self.root), os.path.realpath,
                                        str(self.home), SERVERS)

    def test_a_scan_of_the_project_from_a_listed_server_is_allowed(self):
        self.assertTrue(self.allowed("Snyk_Security", "snyk_code_scan", {"path": self.absolute("")}))

    def test_a_scan_from_a_server_not_listed_is_not(self):
        self.assertFalse(self.allowed("other", "snyk_code_scan", {"path": self.absolute("")}))

    def test_another_tool_of_the_same_server_is_not(self):
        self.assertFalse(self.allowed("Snyk_Security", "snyk_auth", {}))

    def test_a_scan_of_a_path_outside_the_project_is_not(self):
        self.assertFalse(self.allowed("Snyk_Security", "snyk_sca_scan", {"path": str(self.home)}))

    def test_a_scan_with_an_input_that_is_not_a_mapping_is_not(self):
        self.assertFalse(self.allowed("Snyk_Security", "snyk_code_scan", [self.absolute("")]))


class RecordTest(TempDirTest):
    def event(self, tool="snyk_code_scan", tool_input=None, reply=None, kind="PostToolUse", server="Snyk_Security",
              response=None, error=None):
        shown = {"name": server.replace("_", " "), "source": "sdk"}  # the shape the host sent, with the display name
        sent = {"hook_event_name": kind, "mcp_server": shown, "tool_name": f"mcp__{server}__{tool}",
                "tool_input": {"path": str(self.root)} if tool_input is None else tool_input}
        sent["tool_response"] = response if response is not None else [{"type": "text", "text": json.dumps(reply)}]
        return sent if error is None else {**{key: sent[key] for key in sent if key != "tool_response"}, "error": error}

    def read(self, sent, tree=TREE):
        return events.record_from_event(sent, str(self.root), tree, SERVERS, os.path.realpath)

    def reply(self, *issues):
        return {"success": True, "issueCount": len(issues), "issues": list(issues)}

    def test_a_completed_code_scan_becomes_a_record_with_relative_findings(self):
        issue = code_issue(file=self.absolute("a.py"), flow=(self.absolute("a.py"), self.absolute("lib/b.py")))
        scanner, record = self.read(self.event(reply=self.reply(issue)))
        self.assertEqual((scanner, record["status"], record["tree"]), ("code", "completed", TREE))
        self.assertEqual(record["findings"], [{"id": "fp-1", "severity": "low", "kind": "code", "file": "a.py",
                                               "flow": ["a.py", "lib/b.py"]}])

    def test_a_dependency_finding_is_named_by_its_package_and_version(self):
        sent = self.event("snyk_sca_scan", reply=self.reply(sca_issue(self.absolute("video/package.json"))))
        scanner, record = self.read(sent)
        self.assertEqual((scanner, record["findings"][0]["id"], record["findings"][0]["file"]),
                         ("sca", "SNYK-JS-OPEN-1@open@8.4.2", "video/package.json"))

    def test_a_reply_that_is_plain_text_is_an_error(self):
        sent = self.event(response=[{"type": "text", "text": "User not authenticated. Please run 'snyk_auth' first"}])
        self.assertEqual(self.read(sent)[1]["status"], "error")

    def test_a_reply_that_says_it_did_not_succeed_is_an_error(self):
        self.assertEqual(self.read(self.event(reply={"success": False, "issues": []}))[1]["status"], "error")

    def test_a_reply_whose_count_differs_from_its_list_is_an_error(self):
        self.assertEqual(self.read(self.event(reply={"success": True, "issueCount": 3, "issues": []}))[1]["status"],
                         "error")

    def test_a_failure_event_is_an_error(self):
        sent = self.event(kind="PostToolUseFailure", error="file does not exist")
        self.assertEqual(self.read(sent)[1]["status"], "error")

    def test_a_reply_that_is_a_plain_string_is_read_too(self):
        sent = self.event(response=json.dumps(self.reply()))
        self.assertEqual(self.read(sent)[1]["status"], "completed")

    def test_a_server_not_listed_is_ignored(self):
        self.assertIsNone(self.read(self.event(server="other", reply=self.reply())))

    def test_a_tool_that_is_not_a_scan_is_ignored(self):
        self.assertIsNone(self.read(self.event("snyk_auth", reply=self.reply())))

    def test_a_server_name_that_differs_from_the_tool_name_is_ignored(self):
        sent = {**self.event(reply=self.reply()), "mcp_server": {"name": "Other Server", "source": "sdk"}}
        self.assertIsNone(self.read(sent))

    def test_a_server_given_as_plain_text_is_read_too(self):
        sent = {**self.event(reply=self.reply()), "mcp_server": "Snyk_Security"}
        self.assertEqual(self.read(sent)[1]["status"], "completed")

    def test_a_server_that_is_neither_text_nor_a_named_object_is_ignored(self):
        sent = {**self.event(reply=self.reply()), "mcp_server": 5}
        self.assertIsNone(self.read(sent))

    def test_an_event_with_no_server_field_is_read_by_the_tool_name(self):
        sent = {key: value for key, value in self.event(reply=self.reply()).items() if key != "mcp_server"}
        self.assertEqual(self.read(sent)[1]["status"], "completed")

    def test_a_scan_of_a_subfolder_is_unusable(self):
        sent = self.event(tool_input={"path": self.absolute("src")}, reply=self.reply())
        self.assertEqual(self.read(sent)[1]["status"], "unusable")

    def test_a_scan_with_a_threshold_that_hides_findings_is_unusable(self):
        sent = self.event(tool_input={"path": str(self.root), "severity_threshold": "critical"}, reply=self.reply())
        self.assertEqual(self.read(sent)[1]["status"], "unusable")

    def test_a_finding_with_no_fingerprint_makes_the_scan_unusable(self):
        broken = code_issue()
        del broken["fingerPrint"]
        self.assertEqual(self.read(self.event(reply=self.reply(broken)))[1]["status"], "unusable")

    def test_a_scan_when_the_code_cannot_be_hashed_is_unusable(self):
        self.assertEqual(self.read(self.event(reply=self.reply()), tree=None)[1]["status"], "unusable")

    def test_a_reply_with_too_many_findings_is_an_error(self):
        issues = [code_issue(f"fp-{n}") for n in range(events.MAX_FINDINGS + 1)]
        self.assertEqual(self.read(self.event(reply=self.reply(*issues)))[1]["status"], "error")


class TreeHashTest(TempDirTest):
    def git(self, *args):
        subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=n", *args], cwd=self.root, check=True,
                       capture_output=True)

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        (self.root / "a.py").write_text("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "first")

    def test_the_same_code_gives_the_same_hash(self):
        self.assertEqual(events.tree_hash(self.root), events.tree_hash(self.root))

    def test_an_edit_to_a_tracked_file_changes_it(self):
        before = events.tree_hash(self.root)
        (self.root / "a.py").write_text("x = 2\n")
        self.assertNotEqual(events.tree_hash(self.root), before)

    def test_a_new_untracked_file_changes_it(self):
        before = events.tree_hash(self.root)
        (self.root / "b.py").write_text("y = 1\n")
        self.assertNotEqual(events.tree_hash(self.root), before)

    def test_an_edit_inside_the_run_folder_does_not(self):
        (self.root / ".sdlc" / "x").mkdir(parents=True)
        before = events.tree_hash(self.root)
        (self.root / ".sdlc" / "x" / "status.md").write_text("run: x\n")
        self.assertEqual(events.tree_hash(self.root), before)

    def test_a_folder_that_is_not_a_git_repo_has_no_hash(self):
        self.assertIsNone(events.tree_hash(self.home))


if __name__ == "__main__":
    unittest.main()
