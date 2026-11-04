"""Tests for scripts/rate_lesson.py, run on a synthetic eval result and a synthetic lessons file.

Run: python3 -I -m unittest discover -s tests
The result JSON copies the fields `claude plugin eval --json` writes (cases[].name,
cases[].arms.with[].passed and .error, startedAt); a change to that format is not caught here.
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

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rate_lesson.py"

L2 = """## L2 · tech-lead · INV
- cue: a plan sets a contract
- confidence: low
- status: library
- used: none yet
"""

LESSONS = f"""# Lessons

## L1 · backend-developer · INV
- cue: a change alters a constructor's signature
- confidence: low
- status: library
- used: none yet

{L2}"""


def run(passed, error=None, skipped=False):
    return {"passed": passed, "error": error, "skippedPaidGraders": skipped}


def case(name, runs):
    return {"name": name, "arms": {"with": runs}}


class RateLessonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.lessons = self.tmp / "LESSONS.md"
        self.lessons.write_text(LESSONS)
        self.result = self.tmp / "result.json"

    def rate_result(self, cases, lesson="L1", partial=False):
        self.result.write_text(json.dumps({"startedAt": "2026-11-03T02:10:41.000Z", "partial": partial,
                                           "cases": cases}))
        return subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.result), lesson,
                               "--lessons", str(self.lessons)], capture_output=True, text=True, timeout=10)

    def rate(self, with_runs, without_runs, lesson="L1"):
        return self.rate_result([case("lesson-l1-with", with_runs),
                                 case("lesson-l1-without", without_runs)], lesson)

    def test_helped_raises_confidence(self):
        out = self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertEqual(out.returncode, 0, out.stderr)
        text = self.lessons.read_text()
        self.assertIn("- used: eval lesson-l1 2026-11-03T02:10: helped (with 3/3, without 0/3)", text)
        self.assertIn("- confidence: medium", text)
        self.assertIn("- status: library", text)

    def test_helped_leaves_a_proposed_lesson_for_the_owner(self):
        self.lessons.write_text(LESSONS.replace("- status: library", "- status: proposed", 1))
        self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertIn("- status: proposed", self.lessons.read_text())

    def test_hurt_retires_the_lesson(self):
        self.rate([run(False)] * 3, [run(True)] * 3)
        text = self.lessons.read_text()
        self.assertIn("- used: eval lesson-l1 2026-11-03T02:10: hurt (with 0/3, without 3/3)", text)
        self.assertIn("- status: retired", text)

    def test_hurt_retires_a_proposed_lesson_too(self):
        self.lessons.write_text(LESSONS.replace("- status: library", "- status: proposed", 1))
        self.rate([run(False)] * 3, [run(True)] * 3)
        self.assertIn("- status: retired", self.lessons.read_text())

    def test_gap_of_exactly_half_is_helped_with_unequal_arms(self):
        self.rate([run(True)] * 7 + [run(False)] * 3, [run(True)] + [run(False)] * 4)
        self.assertIn("helped (with 7/10, without 1/5)", self.lessons.read_text())

    def test_same_pass_rate_is_no_observed_effect(self):
        self.rate([run(True)] * 3, [run(True)] * 3)
        text = self.lessons.read_text()
        self.assertIn("no observed effect (with 3/3, without 3/3)", text)
        self.assertNotIn("- confidence: medium", text)

    def test_gap_below_half_is_no_observed_effect(self):
        self.rate([run(True), run(True), run(False)], [run(True), run(False), run(False)])
        self.assertIn("no observed effect (with 2/3, without 1/3)", self.lessons.read_text())

    def test_errored_run_is_confounded(self):
        self.rate([run(True), run(True), run(False, "timeout")], [run(False)] * 3)
        self.assertIn("confounded (with 2/3, without 0/3, a run errored)", self.lessons.read_text())

    def test_too_few_runs_is_confounded(self):
        self.rate([run(True)] * 2, [run(False)] * 2)
        self.assertIn("confounded (with 2/2, without 0/2, fewer than 3 runs in an arm)",
                      self.lessons.read_text())

    def test_a_run_that_skipped_its_paid_graders_is_confounded(self):
        self.rate([run(True)] * 3, [run(True), run(False), run(False, skipped=True)])
        self.assertIn("confounded (with 3/3, without 1/3, a run skipped its paid graders)",
                      self.lessons.read_text())

    def test_a_partial_result_is_confounded(self):
        self.rate_result([case("lesson-l1-with", [run(True)] * 3),
                          case("lesson-l1-without", [run(False)] * 3)], partial=True)
        self.assertIn("confounded (with 3/3, without 0/3, the eval stopped early)", self.lessons.read_text())

    def test_hurt_on_a_promoted_lesson_says_to_revert_the_agent_text(self):
        self.lessons.write_text(LESSONS.replace("- status: library", "- status: promoted (backend-developer)", 1))
        out = self.rate([run(False)] * 3, [run(True)] * 3)
        self.assertIn("- status: retired", self.lessons.read_text())
        self.assertIn("revert", out.stdout)

    def test_confidence_with_a_trailing_space_is_raised(self):
        self.lessons.write_text(LESSONS.replace("- confidence: low", "- confidence: low ", 1))
        self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertIn("- confidence: medium", self.lessons.read_text())

    def test_confounded_changes_neither_confidence_nor_status(self):
        self.rate([run(True)] * 3, [run(False, "timeout")] * 3)
        text = self.lessons.read_text()
        self.assertEqual(text.count("- confidence: low"), 2)
        self.assertEqual(text.count("- status: library"), 2)

    def test_other_lessons_are_untouched(self):
        self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertIn(L2, self.lessons.read_text())

    def test_l1_does_not_match_l10(self):
        self.lessons.write_text("## L10 · qa-engineer · INV\n- used: none yet\n\n" + LESSONS)
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.assertIn("## L10 · qa-engineer · INV\n- used: none yet\n", self.lessons.read_text())

    def test_l1_does_not_match_a_heading_that_only_starts_with_it(self):
        self.lessons.write_text("## L1-old · qa-engineer · INV\n- used: none yet\n\n" + LESSONS)
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.assertIn("## L1-old · qa-engineer · INV\n- used: none yet\n", self.lessons.read_text())

    def test_write_keeps_the_file_mode_and_a_symlink(self):
        real = self.tmp / "real-LESSONS.md"
        real.write_text(LESSONS)
        real.chmod(0o644)
        self.lessons.unlink()
        self.lessons.symlink_to(real)
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.assertTrue(self.lessons.is_symlink())
        self.assertEqual(real.stat().st_mode & 0o777, 0o644)
        self.assertIn("no observed effect", real.read_text())

    def test_new_rating_follows_earlier_ones(self):
        self.lessons.write_text(LESSONS.replace("- used: none yet", "- used: demo-run: confounded", 1))
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.assertIn("- used: demo-run: confounded; eval lesson-l1 2026-11-03T02:10: no observed effect",
                      self.lessons.read_text())

    def test_rating_the_same_result_twice_keeps_one_entry(self):
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.rate([run(True)] * 3, [run(True)] * 3)
        self.assertEqual(self.lessons.read_text().count("eval lesson-l1 2026-11-03T02:10:"), 1)

    def test_missing_arm_leaves_the_file_untouched(self):
        out = self.rate_result([case("lesson-l1-with", [run(True)] * 3)])
        self.assertEqual(out.returncode, 2)
        self.assertIn("no case named lesson-l1-without", out.stderr)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_unknown_lesson_leaves_the_file_untouched(self):
        out = self.rate_result([case("lesson-l9-with", [run(True)] * 3),
                                case("lesson-l9-without", [run(False)] * 3)], lesson="L9")
        self.assertEqual(out.returncode, 2)
        self.assertIn("no section '## L9'", out.stderr)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_unreadable_result_leaves_the_file_untouched(self):
        self.result.write_text("{not json")
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.result), "L1",
                              "--lessons", str(self.lessons)], capture_output=True, text=True, timeout=10)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_a_non_utf8_locale_still_reads_and_writes_the_lessons_file(self):
        self.result.write_text(json.dumps({"startedAt": "2026-11-03T02:10:41.000Z", "cases": [
            case("lesson-l1-with", [run(True)] * 3), case("lesson-l1-without", [run(False)] * 3)]}))
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.result), "L1", "--lessons", str(self.lessons)],
                             capture_output=True, text=True, timeout=10,
                             env={**os.environ, "LC_ALL": "en_US.US-ASCII"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("## L1 · backend-developer · INV\n- cue", self.lessons.read_text(encoding="utf-8"))

    def test_missing_lessons_file_is_an_error(self):
        self.lessons.unlink()
        out = self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertEqual(out.returncode, 2)
        self.assertIn("LESSONS.md not changed", out.stderr)

    def test_lesson_without_a_used_line_leaves_the_file_untouched(self):
        broken = LESSONS.replace("- used: none yet\n\n## L2", "\n## L2", 1)
        self.lessons.write_text(broken)
        out = self.rate([run(True)] * 3, [run(False)] * 3)
        self.assertEqual(out.returncode, 2)
        self.assertIn("no '- used:' line", out.stderr)
        self.assertEqual(self.lessons.read_text(), broken)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]


class AgentFingerprintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.lessons = self.tmp / "LESSONS.md"
        self.lessons.write_text(LESSONS)
        self.result = self.tmp / "result.json"
        self.result.write_text(json.dumps({"startedAt": "2026-11-03T02:10:41.000Z", "cases": [
            case("lesson-l1-with", [run(True)] * 3), case("lesson-l1-without", [run(False)] * 3)]}))
        self.backend = self.tmp / "backend-developer.md"
        self.backend.write_text("backend v1")
        self.frontend = self.tmp / "frontend-developer.md"
        self.frontend.write_text("frontend v1")

    def rate(self, *agents):
        args = [arg for agent in agents for arg in ("--agent", str(agent))]
        return subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.result), "L1",
                               "--lessons", str(self.lessons), *args], capture_output=True, text=True, timeout=10)

    def test_the_rating_records_the_hash_of_the_agent_file(self):
        out = self.rate(self.backend)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"helped (with 3/3, without 0/3, agents backend-developer@{fingerprint(self.backend)})",
                      self.lessons.read_text())

    def test_several_agents_are_recorded_in_the_order_given(self):
        self.rate(self.backend, self.frontend)
        self.assertIn(f"agents backend-developer@{fingerprint(self.backend)} "
                      f"frontend-developer@{fingerprint(self.frontend)})", self.lessons.read_text())

    def test_a_changed_agent_file_gives_another_hash(self):
        self.rate(self.backend)
        first = self.lessons.read_text()
        self.backend.write_text("backend v2")
        self.rate(self.backend)
        self.assertNotEqual(first, self.lessons.read_text())

    def test_a_missing_agent_file_leaves_the_lessons_untouched(self):
        out = self.rate(self.tmp / "nobody.md")
        self.assertEqual(out.returncode, 2)
        self.assertIn("nobody.md", out.stderr)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_an_agent_name_the_used_line_cannot_hold_leaves_the_lessons_untouched(self):
        odd = self.tmp / "bad; name.md"
        odd.write_text("x")
        out = self.rate(odd)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_an_agent_name_with_upper_case_is_rejected_like_check_lessons_would(self):
        odd = self.tmp / "Foo_Bar.md"
        odd.write_text("x")
        self.assertEqual(self.rate(odd).returncode, 2)

    def test_the_same_agent_given_twice_is_recorded_once(self):
        self.rate(self.backend, self.backend)
        self.assertEqual(self.lessons.read_text().count("backend-developer@"), 1)

    def test_a_started_at_with_the_entry_separator_is_rejected_in_a_rating_too(self):
        self.result.write_text(json.dumps({"startedAt": "a; b", "cases": [
            case("lesson-l1-with", [run(True)] * 3), case("lesson-l1-without", [run(False)] * 3)]}))
        out = self.rate()
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.lessons.read_text(), LESSONS)

    def test_a_rating_without_agents_keeps_the_old_format(self):
        self.rate()
        self.assertIn("helped (with 3/3, without 0/3)\n", self.lessons.read_text())

    def test_the_entry_stays_one_entry_when_split_on_the_separator(self):
        self.rate(self.backend, self.frontend)
        used = next(line for line in self.lessons.read_text().split("\n") if line.startswith("- used:"))
        self.assertEqual(len(used.split(": ", 1)[1].split("; ")), 1)


PROMOTED = LESSONS.replace("- status: library", '- status: promoted (backend-developer, "Fix it", 2026-11-03)', 1)


class RegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.lessons = self.tmp / "LESSONS.md"
        self.lessons.write_text(PROMOTED)

    def write(self, name, cases, started="2026-11-03T02:10:41.000Z", partial=False):
        path = self.tmp / name
        path.write_text(json.dumps({"startedAt": started, "partial": partial, "cases": cases}))
        return path

    def regress(self, before, after, lesson="L1", *extra):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), str(after), lesson, "--regression", str(before),
                               "--lessons", str(self.lessons), *extra], capture_output=True, text=True, timeout=10)

    def pair(self, before_runs, after_runs, name="case-a", **after_args):
        return (self.write("before.json", [case(name, before_runs)], started="2026-11-03T01:00:00.000Z"),
                self.write("after.json", [case(name, after_runs)], **after_args))

    def used(self):
        return next(line for line in self.lessons.read_text().split("\n") if line.startswith("- used:"))

    def test_no_case_dropping_is_ok(self):
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("regression 2026-11-03T02:10: ok (1 judged, none dropped)", self.used())

    def test_a_drop_of_half_or_more_is_regressed_and_exits_one(self):
        before, after = self.pair([run(True)] * 3, [run(True), run(False), run(False)])
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 1)
        self.assertIn("regression 2026-11-03T02:10: REGRESSED (case-a 3/3 -> 1/3)", self.used())
        self.assertIn("revert", out.stdout)

    def test_a_drop_below_half_is_ok(self):
        before, after = self.pair([run(True)] * 3, [run(True), run(True), run(False)])
        self.assertEqual(self.regress(before, after).returncode, 0)

    def test_an_improvement_is_not_flagged(self):
        before, after = self.pair([run(False)] * 3, [run(True)] * 3)
        self.assertEqual(self.regress(before, after).returncode, 0)
        self.assertIn("none dropped", self.used())

    def test_every_dropped_case_is_named(self):
        before = self.write("before.json", [case("case-a", [run(True)] * 3), case("case-b", [run(True)] * 3)])
        after = self.write("after.json", [case("case-a", [run(False)] * 3), case("case-b", [run(False)] * 3)])
        self.regress(before, after)
        self.assertIn("case-a 3/3 -> 0/3, case-b 3/3 -> 0/3", self.used())

    def test_the_status_and_confidence_of_the_lesson_do_not_change(self):
        before, after = self.pair([run(True)] * 3, [run(False)] * 3)
        self.regress(before, after)
        text = self.lessons.read_text()
        self.assertIn('- status: promoted (backend-developer, "Fix it", 2026-11-03)', text)
        self.assertEqual(text.count("- confidence: low"), 2)

    def test_cases_in_only_one_file_are_ignored(self):
        before = self.write("before.json", [case("case-a", [run(True)] * 3), case("old", [run(True)] * 3)])
        after = self.write("after.json", [case("case-a", [run(True)] * 3), case("new", [run(False)] * 3)])
        self.assertEqual(self.regress(before, after).returncode, 0)
        self.assertIn("(1 judged, none dropped)", self.used())

    def test_no_case_in_common_is_confounded_and_exits_one(self):
        before = self.write("before.json", [case("old", [run(True)] * 3)])
        after = self.write("after.json", [case("new", [run(True)] * 3)])
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 1)
        self.assertIn("confounded (no case judged)", self.used())

    def test_a_case_with_fewer_than_three_runs_is_unjudged(self):
        before = self.write("before.json", [case("case-a", [run(True)] * 3), case("case-b", [run(True)] * 2)])
        after = self.write("after.json", [case("case-a", [run(True)] * 3), case("case-b", [run(False)] * 2)])
        self.assertEqual(self.regress(before, after).returncode, 0)
        self.assertIn("(1 judged, 1 unjudged, none dropped)", self.used())

    def test_a_case_with_an_errored_run_is_unjudged(self):
        before, after = self.pair([run(True)] * 3, [run(False, "timeout")] * 3)
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 1)
        self.assertIn("confounded (no case judged)", self.used())

    def test_a_case_that_skipped_its_paid_graders_is_unjudged(self):
        before, after = self.pair([run(True)] * 3, [run(False, skipped=True)] * 3)
        self.regress(before, after)
        self.assertIn("confounded (no case judged)", self.used())

    def test_a_partial_result_with_no_drop_is_confounded(self):
        before, after = self.pair([run(True)] * 3, [run(True)] * 3, partial=True)
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 1)
        self.assertIn("confounded (the eval stopped early", self.used())

    def test_a_partial_baseline_with_no_drop_is_confounded(self):
        before = self.write("before.json", [case("case-a", [run(True)] * 3)], partial=True)
        after = self.write("after.json", [case("case-a", [run(True)] * 3)])
        self.assertEqual(self.regress(before, after).returncode, 1)

    def test_a_drop_stays_regressed_when_the_eval_stopped_early(self):
        before, after = self.pair([run(True)] * 3, [run(False)] * 3, partial=True)
        self.assertIn("REGRESSED", self.regress(before, after).stdout)

    def test_no_lesson_case_pair_is_needed(self):
        before, after = self.pair([run(True)] * 3, [run(True)] * 3, name="some-other-case")
        self.assertEqual(self.regress(before, after).returncode, 0)

    def test_the_agent_hash_is_recorded_too(self):
        agent = self.tmp / "backend-developer.md"
        agent.write_text("v1")
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        self.regress(before, after, "L1", "--agent", str(agent))
        self.assertIn(f"none dropped, agents backend-developer@{fingerprint(agent)})", self.used())

    def test_a_second_regression_run_replaces_the_first_of_the_same_time(self):
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        self.regress(before, after)
        self.regress(before, after)
        self.assertEqual(self.lessons.read_text().count("regression 2026-11-03T02:10:"), 1)

    def test_it_follows_the_earlier_ratings(self):
        self.lessons.write_text(PROMOTED.replace("- used: none yet", "- used: eval lesson-l1 x: helped (a)", 1))
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        self.regress(before, after)
        self.assertIn("- used: eval lesson-l1 x: helped (a); regression", self.used())

    def rejects(self, payload):
        before = self.write("before.json", [case("case-a", [run(True)] * 3)])
        after = self.tmp / "after.json"
        after.write_text(json.dumps(payload))
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertEqual(self.lessons.read_text(), PROMOTED)

    def test_a_case_name_with_a_newline_is_rejected(self):
        self.rejects({"cases": [case("x\n- status: retired\n## L9", [run(False)] * 3)]})

    def test_a_case_name_with_the_entry_separator_is_rejected(self):
        self.rejects({"cases": [case("x; y", [run(False)] * 3)]})

    def test_a_started_at_with_the_entry_separator_is_rejected(self):
        self.rejects({"startedAt": "2026; x: y; z", "cases": []})

    def test_a_started_at_with_a_newline_is_rejected(self):
        self.rejects({"startedAt": "ab\ncd", "cases": []})

    def test_a_started_at_that_is_not_text_is_rejected(self):
        self.rejects({"startedAt": 5, "cases": []})

    def test_a_started_at_that_is_a_list_is_rejected(self):
        self.rejects({"startedAt": ["a"], "cases": []})

    def test_a_result_that_is_a_list_is_rejected(self):
        self.rejects([])

    def test_cases_that_are_null_are_rejected(self):
        self.rejects({"cases": None})

    def test_a_case_that_is_a_string_is_rejected(self):
        self.rejects({"cases": ["case-a"]})

    def test_a_case_name_that_is_a_list_is_rejected(self):
        self.rejects({"cases": [{"name": ["a"], "arms": {"with": []}}]})

    def test_arms_that_are_null_are_rejected(self):
        self.rejects({"cases": [{"name": "case-a", "arms": None}]})

    def test_runs_that_are_null_are_rejected(self):
        self.rejects({"cases": [{"name": "case-a", "arms": {"with": None}}]})

    def test_a_run_that_is_a_number_is_rejected(self):
        self.rejects({"cases": [{"name": "case-a", "arms": {"with": [1, 2, 3]}}]})

    def test_a_lessons_file_that_is_not_utf8_is_an_error_not_a_crash(self):
        self.lessons.write_bytes(b"## L1\n\xff\n")
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        out = self.regress(before, after)
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_an_unreadable_baseline_leaves_the_lessons_untouched(self):
        after = self.write("after.json", [case("case-a", [run(True)] * 3)])
        out = self.regress(self.tmp / "nope.json", after)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.lessons.read_text(), PROMOTED)

    def test_an_unknown_lesson_leaves_the_lessons_untouched(self):
        before, after = self.pair([run(True)] * 3, [run(True)] * 3)
        out = self.regress(before, after, "L9")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.lessons.read_text(), PROMOTED)


if __name__ == "__main__":
    unittest.main()
