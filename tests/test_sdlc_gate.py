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

    def test_hebrew_approval_unlocks(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("אשר תוכנית")
        self.assertFalse(self.lock.exists())

    def test_approval_with_a_full_stop_unlocks(self):
        self.prompt("/sdlc add a slug helper")
        self.prompt("Approve plan.")
        self.assertFalse(self.lock.exists())

    def test_interpreted_go_ahead_does_not_unlock(self):
        self.prompt("/sdlc add a slug helper")
        done = self.prompt("תן בראש על המשימה")
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
