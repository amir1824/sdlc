"""Tests for plugins/sdlc/hooks/security_gate.py: the pure verdict (PASS, BLOCK or INCOMPLETE) computed from
the recorded Snyk scans, the changed files and the owner's decisions, and the CLI that prints it.

These tests feed the function synthetic scan records. They do not prove that the host records a real Snyk
reply in this shape; that is the probe in the plan.

Run: python3 -I -m unittest discover -s tests
"""
import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "plugins" / "sdlc" / "hooks" / "security_gate.py"
SPEC = importlib.util.spec_from_file_location("security_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

TREE = "tree-now"
OLD_TREE = "tree-before"


def finding(ident="F-a", severity="high", file="src/app.py", kind="code", flow=()):
    return {"id": ident, "severity": severity, "kind": kind, "file": file, "flow": list(flow)}


def scan(findings=(), status="completed", tree=TREE):
    return {"status": status, "tree": tree, "findings": list(findings)}


def state(scans=None, policy="on", accepted=(), waived=()):
    return {"policy": policy, "scans": scans or {}, "accepted": list(accepted), "waived": list(waived)}


def verdict(st, changed=("src/app.py",), tree=TREE):
    return gate.evaluate(st, list(changed), tree)


class RequiredScannersTest(unittest.TestCase):
    def required(self, *changed):
        return gate.required_scanners(list(changed))

    def test_a_source_file_needs_a_code_scan(self):
        self.assertEqual(self.required("src/app.py", "web/a.tsx"), {"code"})

    def test_a_manifest_or_lockfile_needs_a_dependency_scan(self):
        self.assertEqual(self.required("package.json", "video/package-lock.json", "requirements-dev.txt"), {"sca"})

    def test_a_terraform_file_needs_an_iac_scan(self):
        self.assertEqual(self.required("infra/main.tf"), {"iac"})

    def test_docs_alone_need_no_scan(self):
        self.assertEqual(self.required("README.md", "docs/a.txt"), set())

    def test_the_run_folder_is_not_part_of_the_change(self):
        self.assertEqual(self.required(".sdlc/x/status.md", ".sdlc/x/runs/snyk-code.json"), set())

    def test_a_mixed_change_needs_every_matching_scan(self):
        self.assertEqual(self.required("src/app.py", "go.mod", "main.tf", "README.md"), {"code", "sca", "iac"})


class PolicyTest(unittest.TestCase):
    def test_a_project_that_has_not_decided_is_not_enforced(self):
        result = verdict(state(policy=None))
        self.assertEqual((result["enforced"], result["closable"]), (False, True))
        self.assertIn("not decided", result["reasons"][0])

    def test_a_project_that_turned_snyk_off_is_not_enforced(self):
        result = verdict(state(policy="off"))
        self.assertEqual((result["enforced"], result["closable"]), (False, True))
        self.assertIn("off", result["reasons"][0])

    def test_a_policy_the_gate_does_not_know_is_enforced_and_incomplete(self):
        result = verdict(state(policy="maybe"))
        self.assertEqual((result["status"], result["enforced"], result["closable"]), ("INCOMPLETE", True, False))

    def test_a_docs_only_change_passes_with_the_reason_said(self):
        result = verdict(state(), changed=("README.md",))
        self.assertEqual((result["status"], result["enforced"]), ("PASS", True))
        self.assertIn("no scan required", result["reasons"][0])


class IncompleteTest(unittest.TestCase):
    def test_a_required_scan_that_never_ran_is_incomplete(self):
        result = verdict(state())
        self.assertEqual((result["status"], result["closable"]), ("INCOMPLETE", False))
        self.assertIn("code: not run", result["reasons"])

    def test_a_scan_that_ended_in_an_error_is_incomplete(self):
        self.assertIn("code: error", verdict(state({"code": scan(status="error")}))["reasons"])

    def test_a_scan_of_a_narrowed_path_is_incomplete(self):
        self.assertIn("code: unusable", verdict(state({"code": scan(status="unusable")}))["reasons"])

    def test_a_scan_of_older_code_is_incomplete(self):
        self.assertIn("code: stale", verdict(state({"code": scan(tree=OLD_TREE)}))["reasons"])

    def test_a_record_that_is_not_a_scan_is_incomplete(self):
        self.assertIn("code: unusable", verdict(state({"code": "completed"}))["reasons"])

    def test_a_record_whose_findings_are_not_a_list_is_incomplete(self):
        record = {"status": "completed", "tree": TREE, "findings": "none"}
        self.assertIn("code: unusable", verdict(state({"code": record}))["reasons"])

    def test_a_clean_fresh_scan_passes_and_can_close(self):
        result = verdict(state({"code": scan()}))
        self.assertEqual((result["status"], result["closable"]), ("PASS", True))


class BlockTest(unittest.TestCase):
    def test_a_high_in_a_changed_file_blocks(self):
        result = verdict(state({"code": scan([finding()])}))
        self.assertEqual((result["status"], result["closable"]), ("BLOCK", False))

    def test_a_high_whose_flow_passes_through_a_changed_file_blocks(self):
        flowing = finding(file="src/old.py", flow=["src/old.py", "src/app.py"])
        self.assertEqual(verdict(state({"code": scan([flowing])}))["status"], "BLOCK")

    def test_a_high_in_an_untouched_file_is_pre_existing_and_does_not_block(self):
        old = finding(file="src/old.py", flow=["src/old.py"])
        result = verdict(state({"code": scan([old])}))
        self.assertEqual((result["status"], result["findings"][0]["class"]), ("PASS", "pre-existing"))

    def test_a_critical_in_a_changed_file_blocks(self):
        self.assertEqual(verdict(state({"code": scan([finding(severity="critical")])}))["status"], "BLOCK")

    def test_a_medium_in_a_changed_file_does_not_block(self):
        self.assertEqual(verdict(state({"code": scan([finding(severity="medium")])}))["status"], "PASS")

    def test_a_severity_the_gate_does_not_know_blocks(self):
        self.assertEqual(verdict(state({"code": scan([finding(severity="weird")])}))["status"], "BLOCK")

    def test_a_dependency_finding_blocks_when_its_manifest_changed(self):
        dependency = finding("S-1", "critical", "video/package.json", "sca")
        changed = ("video/package-lock.json",)
        self.assertEqual(verdict(state({"sca": scan([dependency])}), changed)["status"], "BLOCK")

    def test_a_dependency_finding_in_an_untouched_manifest_is_pre_existing(self):
        dependency = finding("S-1", "high", "video/package.json", "sca")
        changed = ("src/other/package.json",)
        self.assertEqual(verdict(state({"sca": scan([dependency])}), changed)["status"], "PASS")

    def test_a_scan_that_was_not_required_still_counts_its_findings(self):
        iac = finding("I-1", "high", "src/app.py", "iac")
        self.assertEqual(verdict(state({"code": scan(), "iac": scan([iac])}))["status"], "BLOCK")

    def test_a_block_and_an_incomplete_scan_report_both_and_block(self):
        result = verdict(state({"code": scan([finding()])}), ("src/app.py", "go.mod"))
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("sca: not run", result["reasons"])


class OwnerDecisionTest(unittest.TestCase):
    def test_an_accepted_finding_no_longer_blocks(self):
        result = verdict(state({"code": scan([finding("F-a")])}, accepted=["F-a"]))
        self.assertEqual(result["status"], "PASS")

    def test_accepting_one_finding_leaves_the_other_blocking(self):
        scans = {"code": scan([finding("F-a"), finding("F-b")])}
        result = verdict(state(scans, accepted=["F-a"]))
        self.assertEqual((result["status"], result["findings"][1]["accepted"]), ("BLOCK", False))

    def test_a_waiver_for_this_code_lets_an_incomplete_gate_close(self):
        result = verdict(state(waived=[TREE]))
        self.assertEqual((result["status"], result["closable"]), ("INCOMPLETE", True))
        self.assertIn("waived by owner", result["reasons"][-1])

    def test_a_waiver_for_older_code_does_not_apply(self):
        self.assertEqual(verdict(state(waived=[OLD_TREE]))["closable"], False)

    def test_a_waiver_never_covers_a_blocking_finding(self):
        result = verdict(state({"code": scan([finding()])}, waived=[TREE]))
        self.assertEqual((result["status"], result["closable"]), ("BLOCK", False))


class FindingListTest(unittest.TestCase):
    def test_findings_get_short_ids_in_a_stable_order(self):
        scans = {"code": scan([finding("F-z", file="src/b.py"), finding("F-a", file="src/a.py")])}
        result = verdict(state(scans), ("src/a.py", "src/b.py"))
        self.assertEqual([(f["short"], f["id"]) for f in result["findings"]], [("F1", "F-a"), ("F2", "F-z")])

    def test_evaluating_does_not_change_the_state(self):
        record = state({"code": scan([finding()])}, accepted=["x"])
        before = copy.deepcopy(record)
        verdict(record)
        self.assertEqual(record, before)

    def test_a_malformed_finding_is_unusable_and_not_skipped(self):
        broken = {"code": scan([{"severity": "high"}])}
        self.assertIn("code: unusable", verdict(state(broken))["reasons"])


class CommandLineTest(unittest.TestCase):
    def run_cli(self, payload):
        return subprocess.run([sys.executable, "-I", str(SCRIPT)], input=payload, capture_output=True,
                              text=True, timeout=10)

    def test_the_command_prints_the_gate_line_and_the_findings(self):
        payload = json.dumps({"state": state({"code": scan([finding()])}), "changed": ["src/app.py"], "tree": TREE})
        done = self.run_cli(payload)
        self.assertEqual(done.returncode, 0)
        self.assertIn("Security gate: BLOCK", done.stdout)
        self.assertIn("F1 high src/app.py", done.stdout)

    def test_unreadable_input_is_incomplete_and_exits_2(self):
        done = self.run_cli("not json")
        self.assertEqual(done.returncode, 2)
        self.assertIn("Security gate: INCOMPLETE - input unreadable", done.stdout)


if __name__ == "__main__":
    unittest.main()
