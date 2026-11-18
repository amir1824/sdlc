"""Tests for edits to the frozen tests, by agent and by path.

Run: python3 -I -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support.frozen_base import BUILDER, FrozenGateTest, QA
from support.paths import HOOKS

sys.path.append(str(HOOKS))
from sdlc_hooks.plan import frozen_tests  # noqa: E402


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

    def test_a_hard_link_made_later_for_a_frozen_test_is_the_same_file(self):
        self.approve_frozen()
        self.frozen.parent.mkdir()
        self.frozen.write_text("def test_bug(): assert False\n")
        os.link(self.frozen, self.project / "alias.py")
        self.frozen_denial(self.edit_as(self.project / "alias.py", BUILDER))

    def test_a_hard_link_made_outside_the_project_is_the_same_file(self):
        self.approve_frozen()
        self.frozen.parent.mkdir()
        self.frozen.write_text("def test_bug(): assert False\n")
        os.link(self.frozen, self.tmp / "outside.py")
        self.frozen_denial(self.edit_as(self.tmp / "outside.py", BUILDER))

    def test_a_record_that_cannot_be_read_does_not_gate_a_file_outside_the_project(self):
        self.approve_frozen()
        self.tamper({"paths": [7]})
        self.assertEqual(self.edit_as(self.tmp / "elsewhere.py", BUILDER).stdout, "")

    def test_a_file_that_only_has_the_same_text_as_a_frozen_test_stays_editable(self):
        self.approve_frozen()
        self.frozen.parent.mkdir()
        self.frozen.write_text("def test_bug(): assert False\n")
        (self.project / "copy.py").write_text("def test_bug(): assert False\n")
        self.assertEqual(self.edit_as(self.project / "copy.py", BUILDER).stdout, "")

    def test_a_frozen_test_that_does_not_exist_yet_leaves_every_other_edit_alone(self):
        self.approve_frozen()
        (self.project / "copy.py").write_text("x = 1\n")
        self.assertEqual(self.edit_as(self.project / "copy.py", BUILDER).stdout, "")

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


class FileIdTest(unittest.TestCase):
    def test_two_names_of_one_file_have_the_same_id(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder, "a.py")
            first.write_text("x = 1\n")
            os.link(first, Path(folder, "b.py"))
            self.assertEqual(frozen_tests.file_id(first), frozen_tests.file_id(Path(folder, "b.py")))

    def test_a_path_that_cannot_be_stat_ed_has_no_id(self):
        with mock.patch.object(frozen_tests.os, "stat", side_effect=PermissionError("no")):
            self.assertIsNone(frozen_tests.file_id(Path("/anywhere/a.py")))

    def test_a_file_whose_inode_is_zero_has_no_id(self):
        with mock.patch.object(frozen_tests.os, "stat", return_value=mock.Mock(st_dev=3, st_ino=0)):
            self.assertIsNone(frozen_tests.file_id(Path("/anywhere/a.py")))

    def test_a_file_that_does_not_exist_has_no_id(self):
        self.assertIsNone(frozen_tests.file_id(Path("/no/such/file.py")))


if __name__ == "__main__":
    unittest.main()
