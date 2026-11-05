"""Tests for the /sdlc command file: wording pins and the run fingerprint command.

Run: python3 -I -m unittest discover -s tests
The pins show the text is present, not that the chair follows it. The fingerprint tests run the
command from `### Fingerprint` for real, in a throwaway git repo.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SDLC = REPO / "plugins" / "sdlc" / "commands" / "sdlc.md"
TECH_LEAD = REPO / "plugins" / "sdlc" / "agents" / "tech-lead.md"
QA_ENGINEER = REPO / "plugins" / "sdlc" / "agents" / "qa-engineer.md"
RULES = REPO / "rules" / "sdlc.md"
CHANGELOG = REPO / "CHANGELOG.md"
TRIGGERS = ("adds a schema or migration, changes an event name or payload or a public API signature, "
            "or adds a dependency, a service, a trust boundary or a module")
OLD_LIMIT = re.compile(r"at most (the )?one test file", re.IGNORECASE)
FINGERPRINT = re.compile(r"### Fingerprint.*?```sh\n(.*?)\n```", re.DOTALL)


def files_with_hebrew():
    paths = [p for p in REPO.rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".json", ".sh", ".drawio") and ".git" not in p.parts]
    return [str(p.relative_to(REPO)) for p in sorted(paths) if re.search(r"[\u0590-\u05FF]", p.read_text(encoding="utf-8"))]


def files_with_old_limit():
    paths = [REPO / "README.md", *REPO.glob("rules/*.md"), *REPO.glob("plugins/**/*.md")]
    return [str(p.relative_to(REPO)) for p in paths if OLD_LIMIT.search(p.read_text(encoding="utf-8"))]


class WordingTest(unittest.TestCase):
    def setUp(self):
        self.text = SDLC.read_text(encoding="utf-8")

    def test_no_one_test_file_limit_remains(self):
        self.assertEqual(files_with_old_limit(), [])

    def test_command_defines_the_stage_states(self):
        self.assertIn("pending|running|done|skipped|blocked|failed", self.text)

    def test_command_defines_the_status_header(self):
        self.assertRegex(self.text, r"`run: <slug>`, `risk: .*`base: .*`plan-sha: ")

    def test_command_defines_resume_and_the_built_fingerprint(self):
        self.assertIn("## Resume", self.text)
        self.assertIn("`/sdlc resume <slug>`", self.text)
        self.assertIn("`built: <fingerprint>`", self.text)

    def test_resume_asks_for_approval_before_repairing_build(self):
        self.assertLess(self.text.index("Approval comes before any repair"), self.text.index("4. Build: compare"))

    def test_resume_keeps_the_last_line_for_where_the_run_stands(self):
        self.assertIn("insert `resumed: <date>` above the last line", self.text)

    def test_resume_comes_before_the_empty_request_line(self):
        self.assertLess(self.text.index("## Resume"), self.text.index("If the request above is empty"))

    def test_tech_lead_defines_must_not_happen_for_high_only(self):
        self.assertIn("**Must not happen** (HIGH only)", TECH_LEAD.read_text(encoding="utf-8"))

    def test_qa_engineer_gives_each_must_not_happen_line_a_check_or_not_covered(self):
        text = QA_ENGINEER.read_text(encoding="utf-8")
        self.assertIn("each line is a criterion that needs its own check", text)
        self.assertIn("`not covered`", text)

    def test_plan_gate_shows_must_not_happen_and_assumptions_to_the_owner(self):
        self.assertIn("**Must not happen** and **Assumptions about the request**", self.text)

    def test_verify_records_each_test_run_with_a_fingerprint(self):
        self.assertIn("under **Test runs**", self.text)
        self.assertIn("`| id | command | exit | fingerprint | started (ISO) | output | covers |`", self.text)

    def test_ship_recomputes_the_fingerprint_before_relying_on_a_run(self):
        self.assertIn("the chair recomputes the fingerprint", self.text)

    def test_ship_says_the_fingerprint_check_is_not_a_hook(self):
        self.assertIn("This is the chair's own check, not a hook", self.text)

    def test_resume_marks_test_runs_with_a_different_fingerprint_stale(self):
        self.assertIn("mark every **Test runs** row whose fingerprint differs as stale", self.text)

    def test_the_rules_name_the_must_not_happen_list_for_high_work(self):
        self.assertIn("a must-not-happen list", RULES.read_text(encoding="utf-8"))

    def test_the_rules_ask_for_run_fingerprints_in_the_high_column(self):
        high_cell = RULES.read_text(encoding="utf-8").split("| Verify |")[1].split("\n")[0].split("|")[2]
        self.assertIn("each run records the code it ran on", high_cell)

    def test_tech_lead_defines_the_architecture_section_with_its_triggers(self):
        text = TECH_LEAD.read_text(encoding="utf-8")
        self.assertIn("- **Architecture**: required when the plan " + TRIGGERS, text)

    def test_tech_lead_asks_for_both_diagrams_a_contract_table_and_a_skip_line(self):
        text = TECH_LEAD.read_text(encoding="utf-8")
        self.assertIn("**As-Is**: a fenced `mermaid` block", text)
        self.assertIn("**To-Be**: a fenced `mermaid` block", text)
        self.assertIn("`| Component / contract | Expected change | Verification |`", text)
        self.assertIn("`Architecture diagram: skipped — <specific reason>`", text)

    def test_tech_lead_labels_what_it_could_not_confirm_as_unknown(self):
        text = TECH_LEAD.read_text(encoding="utf-8")
        self.assertIn("Name the file you read for each node", text)
        self.assertIn("labelled `unknown`, never drawn as fact", text)

    def test_tech_lead_requires_the_section_for_new_products_and_high_plans_across_components(self):
        text = TECH_LEAD.read_text(encoding="utf-8")
        self.assertIn("every new-product plan and every HIGH plan that crosses more than one component", text)

    def test_tech_lead_puts_the_rejected_alternative_in_the_approach(self):
        self.assertIn("the main alternative you rejected and the tradeoff", TECH_LEAD.read_text(encoding="utf-8"))

    def test_tech_lead_asks_for_failure_scenarios_in_the_architecture_section(self):
        self.assertIn("**Failure scenarios**: for each dependency the change adds or touches", TECH_LEAD.read_text(encoding="utf-8"))

    def test_the_trigger_list_is_worded_the_same_in_the_agent_the_rules_and_the_readme(self):
        self.assertIn(TRIGGERS, TECH_LEAD.read_text(encoding="utf-8"))
        self.assertIn(TRIGGERS, RULES.read_text(encoding="utf-8"))
        self.assertIn(TRIGGERS, (REPO / "README.md").read_text(encoding="utf-8"))
        self.assertIn(TRIGGERS, CHANGELOG.read_text(encoding="utf-8"))

    def test_tech_lead_defines_the_trigger_terms(self):
        text = TECH_LEAD.read_text(encoding="utf-8")
        self.assertIn("module is a new top-level folder or package", text)
        self.assertIn("new-product is a plan whose PRD starts a new product", text)
        self.assertIn("component is a top-level folder, package or deployable unit", text)

    def test_plan_gate_bounds_the_trust_boundary_rounds_and_the_chair_does_not_redraw(self):
        self.assertIn("The chair does not redraw.", self.text)
        self.assertIn("After two rounds, what still disagrees goes to the owner at the STOP.", self.text)

    def test_plan_gate_checks_the_scope_patterns_against_a_short_list(self):
        self.assertIn("The chair also checks the `sdlc-scope` patterns against a short list", self.text)
        self.assertIn("A match sends the plan back to `tech-lead` once", self.text)
        self.assertIn("The list is a floor, not a ceiling", self.text)
        self.assertIn("the chair also counts the top-level folders in `sdlc-scope`", self.text)

    def test_plan_row_points_at_the_architecture_subsection_and_names_the_failure_scenarios(self):
        self.assertIn("handled as described under \"Architecture in the plan\" below", self.text)
        self.assertIn("the component and contract table and the failure scenarios", self.text)

    def test_plan_gate_treats_a_change_after_approval_as_an_amendment(self):
        self.assertIn("any change to `plan.md` is an amendment that needs `approve plan` again", self.text)

    def test_plan_gate_keeps_the_diagrams_inside_the_hashed_plan(self):
        self.assertIn("in fenced `mermaid` blocks inside `plan.md`, so the plan hash covers them", self.text)

    def test_plan_gate_does_not_let_a_skip_line_satisfy_a_trigger(self):
        self.assertIn("a skip line does not satisfy a trigger", self.text)

    def test_plan_gate_renders_the_diagrams_for_the_owner(self):
        self.assertIn("renders the diagrams with a Mermaid-capable diagram tool", self.text)

    def test_the_rules_ask_for_diagrams_only_when_a_contract_changes(self):
        self.assertIn("otherwise the skip reason in one line", RULES.read_text(encoding="utf-8"))

    def test_the_rules_let_a_high_change_inside_one_component_skip_the_diagrams(self):
        self.assertIn("unless no trigger above applies and the whole change sits inside one existing component", RULES.read_text(encoding="utf-8"))

    def test_readme_says_the_hash_binds_the_file_not_the_owners_reading(self):
        self.assertIn("the hash binds the file, not your reading of it", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_readme_says_a_diagram_does_not_prove_the_design(self):
        self.assertIn("not that it is right, and this is a prompt the model follows", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_plan_gate_answers_a_yes_in_another_language_by_asking_for_the_words(self):
        self.assertIn("a clear yes in another language gets the same answer", self.text)

    def test_the_repo_has_no_hebrew_text(self):
        self.assertEqual(files_with_hebrew(), [])

    def test_readme_calls_the_gates_a_best_effort_guardrail(self):
        self.assertIn("best-effort guardrail", (REPO / "README.md").read_text(encoding="utf-8"))


class FingerprintTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        self.git("init", "-q")
        (self.repo / "a.txt").write_text("one\n")
        self.git("add", "a.txt")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.command = FINGERPRINT.search(SDLC.read_text(encoding="utf-8")).group(1)

    def git(self, *args):
        identity = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        return subprocess.run(["git", *identity, *args], cwd=self.repo, capture_output=True, text=True,
                              check=True, timeout=30).stdout

    def fingerprint(self, cwd=None):
        out = subprocess.run(["bash", "-c", self.command], cwd=cwd or self.repo, capture_output=True, text=True,
                             timeout=30, env={**os.environ, "BASE": self.base})
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_same_tree_gives_the_same_fingerprint(self):
        self.assertEqual(self.fingerprint(), self.fingerprint())

    def test_the_fingerprint_is_one_sha256_line(self):
        self.assertRegex(self.fingerprint(), r"^[0-9a-f]{64}  -\n$")

    def test_an_untracked_file_changes_it(self):
        before = self.fingerprint()
        (self.repo / "new.py").write_text("print(1)\n")
        self.assertNotEqual(self.fingerprint(), before)

    def test_a_tracked_edit_changes_it(self):
        before = self.fingerprint()
        (self.repo / "a.txt").write_text("two\n")
        self.assertNotEqual(self.fingerprint(), before)

    def test_a_deleted_tracked_file_changes_it(self):
        before = self.fingerprint()
        (self.repo / "a.txt").unlink()
        self.assertNotEqual(self.fingerprint(), before)

    def test_an_untracked_file_with_a_space_in_its_name_changes_it(self):
        before = self.fingerprint()
        (self.repo / "my file.py").write_text("print(1)\n")
        self.assertNotEqual(self.fingerprint(), before)

    def test_running_from_a_subdirectory_gives_the_same_fingerprint(self):
        (self.repo / "pkg").mkdir()
        (self.repo / "pkg" / "m.py").write_text("x = 1\n")
        self.assertEqual(self.fingerprint(self.repo / "pkg"), self.fingerprint())

    def test_files_under_sdlc_do_not_change_it(self):
        before = self.fingerprint()
        (self.repo / ".sdlc" / "x").mkdir(parents=True)
        (self.repo / ".sdlc" / "x" / "status.md").write_text("run: x\n")
        self.assertEqual(self.fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
