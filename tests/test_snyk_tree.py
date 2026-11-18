"""Tests for plugins/sdlc/hooks/snyk/tree.py: the hash of the code a scan saw, the files that differ from a base
commit, and the budget that keeps both inside the hook's timeout. They run real git repositories.

Run: python3 -I -m unittest discover -s tests
"""
import importlib.util
import itertools
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "plugins" / "sdlc" / "hooks"
SPEC = importlib.util.spec_from_file_location("snyk_tree", HOOKS / "snyk" / "tree.py")
tree = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tree)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "project"
        self.root.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()


class GitRepoTest(TempDirTest):
    def git(self, *args):
        subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=n", *args], cwd=self.root, check=True,
                       capture_output=True)

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        (self.root / "a.py").write_text("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "first")


class TreeHashTest(GitRepoTest):
    def test_the_same_code_gives_the_same_hash(self):
        self.assertEqual(tree.tree_hash(self.root), tree.tree_hash(self.root))

    def test_an_edit_to_a_tracked_file_changes_it(self):
        before = tree.tree_hash(self.root)
        (self.root / "a.py").write_text("x = 2\n")
        self.assertNotEqual(tree.tree_hash(self.root), before)

    def test_a_new_untracked_file_changes_it(self):
        before = tree.tree_hash(self.root)
        (self.root / "b.py").write_text("y = 1\n")
        self.assertNotEqual(tree.tree_hash(self.root), before)

    def test_an_edit_inside_the_run_folder_does_not(self):
        (self.root / ".sdlc" / "x").mkdir(parents=True)
        before = tree.tree_hash(self.root)
        (self.root / ".sdlc" / "x" / "status.md").write_text("run: x\n")
        self.assertEqual(tree.tree_hash(self.root), before)

    def test_a_folder_that_is_not_a_git_repo_has_no_hash_and_says_why(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "git rev-parse failed"):
            tree.tree_hash(self.home)

    def test_a_symlink_to_a_device_that_never_ends_is_hashed_as_a_link_and_does_not_hang(self):
        (self.root / "pad.bin").symlink_to("/dev/zero")
        self.assertIsNotNone(tree.tree_hash(self.root))

    def test_a_changed_symlink_target_changes_the_hash(self):
        (self.root / "pad.bin").symlink_to("/dev/zero")
        before = tree.tree_hash(self.root)
        (self.root / "pad.bin").unlink()
        (self.root / "pad.bin").symlink_to("/dev/null")
        self.assertNotEqual(tree.tree_hash(self.root), before)

    def test_a_budget_that_is_spent_gives_no_hash_and_says_why(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "time budget spent"):
            tree.tree_hash(self.root, tree.Budget(0))

    def test_a_budget_that_runs_out_after_git_while_links_are_hashed_gives_no_hash(self):
        (self.root / "pad.bin").symlink_to("/dev/zero")
        with mock.patch.object(tree.Budget, "seconds_left", side_effect=itertools.chain([5.0] * 3, itertools.repeat(0.0))):
            with self.assertRaisesRegex(tree.TreeUnavailable, "while hashing"):
                tree.tree_hash(self.root)

    def test_untracked_files_over_the_byte_limit_give_no_hash(self):
        (self.root / "big.bin").write_bytes(b"x" * 100)
        with self.assertRaisesRegex(tree.TreeUnavailable, "while hashing"):
            tree.tree_hash(self.root, tree.Budget(5, max_bytes=10))

    def test_untracked_files_within_the_byte_limit_are_hashed(self):
        (self.root / "small.bin").write_bytes(b"x" * 5)
        self.assertIsNotNone(tree.tree_hash(self.root, tree.Budget(5, max_bytes=10)))


class ChangedFilesTest(GitRepoTest):
    def head(self):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_nothing_changed_lists_nothing(self):
        self.assertEqual(tree.changed_files(self.root, self.head()), [])

    def test_an_edited_tracked_file_is_listed(self):
        (self.root / "a.py").write_text("x = 2\n")
        self.assertEqual(tree.changed_files(self.root, self.head()), ["a.py"])

    def test_an_untracked_file_is_listed(self):
        (self.root / "b.py").write_text("y = 1\n")
        self.assertEqual(tree.changed_files(self.root, self.head()), ["b.py"])

    def test_a_deleted_file_is_listed(self):
        (self.root / "a.py").unlink()
        self.assertEqual(tree.changed_files(self.root, self.head()), ["a.py"])

    def test_a_renamed_file_is_listed_under_both_names(self):
        self.git("mv", "a.py", "c.py")
        self.assertEqual(tree.changed_files(self.root, self.head()), ["a.py", "c.py"])

    def test_the_run_folder_is_left_out(self):
        (self.root / ".sdlc" / "x").mkdir(parents=True)
        (self.root / ".sdlc" / "x" / "status.md").write_text("run: x\n")
        self.assertEqual(tree.changed_files(self.root, self.head()), [])

    def test_a_base_that_is_not_a_hash_is_refused(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "no base commit"):
            tree.changed_files(self.root, "HEAD")

    def test_a_base_that_is_not_a_commit_is_refused(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "git diff failed"):
            tree.changed_files(self.root, "0" * 40)

    def test_a_base_that_is_not_text_is_refused(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "no base commit"):
            tree.changed_files(self.root, None)

    def test_a_spent_budget_is_refused(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "time budget spent"):
            tree.changed_files(self.root, self.head(), tree.Budget(0))


class HeadCommitTest(GitRepoTest):
    def test_the_head_of_a_repo_is_a_commit_hash(self):
        self.assertRegex(tree.head_commit(self.root), tree.COMMIT_HASH.pattern)

    def test_a_folder_that_is_not_a_repo_has_no_head(self):
        with self.assertRaisesRegex(tree.TreeUnavailable, "git rev-parse failed"):
            tree.head_commit(self.home)


class CollectTest(GitRepoTest):
    def head(self):
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_the_facts_hold_the_changed_files_and_the_hash(self):
        (self.root / "a.py").write_text("x = 2\n")
        changed, code, notes = tree.collect(self.root, self.head(), tree.new_budget())
        self.assertEqual((changed, code == tree.tree_hash(self.root), notes), (["a.py"], True, ()))

    def test_a_missing_base_leaves_the_files_unknown_and_says_why(self):
        changed, code, notes = tree.collect(self.root, None, tree.new_budget())
        self.assertEqual((changed, code is None, notes), (None, False, ("changed files: no base commit is pinned",)))

    def test_a_folder_that_is_not_a_repo_says_why_for_both(self):
        changed, code, notes = tree.collect(self.home, "0" * 40, tree.new_budget())
        self.assertEqual((changed, code, len(notes)), (None, None, 2))


class ProjectBelowTheRepoTest(GitRepoTest):
    def setUp(self):
        super().setUp()
        self.project = self.root / "service"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src" / "a.py").write_text("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "second")
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True,
                                   check=True).stdout.strip()

    def test_a_tracked_edit_is_listed_relative_to_the_project(self):
        (self.project / "src" / "a.py").write_text("x = 2\n")
        self.assertEqual(tree.changed_files(self.project, self.base), ["src/a.py"])

    def test_a_new_file_is_listed_relative_to_the_project(self):
        (self.project / "src" / "b.py").write_text("y = 1\n")
        self.assertEqual(tree.changed_files(self.project, self.base), ["src/b.py"])

    def test_an_edit_outside_the_project_is_not_listed(self):
        (self.root / "a.py").write_text("x = 9\n")
        self.assertEqual(tree.changed_files(self.project, self.base), [])


if __name__ == "__main__":
    unittest.main()
