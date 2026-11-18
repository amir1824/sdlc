"""Tests for the file-tool checks of the `tool` mode: the lock and the approved plan.

Run: python3 -I -m unittest discover -s tests
"""
import sys
import unittest

from support.gate_base import GateTest


class FileEditTest(GateTest):
    def test_locked_session_cannot_edit_project_code(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / "text.py")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_locked_session_cannot_edit_a_notebook(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / "a.ipynb", tool="NotebookEdit", key="notebook_path")
        self.assertIn("has not approved the plan", self.reason(done))

    @unittest.skipUnless(sys.platform == "darwin", "the macOS default filesystem ignores case")
    def test_locked_session_cannot_edit_code_through_another_path_case(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(str(self.project / "text.py").upper())
        self.assertIn("has not approved the plan", self.reason(done))

    def test_locked_session_can_write_handoff_files(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / ".sdlc" / "feature" / "prd.md")
        self.assertEqual(done.stdout, "")

    def test_locked_session_cannot_hide_code_in_a_nested_sdlc_folder(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / "src" / ".sdlc" / "app.py")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_locked_session_can_write_outside_the_project(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.tmp / "scratch" / "notes.md")
        self.assertEqual(done.stdout, "")

    def test_session_without_sdlc_edits_freely(self):
        done = self.edit(self.project / "text.py")
        self.assertEqual(done.stdout, "")

    def test_approved_session_edits_code(self):
        self.locked_and_approved()
        done = self.edit(self.project / "text.py")
        self.assertEqual(done.stdout, "")

    def test_plan_changed_after_approval_locks_again(self):
        self.locked_and_approved()
        self.plan.write_text("# Plan v2: a new requirement\n")
        done = self.edit(self.project / "text.py")
        self.assertIn(".sdlc/feature/plan.md changed after the owner approved it", self.reason(done))

    def test_plan_added_after_approval_locks_again(self):
        self.locked_and_approved()
        second = self.project / ".sdlc" / "second" / "plan.md"
        second.parent.mkdir()
        second.write_text("# A plan nobody approved\n")
        done = self.edit(self.project / "text.py")
        self.assertIn(".sdlc/second/plan.md changed after the owner approved it", self.reason(done))

    def test_plan_deleted_after_approval_locks_again(self):
        self.locked_and_approved()
        self.plan.unlink()
        done = self.edit(self.project / "text.py")
        self.assertIn("changed after the owner approved it", self.reason(done))

    def test_unreadable_plan_after_approval_locks_again(self):
        self.locked_and_approved()
        self.plan.chmod(0)
        self.addCleanup(self.plan.chmod, 0o644)
        done = self.edit(self.project / "text.py")
        self.assertIn("unreadable", self.reason(done))

    def test_reapproval_after_a_plan_change_unlocks(self):
        self.locked_and_approved()
        self.plan.write_text("# Plan v2: a new requirement\n")
        self.prompt("approve plan")
        done = self.edit(self.project / "text.py")
        self.assertEqual(done.stdout, "")

    def test_gate_state_cannot_be_written_with_the_file_tools(self):
        done = self.edit(self.home / "sdlc-gate" / "s1.approved", tool="Write")
        self.assertIn("belongs to the owner", self.reason(done))

    def test_kill_switch_lets_a_locked_edit_through(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / "text.py", env={"SDLC_GATE": "off"})
        self.assertEqual(done.stdout, "")


if __name__ == "__main__":
    unittest.main()
