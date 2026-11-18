"""Tests for the `Evidence:` line a `fix:` commit needs, judged from the command.

Run: python3 -I -m unittest discover -s tests
"""
import unittest

from support.gate_base import GateTest


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


if __name__ == "__main__":
    unittest.main()
