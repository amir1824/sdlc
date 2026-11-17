"""Tests for the hook-wiring line of scripts/check.sh, run against a synthetic ~/.claude.

Run: python3 -I -m unittest discover -s tests
The synthetic home has no rules installed, so check.sh exits non-zero for that reason; these
tests read only its settings.json line.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check.sh"
GATE = REPO / "plugins" / "sdlc" / "hooks" / "sdlc_gate.py"


class HookWiringTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)

    def settings_line(self, settings, label):
        (self.home / "settings.json").write_text(settings)
        out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=30,
                             env={**os.environ, "CLAUDE_HOME": str(self.home)})
        return next(line for line in out.stdout.splitlines() if label in line)

    def hooks_line(self, settings):
        return self.settings_line(settings, "settings.json hooks")

    def mcp_line(self, settings):
        return self.settings_line(settings, "settings.json mcp gate")

    def seen_line(self, settings):
        return self.settings_line(settings, "settings.json jira-seen")

    def test_both_events_are_linked(self):
        line = self.hooks_line(f'{{"a": "python3 -I {GATE} prompt", "b": "python3 -I {GATE} tool"}}')
        self.assertTrue(line.startswith("linked"), line)

    def test_both_events_with_a_quoted_path_are_linked(self):
        line = self.hooks_line(f'{{"a": "python3 -I \\"{GATE}\\" prompt", "b": "python3 -I \\"{GATE}\\" tool"}}')
        self.assertTrue(line.startswith("linked"), line)

    def test_one_event_alone_is_partial(self):
        line = self.hooks_line(f'{{"a": "python3 -I {GATE} prompt"}}')
        self.assertTrue(line.startswith("PARTIAL"), line)

    def test_no_events_is_missing(self):
        line = self.hooks_line("{}")
        self.assertTrue(line.startswith("missing"), line)

    def test_the_mcp_mode_is_linked_when_wired(self):
        line = self.mcp_line(f'{{"a": "python3 -I {GATE} mcp"}}')
        self.assertTrue(line.startswith("linked"), line)

    def test_the_mcp_mode_with_a_quoted_path_is_linked(self):
        line = self.mcp_line(f'{{"a": "python3 -I \\"{GATE}\\" mcp"}}')
        self.assertTrue(line.startswith("linked"), line)

    def test_the_mcp_mode_is_missing_when_only_prompt_and_tool_are_wired(self):
        line = self.mcp_line(f'{{"a": "python3 -I {GATE} prompt", "b": "python3 -I {GATE} tool"}}')
        self.assertTrue(line.startswith("missing"), line)

    def test_jira_seen_is_linked_when_wired(self):
        line = self.seen_line(f'{{"a": "python3 -I {GATE} jira-seen"}}')
        self.assertTrue(line.startswith("linked"), line)

    def test_jira_seen_is_missing_when_only_the_mcp_mode_is_wired(self):
        line = self.seen_line(f'{{"a": "python3 -I {GATE} mcp"}}')
        self.assertTrue(line.startswith("missing"), line)

    def test_a_missing_mcp_mode_does_not_turn_linked_prompt_and_tool_into_partial(self):
        line = self.hooks_line(f'{{"a": "python3 -I {GATE} prompt", "b": "python3 -I {GATE} tool"}}')
        self.assertTrue(line.startswith("linked"), line)


if __name__ == "__main__":
    unittest.main()
