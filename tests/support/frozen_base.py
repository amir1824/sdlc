"""The base class of the tests of an approved plan that freezes its reproduction tests.
"""
import json

from support.gate_base import GateTest


BUILDER = "sdlc:backend-developer"
QA = "sdlc:qa-engineer"


class FrozenGateTest(GateTest):
    def setUp(self):
        super().setUp()
        self.approved = self.home / "sdlc-gate" / "s1.approved"
        self.log = self.home / "sdlc-gate" / "approvals.log"
        self.frozen = self.project / "tests" / "test_bug.py"

    def frozen_block(self, *paths):
        return "## Reproduction\n```sdlc-tests\n" + "\n".join(paths) + "\n```\n"

    def scope_block(self, *globs):
        return "## Scope\n```sdlc-scope\n" + "\n".join(globs) + "\n```\n"

    def approve_plan(self, text):
        self.plan.write_text(text)
        self.prompt("/sdlc fix the rounding bug")
        return self.prompt("approve plan")

    def approve_frozen(self, *paths):
        return self.approve_plan("# Plan\n" + self.frozen_block(*(paths or ("tests/test_bug.py",))))

    def edit_as(self, path, agent=None, tool="Edit", key="file_path", env=None, **payload):
        who = {"agent_type": agent} if agent else {}
        return self.run_hook("tool", {"tool_name": tool, "tool_input": {key: str(path)}, **who, **payload}, env)

    def frozen_denial(self, done):
        self.assertIn("sdlc-gate: [tests]", self.reason(done))

    def refused(self, done, why):
        self.assertIn(why, self.context(done))
        self.assertFalse(self.approved.exists())
        self.assertTrue(self.lock.is_file())

    def tamper(self, tests):
        record = json.loads(self.approved.read_text())
        record["tests"] = tests
        self.approved.write_text(json.dumps(record))
