# -*- coding: utf-8 -*-
"""Keep the installable skill small, offline and audit-clean.

skills.sh audits (Snyk, Socket, Gen Agent Trust Hub) and `npx skills add` both work on the
folder that holds SKILL.md, so that folder must contain only what a student needs.
"""
from tests import skillpath  # noqa: F401  (skill folder on sys.path)
import json
import os
import re
import unittest

ROOT = skillpath.ROOT
SKILL_DIR = skillpath.SKILL_DIR
NAME = "universal-exam-cram-coach"
ALLOWED_TOP = {"SKILL.md", "LICENSE", "coach.py", "coach"}
FORBIDDEN_CODE = [r"\bimport\s+subprocess\b", r"\bfrom\s+subprocess\b", r"\bimport\s+socket\b", r"\burllib\b",
                  r"\bhttp\.client\b", r"\bimport\s+requests\b", r"\bos\.system\b", r"\bos\.popen\b",
                  r"(?<![\w.])eval\(", r"(?<![\w.])exec\(", r"\bpickle\b", r"\bctypes\b"]
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    assert m, "%s has no frontmatter" % path
    fm, section = {}, None
    for line in m.group(1).split("\n"):
        if re.match(r"^\S[^:]*:\s*$", line):
            section = line.split(":")[0].strip()
            fm[section] = {}
        elif line.startswith("  ") and section:
            k, v = line.strip().split(":", 1)
            fm[section][k.strip()] = v.strip().strip('"')
        elif ":" in line:
            section = None
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm


def discover(base):
    """The skills CLI (vercel-labs/skills v1.7) discovery rules that matter for this repo."""
    def parse(d):
        p = os.path.join(d, "SKILL.md")
        if not os.path.isfile(p):
            return None
        fm = frontmatter(p)
        if not fm.get("name") or not fm.get("description"):
            return "invalid"
        if isinstance(fm.get("metadata"), dict) and fm["metadata"].get("internal") == "true":
            return "internal"
        return fm["name"]

    top = parse(base)
    if top not in (None, "invalid", "internal"):
        return [top]  # a root SKILL.md wins and the whole repo is copied
    found = []

    def walk(d, max_depth, depth=1):
        for entry in sorted(os.listdir(d)):
            child = os.path.join(d, entry)
            if not os.path.isdir(child):
                continue
            got = parse(child)
            if got not in (None,):
                if got not in ("invalid", "internal") and got not in found:
                    found.append(got)
                continue  # never descend below a skill
            if depth >= max_depth or entry in SKIP_DIRS:
                continue
            walk(child, max_depth, depth + 1)

    walk(base, 1)
    if os.path.isdir(os.path.join(base, "skills")):
        walk(os.path.join(base, "skills"), 3)
    return found


class SkillSurfaceTest(unittest.TestCase):
    def test_only_student_facing_files_ship(self):
        self.assertEqual(set(os.listdir(SKILL_DIR)) - {"__pycache__"}, ALLOWED_TOP)
        for f in os.listdir(os.path.join(SKILL_DIR, "coach")):
            if f != "__pycache__":
                self.assertTrue(f.endswith(".py"), f)

    def test_frontmatter_follows_the_agent_skills_spec(self):
        fm = frontmatter(os.path.join(SKILL_DIR, "SKILL.md"))
        self.assertEqual(fm["name"], NAME)
        self.assertEqual(os.path.basename(SKILL_DIR), fm["name"])
        self.assertRegex(fm["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(fm["name"]), 64)
        self.assertLessEqual(len(fm["description"]), 1024)
        self.assertLessEqual(len(fm["compatibility"]), 500)
        self.assertEqual(fm["license"], "MIT")

    def test_code_needs_no_network_or_subprocess(self):
        for base, _, files in os.walk(SKILL_DIR):
            for f in files:
                if f.endswith(".py"):
                    src = open(os.path.join(base, f), encoding="utf-8").read()
                    for pat in FORBIDDEN_CODE:
                        self.assertIsNone(re.search(pat, src), "%s matches %s" % (f, pat))

    def test_no_urls_or_secret_like_strings(self):
        skill_md = open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
        self.assertNotRegex(skill_md, r"https?://")
        for base, _, files in os.walk(SKILL_DIR):
            for f in files:
                if f.endswith((".py", ".md")):
                    text = open(os.path.join(base, f), encoding="utf-8").read()
                    # long runs mixing letters and digits look like keys/tokens to secret scanners
                    self.assertNotRegex(text, r"(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}", f)

    def test_npx_skills_add_finds_exactly_the_flash_skill(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "SKILL.md")), "a root SKILL.md would ship the whole repo")
        self.assertEqual(discover(ROOT), [NAME])

    def test_full_edition_is_hidden_but_installable_by_name(self):
        fm = frontmatter(os.path.join(ROOT, "full", "SKILL.md"))
        self.assertEqual(fm["name"], NAME + "-full")
        self.assertEqual(fm["metadata"].get("internal"), "true")

    def test_claude_plugin_marketplace_points_at_the_skill_only(self):
        path = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
        data = json.load(open(path, encoding="utf-8"))
        (plugin,) = data["plugins"]
        self.assertEqual(plugin["source"], "./")
        self.assertEqual(plugin["skills"], ["./skills/" + NAME])
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", NAME, "SKILL.md")))


if __name__ == "__main__":
    unittest.main()
