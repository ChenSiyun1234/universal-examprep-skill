# -*- coding: utf-8 -*-
"""PR F — runtime skill text describes current behavior, not version eras. Stdlib only.

Runtime/operational files must not carry V2.0 / V2.1 prose; version history lives only in
CHANGELOG.md. A skill should execute the current behavior directly (knowledge provenance,
diagram protocol, six quiz types, LLM Wiki lazy loading, …) instead of reasoning about which
version introduced what.

Allowlist: CHANGELOG.md (the history file), benchmark/ (historical reports — not scanned),
and the root SKILL.md frontmatter `metadata.version` line (machine-readable, stripped before scan).
"""
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN = ["V2.0", "V2.1", "v2.0", "v2.1", "New in V2", "重大更新特性", "突破性更新特性"]


def runtime_files():
    rels = ["README.md", "SKILL.md", "AGENTS.md"]
    for pat in ("docs/*.md", "prompts/*.md", "skills/**/*.md"):
        for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
            rels.append(os.path.relpath(p, ROOT).replace("\\", "/"))
    return sorted(set(rels))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def body_without_frontmatter(text):
    # strip a leading YAML frontmatter block (metadata such as version: lives there and is allowed)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


class NoVersionEraRuntimeTextTest(unittest.TestCase):
    def test_runtime_files_have_no_version_era_wording(self):
        offenders = []
        for rel in runtime_files():
            body = body_without_frontmatter(read(rel))
            for tok in FORBIDDEN:
                if tok in body:
                    offenders.append(f"{rel} -> {tok!r}")
        self.assertEqual(offenders, [], "运行时文本仍含版本号措辞: " + "; ".join(offenders))

    def test_readme_uses_capability_not_version_sections(self):
        r = read("README.md")
        self.assertNotIn("突破性更新特性", r, "README 仍把能力框定为「突破性更新特性」版本段")
        self.assertNotIn("重大更新特性", r, "README 仍把能力框定为「重大更新特性」版本段")
        for tok in ("V2.0", "V2.1"):
            self.assertNotIn(tok, r, f"README 仍含 {tok}")

    def test_history_preserved_in_changelog(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "CHANGELOG.md")), "缺少 CHANGELOG.md")
        c = read("CHANGELOG.md")
        self.assertIn("V2.1", c, "CHANGELOG 未保留 V2.1 历史")
        self.assertIn("V2.0", c, "CHANGELOG 未保留 V2.0 历史")

    def test_skill_frontmatter_version_allowed_body_clean(self):
        text = read("SKILL.md")
        self.assertTrue(text.startswith("---"), "SKILL.md 应有 frontmatter")
        body = body_without_frontmatter(text)
        self.assertNotIn("V2.1", body, "SKILL.md 正文仍含 V2.1")
        self.assertNotIn("V2.0", body, "SKILL.md 正文仍含 V2.0")


if __name__ == "__main__":
    unittest.main()
