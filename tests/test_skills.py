"""The skills the gates call must ship in the plugin, and every sdlc:<name> reference must resolve to one."""
import hashlib
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "plugins" / "sdlc" / "skills"
GATE_SKILLS = ["architecture-slayer", "idea-slayer", "change-impact", "canary-watch", "browser-qa", "click-path-audit"]
ECC_SHA256 = {
    "change-impact": "b8d8a11417af8b84e93983a8eb682e3b9a16d04f926778eb635c96e90019bf18",
    "canary-watch": "d2cb536f8ccb201266e094542cb20af8a4d6474feb5b16116cfb4497c2b8149f",
    "browser-qa": "6eb78a2460adcde116e6b44fcdff7ae37aeec6208241a24417cb2db4b3b254cd",
    "click-path-audit": "662fc5d02483bcd8ff799d6d3109a38da673182341cfc14445e9076fcd920162",
}
REFERENCE = re.compile(r"`sdlc:([a-z0-9-]+)`")


def frontmatter_name(skill):
    match = re.search(r"^name:\s*(\S+)", (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def sha256_of(skill):
    return hashlib.sha256((SKILLS / skill / "SKILL.md").read_bytes()).hexdigest()


def files_with_hebrew():
    return [str(p.relative_to(REPO)) for p in sorted(SKILLS.rglob("*")) if p.is_file() and re.search(r"[\u0590-\u05FF]", p.read_text(encoding="utf-8"))]


def referenced_skills():
    paths = [REPO / "README.md", *REPO.glob("plugins/sdlc/agents/*.md"), *REPO.glob("plugins/sdlc/commands/*.md")]
    return sorted({name for p in paths for name in REFERENCE.findall(p.read_text(encoding="utf-8"))})


def unbundled(names):
    return [name for name in names if not (SKILLS / name / "SKILL.md").exists()]


class BundledSkillsTest(unittest.TestCase):
    def test_every_sdlc_skill_the_agents_name_is_bundled(self):
        self.assertEqual(unbundled(referenced_skills()), [])

    def test_the_six_gate_skills_are_bundled(self):
        self.assertEqual(unbundled(GATE_SKILLS), [])

    def test_the_agents_name_the_bundled_copies_of_the_gate_skills(self):
        self.assertIn("architecture-slayer", referenced_skills())
        self.assertIn("idea-slayer", referenced_skills())

    def test_architecture_slayer_keeps_its_reference_file(self):
        self.assertTrue((SKILLS / "architecture-slayer" / "references" / "failure-modes.md").exists())

    def test_each_skill_folder_matches_its_frontmatter_name(self):
        self.assertEqual([frontmatter_name(name) for name in GATE_SKILLS], GATE_SKILLS)

    def test_the_four_ecc_skills_are_unchanged_copies(self):
        self.assertEqual({name: sha256_of(name) for name in ECC_SHA256}, ECC_SHA256)

    def test_the_notice_credits_ecc_and_carries_its_license(self):
        notice = (SKILLS / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 Affaan Mustafa", notice)
        self.assertIn("Permission is hereby granted, free of charge", notice)

    def test_the_notice_names_all_six_skills(self):
        notice = (SKILLS / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertEqual([name for name in GATE_SKILLS if f"`{name}`" in notice], GATE_SKILLS)

    def test_no_bundled_skill_contains_hebrew(self):
        self.assertEqual(files_with_hebrew(), [])

    def test_the_readme_links_the_optional_skills_list(self):
        self.assertIn("[docs/skills.md](docs/skills.md)", (REPO / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
