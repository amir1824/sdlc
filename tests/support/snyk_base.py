"""The base classes and the data of the tests of the Snyk parts of the sdlc gate.
"""
import json
import subprocess

from support.mcp_base import McpGateTest


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


GATE_TAG = "Snyk gate"
OPEN_RUN = "run: feature\n6 Verify: done\nwaiting: owner\n"
CLOSED_RUN = "run: feature\nclosed\n"
HIGH = {**ISSUE, "severity": "High", "filePath": "app.py", "fingerPrint": "fp-high",
        "dataflow": [{"position": 0, "filePath": "app.py"}]}


class SnykCloseTest(SnykGateTest):
    def setUp(self):
        super().setUp()
        self.status = self.project / ".sdlc" / "feature" / "status.md"
        self.status.write_text(OPEN_RUN)

    def close_with(self, text=CLOSED_RUN, path=None):
        return self.run_hook("tool", {"tool_name": "Write",
                                      "tool_input": {"file_path": str(path or self.status), "content": text}})

    def closing_denied(self, text=CLOSED_RUN, path=None):
        return GATE_TAG in self.close_with(text, path).stdout

    def edit_status(self, tool, tool_input):
        done = self.run_hook("tool", {"tool_name": tool, "tool_input": {"file_path": str(self.status), **tool_input}})
        return GATE_TAG in done.stdout

    def edit_code(self, text="x = 2\n"):
        (self.project / "app.py").write_text(text)

    def snyk_on_and_approved(self):
        self.prompt("sdlc snyk on")
        self.locked_and_approved()

    def head(self):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project, capture_output=True, text=True,
                              check=True).stdout.strip()

    def denial(self, text=CLOSED_RUN):
        return self.reason(self.close_with(text))
