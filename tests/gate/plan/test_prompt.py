"""Tests for the `prompt` mode of the sdlc gate: the typed `/sdlc`, `approve plan` and `sdlc off`.

Run: python3 -I -m unittest discover -s tests
"""
import unittest

from support.gate_base import GateTest


class PromptTest(GateTest):
    def test_sdlc_prompt_locks_the_session(self):
        done = self.prompt("/sdlc add a slug helper")
        self.assertTrue(self.lock.is_file())
        self.assertIn("approve plan", self.context(done))

    def test_namespaced_sdlc_prompt_locks_the_session(self):
        self.prompt("/my-agents:sdlc continue the slugify feature")
        self.assertTrue(self.lock.is_file())

    def test_ordinary_prompt_changes_nothing(self):
        done = self.prompt("fix the login bug")
        self.assertFalse(self.lock.exists())
        self.assertEqual(done.stdout, "")

    def test_missing_rules_are_reported_when_a_run_starts(self):
        (self.home / "rules" / "sdlc.md").unlink()
        done = self.prompt("/sdlc add a slug helper")
        self.assertIn("is not installed", self.context(done))

    def test_approve_plan_unlocks_and_logs_the_owners_words(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertFalse(self.lock.exists())
        self.assertIn('prompt="approve plan"', (self.home / "sdlc-gate" / "approvals.log").read_text())
        self.assertIn(".sdlc/feature/plan.md", self.context(done))

    def test_the_former_hebrew_approval_phrase_no_longer_unlocks(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("\u05d0\u05e9\u05e8 \u05ea\u05d5\u05db\u05e0\u05d9\u05ea")
        self.assertTrue(self.lock.is_file())

    def test_approval_with_a_full_stop_unlocks(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("Approve plan.")
        self.assertFalse(self.lock.exists())

    def test_interpreted_go_ahead_does_not_unlock(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("looks good, go for it")
        self.assertTrue(self.lock.is_file())
        self.assertEqual(done.stdout, "")

    def test_approval_with_a_condition_does_not_unlock(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan only if the tests pass")
        self.assertTrue(self.lock.is_file())

    def test_approval_before_any_plan_exists_keeps_the_lock(self):
        self.plan.unlink()
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertTrue(self.lock.is_file())
        self.assertIn("no .sdlc/*/plan.md exists yet", self.context(done))

    def test_approval_in_an_ungated_session_is_ignored(self):
        done = self.prompt("approve plan")
        self.assertFalse((self.home / "sdlc-gate" / "s1.approved").exists())
        self.assertEqual(done.stdout, "")

    def test_sdlc_off_releases_the_session(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("sdlc off")
        self.assertFalse(self.lock.exists())
        self.assertIn(" release ", (self.home / "sdlc-gate" / "approvals.log").read_text())

    def test_slash_sdlc_off_releases_instead_of_locking(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("/sdlc off")
        self.assertFalse(self.lock.exists())

    def test_slash_sdlc_off_in_an_ungated_session_does_not_lock(self):
        self.prompt("/sdlc off")
        self.assertFalse(self.lock.exists())

    def test_unsafe_session_id_writes_no_state(self):
        done = self.prompt("/sdlc add a slug helper", session_id="../escape")
        self.assertEqual(list(self.tmp.rglob("*.locked")), [])
        self.assertEqual(done.stdout, "")

    def test_state_files_are_private_to_the_owner(self):
        self.prompt("/sdlc add a slug helper")
        self.assertEqual(self.lock.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
