"""Tests for how the entry loads the sdlc_hooks package: a module that cannot be imported, and code in the
project's own folder that must never be loaded in its place.

A broken module is made in a copy of the hooks folder, so the real one stays whole.

Run: python3 -I -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys

from support.gate_base import GateTest
from support.paths import HOOKS, SCRIPT

JIRA_WRITE = {"tool_name": "mcp__atlassian__createJiraIssue", "tool_input": {}}
BAD_SOURCE = "\n)))\n"


class BrokenModuleTest(GateTest):
    def setUp(self):
        super().setUp()
        self.copy = self.tmp / "hooks"
        shutil.copytree(HOOKS, self.copy, ignore=shutil.ignore_patterns("__pycache__"))
        self.state = self.home / "sdlc-gate"
        self.state.mkdir(parents=True, exist_ok=True)

    def break_module(self, relative):
        with (self.copy / "sdlc_hooks" / relative).open("a") as module:
            module.write(BAD_SOURCE)

    def run_copy(self, mode, payload):
        data = json.dumps({"session_id": "s1", "cwd": str(self.project), **payload})
        env = {**os.environ, "SDLC_GATE": "", "SDLC_GATE_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.project)}
        return subprocess.run([sys.executable, "-I", str(self.copy / "sdlc_gate.py"), mode], input=data,
                              capture_output=True, text=True, env=env, timeout=5)

    def edit_payload(self):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(self.project / "app.py")}}

    def test_a_broken_tool_module_denies_in_a_session_with_a_lock(self):
        self.locked_and_approved()
        self.break_module("tool.py")
        done = self.run_copy("tool", self.edit_payload())
        self.assertIn("the gate failed (SyntaxError) while this session is locked or has an approved plan",
                      self.reason(done))

    def test_a_broken_tool_module_lets_a_session_with_no_lock_through(self):
        self.break_module("tool.py")
        done = self.run_copy("tool", self.edit_payload())
        self.assertEqual((done.returncode, done.stdout), (1, ""))

    def test_a_broken_mcp_module_denies_in_a_jira_run(self):
        (self.state / "s1.jira").write_text("")
        self.break_module("jira/mcp.py")
        done = self.run_copy("mcp", JIRA_WRITE)
        self.assertIn("the gate failed (SyntaxError) while this session has a Jira run", self.reason(done))

    def test_a_broken_snyk_seen_module_is_logged_and_does_not_fail_the_host(self):
        self.break_module("snyk_gate.py")
        done = self.run_copy("snyk-seen", {"tool_name": "mcp__Snyk__snyk_code_scan"})
        self.assertEqual(done.returncode, 0)
        self.assertIn("snyk-seen-error", (self.state / "approvals.log").read_text())

    def test_a_broken_module_that_decides_the_limit_lets_a_jira_run_through(self):
        """The known limit written in sdlc_gate.handle: the predicate's own module is the one that is broken."""
        (self.state / "s1.jira").write_text("")
        self.break_module("jira/markers.py")
        done = self.run_copy("mcp", JIRA_WRITE)
        self.assertEqual((done.returncode, done.stdout), (1, ""))


    def test_a_broken_denial_module_lets_a_locked_session_through(self):
        """The same known limit: the module that prints the denial is the one that is broken."""
        self.locked_and_approved()
        self.break_module("core/output.py")
        done = self.run_copy("tool", self.edit_payload())
        self.assertEqual((done.returncode, done.stdout), (1, ""))


class ProjectFolderTest(GateTest):
    def plant(self, relative):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"import pathlib\npathlib.Path({str(self.tmp / 'planted')!r}).write_text('loaded')\n")

    def test_code_in_the_project_folder_is_never_loaded_in_place_of_the_package(self):
        self.plant("sdlc_hooks/__init__.py")
        self.plant("sdlc_hooks/core/__init__.py")
        self.plant("json.py")
        self.plant("re.py")
        self.plant("pathlib.py")
        self.plant("importlib.py")
        env = {**os.environ, "SDLC_GATE": "", "SDLC_GATE_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.project),
               "PYTHONPATH": str(self.project)}
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "prompt"], input=json.dumps({"session_id": "s1", "prompt": "hello"}),
                              capture_output=True, text=True, env=env, cwd=self.project, timeout=5)
        self.assertEqual((done.returncode, (self.tmp / "planted").exists()), (0, False))
