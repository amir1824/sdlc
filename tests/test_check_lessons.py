"""Tests for scripts/check_lessons.py and its line in scripts/check.sh, run on a synthetic lessons file
and a synthetic agents folder.

Run: python3 -I -m unittest discover -s tests
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_lessons.py"
RATE = REPO / "scripts" / "rate_lesson.py"
CHECK = REPO / "scripts" / "check.sh"
GATE = REPO / "plugins" / "sdlc" / "hooks" / "sdlc_gate.py"


def lesson(lesson_id, status, used="none yet"):
    return (f"## {lesson_id} · backend-developer · INV\n- cue: a cue\n- confidence: medium\n"
            f"- status: {status}\n- used: {used}\n\n")


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()[:10]


class CheckLessonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.agents = self.tmp / "agents"
        self.agents.mkdir()
        self.lessons = self.tmp / "LESSONS.md"

    def agent(self, name, text):
        (self.agents / f"{name}.md").write_text(text)

    def check(self, *sections):
        self.lessons.write_text("# Lessons\n\n" + "".join(sections))
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--lessons", str(self.lessons),
                               "--agents", str(self.agents)], capture_output=True, text=True, timeout=10)

    def test_a_promoted_lesson_whose_text_is_in_the_agent_passes(self):
        self.agent("backend-developer", "- **Fix what your change breaks, then report it.** more")
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix what your change breaks", 2026-11-03)'))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("ok       L1 backend-developer", out.stdout)

    def test_a_promoted_lesson_whose_text_is_missing_is_drift(self):
        self.agent("frontend-developer", "nothing about it")
        out = self.check(lesson("L1", 'promoted (frontend-developer, "Fix what your change breaks", 2026-11-03)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn('DRIFT    L1 frontend-developer: "Fix what your change breaks" is not in', out.stdout)

    def test_only_the_agent_that_lacks_the_text_is_reported(self):
        self.agent("backend-developer", "Fix what your change breaks")
        self.agent("frontend-developer", "other")
        out = self.check(lesson("L1", 'promoted (backend-developer and frontend-developer, "Fix what your change breaks", d)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn("DRIFT    L1 frontend-developer", out.stdout)
        self.assertNotIn("DRIFT    L1 backend-developer", out.stdout)

    def test_agents_separated_by_commas_are_all_checked(self):
        self.agent("backend-developer", "Fix it")
        out = self.check(lesson("L1", 'promoted (backend-developer, frontend-developer, "Fix it", d)'))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("missing  L1 frontend-developer", out.stdout)

    def test_an_agent_that_is_not_installed_is_not_a_problem(self):
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix it", d)'))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("missing  L1 backend-developer", out.stdout)

    def test_an_agent_reached_through_a_symlink_is_read(self):
        real = self.tmp / "real.md"
        real.write_text("Fix it")
        (self.agents / "backend-developer.md").symlink_to(real)
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix it", d)'))
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_a_promoted_status_without_a_quoted_text_cannot_be_checked(self):
        out = self.check(lesson("L1", "promoted (backend-developer)"))
        self.assertEqual(out.returncode, 1)
        self.assertIn("UNCHECKED L1", out.stdout)

    def test_a_promoted_status_without_agents_cannot_be_checked(self):
        out = self.check(lesson("L1", 'promoted ("Fix it", d)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn("UNCHECKED L1", out.stdout)

    def test_an_agent_name_that_walks_out_of_the_folder_is_not_read(self):
        (self.tmp / "secret.md").write_text("Fix it")
        out = self.check(lesson("L1", 'promoted (../secret, "Fix it", d)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn("UNCHECKED L1", out.stdout)

    def test_a_lesson_that_is_not_promoted_is_ignored(self):
        out = self.check(lesson("L1", "library"), lesson("L2", "retired"), lesson("L3", "proposed"))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("0 promoted", out.stdout)

    def test_a_status_that_only_mentions_promoted_is_ignored(self):
        out = self.check(lesson("L1", "retired (was promoted)"))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("0 promoted", out.stdout)

    def test_a_rating_of_the_current_agent_file_is_not_stale(self):
        self.agent("backend-developer", "Fix it")
        used = f"eval lesson-l1 x: helped (with 3/3, without 0/3, agents backend-developer@{fingerprint('Fix it')})"
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix it", d)', used))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("stale", out.stdout)

    def test_a_rating_of_an_older_agent_file_is_reported_as_stale_but_not_a_problem(self):
        self.agent("backend-developer", "Fix it, v2")
        used = f"eval lesson-l1 x: helped (with 3/3, without 0/3, agents backend-developer@{fingerprint('Fix it')})"
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix it", d)', used))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("stale    L1 backend-developer", out.stdout)

    def test_the_latest_rating_that_names_the_agent_decides_staleness(self):
        self.agent("backend-developer", "Fix it")
        old = f"eval lesson-l1 a: helped (agents backend-developer@{fingerprint('old')})"
        new = f"regression b: ok (1 judged, none dropped, agents backend-developer@{fingerprint('Fix it')})"
        out = self.check(lesson("L1", 'promoted (backend-developer, "Fix it", d)', f"{old}; {new}"))
        self.assertNotIn("stale", out.stdout)

    def test_a_lesson_that_is_not_promoted_gets_no_stale_line(self):
        self.agent("backend-developer", "v2")
        used = f"eval lesson-l1 x: helped (agents backend-developer@{fingerprint('v1')})"
        out = self.check(lesson("L1", "library", used))
        self.assertNotIn("stale", out.stdout)

    def test_a_missing_lessons_file_is_reported_without_a_crash(self):
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), "--lessons", str(self.tmp / "none.md"),
                              "--agents", str(self.agents)], capture_output=True, text=True, timeout=10)
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_lessons_file_that_is_not_utf8_exits_two_without_a_crash(self):
        self.lessons.write_bytes(b"## L1\n\xff\n")
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), "--lessons", str(self.lessons),
                              "--agents", str(self.agents)], capture_output=True, text=True, timeout=10)
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_an_agent_file_that_is_not_utf8_is_unchecked_and_the_rest_still_run(self):
        (self.agents / "badenc.md").write_bytes(b"\xff\xfe\x00bad")
        self.agent("backend-developer", "Fix it")
        out = self.check(lesson("L1", 'promoted (badenc, "Fix", d)'),
                         lesson("L2", 'promoted (backend-developer, "Fix it", d)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn("UNCHECKED L1 badenc", out.stdout)
        self.assertIn("ok       L2 backend-developer", out.stdout)

    def test_a_blank_quoted_text_cannot_be_checked(self):
        self.agent("backend-developer", "anything")
        out = self.check(lesson("L1", 'promoted (backend-developer, " ", d)'))
        self.assertEqual(out.returncode, 1)
        self.assertIn("UNCHECKED L1", out.stdout)

    def test_the_hash_matches_the_one_rate_lesson_writes(self):
        self.agent("backend-developer", "Fix it")
        passing = '[{"passed": true}, {"passed": true}, {"passed": true}]'
        failing = '[{"passed": false}, {"passed": false}, {"passed": false}]'
        result = self.tmp / "result.json"
        result.write_text('{"startedAt": "2026-11-03T02:10:41.000Z", "cases": ['
                          f'{{"name": "lesson-l1-with", "arms": {{"with": {passing}}}}},'
                          f'{{"name": "lesson-l1-without", "arms": {{"with": {failing}}}}}]}}')
        self.lessons.write_text("# Lessons\n\n" + lesson("L1", 'promoted (backend-developer, "Fix it", d)'))
        subprocess.run([sys.executable, "-I", str(RATE), str(result), "L1", "--lessons", str(self.lessons),
                        "--agent", str(self.agents / "backend-developer.md")],
                       check=True, capture_output=True, timeout=10)
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), "--lessons", str(self.lessons),
                              "--agents", str(self.agents)], capture_output=True, text=True, timeout=10)
        self.assertNotIn("stale", out.stdout)


class CheckShLessonsTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        (self.home / "agents").mkdir()
        (self.home / "lessons").mkdir()
        (self.home / "settings.json").write_text(f'{{"a": "python3 -I {GATE} prompt", "b": "python3 -I {GATE} tool"}}')

    def run_check(self):
        return subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CLAUDE_HOME": str(self.home)})

    def test_a_promoted_lesson_missing_from_an_installed_agent_is_a_problem(self):
        (self.home / "agents" / "frontend-developer.md").write_text("old")
        (self.home / "lessons" / "LESSONS.md").write_text(
            "# Lessons\n\n" + lesson("L1", 'promoted (frontend-developer, "Fix it", d)'))
        out = self.run_check()
        self.assertIn("DRIFT    L1 frontend-developer", out.stdout)
        self.assertNotEqual(out.returncode, 0)

    def test_without_a_lessons_file_the_check_says_nothing_about_lessons(self):
        out = self.run_check()
        self.assertNotIn("lessons:", out.stdout)


if __name__ == "__main__":
    unittest.main()
