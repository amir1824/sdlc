"""Tests for the Bash side of the Snyk close gate: a command that names a status.md is denied while Snyk is required,
and a command that types the owner's words is denied in every project. Run through plugins/sdlc/hooks/sdlc_gate.py
as Claude Code runs it.

Run: python3 -I -m unittest discover -s tests
The check is on the name: a path built at run time, or a script that writes the file without naming it, is not seen.
"""
import unittest

from support.snyk_base import GATE_TAG, SnykCloseTest

STATUS = ".sdlc/feature/status.md"
OWNER_OFF = "sdlc snyk" + " off"  # spelled apart: this file is itself written through the gate
OWNER_ON = "sdlc snyk" + " on"


class BashTest(SnykCloseTest):
    def bash_denied(self, command):
        return GATE_TAG in self.bash(command).stdout


class WritesToStatusTest(BashTest):
    def setUp(self):
        super().setUp()
        self.snyk_on_and_approved()

    def test_a_redirect_into_status_md_is_denied(self):
        self.assertTrue(self.bash_denied(f"echo closed >> {STATUS}"))

    def test_the_denial_points_to_read_grep_and_write(self):
        self.assertIn("Read or Grep and write it with Write", self.reason(self.bash(f"echo closed >> {STATUS}")))

    def test_a_status_md_in_another_case_is_denied(self):
        self.assertTrue(self.bash_denied("echo closed >> .sdlc/feature/Status.md"))

    def test_a_one_line_python_write_is_denied(self):
        self.assertTrue(self.bash_denied(f"python3 -c \"import os; open('{STATUS}','a').write('closed')\""))

    def test_a_one_line_node_write_is_denied(self):
        self.assertTrue(self.bash_denied(f"node -e \"const fs=require('fs'); fs.appendFileSync('{STATUS}','x')\""))

    def test_a_python_write_in_several_lines_is_denied(self):
        self.assertTrue(self.bash_denied(f"python3 -c \"\nopen('{STATUS}','a').write('closed')\n\""))

    def test_a_node_write_in_several_lines_is_denied(self):
        self.assertTrue(self.bash_denied(f"node -e '\nrequire(\"fs\").appendFileSync(\"{STATUS}\",\"x\")\n'"))

    def test_a_python_heredoc_that_names_it_is_denied(self):
        self.assertTrue(self.bash_denied(f"python3 - <<'EOF'\nopen('{STATUS}','a').write('closed')\nEOF"))

    def test_git_show_redirected_into_it_is_denied(self):
        self.assertTrue(self.bash_denied(f"git show HEAD:{STATUS} > {STATUS}"))

    def test_git_checkout_of_it_from_a_commit_is_denied(self):
        self.assertTrue(self.bash_denied(f"git checkout HEAD~1 -- {STATUS}"))

    def test_a_pipe_into_tee_after_git_add_is_denied(self):
        self.assertTrue(self.bash_denied(f"git add a | tee {STATUS}"))

    def test_a_write_after_a_background_ampersand_is_denied(self):
        self.assertTrue(self.bash_denied(f"git add . & echo closed >> {STATUS}"))

    def test_a_commit_message_that_runs_a_write_is_denied(self):
        self.assertTrue(self.bash_denied(f'git commit -m "$(echo closed > {STATUS})"'))

    def test_a_command_that_only_reads_it_is_denied_too(self):
        self.assertTrue(self.bash_denied(f"cat {STATUS}"))

    def test_git_add_of_it_is_denied_too(self):
        self.assertTrue(self.bash_denied(f"git add {STATUS}"))

    def test_a_commit_message_that_names_it_is_denied_too(self):
        self.assertTrue(self.bash_denied('git commit -m "docs: say what status.md holds"'))

    def test_the_denial_says_how_to_commit_without_the_name(self):
        self.assertIn("git commit -F", self.reason(self.bash('git commit -m "docs: status.md"')))


class WritesToTheRecordTest(BashTest):
    def setUp(self):
        super().setUp()
        self.snyk_on_and_approved()

    def test_a_removal_of_the_record_from_a_folder_it_changed_into_is_denied(self):
        self.assertTrue(self.bash_denied("cd ~/.claude && rm -r sdlc-gate/snyk"))

    def test_the_denial_says_how_to_commit_a_message_that_names_the_folder(self):
        self.assertIn("git commit -F", self.reason(self.bash('git commit -m "fix: sdlc-gate"')))

    def test_a_read_of_the_gates_folder_is_allowed(self):
        self.assertFalse(self.bash_denied("ls ~/.claude/sdlc-gate"))

    def test_a_denial_of_a_bash_command_is_logged_with_its_start(self):
        self.bash(f"echo closed >> {STATUS}")
        log = (self.home / "sdlc-gate" / "approvals.log").read_text()
        self.assertIn(f'deny-snyk session=s1 cwd="{self.project}" prompt="echo closed >> {STATUS}"', log)


class WhatStaysAllowedTest(BashTest):
    def setUp(self):
        super().setUp()
        self.snyk_on_and_approved()

    def test_git_add_of_the_run_folder_is_allowed(self):
        self.assertFalse(self.bash_denied("git add .sdlc"))

    def test_a_commit_that_reads_its_message_from_a_file_is_allowed(self):
        self.assertFalse(self.bash_denied("git commit -F msg.txt"))

    def test_a_test_run_that_writes_its_output_into_the_run_folder_is_allowed(self):
        self.assertFalse(self.bash_denied("python3 -m unittest > .sdlc/feature/runs/t.txt"))

    def test_a_write_elsewhere_in_a_command_that_does_not_name_it_is_allowed(self):
        self.assertFalse(self.bash_denied("echo hi > /tmp/x; ls"))

    def test_a_search_for_the_owners_words_without_a_verb_is_allowed(self):
        self.assertFalse(self.bash_denied("grep -rn 'sdlc snyk' ."))


class SnykOffTest(BashTest):
    def test_a_write_to_status_md_is_allowed_with_snyk_off(self):
        self.prompt(OWNER_OFF)
        self.locked_and_approved()
        self.assertFalse(self.bash_denied(f"echo closed >> {self.status}"))

    def test_a_write_to_status_md_is_allowed_while_snyk_is_undecided(self):
        self.locked_and_approved()
        self.assertFalse(self.bash_denied(f"echo closed >> {self.status}"))


class OwnerWordsTest(BashTest):
    def test_a_child_claude_that_types_them_is_denied_with_snyk_on(self):
        self.prompt(OWNER_ON)
        self.assertTrue(self.bash_denied(f"claude -p '{OWNER_OFF}'"))

    def test_the_same_command_is_denied_while_snyk_is_undecided(self):
        self.assertTrue(self.bash_denied(f"claude -p '{OWNER_ON}'"))

    def test_the_same_command_is_denied_with_snyk_off(self):
        self.prompt(OWNER_OFF)
        self.assertTrue(self.bash_denied(f"claude -p '{OWNER_ON}'"))

    def test_accept_and_waive_are_denied_too(self):
        accept, waive = "echo sdlc snyk" + " accept F1 ok", "echo sdlc snyk" + " waive x"
        self.assertEqual((self.bash_denied(accept), self.bash_denied(waive)), (True, True))

    def test_the_denial_tells_how_to_search_for_the_words(self):
        self.assertIn("a pattern that stops before the verb", self.reason(self.bash(f"echo {OWNER_ON}")))


if __name__ == "__main__":
    unittest.main()
