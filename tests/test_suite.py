"""Tests for scripts/suite.py: freezing eval cases by hash, checking them, and writing a baseline.

Run: python3 -I -m unittest discover -s tests
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "suite.py"
RATE = REPO / "scripts" / "rate_lesson.py"


def run(passed=True, error=None, cost=0.1, seconds=30):
    return {"passed": passed, "error": error, "skippedPaidGraders": False, "costUsd": cost,
            "durationSeconds": seconds, "turns": 3, "tracePath": "/x/trace.json"}


def case(name, runs):
    return {"name": name, "promptMarkdown": "a long prompt", "arms": {"with": runs}}


def result(cases, started="2026-11-03T10:00:00.000Z", partial=False):
    return {"startedAt": started, "partial": partial, "claudeVersion": "2.1.309", "cases": cases}


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]


class SuiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.evals = self.tmp / "evals"
        self.manifest = self.tmp / "suites" / "regression.json"
        self.baselines = self.tmp / "baselines"
        self.agents = self.tmp / "agents"
        self.agents.mkdir()
        self.make_case("tech-lead-plan", {"prompt.md": "plan it", "graders/a.md": "---\ntype: llm\n---\nx"})
        self.make_case("qa-engineer-flaky", {"prompt.md": "test it", "scaffold.sh": "echo hi"})

    def make_case(self, name, files):
        for relative, text in files.items():
            path = self.evals / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def suite(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, timeout=20)

    def freeze(self, *names):
        return self.suite("freeze", str(self.manifest), str(self.evals), *names)

    def check(self, *extra):
        return self.suite("check", str(self.manifest), str(self.evals), *extra)

    def write_result(self, name, cases, **kwargs):
        path = self.tmp / name
        path.write_text(json.dumps(result(cases, **kwargs)))
        return path

    def baseline(self, results, *extra, agent="qa-engineer"):
        agent_file = self.agents / f"{agent}.md"
        agent_file.write_text("agent v1")
        return self.suite("baseline", *[str(r) for r in results], "--agent-file", str(agent_file),
                          "--out", str(self.baselines), *extra)

    def baseline_file(self, agent="qa-engineer"):
        return self.baselines / f"{agent}-{fingerprint(self.agents / (agent + '.md'))}.json"

    # freeze

    def test_freeze_writes_a_hash_for_each_named_case(self):
        out = self.freeze("tech-lead-plan", "qa-engineer-flaky")
        self.assertEqual(out.returncode, 0, out.stderr)
        cases = json.loads(self.manifest.read_text())["cases"]
        self.assertEqual(sorted(cases), ["qa-engineer-flaky", "tech-lead-plan"])

    def test_freeze_refuses_to_overwrite_a_manifest(self):
        self.freeze("tech-lead-plan")
        before = self.manifest.read_text()
        out = self.freeze("qa-engineer-flaky")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.manifest.read_text(), before)

    def test_freeze_of_a_missing_case_writes_nothing(self):
        out = self.freeze("tech-lead-plan", "no-such-case")
        self.assertEqual(out.returncode, 2)
        self.assertFalse(self.manifest.exists())

    def test_freeze_refuses_a_case_name_that_walks_out_of_the_folder(self):
        out = self.freeze("../evals")
        self.assertEqual(out.returncode, 2)
        self.assertFalse(self.manifest.exists())

    def test_a_manifest_path_that_is_a_dangling_symlink_is_not_written_through(self):
        target = self.tmp / "elsewhere.json"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.symlink_to(target)
        out = self.freeze("tech-lead-plan")
        self.assertEqual(out.returncode, 2)
        self.assertFalse(target.exists())

    def test_a_symlink_inside_a_case_is_refused(self):
        (self.evals / "tech-lead-plan" / "link.md").symlink_to(self.evals / "qa-engineer-flaky" / "prompt.md")
        out = self.freeze("tech-lead-plan")
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_symlinked_folder_inside_a_case_is_refused(self):
        (self.evals / "tech-lead-plan" / "dir").symlink_to(self.evals / "qa-engineer-flaky")
        self.assertEqual(self.freeze("tech-lead-plan").returncode, 2)

    def test_a_dangling_symlink_in_a_frozen_case_is_an_error_not_a_crash(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "dang").symlink_to(self.tmp / "nowhere")
        out = self.check()
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_ds_store_file_in_a_subfolder_is_ignored_too(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "graders" / ".DS_Store").write_bytes(b"junk")
        self.assertEqual(self.check().returncode, 0)

    def test_the_hash_ignores_a_ds_store_file(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / ".DS_Store").write_bytes(b"junk")
        self.assertEqual(self.check().returncode, 0)

    # check

    def test_unchanged_cases_are_ok(self):
        self.freeze("tech-lead-plan", "qa-engineer-flaky")
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("ok       tech-lead-plan", out.stdout)
        self.assertIn("suite: 2 cases, 0 problem(s)", out.stdout)

    def test_an_edited_prompt_is_changed(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "prompt.md").write_text("plan it differently")
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("CHANGED  tech-lead-plan", out.stdout)

    def test_an_edited_grader_is_changed(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "graders" / "a.md").write_text("softer")
        self.assertEqual(self.check().returncode, 1)

    def test_an_added_file_is_changed(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "graders" / "b.md").write_text("new")
        self.assertEqual(self.check().returncode, 1)

    def test_a_removed_file_is_changed(self):
        self.freeze("tech-lead-plan")
        (self.evals / "tech-lead-plan" / "graders" / "a.md").unlink()
        self.assertEqual(self.check().returncode, 1)

    def test_a_removed_case_is_missing(self):
        self.freeze("tech-lead-plan")
        shutil.rmtree(self.evals / "tech-lead-plan")
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("MISSING  tech-lead-plan", out.stdout)

    def test_a_manifest_that_cannot_be_read_is_an_error(self):
        out = self.check()
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_manifest_that_is_not_the_expected_shape_is_an_error(self):
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text('{"cases": ["a"]}')
        out = self.check()
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_case_name_that_walks_out_of_the_evals_folder_is_an_error(self):
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text('{"cases": {"../outside": "abc"}}')
        out = self.check()
        self.assertEqual(out.returncode, 2)

    def test_a_baseline_for_the_current_agent_file_is_not_stale(self):
        self.freeze("qa-engineer-flaky")
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        out = self.check("--baselines", str(self.baselines), "--agents-dir", str(self.agents))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("stale", out.stdout)

    def test_a_baseline_for_an_older_agent_file_is_stale_but_not_a_problem(self):
        self.freeze("qa-engineer-flaky")
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        (self.agents / "qa-engineer.md").write_text("agent v2")
        out = self.check("--baselines", str(self.baselines), "--agents-dir", str(self.agents))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn(f"stale    qa-engineer: no baseline for the file now ({fingerprint(self.agents / 'qa-engineer.md')})",
                      out.stdout)

    def test_a_baseline_whose_agent_file_is_gone_is_reported_as_missing(self):
        self.freeze("qa-engineer-flaky")
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        (self.agents / "qa-engineer.md").unlink()
        out = self.check("--baselines", str(self.baselines), "--agents-dir", str(self.agents))
        self.assertIn("missing  qa-engineer: no agent file in", out.stdout)
        self.assertEqual(out.returncode, 0)

    def test_without_a_baselines_folder_nothing_is_said_about_baselines(self):
        self.freeze("qa-engineer-flaky")
        self.assertNotIn("stale", self.check().stdout)

    # baseline

    def test_baseline_keeps_only_the_cases_of_the_agent(self):
        source = self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5), case("tech-lead-plan", [run()] * 5)])
        out = self.baseline([source])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        text = self.baseline_file().read_text()
        self.assertIn('"qa-engineer-flaky"', text)
        self.assertNotIn('"tech-lead-plan"', text)

    def test_baseline_keeps_pass_error_cost_and_time_and_drops_the_prompt_and_trace(self):
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run(cost=0.2, seconds=44)] * 5)])])
        text = self.baseline_file().read_text()
        self.assertIn('"costUsd": 0.2', text)
        self.assertIn('"durationSeconds": 44', text)
        self.assertNotIn("a long prompt", text)
        self.assertNotIn("trace.json", text)

    def test_baseline_records_the_agent_and_its_hash(self):
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        data = json.loads(self.baseline_file().read_text())
        self.assertEqual((data["agent"], data["agentHash"]), ("qa-engineer", fingerprint(self.agents / "qa-engineer.md")))

    def test_a_later_result_replaces_the_runs_of_a_case(self):
        first = self.write_result("one.json", [case("qa-engineer-flaky", [run(error="timed out")] * 5)])
        second = self.write_result("two.json", [case("qa-engineer-flaky", [run()] * 5)], started="2026-11-03T11:00:00.000Z")
        out = self.baseline([first, second])
        self.assertEqual(out.returncode, 0, out.stdout)
        text = self.baseline_file().read_text()
        self.assertEqual(text.count('"passed"'), 5)
        self.assertNotIn("timed out", text)

    def test_a_case_with_an_errored_run_is_listed_for_a_rerun_and_exits_one(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 4 + [run(error="timed out")])])])
        self.assertEqual(out.returncode, 1)
        self.assertIn("RERUN    qa-engineer-flaky", out.stdout)
        self.assertTrue(self.baseline_file().exists())

    def test_a_case_with_too_few_runs_is_listed_for_a_rerun(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 3)])])
        self.assertEqual(out.returncode, 1)
        self.assertIn("RERUN    qa-engineer-flaky: 3 runs, 5 needed", out.stdout)

    def test_runs_sets_how_many_a_case_needs(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 3)])], "--runs", "3")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_run_that_skipped_a_paid_grader_is_listed_for_a_rerun(self):
        skipped = dict(run(), skippedPaidGraders=True)
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 4 + [skipped])])])
        self.assertEqual(out.returncode, 1)
        self.assertIn("a paid grader was skipped", out.stdout)

    def test_a_frozen_case_of_the_agent_missing_from_the_results_is_listed_for_a_rerun(self):
        self.make_case("qa-engineer-other", {"prompt.md": "x"})
        self.freeze("qa-engineer-flaky", "qa-engineer-other")
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])],
                            "--manifest", str(self.manifest))
        self.assertEqual(out.returncode, 1)
        self.assertIn("RERUN    qa-engineer-other: not in the results", out.stdout)

    def test_every_frozen_case_of_the_agent_present_is_ok(self):
        self.freeze("qa-engineer-flaky", "tech-lead-plan")
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])],
                            "--manifest", str(self.manifest))
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_the_agent_name_comes_from_the_file_name(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        self.assertIn("qa-engineer-", out.stdout.splitlines()[0])

    def test_an_agent_file_whose_name_is_not_an_agent_name_is_refused(self):
        odd = self.agents / "Odd Name.md"
        odd.write_text("x")
        out = self.suite("baseline", str(self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])),
                         "--agent-file", str(odd), "--out", str(self.baselines))
        self.assertEqual(out.returncode, 2)

    def test_fewer_than_three_runs_needed_is_refused(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])], "--runs", "2")
        self.assertEqual(out.returncode, 2)

    def test_an_unrelated_case_with_an_odd_name_does_not_stop_the_baseline(self):
        source = self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5), case("odd name", [run()] * 5)])
        self.assertEqual(self.baseline([source]).returncode, 0)

    def test_an_out_folder_that_is_a_file_is_an_error_not_a_crash(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("x")
        agent_file = self.agents / "qa-engineer.md"
        agent_file.write_text("agent v1")
        out = self.suite("baseline", str(self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])),
                         "--agent-file", str(agent_file), "--out", str(blocker / "sub"))
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_the_hash_matches_the_one_rate_lesson_writes(self):
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        lessons = self.tmp / "LESSONS.md"
        lessons.write_text("## L1 · qa-engineer · INV\n- confidence: low\n- status: library\n- used: none yet\n")
        subprocess.run([sys.executable, "-I", str(RATE), str(self.write_result("rl.json", [
            case("lesson-l1-with", [run()] * 3), case("lesson-l1-without", [run(False)] * 3)])), "L1",
            "--lessons", str(lessons), "--agent", str(self.agents / "qa-engineer.md")],
            check=True, capture_output=True, timeout=20)
        self.assertIn(f"qa-engineer@{fingerprint(self.agents / 'qa-engineer.md')}", lessons.read_text())

    def test_a_partial_result_is_refused(self):
        out = self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)], partial=True)])
        self.assertEqual(out.returncode, 2)
        self.assertFalse(self.baselines.exists())

    def test_a_result_with_no_case_of_the_agent_is_refused(self):
        out = self.baseline([self.write_result("r.json", [case("tech-lead-plan", [run()] * 5)])])
        self.assertEqual(out.returncode, 2)

    def test_a_result_that_is_not_json_is_refused(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json")
        out = self.baseline([bad])
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_baseline_is_a_valid_input_for_the_regression_check(self):
        self.baseline([self.write_result("r.json", [case("qa-engineer-flaky", [run()] * 5)])])
        lessons = self.tmp / "LESSONS.md"
        lessons.write_text("## L1 · qa-engineer · INV\n- confidence: low\n- status: library\n- used: none yet\n")
        after = self.write_result("after.json", [case("qa-engineer-flaky", [run()] * 5)])
        out = subprocess.run([sys.executable, "-I", str(RATE), str(after), "L1", "--regression",
                              str(self.baseline_file()), "--lessons", str(lessons)],
                             capture_output=True, text=True, timeout=20)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("1 judged, none dropped", lessons.read_text())


class CheckShSuiteTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.evals = self.home / "plugin" / "evals"
        (self.evals / "case-a").mkdir(parents=True)
        (self.evals / "case-a" / "prompt.md").write_text("x")
        (self.home / "plugin" / "agents").mkdir()
        (self.home / "settings.json").write_text("{}")

    def run_check(self, env_evals=True):
        env = {**os.environ, "CLAUDE_HOME": str(self.home)}
        env.pop("SDLC_EVALS", None)
        env.update({"SDLC_EVALS": str(self.evals)} if env_evals else {})
        return subprocess.run(["bash", str(REPO / "scripts" / "check.sh")], capture_output=True, text=True,
                              timeout=30, env=env)

    def freeze(self):
        subprocess.run([sys.executable, "-I", str(SCRIPT), "freeze", str(self.evals / "suites" / "regression.json"),
                        str(self.evals), "case-a"], check=True, capture_output=True, timeout=20)

    def test_a_changed_frozen_case_is_a_problem(self):
        self.freeze()
        (self.evals / "case-a" / "prompt.md").write_text("changed")
        out = self.run_check()
        self.assertIn("CHANGED  case-a", out.stdout)
        self.assertNotEqual(out.returncode, 0)

    def test_an_unchanged_frozen_case_says_ok(self):
        self.freeze()
        self.assertIn("ok       case-a", self.run_check().stdout)

    def test_without_the_variable_nothing_is_said_about_a_suite(self):
        self.freeze()
        self.assertNotIn("suite:", self.run_check(env_evals=False).stdout)

    def test_a_folder_without_a_manifest_says_nothing(self):
        self.assertNotIn("suite:", self.run_check().stdout)


if __name__ == "__main__":
    unittest.main()
