"""Tests for approving again and for the limits the freeze does not cover.

Run: python3 -I -m unittest discover -s tests
"""
import json
import unittest

from support.frozen_base import BUILDER, FrozenGateTest, QA


class ReapprovalTest(FrozenGateTest):
    """The frozen list changes only through `approve plan`, and the notice says what changed."""

    def test_a_changed_plan_locks_the_test_for_qa_engineer_too(self):
        self.approve_frozen()
        self.plan.write_text("# Plan with no block\n")
        self.assertIn("changed after the owner approved it", self.reason(self.edit_as(self.frozen, QA)))

    def test_a_changed_plan_does_not_unfreeze_before_the_owner_approves(self):
        self.approve_frozen()
        self.plan.write_text("# Plan with no block\n")
        self.assertIn("changed after the owner approved it", self.reason(self.edit_as(self.frozen, BUILDER)))

    def test_the_notice_names_a_test_that_is_no_longer_frozen(self):
        self.approve_frozen("tests/test_bug.py", "tests/test_other.py")
        self.plan.write_text("# Plan\n" + self.frozen_block("tests/test_other.py"))
        done = self.prompt("approve plan")
        self.assertIn("NO LONGER FROZEN since the last approval: tests/test_bug.py.", self.context(done))

    def test_the_notice_names_every_test_when_the_block_is_removed(self):
        self.approve_frozen()
        self.plan.write_text("# Plan with no block\n")
        done = self.prompt("approve plan")
        self.assertIn("NO LONGER FROZEN since the last approval: tests/test_bug.py.", self.context(done))

    def test_the_notice_names_a_newly_frozen_test(self):
        self.approve_frozen()
        self.plan.write_text("# Plan\n" + self.frozen_block("tests/test_bug.py", "tests/test_other.py"))
        done = self.prompt("approve plan")
        self.assertIn("Newly frozen since the last approval: tests/test_other.py.", self.context(done))

    def test_a_removal_comes_before_the_scope_list_in_the_notice(self):
        self.approve_plan(self.scope_block("tests/**") + self.frozen_block("tests/test_bug.py", "tests/test_other.py"))
        self.plan.write_text(self.scope_block("tests/**") + self.frozen_block("tests/test_other.py"))
        notice = json.loads(self.prompt("approve plan").stdout)["systemMessage"]
        self.assertLess(notice.index("NO LONGER FROZEN"), notice.index("Edits are limited"))

    def test_a_change_of_case_only_is_not_reported_as_a_removal(self):
        self.approve_frozen("tests/Test_Bug.py")
        self.plan.write_text("# Plan\n" + self.frozen_block("tests/test_bug.py"))
        self.assertNotIn("NO LONGER FROZEN", self.context(self.prompt("approve plan")))

    def test_the_same_paths_again_report_no_change(self):
        self.approve_frozen()
        self.plan.write_text("# Plan, reworded\n" + self.frozen_block("tests/test_bug.py"))
        context = self.context(self.prompt("approve plan"))
        self.assertNotIn("NO LONGER FROZEN", context)
        self.assertNotIn("Newly frozen", context)

    def test_a_removal_the_owner_approved_unfreezes_the_test(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))
        self.plan.write_text("# Plan with no block\n")
        self.prompt("approve plan")
        self.assertEqual(self.edit_as(self.frozen, BUILDER).stdout, "")


class OtherLimitsTest(FrozenGateTest):
    """The freeze is the last check: it never lifts the lock or the scope, and it fails closed."""

    def test_qa_engineer_is_locked_out_before_approval(self):
        self.plan.write_text("# Plan\n" + self.frozen_block("tests/test_bug.py"))
        self.prompt("/sdlc fix the rounding bug")
        self.assertIn("has not approved the plan", self.reason(self.edit_as(self.frozen, QA)))

    def test_qa_engineer_stays_inside_the_scope(self):
        self.approve_plan(self.scope_block("tests/**") + self.frozen_block("tests/test_bug.py"))
        self.assertIn("sdlc-gate: [scope]", self.reason(self.edit_as(self.project / "src" / "money.py", QA)))

    def test_turning_the_scope_off_keeps_the_freeze(self):
        self.approve_plan(self.scope_block("tests/**") + self.frozen_block("tests/test_bug.py"))
        self.frozen_denial(self.edit_as(self.frozen, BUILDER, env={"SDLC_GATE_SCOPE": "off"}))

    def test_a_record_whose_tests_are_not_a_mapping_denies_everyone(self):
        self.approve_frozen()
        self.tamper("tests/test_bug.py")
        self.assertIn("frozen-tests check failed", self.reason(self.edit_as(self.frozen, QA)))

    def test_a_record_with_no_paths_denies(self):
        self.approve_frozen()
        self.tamper({"plan": ".sdlc/feature/plan.md"})
        self.assertIn("frozen-tests check failed", self.reason(self.edit_as(self.frozen, BUILDER)))

    def test_a_record_with_a_path_that_is_not_text_denies(self):
        self.approve_frozen()
        self.tamper({"paths": ["tests/test_bug.py", 7]})
        self.assertIn("frozen-tests check failed", self.reason(self.edit_as(self.project / "src" / "x.py", BUILDER)))

    def test_a_record_with_an_empty_list_denies(self):
        self.approve_frozen()
        self.tamper({"paths": []})
        self.assertIn("frozen-tests check failed", self.reason(self.edit_as(self.frozen, BUILDER)))

    def test_the_runs_own_files_stay_writable_with_frozen_tests(self):
        self.approve_frozen()
        self.assertEqual(self.edit_as(self.plan.parent / "status.md").stdout, "")

    def test_the_runs_own_files_stay_writable_when_the_record_is_damaged(self):
        self.approve_frozen()
        self.tamper("tests/test_bug.py")
        self.assertEqual(self.edit_as(self.plan.parent / "status.md").stdout, "")

    def test_a_scope_fence_in_another_case_is_a_near_miss_too(self):
        done = self.approve_plan("# Plan\n```SDLC-SCOPE\nsrc/**\n```\n")
        self.refused(done, "not the exact fence")

    def test_the_hash_check_of_verify_is_a_command_the_read_only_reviewer_may_run(self):
        self.approve_frozen()
        done = self.bash("git hash-object tests/test_bug.py", agent_type="sdlc:brutal-reviewer")
        self.assertEqual(done.stdout, "")

    def test_the_freeze_holds_only_in_the_session_that_approved(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))
        self.assertEqual(self.edit_as(self.frozen, BUILDER, session_id="other").stdout, "")

    def test_the_gate_off_switch_turns_the_freeze_off_too(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))
        self.assertEqual(self.edit_as(self.frozen, BUILDER, env={"SDLC_GATE": "off"}).stdout, "")


if __name__ == "__main__":
    unittest.main()
