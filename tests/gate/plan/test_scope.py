"""Tests for the frozen scope of an approved plan: which files an edit may touch.

Run: python3 -I -m unittest discover -s tests
"""
import json
import sys
import unittest

from support.gate_base import GateTest


class ScopeTest(GateTest):
    """Approval bound to a set of paths: the plan's `sdlc-scope` block, frozen when the owner approves."""

    def setUp(self):
        super().setUp()
        self.approved = self.home / "sdlc-gate" / "s1.approved"
        self.log = self.home / "sdlc-gate" / "approvals.log"

    def block(self, body):
        return "# Plan\n\n## Scope\n```sdlc-scope\n" + body + "\n```\n"

    def scoped(self, *globs, plan=None):
        (plan or self.plan).write_text(self.block("\n".join(globs)))

    def approve_scoped(self, *globs):
        self.scoped(*globs)
        self.locked_and_approved()

    def second_plan(self, slug, *globs):
        plan = self.project / ".sdlc" / slug / "plan.md"
        plan.parent.mkdir()
        self.scoped(*globs, plan=plan)

    def refuses(self, plan_text, needle):
        self.plan.write_text(plan_text)
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertTrue(self.lock.is_file())
        self.assertFalse(self.approved.exists())
        self.assertIn(needle, self.context(done))

    def denied(self, done):
        self.assertIn("outside the approved scope", self.reason(done))

    def test_edit_inside_the_scope_is_allowed(self):
        self.approve_scoped("src/**", "tests/**")
        self.assertEqual(self.edit(self.project / "src" / "a" / "b.py").stdout, "")

    def test_edit_outside_the_scope_is_denied_with_the_way_forward(self):
        self.approve_scoped("src/**")
        reason = self.reason(self.edit(self.project / "docs" / "guide.md"))
        self.assertIn("docs/guide.md is outside the approved scope", reason)
        self.assertIn("approve plan", reason)

    def test_a_notebook_outside_the_scope_is_denied(self):
        self.approve_scoped("src/**")
        self.denied(self.edit(self.project / "a.ipynb", tool="NotebookEdit", key="notebook_path"))

    def test_handoff_files_stay_writable_under_a_scope(self):
        self.approve_scoped("src/**")
        self.assertEqual(self.edit(self.project / ".sdlc" / "feature" / "build.md").stdout, "")

    def test_the_agents_own_settings_are_outside_a_scope(self):
        self.approve_scoped("src/**")
        self.denied(self.edit(self.project / ".claude" / "settings.json"))

    def test_a_plan_without_a_scope_block_is_not_path_limited(self):
        self.locked_and_approved()
        self.assertEqual(self.edit(self.project / "anything" / "x.py").stdout, "")

    def test_an_unscoped_record_has_no_scope_key(self):
        self.locked_and_approved()
        self.assertNotIn("scope", json.loads(self.approved.read_text()))

    def test_the_approval_says_when_a_plan_has_no_scope(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertIn("not limited to a set of paths", self.context(done))
        self.assertIn("scope=none", self.log.read_text())

    def test_the_approval_echoes_the_scope_it_froze(self):
        self.scoped("src/**", "tests/**")
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertIn("src/**, tests/**", self.context(done))
        self.assertIn("scope=2", self.log.read_text())

    def test_the_record_holds_the_frozen_patterns(self):
        self.approve_scoped("src/**")
        self.assertEqual(json.loads(self.approved.read_text())["scope"],
                         {"plan": ".sdlc/feature/plan.md", "globs": ["src/**"]})

    def test_changing_the_scope_locks_and_reapproval_refreezes(self):
        self.approve_scoped("src/**")
        self.scoped("docs/**")
        self.assertIn("changed after the owner approved it", self.reason(self.edit(self.project / "docs" / "a.md")))
        self.prompt("approve plan")
        self.assertEqual(self.edit(self.project / "docs" / "a.md").stdout, "")
        self.denied(self.edit(self.project / "src" / "a.py"))

    def test_square_brackets_in_a_path_are_literal(self):
        self.approve_scoped("app/users/[id]/**")
        self.assertEqual(self.edit(self.project / "app" / "users" / "[id]" / "page.tsx").stdout, "")

    def test_a_bracket_class_does_not_match_a_neighbour(self):
        self.approve_scoped("app/users/[id]/**")
        self.denied(self.edit(self.project / "app" / "users" / "i" / "page.tsx"))

    def test_a_dotdot_path_is_resolved_before_matching(self):
        self.approve_scoped("src/**")
        self.denied(self.edit(str(self.project / "src" / ".." / "secrets.py")))

    def test_a_symlink_that_leaves_the_project_is_denied(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src" / "link").symlink_to(outside)
        self.approve_scoped("src/**")
        done = self.edit(self.project / "src" / "link" / "x.py")
        self.assertIn("resolves outside the project", self.reason(done))

    @unittest.skipUnless(sys.platform == "darwin", "the macOS default filesystem ignores case")
    def test_another_path_case_still_matches_the_scope(self):
        self.approve_scoped("src/**")
        self.assertEqual(self.edit(str(self.project / "SRC" / "a.py")).stdout, "")

    def test_a_hostile_file_name_is_matched_in_bounded_time(self):
        self.approve_scoped("src/" + "a*" * 40 + "b")
        self.denied(self.edit(self.project / "src" / ("a" * 200)))

    def test_a_wildcard_scope_cannot_reach_the_claude_folder(self):
        self.approve_scoped("**/*.py")
        self.denied(self.edit(self.project / ".claude" / "hooks" / "guard.py"))

    def test_a_wildcard_scope_still_covers_normal_code(self):
        self.approve_scoped("**/*.py")
        self.assertEqual(self.edit(self.project / "src" / "a.py").stdout, "")

    def test_a_leading_wildcard_that_matches_the_claude_folder_is_refused(self):
        self.refuses(self.block(".c*/**"), ".git or .claude")

    def test_a_record_that_is_not_an_object_denies_instead_of_crashing(self):
        self.approve_scoped("src/**")
        self.approved.write_text("[]")
        done = self.edit(self.project / "docs" / "a.md")
        self.assertEqual(done.returncode, 0)
        self.assertIn("unreadable", self.reason(done))

    def test_a_record_whose_plans_is_not_a_map_denies_instead_of_crashing(self):
        self.approve_scoped("src/**")
        record = json.loads(self.approved.read_text())
        record["plans"] = []
        self.approved.write_text(json.dumps(record))
        done = self.edit(self.project / "docs" / "a.md")
        self.assertEqual(done.returncode, 0)
        self.assertIn("unreadable", self.reason(done))

    def test_a_symlinked_project_dir_still_catches_a_symlink_escape(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src" / "link").symlink_to(outside)
        alias = self.tmp / "alias"
        alias.symlink_to(self.project)
        self.approve_scoped("src/**")
        done = self.edit(self.project.resolve() / "src" / "link" / "x.py", env={"CLAUDE_PROJECT_DIR": str(alias)})
        self.assertIn("resolves outside the project", self.reason(done))

    def test_two_unscoped_plans_are_approved_without_a_name(self):
        older = self.project / ".sdlc" / "older" / "plan.md"
        older.parent.mkdir()
        older.write_text("# An older plan\n")
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan")
        self.assertFalse(self.lock.exists())

    def test_a_full_stop_after_a_name_is_punctuation(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan feature.")
        self.assertFalse(self.lock.exists())

    def test_a_near_miss_fence_is_refused(self):
        self.refuses("# Plan\n~~~sdlc-scope\nsrc/**\n~~~\n", "not the exact fence")

    def test_prose_that_mentions_the_block_is_not_a_fence(self):
        self.plan.write_text("# Plan\nThe sdlc-scope block lists the files.\n")
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan")
        self.assertFalse(self.lock.exists())

    def relative_edit(self, path, cwd):
        return self.run_hook("tool", {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": str(cwd)})

    def unreadable(self, done):
        self.assertEqual(done.returncode, 0)
        self.assertIn("could not check this path", self.reason(done))

    def test_a_nul_path_is_denied_while_a_scope_is_frozen(self):
        self.approve_scoped("src/**")
        self.unreadable(self.edit(str(self.project / "src") + "/\0/../config.py"))

    def test_a_lone_surrogate_path_is_denied_while_a_scope_is_frozen(self):
        self.approve_scoped("src/**")
        self.unreadable(self.edit(str(self.project / "src") + "/\ud800/../config.py"))

    def test_a_non_text_path_is_denied_while_the_session_is_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.unreadable(self.run_hook("tool", {"tool_name": "Edit", "tool_input": {"file_path": 123}}))

    def test_a_path_the_gate_cannot_read_fails_open_when_no_run_is_on(self):
        done = self.edit(str(self.project) + "/a\0b.py")
        self.assertNotIn(done.returncode, (0, 2))
        self.assertEqual(done.stdout, "")

    def test_a_relative_path_is_resolved_against_the_session_cwd(self):
        self.approve_scoped("src/**")
        self.denied(self.relative_edit("src/a.py", self.project / "docs"))

    def test_a_relative_path_inside_the_scope_is_allowed(self):
        self.approve_scoped("src/**")
        self.assertEqual(self.relative_edit("src/a.py", self.project).stdout, "")

    def test_a_relative_path_is_gated_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.relative_edit("text.py", self.project)
        self.assertIn("has not approved the plan", self.reason(done))

    def test_a_notebook_edit_is_checked_on_both_path_keys(self):
        self.approve_scoped("src/**")
        done = self.run_hook("tool", {"tool_name": "NotebookEdit", "tool_input": {
            "file_path": str(self.project / "src" / "a.py"),
            "notebook_path": str(self.project / "config.ipynb")}})
        self.denied(done)

    def test_the_mcp_config_is_never_covered(self):
        self.approve_scoped("**/*.json")
        self.denied(self.edit(self.project / ".mcp.json"))

    def test_a_nested_claude_folder_is_never_covered(self):
        self.approve_scoped("**/*.py")
        self.denied(self.edit(self.project / "pkg" / ".claude" / "x.py"))

    def test_patterns_that_are_narrow_alone_but_cover_the_tree_together_are_refused(self):
        self.refuses(self.block("a*/**\ns*/**\nd*/**"), "together")

    def test_a_line_separator_inside_an_entry_is_refused(self):
        self.refuses(self.block("src/**\x0bevil/**"), "invisible")

    def test_an_example_fence_around_the_block_is_refused(self):
        self.refuses("# Plan\n````md\n```sdlc-scope\nsrc/**\n```\n````\n", "inside another code fence")

    def test_an_indented_fence_is_refused(self):
        self.refuses("# Plan\n    ```sdlc-scope\n    src/**\n    ```\n", "not the exact fence")

    def test_the_approval_also_reaches_the_owner(self):
        self.scoped("src/**", "tests/**")
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertIn("Edits are limited to 2 pattern(s)", json.loads(done.stdout)["systemMessage"])

    def test_a_tool_input_that_is_not_an_object_is_denied_while_the_session_is_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.unreadable(self.run_hook("tool", {"tool_name": "Edit", "tool_input": "x"}))

    def test_a_wildcard_first_segment_is_accepted(self):
        self.approve_scoped("*/index.ts")
        self.assertEqual(self.edit(self.project / "pkg" / "index.ts").stdout, "")

    def test_a_near_miss_fence_in_one_of_two_plans_asks_for_a_name(self):
        self.plan.write_text("# Plan\n~~~sdlc-scope\nsrc/**\n~~~\n")
        older = self.project / ".sdlc" / "older" / "plan.md"
        older.parent.mkdir()
        older.write_text("# An older plan\n")
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertTrue(self.lock.is_file())
        self.assertIn("approve plan <folder>", self.context(done))

    def test_an_absolute_entry_is_refused(self):
        self.refuses(self.block("/etc/**"), "absolute")

    def test_a_dotdot_entry_is_refused(self):
        self.refuses(self.block("../other/**"), "`..`")

    def test_a_trailing_slash_is_refused(self):
        self.refuses(self.block("src/"), "empty")

    def test_a_backslash_is_refused(self):
        self.refuses(self.block("src\\a"), "backslash")

    def test_match_everything_is_refused(self):
        self.refuses(self.block("**"), "nearly every file")

    def test_a_near_match_everything_is_refused(self):
        self.refuses(self.block("*/**"), "nearly every file")

    def test_reaching_the_git_folder_is_refused(self):
        self.refuses(self.block(".git/**"), ".git or .claude")

    def test_reaching_the_claude_folder_is_refused(self):
        self.refuses(self.block(".claude/**"), ".git or .claude")

    def test_a_protected_folder_below_the_top_level_is_refused(self):
        self.refuses(self.block("src/.claude/**"), ".git or .claude")

    def test_a_folder_that_only_starts_like_a_protected_name_is_allowed(self):
        self.approve_scoped("src/.github/**")
        self.assertEqual(self.edit(self.project / "src" / ".github" / "ci.yml").stdout, "")

    def test_a_failed_log_write_leaves_the_lock_on_and_records_no_approval(self):
        self.scoped("src/**")
        self.prompt("/sdlc add a slug helper")
        self.log.unlink(missing_ok=True)
        self.log.mkdir()
        self.prompt("approve plan")
        self.assertTrue(self.lock.is_file())
        self.assertFalse(self.approved.exists())

    def test_an_empty_block_is_refused(self):
        self.refuses(self.block("# nothing yet"), "block is empty")

    def test_two_blocks_are_refused(self):
        self.refuses(self.block("src/**") + self.block("docs/**"), "more than one")

    def test_an_unclosed_block_is_refused(self):
        self.refuses("# Plan\n```sdlc-scope\nsrc/**\n", "is not closed")

    def test_too_many_entries_are_refused(self):
        self.refuses(self.block("\n".join(["src/**"] * 101)), "more than 100")

    def test_two_plans_need_a_name(self):
        self.second_plan("older", "docs/**")
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan")
        self.assertTrue(self.lock.is_file())
        self.assertIn("approve plan <folder>", self.context(done))

    def test_a_named_approval_scopes_only_that_plan(self):
        self.scoped("src/**")
        self.second_plan("older", "docs/**")
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan feature")
        self.assertEqual(self.edit(self.project / "src" / "a.py").stdout, "")
        self.denied(self.edit(self.project / "docs" / "a.md"))

    def test_the_other_plans_stay_hash_bound_after_a_named_approval(self):
        self.scoped("src/**")
        self.second_plan("older", "docs/**")
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan feature")
        (self.project / ".sdlc" / "older" / "plan.md").write_text("# rewritten\n")
        self.assertIn(".sdlc/older/plan.md changed", self.reason(self.edit(self.project / "src" / "a.py")))

    def test_a_name_is_accepted_when_one_plan_exists(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan feature")
        self.assertFalse(self.lock.exists())

    def test_an_unknown_name_is_refused(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("approve plan nope")
        self.assertTrue(self.lock.is_file())
        self.assertIn("no plan named `nope`", self.context(done))

    def test_a_corrupt_scope_in_the_record_denies_instead_of_crashing(self):
        self.approve_scoped("src/**")
        record = json.loads(self.approved.read_text())
        record["scope"]["globs"] = "src/**"
        self.approved.write_text(json.dumps(record))
        done = self.edit(self.project / "src" / "a.py")
        self.assertEqual(done.returncode, 0)
        self.assertIn("SDLC_GATE_SCOPE=off", self.reason(done))

    def test_a_non_text_pattern_in_the_record_denies_instead_of_crashing(self):
        self.approve_scoped("src/**")
        record = json.loads(self.approved.read_text())
        record["scope"]["globs"] = [1]
        self.approved.write_text(json.dumps(record))
        done = self.edit(self.project / "src" / "a.py")
        self.assertIn("SDLC_GATE_SCOPE=off", self.reason(done))

    def test_the_scope_switch_lets_an_outside_edit_through(self):
        self.approve_scoped("src/**")
        done = self.edit(self.project / "docs" / "a.md", env={"SDLC_GATE_SCOPE": "off"})
        self.assertEqual(done.stdout, "")

    def test_the_scope_switch_does_not_lift_the_plan_lock(self):
        self.prompt("/sdlc add a slug helper")
        done = self.edit(self.project / "a.py", env={"SDLC_GATE_SCOPE": "off"})
        self.assertIn("has not approved the plan", self.reason(done))

    def test_a_scope_denial_is_logged(self):
        self.approve_scoped("src/**")
        self.edit(self.project / "docs" / "a.md")
        self.assertIn("deny-scope", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
