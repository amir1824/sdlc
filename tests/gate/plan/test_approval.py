"""Tests for the plan approval and the frozen tests it records.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.frozen_base import BUILDER, FrozenGateTest


class ApprovalTest(FrozenGateTest):
    """What `approve plan` freezes, and what it refuses while the owner is watching."""

    def test_the_record_holds_the_frozen_paths(self):
        self.approve_frozen("tests/test_bug.py", "tests/test_other.py")
        self.assertEqual(json.loads(self.approved.read_text())["tests"],
                         {"plan": ".sdlc/feature/plan.md", "paths": ["tests/test_bug.py", "tests/test_other.py"]})

    def test_the_approval_names_the_frozen_tests_and_logs_them(self):
        done = self.approve_frozen()
        self.assertIn("Frozen tests, which only qa-engineer may edit: tests/test_bug.py.", self.context(done))
        self.assertIn("tests=1", self.log.read_text())

    def test_a_first_approval_does_not_call_its_tests_newly_frozen(self):
        self.assertNotIn("Newly frozen", self.context(self.approve_frozen()))

    def test_a_plan_without_the_block_has_no_tests_key(self):
        self.locked_and_approved()
        self.assertNotIn("tests", json.loads(self.approved.read_text()))

    def test_a_plan_without_the_block_gets_the_notice_it_always_got(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertTrue(self.context(done).endswith(
            "No `sdlc-scope` block was approved, so edits are not limited to a set of paths. Copy this line "
            "into status.md. A change to any of these plan.md files locks code edits again."))

    def test_a_plan_without_the_block_logs_no_tests_line(self):
        self.locked_and_approved()
        self.assertNotIn(" tests ", self.log.read_text())

    def test_comment_and_blank_lines_are_not_paths(self):
        self.approve_frozen("# the reproduction", "", "tests/test_bug.py")
        self.assertEqual(json.loads(self.approved.read_text())["tests"]["paths"], ["tests/test_bug.py"])

    def test_a_star_is_refused(self):
        self.refused(self.approve_frozen("tests/*.py"), "has a wildcard")

    def test_a_question_mark_is_refused(self):
        self.refused(self.approve_frozen("tests/test_?.py"), "has a wildcard")

    def test_a_bracket_is_a_plain_character_of_an_exact_path(self):
        self.approve_frozen("pages/[id].test.tsx")
        self.frozen_denial(self.edit_as(self.project / "pages" / "[id].test.tsx", BUILDER))

    def test_a_look_alike_letter_is_refused(self):
        self.refused(self.approve_frozen("tests/test_pаyment.py"), "outside ASCII")

    def test_a_no_break_space_is_refused(self):
        self.refused(self.approve_frozen("tests/test bug.py"), "outside ASCII")

    def test_a_path_through_a_symlinked_folder_is_refused(self):
        (self.project / "spec").mkdir()
        (self.project / "tests").symlink_to(self.project / "spec")
        self.refused(self.approve_frozen(), "passes through a symlink")

    def test_a_path_that_is_a_symlink_is_refused(self):
        self.frozen.parent.mkdir()
        self.frozen.symlink_to(self.tmp / "elsewhere.py")
        self.refused(self.approve_frozen(), "passes through a symlink")

    def test_the_runs_folder_in_another_case_is_refused(self):
        self.refused(self.approve_frozen(".SDLC/feature/test_bug.py"), "under .sdlc/")

    def test_a_fence_in_another_case_is_a_near_miss(self):
        done = self.approve_plan("# Plan\n```SDLC-TESTS\ntests/test_bug.py\n```\n")
        self.refused(done, "not the exact fence")

    def test_an_absolute_path_is_refused(self):
        self.refused(self.approve_frozen("/etc/test_bug.py"), "absolute path")

    def test_a_parent_segment_is_refused(self):
        self.refused(self.approve_frozen("tests/../test_bug.py"), "`..` segment")

    def test_a_backslash_is_refused(self):
        self.refused(self.approve_frozen("tests\\test_bug.py"), "backslash")

    def test_a_path_under_the_runs_folder_is_refused(self):
        self.refused(self.approve_frozen(".sdlc/feature/test_bug.py"), "under .sdlc/")

    def test_a_path_under_git_is_refused(self):
        self.refused(self.approve_frozen(".git/hooks/test_bug.py"), "reaches .git or .claude")

    def test_a_path_under_the_agents_settings_is_refused(self):
        self.refused(self.approve_frozen(".claude/test_bug.py"), "reaches .git or .claude")

    def test_a_folder_is_refused(self):
        self.frozen.parent.mkdir()
        self.refused(self.approve_frozen("tests"), "is a folder")

    def test_the_same_file_twice_is_refused(self):
        self.refused(self.approve_frozen("tests/test_bug.py", "tests/TEST_BUG.py"), "names a file twice")

    def test_more_than_twenty_paths_are_refused(self):
        self.refused(self.approve_frozen(*[f"tests/test_{n}.py" for n in range(21)]), "more than 20 paths")

    def test_an_empty_block_is_refused(self):
        self.refused(self.approve_frozen("# nothing yet"), "`sdlc-tests` block is empty")

    def test_two_blocks_are_refused(self):
        done = self.approve_plan(self.frozen_block("tests/a.py") + self.frozen_block("tests/b.py"))
        self.refused(done, "more than one `sdlc-tests` block")

    def test_a_near_miss_fence_is_refused(self):
        done = self.approve_plan("# Plan\n``` sdlc-tests\ntests/test_bug.py\n```\n")
        self.refused(done, "not the exact fence")

    def test_an_unclosed_block_is_refused(self):
        done = self.approve_plan("# Plan\n```sdlc-tests\ntests/test_bug.py\n")
        self.refused(done, "`sdlc-tests` block is not closed")

    def test_a_block_inside_another_fence_is_refused(self):
        done = self.approve_plan("# Plan\n```text\n" + self.frozen_block("tests/test_bug.py") + "```\n")
        self.refused(done, "sits inside another code fence")

    def test_a_test_outside_the_scope_is_refused(self):
        done = self.approve_plan(self.scope_block("src/**") + self.frozen_block("tests/test_bug.py"))
        self.refused(done, "outside the `sdlc-scope` block")

    def test_scope_then_tests_freezes_both(self):
        self.approve_plan(self.scope_block("src/**", "tests/**") + self.frozen_block("tests/test_bug.py"))
        record = json.loads(self.approved.read_text())
        self.assertEqual((record["scope"]["globs"], record["tests"]["paths"]),
                         (["src/**", "tests/**"], ["tests/test_bug.py"]))

    def test_tests_then_scope_freezes_both(self):
        self.approve_plan(self.frozen_block("tests/test_bug.py") + self.scope_block("src/**", "tests/**"))
        record = json.loads(self.approved.read_text())
        self.assertEqual((record["scope"]["globs"], record["tests"]["paths"]),
                         (["src/**", "tests/**"], ["tests/test_bug.py"]))

    def test_several_plans_and_a_frozen_block_need_the_plans_name(self):
        other = self.project / ".sdlc" / "other" / "plan.md"
        other.parent.mkdir()
        other.write_text("# Other plan\n")
        self.refused(self.approve_frozen(), "one holds a tests block")

    def test_naming_the_plan_freezes_its_tests(self):
        other = self.project / ".sdlc" / "other" / "plan.md"
        other.parent.mkdir()
        other.write_text("# Other plan\n")
        self.approve_frozen()
        self.prompt("approve plan feature")
        self.assertEqual(json.loads(self.approved.read_text())["tests"]["paths"], ["tests/test_bug.py"])


if __name__ == "__main__":
    unittest.main()
