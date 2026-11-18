"""The base class of every test that runs the sdlc gate hook as Claude Code runs it: JSON on stdin.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path
from support.paths import SCRIPT


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        self.plan = self.project / ".sdlc" / "feature" / "plan.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text("# Plan v1\n")
        (self.home / "rules").mkdir(parents=True)
        (self.home / "rules" / "sdlc.md").write_text("rules\n")
        self.lock = self.home / "sdlc-gate" / "s1.locked"

    def run_raw(self, mode, stdin, env=None):
        full_env = {**os.environ, "SDLC_GATE": "", "SDLC_GATE_HOME": str(self.home),
                    "CLAUDE_PROJECT_DIR": str(self.project), **(env or {})}
        return subprocess.run([sys.executable, "-I", str(SCRIPT), mode], input=stdin,
                              capture_output=True, text=True, env=full_env, timeout=5)

    def run_hook(self, mode, payload, env=None):
        data = {"session_id": "s1", "cwd": str(self.project), **payload}
        return self.run_raw(mode, json.dumps(data), env)

    def prompt(self, text, **payload):
        return self.run_hook("prompt", {"prompt": text, **payload})

    def edit(self, path, env=None, tool="Edit", key="file_path"):
        return self.run_hook("tool", {"tool_name": tool, "tool_input": {key: str(path)}}, env)

    def bash(self, command, **payload):
        return self.run_hook("tool", {"tool_name": "Bash", "tool_input": {"command": command}, **payload})

    def locked_and_approved(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan")

    def reason(self, done):
        return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

    def context(self, done):
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
