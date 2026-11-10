"""Tests for the frozen reproduction tests of plugins/sdlc/hooks/sdlc_gate.py: the plan's `sdlc-tests` block.

Run: python3 -I -m unittest discover -s tests
These feed the hook the documented input shape, so they prove the gate's logic, not what the host sends.
They cover the four file tools only: the gate does not stop a Bash write to a frozen test.
"""
import json
import unittest

from test_sdlc_gate import GateTest

BUILDER = "sdlc:backend-developer"
QA = "sdlc:qa-engineer"


class FrozenGateTest(GateTest):
    def setUp(self):
        super().setUp()
        self.approved = self.home / "sdlc-gate" / "s1.approved"
        self.log = self.home / "sdlc-gate" / "approvals.log"
        self.frozen = self.project / "tests" / "test_bug.py"

    def frozen_block(self, *paths):
        return "## Reproduction\n```sdlc-tests\n" + "\n".join(paths) + "\n```\n"

    def scope_block(self, *globs):
        return "## Scope\n```sdlc-scope\n" + "\n".join(globs) + "\n```\n"

    def approve_plan(self, text):
        self.plan.write_text(text)
        self.prompt("/sdlc fix the rounding bug")
        return self.prompt("approve plan")

    def approve_frozen(self, *paths):
        return self.approve_plan("# Plan\n" + self.frozen_block(*(paths or ("tests/test_bug.py",))))

    def edit_as(self, path, agent=None, tool="Edit", key="file_path", env=None, **payload):
        who = {"agent_type": agent} if agent else {}
        return self.run_hook("tool", {"tool_name": tool, "tool_input": {key: str(path)}, **who, **payload}, env)

    def frozen_denial(self, done):
        self.assertIn("sdlc-gate: [tests]", self.reason(done))

    def refused(self, done, why):
        self.assertIn(why, self.context(done))
        self.assertFalse(self.approved.exists())
        self.assertTrue(self.lock.is_file())

    def tamper(self, tests):
        record = json.loads(self.approved.read_text())
        record["tests"] = tests
        self.approved.write_text(json.dumps(record))


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


class EditTest(FrozenGateTest):
    """After approval only qa-engineer edits a frozen test with a file tool."""

    def test_a_builder_cannot_edit_a_frozen_test(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))

    def test_the_main_session_cannot_edit_a_frozen_test(self):
        self.approve_frozen()
        self.assertIn("this call came from the main session", self.reason(self.edit_as(self.frozen)))

    def test_a_read_only_planner_cannot_edit_a_frozen_test(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, "sdlc:tech-lead"))

    def test_an_agent_whose_name_only_starts_like_qa_is_denied(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, "sdlc:qa-engineer-helper"))

    def test_write_is_denied_like_edit(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER, tool="Write"))

    def test_a_notebook_edit_is_denied_like_edit(self):
        self.approve_frozen("tests/repro.ipynb")
        done = self.edit_as(self.project / "tests" / "repro.ipynb", BUILDER, tool="NotebookEdit", key="notebook_path")
        self.frozen_denial(done)

    def test_qa_engineer_can_edit_a_frozen_test(self):
        self.approve_frozen()
        self.assertEqual(self.edit_as(self.frozen, QA).stdout, "")

    def test_qa_engineer_without_a_plugin_prefix_can_edit(self):
        self.approve_frozen()
        self.assertEqual(self.edit_as(self.frozen, "qa-engineer").stdout, "")

    def test_the_payload_shape_the_host_sends_for_a_subagent_is_allowed(self):
        self.approve_frozen()
        done = self.edit_as(self.frozen, QA, agent_id="a1b2c3", hook_event_name="PreToolUse", tool_use_id="toolu_1")
        self.assertEqual(done.stdout, "")

    def test_a_builder_can_edit_a_file_that_is_not_frozen(self):
        self.approve_frozen()
        self.assertEqual(self.edit_as(self.project / "src" / "money.py", BUILDER).stdout, "")

    def test_a_relative_path_is_the_same_file(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as("tests/test_bug.py", BUILDER))

    def test_another_case_of_the_name_is_the_same_file(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.project / "TESTS" / "Test_Bug.py", BUILDER))

    def test_multi_edit_is_denied_like_edit(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER, tool="MultiEdit"))

    def test_the_real_folder_behind_a_frozen_name_that_became_a_symlink_is_covered(self):
        self.approve_frozen()
        (self.project / "spec").mkdir()
        (self.project / "tests").symlink_to(self.project / "spec")
        self.frozen_denial(self.edit_as(self.project / "spec" / "test_bug.py", BUILDER))

    def test_a_symlinked_folder_made_later_that_leads_to_a_frozen_test_is_covered(self):
        (self.project / "spec").mkdir()
        self.approve_frozen("spec/test_bug.py")
        (self.project / "tests").symlink_to(self.project / "spec")
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))

    def test_a_frozen_name_that_later_leaves_the_project_through_a_symlink_is_covered(self):
        self.approve_frozen()
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.project / "tests").symlink_to(outside)
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))

    def test_a_frozen_name_that_later_leads_into_the_runs_folder_is_covered(self):
        self.approve_frozen()
        (self.project / "tests").symlink_to(self.plan.parent)
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))

    def test_an_alias_made_later_for_a_frozen_test_is_covered(self):
        self.approve_frozen()
        self.frozen.parent.mkdir()
        self.frozen.write_text("def test_bug(): assert False\n")
        (self.project / "alias.py").symlink_to(self.frozen)
        self.frozen_denial(self.edit_as(self.project / "alias.py", BUILDER))

    def test_the_denial_names_the_way_to_change_a_frozen_test(self):
        self.approve_frozen()
        reason = self.reason(self.edit_as(self.frozen, BUILDER))
        self.assertIn("amended plan.md and the owner's `approve plan`", reason)
        self.assertIn("sdlc off", reason)

    def test_a_denial_is_logged_with_the_caller(self):
        self.approve_frozen()
        self.edit_as(self.frozen, BUILDER)
        self.assertRegex(self.log.read_text(), r'deny-tests [^\n]*prompt="agent=backend-developer ')

    def test_a_denial_of_the_main_session_is_logged_as_main(self):
        self.approve_frozen()
        self.edit_as(self.frozen)
        self.assertRegex(self.log.read_text(), r'deny-tests [^\n]*prompt="agent=main ')

    def test_sdlc_off_releases_the_freeze(self):
        self.approve_frozen()
        self.frozen_denial(self.edit_as(self.frozen, BUILDER))
        self.prompt("sdlc off")
        self.assertEqual(self.edit_as(self.frozen, BUILDER).stdout, "")


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
