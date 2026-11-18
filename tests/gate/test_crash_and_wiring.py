"""Tests for what the gate does when it crashes, and for how hooks.json wires it.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.gate_base import GateTest
from support.paths import HOOKS, SCRIPT


class FailureTest(GateTest):
    def test_malformed_input_fails_open(self):
        done = self.run_raw("tool", "not json")
        self.assertNotIn(done.returncode, (0, 2))
        self.assertEqual(done.stdout, "")

    def test_unknown_mode_fails_open(self):
        done = self.run_hook("sideways", {})
        self.assertNotIn(done.returncode, (0, 2))

    def test_trace_records_the_agent_the_host_sent(self):
        self.run_hook("tool", {"tool_name": "Bash", "tool_input": {"command": "ls"},
                               "agent_type": "qa-engineer"}, env={"SDLC_GATE_TRACE": "1"})
        line = json.loads((self.home / "sdlc-gate" / "trace.log").read_text())
        self.assertEqual(line["agent_type"], "qa-engineer")

    def test_hooks_json_points_at_this_script(self):
        hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]
        commands = [hooks["UserPromptSubmit"][0]["hooks"][0]["command"],
                    hooks["PreToolUse"][0]["hooks"][0]["command"]]
        self.assertEqual(commands, ['python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" prompt',
                                    'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" tool'])
        self.assertTrue(SCRIPT.is_file())


class FailClosedTest(GateTest):
    """A crash of the tool hook denies while the session is gated and lets the action through otherwise."""

    def crash(self):
        return self.run_hook("tool", {"tool_name": "Bash", "tool_input": "not a mapping"})

    def test_a_crash_while_locked_denies(self):
        self.prompt("/sdlc add a slug helper")
        done = self.crash()
        self.assertEqual(done.returncode, 0)
        self.assertIn("the gate failed", self.reason(done))

    def test_a_crash_while_approved_denies(self):
        self.locked_and_approved()
        self.assertIn("the gate failed", self.reason(self.crash()))

    def test_the_denial_names_the_way_out(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("sdlc off", self.reason(self.crash()))

    def test_a_crash_in_a_session_that_never_ran_sdlc_fails_open(self):
        done = self.crash()
        self.assertNotIn(done.returncode, (0, 2))
        self.assertEqual(done.stdout, "")

    def test_a_crash_in_another_session_does_not_deny(self):
        self.prompt("/sdlc add a slug helper")
        done = self.run_hook("tool", {"session_id": "other", "tool_name": "Bash", "tool_input": "x"})
        self.assertEqual(done.stdout, "")

    def test_the_prompt_hook_never_denies_when_it_crashes(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("a file where the state folder should be")
        done = self.run_hook("prompt", {"prompt": "/sdlc add a slug helper"}, env={"SDLC_GATE_HOME": str(blocker)})
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("deny", done.stdout)


if __name__ == "__main__":
    unittest.main()
