"""Tests for how hooks.json wires the `snyk-seen` mode.

Run: python3 -I -m unittest discover -s tests
"""
import json
import re
import unittest

from support.paths import REPO
from support.snyk_base import OTHER_SNYK_TOOLS, SCANS, SNYK


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
