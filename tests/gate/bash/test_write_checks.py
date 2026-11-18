"""Tests for the Bash writes the gate denies: from a read-only agent, while the plan is locked, through an interpreter, and to the gate's state.

Run: python3 -I -m unittest discover -s tests
"""
import unittest

from support.gate_base import GateTest


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


if __name__ == "__main__":
    unittest.main()
