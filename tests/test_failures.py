"""Tests for scripts/failures.py, run on synthetic `.sdlc/<slug>/retro.md` files.

Run: python3 -I -m unittest discover -s tests
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "failures.py"
COMMAND = REPO / "plugins" / "sdlc" / "commands" / "sdlc.md"

HEADER = ("| Tag | Stage | Agent | Root cause | Evidence | Resolution |\n"
          "|---|---|---|---|---|---|\n")


def row(tag="missing-call-sites", stage="Verify", agent="backend-developer",
        cause="incomplete-impact-analysis", evidence="review.md F2", resolution="fixed"):
    return f"| {tag} | {stage} | {agent} | {cause} | {evidence} | {resolution} |\n"


def retro(*rows, heading="## Failures"):
    return f"# retro\n\n## Failed a gate\nx\n\n{heading}\n\n{HEADER}{''.join(rows)}"


class FailuresTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def put(self, project, slug, text):
        path = self.root / project / ".sdlc" / slug / "retro.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_script(self, *args, roots=None, cwd=None):
        roots = [str(self.root)] if roots is None else roots
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args, *roots],
                              capture_output=True, text=True, timeout=20, cwd=cwd)

    def test_one_failure_in_one_task_counts_once(self):
        self.put("app", "task-a", retro(row()))
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("1x  missing-call-sites  backend-developer", out.stdout)

    def test_the_same_failure_twice_in_one_task_counts_once(self):
        self.put("app", "task-a", retro(row(evidence="review.md F2"), row(evidence="test_orders failed")))
        self.assertIn("1x  missing-call-sites  backend-developer", self.run_script().stdout)

    def test_the_same_failure_in_three_tasks_counts_three(self):
        self.put("app", "task-a", retro(row()))
        self.put("app", "task-b", retro(row()))
        self.put("app", "task-c", retro(row()))
        self.assertIn("3x  missing-call-sites  backend-developer", self.run_script().stdout)

    def test_the_same_slug_in_two_projects_is_two_tasks(self):
        self.put("one", "task-a", retro(row()))
        self.put("two", "task-a", retro(row()))
        self.assertIn("2x  missing-call-sites  backend-developer", self.run_script().stdout)

    def test_the_same_tag_for_two_agents_is_two_lines(self):
        self.put("app", "task-a", retro(row(), row(agent="frontend-developer")))
        out = self.run_script().stdout
        self.assertIn("1x  missing-call-sites  backend-developer", out)
        self.assertIn("1x  missing-call-sites  frontend-developer", out)

    def test_each_task_and_its_evidence_are_listed_under_the_line(self):
        self.put("app", "task-a", retro(row(evidence="review.md F2")))
        self.assertIn("  app/task-a: review.md F2", self.run_script().stdout)

    def test_an_unknown_tag_is_a_problem_and_is_not_counted(self):
        self.put("app", "task-a", retro(row(tag="made-up-tag")))
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("PROBLEM app/task-a: made-up-tag is not in the tag list", out.stdout)
        self.assertNotIn("1x  made-up-tag", out.stdout)

    def test_a_row_with_too_few_cells_is_a_problem(self):
        self.put("app", "task-a", retro("| missing-call-sites | Verify | backend-developer |\n"))
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("PROBLEM app/task-a: a row needs 6 cells", out.stdout)

    def test_the_line_none_means_no_failures(self):
        self.put("app", "task-a", "# retro\n\n## Failures\n\nnone\n")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("1 with a Failures table", out.stdout)

    def test_a_retro_without_the_section_is_counted_as_having_no_table(self):
        self.put("app", "task-a", "# retro\n\n## Failed a gate\nx\n")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("1 read, 0 with a Failures table", out.stdout)

    def test_backticks_and_case_around_the_tag_are_ignored(self):
        self.put("app", "task-a", retro(row(tag="`Missing-Call-Sites`", agent="`backend-developer`")))
        self.assertIn("1x  missing-call-sites  backend-developer", self.run_script().stdout)

    def test_a_table_under_another_heading_is_not_read(self):
        self.put("app", "task-a", retro(row(), heading="## Cost us time"))
        self.assertNotIn("missing-call-sites", self.run_script().stdout)

    def test_rows_after_the_next_heading_are_not_read(self):
        text = retro(row()) + "\n## Teach the agent\n" + row(tag="test-gap")
        self.put("app", "task-a", text)
        self.assertNotIn("test-gap", self.run_script().stdout)

    def test_min_hides_the_failures_seen_in_fewer_tasks(self):
        self.put("app", "task-a", retro(row(), row(tag="test-gap")))
        self.put("app", "task-b", retro(row()))
        out = self.run_script("--min", "2").stdout
        self.assertIn("2x  missing-call-sites", out)
        self.assertNotIn("test-gap", out)

    def test_min_still_shows_problems(self):
        self.put("app", "task-a", retro(row(tag="made-up-tag")))
        self.assertIn("PROBLEM", self.run_script("--min", "5").stdout)

    def test_the_same_folder_given_twice_counts_once(self):
        self.put("app", "task-a", retro(row()))
        out = self.run_script(roots=[str(self.root), str(self.root / "app")])
        self.assertIn("1x  missing-call-sites", out.stdout)

    def test_a_folder_reached_through_a_symlink_counts_once(self):
        self.put("app", "task-a", retro(row()))
        link = self.root.parent / (self.root.name + "-link")
        link.symlink_to(self.root)
        self.addCleanup(link.unlink)
        out = self.run_script(roots=[str(self.root), str(link)])
        self.assertIn("1x  missing-call-sites", out.stdout)

    def test_a_symlink_loop_does_not_hang(self):
        self.put("app", "task-a", retro(row()))
        (self.root / "app" / "loop").symlink_to(self.root)
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_node_modules_and_git_are_skipped(self):
        self.put("app/node_modules/pkg", "task-a", retro(row()))
        self.put("app/.git/x", "task-b", retro(row()))
        self.assertIn("0 read", self.run_script().stdout)

    def test_a_retro_outside_a_sdlc_task_folder_is_ignored(self):
        path = self.root / "docs" / "retro.md"
        path.parent.mkdir()
        path.write_text(retro(row()))
        self.assertIn("0 read", self.run_script().stdout)

    def test_a_retro_that_is_not_utf8_is_a_problem_and_the_rest_still_count(self):
        bad = self.put("app", "task-a", "x")
        bad.write_bytes(b"\xff\xfe\x00")
        self.put("app", "task-b", retro(row()))
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("PROBLEM app/task-a:", out.stdout)
        self.assertIn("1x  missing-call-sites", out.stdout)

    def test_windows_line_endings_are_read(self):
        self.put("app", "task-a", retro(row()).replace("\n", "\r\n"))
        self.assertIn("1x  missing-call-sites", self.run_script().stdout)

    def test_no_retros_at_all_is_not_an_error(self):
        out = self.run_script()
        self.assertEqual(out.returncode, 0)
        self.assertIn("0 read", out.stdout)

    def test_a_root_that_does_not_exist_is_an_error(self):
        out = self.run_script(roots=[str(self.root / "nope")])
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_row_indented_by_spaces_is_read(self):
        self.put("app", "task-a", retro("  " + row()))
        self.assertIn("1x  missing-call-sites", self.run_script().stdout)

    def test_a_row_inside_a_blockquote_is_a_problem(self):
        self.put("app", "task-a", retro("> " + row()))
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("PROBLEM app/task-a: a table row must start with |", out.stdout)

    def test_a_row_inside_a_list_item_is_a_problem(self):
        self.put("app", "task-a", retro("- " + row()))
        self.assertEqual(self.run_script().returncode, 1)

    def test_a_failures_heading_inside_a_code_fence_is_not_a_section(self):
        text = "# retro\n\n## Cost us time\n\n```\n## Failures\n" + row() + "```\n"
        self.put("app", "task-a", text)
        out = self.run_script()
        self.assertNotIn("missing-call-sites", out.stdout)
        self.assertIn("0 with a Failures table", out.stdout)

    def test_a_heading_inside_a_code_fence_does_not_end_the_section(self):
        self.put("app", "task-a", retro("```\n## example\n```\n", row()))
        self.assertIn("1x  missing-call-sites", self.run_script().stdout)

    def test_an_empty_agent_cell_is_a_problem(self):
        self.put("app", "task-a", retro(row(agent="")))
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("a row needs an Agent and Evidence", out.stdout)

    def test_an_empty_evidence_cell_is_a_problem(self):
        self.put("app", "task-a", retro(row(evidence="")))
        self.assertEqual(self.run_script().returncode, 1)

    def test_an_all_empty_row_is_a_problem(self):
        self.put("app", "task-a", retro("| | | | | | |\n"))
        self.assertEqual(self.run_script().returncode, 1)

    def test_an_escaped_pipe_in_a_cell_is_part_of_the_cell(self):
        self.put("app", "task-a", retro(row(evidence=r"review.md F2 \| F3")))
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("app/task-a: review.md F2 | F3", out.stdout)

    def test_a_byte_order_mark_before_the_heading_is_ignored(self):
        path = self.put("app", "task-a", "x")
        path.write_bytes(b"\xef\xbb\xbf" + retro(row()).encode())
        self.assertIn("1x  missing-call-sites", self.run_script().stdout)

    def test_a_heading_with_a_suffix_still_opens_the_section(self):
        self.put("app", "task-a", retro(row(), heading="## Failures (draft)"))
        self.assertIn("1x  missing-call-sites", self.run_script().stdout)

    def test_a_top_level_heading_ends_the_section(self):
        self.put("app", "task-a", retro(row()) + "\n# Other\n" + row(tag="test-gap"))
        self.assertNotIn("test-gap", self.run_script().stdout)

    def test_a_separator_unicode_line_break_inside_a_row_does_not_split_it(self):
        self.put("app", "task-a", retro(row(evidence="review.md F2")))
        self.assertEqual(self.run_script().returncode, 0)

    def test_the_label_names_the_project_when_the_folder_is_dot(self):
        self.put("app", "task-a", retro(row()))
        out = self.run_script(roots=["."], cwd=self.root / "app")
        self.assertIn("  app/task-a:", out.stdout)

    def test_two_projects_with_the_same_name_get_distinguishable_labels(self):
        self.put("a/app", "task-a", retro(row()))
        self.put("b/app", "task-a", retro(row()))
        out = self.run_script().stdout
        self.assertIn("  a/app/task-a:", out)
        self.assertIn("  b/app/task-a:", out)

    def test_a_retro_over_the_size_limit_is_a_problem(self):
        path = self.put("app", "task-a", "x")
        path.write_bytes(b"x" * 1_000_001)
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("PROBLEM app/task-a: larger than 1 MB", out.stdout)

    def test_a_dangling_retro_symlink_is_a_problem(self):
        path = self.put("app", "task-a", "x")
        path.unlink()
        path.symlink_to(self.root / "missing.md")
        self.assertEqual(self.run_script().returncode, 1)

    def test_a_retro_that_is_a_named_pipe_is_a_problem_and_does_not_block(self):
        path = self.put("app", "task-a", "x")
        path.unlink()
        os.mkfifo(path)
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertIn("not a regular file", out.stdout)

    def test_a_folder_argument_that_is_a_file_is_an_error(self):
        plain = self.root / "plain.txt"
        plain.write_text("x")
        self.assertEqual(self.run_script(roots=[str(plain)]).returncode, 2)

    def test_a_sdlc_folder_that_is_a_symlink_is_not_followed(self):
        real = self.root / "elsewhere" / "task-a"
        real.mkdir(parents=True)
        (real / "retro.md").write_text(retro(row()))
        (self.root / "app").mkdir()
        (self.root / "app" / ".sdlc").symlink_to(self.root / "elsewhere")
        self.assertIn("0 read", self.run_script(roots=[str(self.root / "app")]).stdout)

    def test_the_most_repeated_failure_comes_first(self):
        self.put("app", "task-a", retro(row(tag="test-gap")))
        self.put("app", "task-b", retro(row(tag="test-gap"), row()))
        self.put("app", "task-c", retro(row(tag="test-gap")))
        self.assertTrue(self.run_script().stdout.startswith("3x  test-gap"))


class TagListTest(unittest.TestCase):
    def tags(self):
        out = subprocess.run([sys.executable, "-I", str(SCRIPT), "--tags"], capture_output=True, text=True,
                             timeout=20)
        return out.stdout.split()

    def test_the_tag_list_ends_with_other(self):
        self.assertEqual(self.tags()[-1], "other")

    def test_the_sdlc_command_lists_exactly_these_tags_in_this_order(self):
        sentence = COMMAND.read_text(encoding="utf-8").split("Tag is one of:")[1].split("Stage is")[0]
        self.assertEqual(tuple(re.findall(r"`([a-z-]+)`", sentence)), tuple(self.tags()))

    def test_the_sdlc_command_states_the_table_columns(self):
        self.assertIn("| Tag | Stage | Agent | Root cause | Evidence | Resolution |",
                      COMMAND.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
