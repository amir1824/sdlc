"""Tests for plugins/sdlc/hooks/sdlc_gate.py, run as Claude Code runs it: JSON on stdin.

Run: python3 -I -m unittest discover -s tests (also under the oldest python3 you support).
These feed the hook the documented input shape, so they prove the gate's logic, not what the
host sends. SDLC_GATE_TRACE=1 records what the host sends, to check that part in a real session.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "plugins" / "sdlc" / "hooks"
SCRIPT = HOOKS / "sdlc_gate.py"


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        self.plan = self.project / ".sdlc" / "feature" / "plan.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text("# Plan v1\n")
        (self.home / "rules").mkdir(parents=True)
        (self.home / "rules" / "sdlc.md").write_text("rules\n")
        self.lock = self.home / "sdlc-gate" / "s1.locked"

    def run_raw(self, mode, stdin, env=None):
        full_env = {**os.environ, "SDLC_GATE": "", "SDLC_GATE_HOME": str(self.home),
                    "CLAUDE_PROJECT_DIR": str(self.project), **(env or {})}
        return subprocess.run([sys.executable, "-I", str(SCRIPT), mode], input=stdin,
                              capture_output=True, text=True, env=full_env, timeout=5)

    def run_hook(self, mode, payload, env=None):
        data = {"session_id": "s1", "cwd": str(self.project), **payload}
        return self.run_raw(mode, json.dumps(data), env)

    def prompt(self, text, **payload):
        return self.run_hook("prompt", {"prompt": text, **payload})

    def edit(self, path, env=None, tool="Edit", key="file_path"):
        return self.run_hook("tool", {"tool_name": tool, "tool_input": {key: str(path)}}, env)

    def bash(self, command, **payload):
        return self.run_hook("tool", {"tool_name": "Bash", "tool_input": {"command": command}, **payload})

    def locked_and_approved(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("approve plan")

    def reason(self, done):
        return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

    def context(self, done):
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


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


class CommitTest(GateTest):
    def test_fix_commit_without_evidence_is_denied(self):
        done = self.bash('git commit -m "fix: guard the empty title"')
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_in_a_heredoc_with_evidence_is_allowed(self):
        done = self.bash("git commit -m \"$(cat <<'EOF'\nfix: guard the empty title\n\n"
                         "Evidence: test_empty_title failed before the change\nEOF\n)\"")
        self.assertEqual(done.stdout, "")

    def test_fix_commit_in_a_heredoc_without_evidence_is_denied(self):
        done = self.bash("git commit -m \"$(cat <<'EOF'\nfix: guard the empty title\nEOF\n)\"")
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_with_evidence_in_a_second_message_is_allowed(self):
        done = self.bash('git -C repo commit -m "fix(api): guard" -m "Evidence: api.log:12"')
        self.assertEqual(done.stdout, "")

    def test_fix_commit_from_stdin_heredoc_with_evidence_is_allowed(self):
        done = self.bash("git commit -F - <<'EOF'\nfix: guard\n\nEvidence: api.log:12\nEOF")
        self.assertEqual(done.stdout, "")

    def test_fix_commit_from_a_message_file_without_evidence_is_denied(self):
        (self.project / "msg.txt").write_text("fix: guard the empty title\n\nNo proof here.\n")
        done = self.bash("git commit -F msg.txt")
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_from_a_message_file_after_cd_without_evidence_is_denied(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "msg.txt").write_text("fix: guard the empty title\n")
        done = self.bash("cd sub && git commit -F msg.txt")
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_from_a_message_file_through_git_c_without_evidence_is_denied(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "msg.txt").write_text("fix: guard the empty title\n")
        done = self.bash("git -C sub commit -F msg.txt")
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_from_a_message_file_after_cd_with_evidence_is_allowed(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "msg.txt").write_text("fix: guard\n\nEvidence: api.log:12\n")
        done = self.bash("cd sub && git commit -F msg.txt")
        self.assertEqual(done.stdout, "")

    def test_an_unreadable_message_file_with_no_fix_in_the_command_is_allowed(self):
        done = self.bash("git commit -F missing.txt")
        self.assertEqual(done.stdout, "")

    def test_a_command_that_only_mentions_a_commit_is_allowed(self):
        done = self.bash("grep -n 'git commit -F msg.txt' README.md")
        self.assertEqual(done.stdout, "")

    def test_a_piped_fix_message_without_evidence_is_denied(self):
        done = self.bash("printf 'fix: guard' | git commit -F -")
        self.assertIn("Evidence:", self.reason(done))

    def test_a_piped_fix_message_with_evidence_is_allowed(self):
        done = self.bash("printf 'fix: guard\\n\\nEvidence: api.log:12' | git commit -F -")
        self.assertEqual(done.stdout, "")

    def test_a_fix_message_file_written_in_the_same_command_is_checked(self):
        done = self.bash("printf 'fix: guard' > m.txt && git commit -F m.txt")
        self.assertIn("Evidence:", self.reason(done))

    def test_a_fix_heredoc_piped_into_a_commit_without_evidence_is_denied(self):
        done = self.bash("cat <<'EOF' | git commit -F -\nfix: guard\nEOF")
        self.assertIn("Evidence:", self.reason(done))

    def test_a_fix_body_that_mentions_git_commit_before_its_evidence_is_allowed(self):
        done = self.bash("git commit -F - <<EOF\nfix: stop the double write\n\nthe hook ran\n"
                         "git commit twice in one turn\n\nEvidence: api.log:12\nEOF")
        self.assertEqual(done.stdout, "")

    def test_a_fix_word_elsewhere_in_the_command_does_not_count(self):
        done = self.bash('git log --grep="fix:" --oneline; git commit -F -')
        self.assertEqual(done.stdout, "")

    def test_a_commit_mentioned_in_a_pr_body_heredoc_is_not_checked(self):
        done = self.bash('gh pr create --title "fix: x" --body "$(cat <<EOF\nrun\ngit commit -F msg\nEOF\n)"')
        self.assertEqual(done.stdout, "")

    def test_evidence_of_another_commit_does_not_cover_a_piped_fix(self):
        done = self.bash('git commit -m "fix: a" -m "Evidence: l:1" && printf "fix: b" | git commit -F -')
        self.assertIn("Evidence:", self.reason(done))

    def test_a_cd_inside_quotes_does_not_move_the_message_file(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "m.txt").write_text("fix: guard\n")
        (self.project / "m.txt").write_text("chore: tidy\n")
        done = self.bash('echo "; cd sub" && git commit -F m.txt')
        self.assertEqual(done.stdout, "")

    def test_many_commits_in_one_command_are_answered_before_the_hook_timeout(self):
        done = self.bash("git commit -F -;" * 6000)
        self.assertIn("too many to check", self.reason(done))

    def test_a_long_unterminated_heredoc_header_is_answered_before_the_hook_timeout(self):
        done = self.bash('git commit -m "chore: tidy"; cat <<' + "A" * 150000)
        self.assertEqual(done.stdout, "")

    def test_many_heredoc_heads_on_one_line_are_answered_before_the_hook_timeout(self):
        done = self.bash("git commit -F -; " + "<<A " * 75000)
        self.assertEqual(done.stdout, "")

    def test_an_empty_heredoc_does_not_hide_a_later_fix_commit(self):
        done = self.bash('cat <<EOF\nEOF\ngit commit -m "fix: guard"')
        self.assertIn("Evidence:", self.reason(done))

    def test_a_shift_does_not_start_a_heredoc(self):
        done = self.bash('echo $((1 << 3))\ngit commit -m "fix: guard"')
        self.assertIn("Evidence:", self.reason(done))

    def test_a_continued_pipe_into_a_commit_is_checked(self):
        done = self.bash('printf "fix: guard" \\\n| git commit -F -')
        self.assertIn("Evidence:", self.reason(done))

    def test_a_cd_inside_a_heredoc_body_does_not_move_the_message_file(self):
        (self.project / "sub").mkdir()
        (self.project / "sub" / "m.txt").write_text("fix: guard\n")
        (self.project / "m.txt").write_text("chore: tidy\n")
        done = self.bash("cat > notes <<EOF\nx\ncd sub\nEOF\ngit commit -F m.txt")
        self.assertEqual(done.stdout, "")

    def test_a_long_run_of_fix_parens_is_answered_before_the_hook_timeout(self):
        done = self.bash("printf '" + "fix(" * 60000 + "' | git commit -F -")
        self.assertEqual(done.stdout, "")

    def test_a_second_fix_commit_in_one_command_is_checked(self):
        done = self.bash('git commit -m "chore: tidy" && git commit --amend -m "fix: guard"')
        self.assertIn("Evidence:", self.reason(done))

    def test_evidence_inside_the_subject_does_not_count(self):
        done = self.bash('git commit -m "fix: show the Evidence: column"')
        self.assertIn("Evidence:", self.reason(done))

    def test_empty_evidence_line_does_not_count(self):
        done = self.bash('git commit -m "fix: guard" -m "Evidence:"')
        self.assertIn("Evidence:", self.reason(done))

    def test_evidence_in_a_shell_comment_does_not_count(self):
        done = self.bash('git commit -m "fix: guard" # Evidence: trust me')
        self.assertIn("Evidence:", self.reason(done))

    def test_capitalised_fix_without_evidence_is_denied(self):
        done = self.bash('git commit -m "Fix: guard"')
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_behind_an_env_prefix_is_denied(self):
        done = self.bash('GIT_AUTHOR_NAME=a git --no-pager commit -m "fix: guard"')
        self.assertIn("Evidence:", self.reason(done))

    def test_fix_commit_through_a_binary_path_and_sh_c_is_denied(self):
        done = self.bash("sh -c \"/usr/bin/git -C '/a b' commit -m 'fix: guard'\"")
        self.assertIn("Evidence:", self.reason(done))

    def test_feat_commit_mentioning_a_fix_is_allowed(self):
        done = self.bash('git commit -m "feat: add slugify" -m "fix: typo in docs"')
        self.assertEqual(done.stdout, "")

    def test_amend_without_a_message_is_allowed(self):
        done = self.bash("git commit --amend --no-edit")
        self.assertEqual(done.stdout, "")

    def test_fix_commit_with_escaped_or_tripled_quotes_is_denied(self):
        escaped = self.bash('bash -c "git commit -m \\"fix: guard\\""')
        tripled = self.bash('git commit -m """fix: guard"""')
        self.assertIn("Evidence:", self.reason(escaped))
        self.assertIn("Evidence:", self.reason(tripled))

    def test_many_assignment_lines_before_a_fix_commit_are_answered(self):
        done = self.bash("a=b\n" * 20_000 + ";\ngit commit -m 'fix: guard'")
        self.assertIn("Evidence:", self.reason(done))

    def test_a_long_run_of_quotes_is_answered_before_the_hook_timeout(self):
        done = self.bash("'" * 150_000)
        self.assertEqual(done.stdout, "")


class ReadOnlyAgentTest(GateTest):
    def test_redirect_into_a_file_is_denied(self):
        done = self.bash("git diff > review.txt", agent_type="security-reviewer")
        self.assertIn("security-reviewer is read-only", self.reason(done))

    def test_rm_is_denied(self):
        done = self.bash("ls && rm -rf build", agent_type="sdlc:brutal-reviewer")
        self.assertIn("brutal-reviewer is read-only", self.reason(done))

    def test_rm_through_a_binary_path_is_denied(self):
        done = self.bash("/bin/rm -rf src", agent_type="tech-lead")
        self.assertIn("tech-lead is read-only", self.reason(done))

    def test_a_write_inside_sh_c_is_denied(self):
        done = self.bash('sh -c "echo x > f"', agent_type="analyst")
        self.assertIn("analyst is read-only", self.reason(done))

    def test_find_delete_is_denied(self):
        done = self.bash("find . -name '*.pyc' -delete", agent_type="leak-scanner")
        self.assertIn("leak-scanner is read-only", self.reason(done))

    def test_deleting_a_branch_is_denied(self):
        done = self.bash("git branch -D old", agent_type="tech-lead")
        self.assertIn("tech-lead is read-only", self.reason(done))

    def test_creating_a_branch_is_denied(self):
        done = self.bash("git branch review-notes", agent_type="brutal-reviewer")
        self.assertIn("brutal-reviewer is read-only", self.reason(done))

    def test_copying_a_branch_is_denied(self):
        done = self.bash("git branch -c main main-copy", agent_type="brutal-reviewer")
        self.assertIn("brutal-reviewer is read-only", self.reason(done))

    def test_listing_branches_is_allowed(self):
        done = self.bash("git branch -a && git branch --merged main --contains abc123", agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_perl_in_place_edit_is_denied(self):
        done = self.bash("perl -pi -e 's/a/b/' f.txt", agent_type="tech-lead")
        self.assertIn("tech-lead is read-only", self.reason(done))

    def test_a_long_separator_chain_is_answered_before_the_hook_timeout(self):
        done = self.bash("; sed a" * 2_000, agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_a_long_run_of_blank_lines_is_answered_and_still_denies_rm(self):
        done = self.bash("\n" * 8_000 + "x\nrm y", agent_type="tech-lead")
        self.assertIn("tech-lead is read-only", self.reason(done))

    def test_rm_behind_time_or_a_backslash_is_denied(self):
        done = self.bash("time \\rm -rf build", agent_type="tech-lead")
        self.assertIn("tech-lead is read-only", self.reason(done))

    def test_listing_tags_is_allowed_and_creating_one_is_denied(self):
        listing = self.bash("git tag && git tag --contains HEAD", agent_type="tech-lead")
        creating = self.bash("git tag v1.0", agent_type="tech-lead")
        self.assertEqual(listing.stdout, "")
        self.assertIn("tech-lead is read-only", self.reason(creating))

    def test_a_command_too_long_to_check_is_denied(self):
        done = self.bash("echo " + "7" * 20_000, agent_type="tech-lead")
        self.assertIn("too long to check", self.reason(done))

    def test_grep_for_an_arrow_and_dropping_errors_is_allowed(self):
        done = self.bash("grep -rn '=>' src 2>/dev/null | head", agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_merge_base_and_stash_list_are_allowed(self):
        done = self.bash("git merge-base main HEAD && git stash list", agent_type="security-reviewer")
        self.assertEqual(done.stdout, "")

    def test_a_builder_agent_can_redirect(self):
        done = self.bash("git diff > review.txt", agent_type="backend-developer")
        self.assertEqual(done.stdout, "")


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


class FailureTest(GateTest):
    def test_malformed_input_fails_open(self):
        done = self.run_raw("tool", "not json")
        self.assertNotIn(done.returncode, (0, 2))
        self.assertEqual(done.stdout, "")

    def test_unknown_mode_fails_open(self):
        done = self.run_hook("sideways", {})
        self.assertNotIn(done.returncode, (0, 2))

    def test_trace_records_the_agent_the_host_sent(self):
        self.run_hook("tool", {"tool_name": "Bash", "tool_input": {"command": "ls"},
                               "agent_type": "qa-engineer"}, env={"SDLC_GATE_TRACE": "1"})
        line = json.loads((self.home / "sdlc-gate" / "trace.log").read_text())
        self.assertEqual(line["agent_type"], "qa-engineer")

    def test_hooks_json_points_at_this_script(self):
        hooks = json.loads((HOOKS / "hooks.json").read_text())["hooks"]
        commands = [hooks["UserPromptSubmit"][0]["hooks"][0]["command"],
                    hooks["PreToolUse"][0]["hooks"][0]["command"]]
        self.assertEqual(commands, ['python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" prompt',
                                    'python3 -I "${CLAUDE_PLUGIN_ROOT}/hooks/sdlc_gate.py" tool'])
        self.assertTrue(SCRIPT.is_file())


class LockedBashTest(GateTest):
    """The lock also holds for Bash from any agent, not only for the read-only ones."""

    def test_a_redirect_from_the_main_agent_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("has not approved the plan", self.reason(self.bash("echo x > app.py")))

    def test_a_redirect_from_a_builder_agent_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("echo x > app.py", agent_type="backend-developer")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_the_denial_points_at_the_write_tool_for_handoff_files(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("Write tool", self.reason(self.bash("mkdir -p .sdlc/feature")))

    def test_read_only_commands_still_run_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("git diff --stat 2>&1 | head && grep -rn 'a=>b' src 2>/dev/null")
        self.assertEqual(done.stdout, "")

    def test_a_redirect_is_allowed_once_the_plan_is_approved(self):
        self.locked_and_approved()
        self.assertEqual(self.bash("echo x > app.py").stdout, "")

    def test_a_redirect_is_denied_again_after_the_plan_changes(self):
        self.locked_and_approved()
        self.plan.write_text("# Plan v2\n")
        self.assertIn("changed after the owner approved", self.reason(self.bash("echo x > app.py")))

    def test_a_redirect_is_allowed_in_a_session_that_never_ran_sdlc(self):
        self.assertEqual(self.bash("echo x > app.py").stdout, "")

    def test_a_heredoc_body_is_text_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("gh pr comment 1 --body-file - <<'EOF'\nok -> done, then git checkout -b x\nEOF")
        self.assertEqual(done.stdout, "")

    def test_a_redirect_into_tmp_is_allowed_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.assertEqual(self.bash("echo x > /tmp/scratch.txt && echo y >/dev/stderr").stdout, "")

    def test_a_shell_fed_a_heredoc_is_judged_by_its_head_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("has not approved the plan", self.reason(self.bash("bash <<'EOF'\nrm -rf src\nEOF")))

    def test_a_locked_command_too_long_to_check_is_denied_before_the_hook_times_out(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("python3 -u " * 15_000)
        self.assertIn("too long to check", self.reason(done))

    def test_a_long_separator_chain_is_answered_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("; sed a" * 2_000)
        self.assertEqual(done.stdout, "")


class InterpreterWriteTest(GateTest):
    """Interpreters that take code on the command line write files the denylist could not see."""

    def read_only(self, command):
        return self.reason(self.bash(command, agent_type="tech-lead"))

    def test_python_dash_c_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("python3 -c \"open('f', 'w').write('x')\""))

    def test_python_with_an_option_before_dash_c_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("ls; python3.12 -u -c 'print(1)'"))

    def test_python_fed_a_heredoc_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("python3 <<'EOF'\nprint(1)\nEOF"))

    def test_node_dash_e_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("node -e \"require('fs').writeFileSync('f', 'x')\""))

    def test_ruby_dash_e_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("ruby -e 'File.write(%q(f), %q(x))'"))

    def test_perl_dash_e_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("perl -e 'open F, q(>f)'"))

    def test_php_dash_r_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("php -r 'file_put_contents(\"f\", \"x\");'"))

    def test_an_interpreter_inside_a_command_substitution_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("echo $(python3 -c 'print(1)')"))

    def test_awk_that_prints_into_a_file_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("awk '{print $1 > \"out.txt\"}' in.txt"))

    def test_awk_that_runs_a_command_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("awk 'BEGIN { system(\"touch f\") }'"))

    def test_an_environment_prefix_does_not_hide_the_interpreter(self):
        self.assertIn("tech-lead is read-only", self.read_only("PYTHONPATH=. python3 -c 'print(1)'"))

    def test_sudo_does_not_hide_the_interpreter(self):
        self.assertIn("tech-lead is read-only", self.read_only("sudo python3 -c 'print(1)'"))

    def test_a_loop_body_does_not_hide_the_interpreter(self):
        self.assertIn("tech-lead is read-only", self.read_only("for f in a b; do python3 -c 'print(1)'; done"))

    def test_uv_run_does_not_hide_the_interpreter(self):
        self.assertIn("tech-lead is read-only", self.read_only("uv run python -c 'print(1)'"))

    def test_combined_short_flags_are_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("python3 -Bc 'print(1)'"))
        self.assertIn("tech-lead is read-only", self.read_only("perl -lne 'print' f.txt"))

    def test_node_print_flag_and_long_eval_flag_are_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("node -pe '1 + 1'"))
        self.assertIn("tech-lead is read-only", self.read_only("node --eval='1 + 1'"))

    def test_nodejs_bun_and_deno_inline_code_are_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("nodejs -e 'x'"))
        self.assertIn("tech-lead is read-only", self.read_only("bun -e 'x'"))
        self.assertIn("tech-lead is read-only", self.read_only("deno eval 'x'"))

    def test_gawk_in_place_is_denied(self):
        self.assertIn("tech-lead is read-only", self.read_only("gawk -i inplace '{print}' f.txt"))

    def test_a_shell_fed_a_heredoc_is_denied_for_a_read_only_agent(self):
        self.assertIn("tech-lead is read-only", self.read_only("bash <<'EOF'\nrm -rf src\nEOF"))

    def test_text_in_a_heredoc_body_is_not_judged_for_a_read_only_agent(self):
        done = self.bash("cat <<'EOF'\nrm -rf build && tee out\nEOF", agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_running_a_script_or_a_module_is_allowed(self):
        done = self.bash("python3 -I -m unittest discover && node build.js", agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_awk_that_only_reads_is_allowed(self):
        done = self.bash("awk '$1 >= 5 { print $2 }' in.txt", agent_type="tech-lead")
        self.assertEqual(done.stdout, "")

    def test_a_locked_main_agent_cannot_write_through_python(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("python3 -c \"open('app.py', 'w').write('x')\"")
        self.assertIn("has not approved the plan", self.reason(done))


class GateStateTest(GateTest):
    """Bash may not change the gate's own state, locked or not."""

    def test_deleting_the_lock_file_is_denied(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash(f"rm -f {self.lock}")
        self.assertIn("gate's state belongs to the owner", self.reason(done))

    def test_deleting_the_state_folder_is_denied_even_without_a_lock(self):
        done = self.bash("rm -rf ~/.claude/sdlc-gate")
        self.assertIn("gate's state belongs to the owner", self.reason(done))

    def test_truncating_the_approvals_log_is_denied(self):
        done = self.bash(f": > {self.home}/sdlc-gate/approvals.log")
        self.assertIn("gate's state belongs to the owner", self.reason(done))

    def test_reading_the_state_is_allowed(self):
        done = self.bash("cat ~/.claude/sdlc-gate/approvals.log | tail -3")
        self.assertEqual(done.stdout, "")

    def test_a_commit_that_quotes_the_state_folder_in_its_message_is_allowed(self):
        done = self.bash("git commit -m 'docs: the lock lives in ~/.claude/sdlc-gate/'")
        self.assertEqual(done.stdout, "")

    def test_a_write_in_another_statement_than_the_one_that_names_the_folder_is_allowed(self):
        done = self.bash("echo notes > n.md ; grep -rn .claude/sdlc-gate README.md")
        self.assertEqual(done.stdout, "")

    def test_a_heredoc_that_mentions_the_state_folder_is_allowed(self):
        done = self.bash("cat <<'EOF'\nthe lock lives in ~/.claude/sdlc-gate/ and rm removes it\nEOF")
        self.assertEqual(done.stdout, "")

    def test_deleting_the_folder_through_a_quoted_path_is_denied(self):
        done = self.bash('rm -rf "$HOME/.claude/sdlc-gate"')
        self.assertIn("gate's state belongs to the owner", self.reason(done))


class FailClosedTest(GateTest):
    """A crash of the tool hook denies while the session is gated and lets the action through otherwise."""

    def crash(self):
        return self.run_hook("tool", {"tool_name": "Bash", "tool_input": "not a mapping"})

    def test_a_crash_while_locked_denies(self):
        self.prompt("/sdlc add a slug helper")
        done = self.crash()
        self.assertEqual(done.returncode, 0)
        self.assertIn("the gate failed", self.reason(done))

    def test_a_crash_while_approved_denies(self):
        self.locked_and_approved()
        self.assertIn("the gate failed", self.reason(self.crash()))

    def test_the_denial_names_the_way_out(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("sdlc off", self.reason(self.crash()))

    def test_a_crash_in_a_session_that_never_ran_sdlc_fails_open(self):
        done = self.crash()
        self.assertNotIn(done.returncode, (0, 2))
        self.assertEqual(done.stdout, "")

    def test_a_crash_in_another_session_does_not_deny(self):
        self.prompt("/sdlc add a slug helper")
        done = self.run_hook("tool", {"session_id": "other", "tool_name": "Bash", "tool_input": "x"})
        self.assertEqual(done.stdout, "")

    def test_the_prompt_hook_never_denies_when_it_crashes(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("a file where the state folder should be")
        done = self.run_hook("prompt", {"prompt": "/sdlc add a slug helper"}, env={"SDLC_GATE_HOME": str(blocker)})
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("deny", done.stdout)


if __name__ == "__main__":
    unittest.main()
