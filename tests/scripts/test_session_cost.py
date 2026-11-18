"""Tests for scripts/session_cost.py, run on synthetic Claude Code transcripts.

Run: python3 -I -m unittest discover -s tests
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "session_cost.py"
HEADER = ["session", "messages", "input", "cache_creation", "cache_read", "output", "fresh"]


def assistant(message_id, input_tokens=0, cache_creation=0, cache_read=0, output=0):
    usage = {"input_tokens": input_tokens, "cache_creation_input_tokens": cache_creation,
             "cache_read_input_tokens": cache_read, "output_tokens": output}
    return json.dumps({"type": "assistant", "isSidechain": False, "requestId": f"req_{message_id}",
                       "message": {"id": message_id, "usage": usage}})


DEEPLY_NESTED = '{"a":' * 100000


def usage_record(output, **ids):
    return json.dumps({"type": "assistant", **ids, "message": {"usage": {"output_tokens": output}}})


def write_lines(path, *lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def row(stdout, name):
    return next(line.split() for line in stdout.splitlines() if line.split()[:1] == [name])


def names(stdout):
    return [line.split()[0] for line in stdout.splitlines()[:-1]]


class SessionCostTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.session = self.root / "abc.jsonl"

    def subagent(self, name, *lines):
        return write_lines(self.root / "abc" / "subagents" / f"{name}.jsonl", *lines)

    def run_script(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, timeout=20)

    def cost(self):
        return self.run_script(str(self.session))

    def test_the_header_names_the_six_columns(self):
        write_lines(self.session, assistant("m1"))
        self.assertEqual(self.cost().stdout.splitlines()[0].split(), HEADER)

    def test_the_main_session_a_subagent_and_the_total_each_get_a_row(self):
        write_lines(self.session, assistant("m1", 3, 100, 2000, 50), assistant("m2", 1, 10, 20, 5))
        self.subagent("agent-a", assistant("s1", 2, 0, 500, 7))
        out = self.cost().stdout
        self.assertEqual(row(out, "abc"), ["abc", "2", "4", "110", "2020", "55", "169"])
        self.assertEqual(row(out, "agent-a"), ["agent-a", "1", "2", "0", "500", "7", "9"])
        self.assertEqual(row(out, "total"), ["total", "3", "6", "110", "2520", "62", "178"])

    def test_the_subagent_rows_come_sorted_between_the_session_and_the_total(self):
        write_lines(self.session, assistant("m1"))
        self.subagent("agent-b", assistant("s2"))
        self.subagent("agent-a", assistant("s1"))
        self.assertEqual(names(self.cost().stdout), ["session", "abc", "agent-a", "agent-b", "total"])

    def test_a_meta_file_beside_a_subagent_is_not_a_row(self):
        write_lines(self.session, assistant("m1"))
        self.subagent("agent-a", assistant("s1"))
        write_lines(self.root / "abc" / "subagents" / "agent-a.meta.json", '{"agentType": "explore"}')
        self.assertEqual(names(self.cost().stdout), ["session", "abc", "agent-a", "total"])

    def test_a_session_with_no_subagents_folder_has_only_its_own_row_and_the_total(self):
        write_lines(self.session, assistant("m1", 1, 1, 1, 1))
        result = self.cost()
        self.assertEqual((result.returncode, names(result.stdout)), (0, ["session", "abc", "total"]))

    def test_a_streamed_message_counts_once_with_its_last_usage(self):
        write_lines(self.session, assistant("m1", 3, 100, 2000, 5), assistant("m1", 3, 100, 2000, 50))
        self.assertEqual(row(self.cost().stdout, "abc"), ["abc", "1", "3", "100", "2000", "50", "153"])

    def test_records_without_usage_and_non_assistant_records_are_skipped(self):
        no_usage = json.dumps({"type": "assistant", "message": {"id": "m2"}})
        user = json.dumps({"type": "user", "message": {"id": "u1", "usage": {"output_tokens": 999}}})
        write_lines(self.session, assistant("m1", 1, 0, 0, 1), no_usage, user)
        result = self.cost()
        self.assertEqual(row(result.stdout, "abc"), ["abc", "1", "1", "0", "0", "1", "2"])
        self.assertEqual(result.stdout.splitlines()[-1], "unreadable lines: 0")

    def test_lines_that_are_not_json_are_skipped_and_counted_across_all_files(self):
        write_lines(self.session, assistant("m1"), "not json", "[1, 2]")
        self.subagent("agent-a", assistant("s1"), "{broken")
        result = self.cost()
        self.assertEqual(row(result.stdout, "total")[1], "2")
        self.assertEqual(result.stdout.splitlines()[-1], "unreadable lines: 3")

    def test_a_line_nested_too_deeply_to_parse_is_counted_as_unreadable(self):
        write_lines(self.session, assistant("m1"), DEEPLY_NESTED)
        result = self.cost()
        self.assertEqual((result.returncode, row(result.stdout, "abc")[1]), (0, "1"))
        self.assertEqual(result.stdout.splitlines()[-1], "unreadable lines: 1")

    def test_a_subagent_file_that_cannot_be_read_exits_2_naming_it(self):
        write_lines(self.session, assistant("m1"))
        (self.root / "abc" / "subagents" / "x.jsonl").mkdir(parents=True)
        result = self.cost()
        self.assertEqual((result.returncode, result.stdout, len(result.stderr.splitlines())), (2, "", 1))
        self.assertIn("x.jsonl", result.stderr)

    def test_records_without_a_message_id_count_once_per_request_id(self):
        write_lines(self.session, usage_record(5, requestId="r1"), usage_record(9, requestId="r1"))
        self.assertEqual(row(self.cost().stdout, "abc"), ["abc", "1", "0", "0", "0", "9", "9"])

    def test_records_with_neither_a_message_id_nor_a_request_id_count_separately(self):
        write_lines(self.session, usage_record(5), usage_record(9))
        self.assertEqual(row(self.cost().stdout, "abc"), ["abc", "2", "0", "0", "0", "14", "14"])

    def test_token_values_that_are_bool_or_float_count_as_zero(self):
        bad = json.dumps({"type": "assistant", "message": {"id": "m1", "usage": {
            "input_tokens": True, "cache_creation_input_tokens": 1.5, "cache_read_input_tokens": "7", "output_tokens": None}}})
        write_lines(self.session, bad)
        self.assertEqual(row(self.cost().stdout, "abc"), ["abc", "1", "0", "0", "0", "0", "0"])

    def test_a_line_with_invalid_utf8_does_not_stop_the_lines_around_it(self):
        self.session.write_bytes(assistant("m1", output=1).encode() + b"\n\xff\xfe broken\n" + assistant("m2", output=2).encode() + b"\n")
        result = self.cost()
        self.assertEqual((result.returncode, row(result.stdout, "abc")[1:]), (0, ["2", "0", "0", "0", "3", "3"]))
        self.assertEqual(result.stdout.splitlines()[-1], "unreadable lines: 1")

    def test_a_missing_session_prints_one_error_line_and_exits_2(self):
        result = self.run_script(str(self.root / "missing.jsonl"))
        self.assertEqual((result.returncode, result.stdout, len(result.stderr.splitlines())), (2, "", 1))
        self.assertIn("missing.jsonl", result.stderr)

    def test_no_argument_prints_one_usage_line_and_exits_2(self):
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout, len(result.stderr.splitlines())), (2, "", 1))


if __name__ == "__main__":
    unittest.main()
