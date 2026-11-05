"""Regression tests for the gaps a code review found in the Bash write check (0.4.0)."""
import unittest

from test_sdlc_gate import GateTest

DENIED = "is read-only"


class HeredocBodyTest(GateTest):
    def test_a_body_piped_to_a_shell_is_read_as_commands(self):
        done = self.bash("cat <<'EOF' | sh\nrm -rf src\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_a_shell_with_an_option_fed_a_heredoc_is_denied(self):
        done = self.bash("bash -s <<'EOF'\nrm -rf src\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_an_interpreter_with_an_option_fed_a_heredoc_is_denied(self):
        done = self.bash("python3 -u <<'EOF'\nimport os\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_a_quoted_heredoc_marker_does_not_hide_the_next_line(self):
        done = self.bash("echo '<<X'\nrm -rf src", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_a_shell_with_a_word_argument_fed_a_heredoc_is_denied(self):
        done = self.bash("bash -s foo <<EOF\nrm -rf src\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_sourcing_stdin_fed_a_heredoc_is_denied(self):
        done = self.bash("source /dev/stdin <<EOF\nrm -rf src\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_dash_fed_a_heredoc_is_denied(self):
        done = self.bash("dash <<EOF\nrm -rf src\nEOF", agent_type="brutal-reviewer")
        self.assertIn(DENIED, self.reason(done))

    def test_a_plain_heredoc_body_is_still_text(self):
        done = self.bash("cat <<'EOF'\nrm -rf src is how it is removed\nEOF", agent_type="brutal-reviewer")
        self.assertEqual((done.returncode, done.stdout), (0, ""))


class LockedBypassTest(GateTest):
    def test_a_redirect_through_dot_dot_out_of_tmp_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("echo x > /tmp/../Users/me/app.py")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_a_redirect_inside_tmp_is_allowed_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("echo x > /tmp/out.log")
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_a_quoted_dot_dot_in_a_tmp_redirect_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("echo x > /tmp/'..'/Users/me/app.py")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_a_variable_in_a_tmp_redirect_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        done = self.bash("echo x > /tmp/$DIR/app.py")
        self.assertIn("has not approved the plan", self.reason(done))

    def test_an_assignment_before_rm_is_denied_while_locked(self):
        self.prompt("/sdlc add a slug helper")
        self.assertIn("has not approved the plan", self.reason(self.bash("FOO=1 rm -rf src")))


class StateStatementTest(GateTest):
    STATE = "gate's state belongs to the owner"

    def test_a_delete_after_and_and_is_denied_without_a_lock(self):
        self.assertIn(self.STATE, self.reason(self.bash("ls && rm ~/.claude/sdlc-gate/s1.approved")))

    def test_a_delete_after_a_semicolon_and_a_space_is_denied_without_a_lock(self):
        self.assertIn(self.STATE, self.reason(self.bash("ls; rm ~/.claude/sdlc-gate/s1.approved")))

    def test_a_delete_after_a_commit_is_denied_without_a_lock(self):
        done = self.bash("git commit -m 'docs: x' ; rm ~/.claude/sdlc-gate/s1.approved")
        self.assertIn(self.STATE, self.reason(done))

    def test_a_touch_whose_flag_ends_in_m_is_still_a_write_to_the_state(self):
        self.assertIn(self.STATE, self.reason(self.bash("touch -m ~/.claude/sdlc-gate/s1.approved")))


class CommitMessageStateTest(GateTest):
    def test_a_commit_with_combined_flags_that_quotes_the_state_folder_is_allowed(self):
        done = self.bash("git commit -am 'docs: ~/.claude/sdlc-gate'")
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_a_commit_with_an_unquoted_message_that_names_the_state_folder_is_allowed(self):
        done = self.bash("git commit -m docs:~/.claude/sdlc-gate")
        self.assertEqual((done.returncode, done.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
