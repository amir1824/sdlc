"""Tests for scripts/rate_lesson.py, run on a synthetic eval result and a synthetic lessons file.

Run: python3 -I -m unittest discover -s tests
The result JSON copies the fields `claude plugin eval --json` writes (cases[].name,
cases[].arms.with[].passed and .error, startedAt); a change to that format is not caught here.
"""
import json
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


def run(passed, error=None):
    return {"passed": passed, "error": error}


def case(name, runs):
    return {"name": name, "arms": {"with": runs}}


class RateLessonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.lessons = self.tmp / "LESSONS.md"
        self.lessons.write_text(LESSONS)
        self.result = self.tmp / "result.json"

    def rate_result(self, cases, lesson="L1"):
        self.result.write_text(json.dumps({"startedAt": "2026-11-03T02:10:41.000Z", "cases": cases}))
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


if __name__ == "__main__":
    unittest.main()
