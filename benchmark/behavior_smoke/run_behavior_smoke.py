#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tier 2 behavioral smoke — DETERMINISTIC by default, real-LLM smoke OPT-IN only.

This harness tests the skill as a *tutoring workflow*, not just as static files.

  python benchmark/behavior_smoke/run_behavior_smoke.py --check-fixture   # validate the mini-course
  python benchmark/behavior_smoke/run_behavior_smoke.py --mock            # run detectors on mock outputs

The --mock / --check-fixture paths are stdlib-only, no network, no LLM, no API key — safe for CI.
Real-agent smoke is gated behind BOTH a flag and an env opt-in and never runs by default:

  RUN_SKILL_BEHAVIOR_LLM=1 python benchmark/behavior_smoke/run_behavior_smoke.py --llm

It will NOT call any model in CI, never reads API keys, and never runs a paid benchmark.
"""
import os
import re
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))           # repo root
FIXTURE = os.path.join(HERE, "fixtures", "mini_course")
SCENARIOS = os.path.join(HERE, "scenarios.json")
RESULTS_DIR = os.path.join(HERE, "results")             # gitignored output dir

# canonical provenance labels — single source of truth is docs/language-policy.md
CANON_LABELS = [
    "🟢 来自资料",
    "🟡 AI补充，可能与你老师讲的不完全一致",
    "⚠️ AI生成答案，非老师/教材提供",
]


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


# ---------------- detectors (deterministic, stdlib-only) ----------------

def load_quiz_bank_ids(workspace):
    data = json.loads(_read(os.path.join(workspace, "references", "quiz_bank.json")))
    return {str(q.get("id")) for q in data if isinstance(q, dict) and q.get("id") is not None}


def extract_question_ids(text):
    """Quiz outputs mark each drawn item as [#<id>]; pull them all out."""
    return re.findall(r"\[#([^\]\s]+)\]", text or "")


def assert_quiz_ids_in_bank(text, bank_ids):
    ids = extract_question_ids(text)
    return bool(ids) and all(i in bank_ids for i in ids)


def has_canonical_provenance_labels(text):
    t = text or ""
    return all(lbl in t for lbl in CANON_LABELS)


def has_zero_basic_sections(text):
    t = text or ""
    return ("考点拆解" in t
            and ("标准答题步骤" in t or "标准答题模板" in t)
            and "易错点" in t
            and "3分钟速记" in t)


def has_hint_skip_offer(text):
    t = (text or "")
    tl = t.lower()
    has_hint = ("提示" in t) or ("hint" in tl)
    has_skip = ("跳过" in t) or ("skip" in tl)
    has_archive = ("错题本" in t) or ("归档" in t)
    return has_hint and has_skip and has_archive


def _section(text, header_keyword):
    """Lines under the first markdown '## ' header containing header_keyword, until the next '## '."""
    out, grab = [], False
    for ln in (text or "").splitlines():
        if ln.startswith("## "):
            grab = header_keyword in ln
            continue
        if grab:
            out.append(ln)
    return "\n".join(out)


def _table_data_rows(section_text):
    """Markdown table data rows in a section (excludes header, separator, and non-table prose)."""
    rows = []
    seen_header = False
    for ln in section_text.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):   # separator row ( | --- | --- | )
            continue
        if not seen_header:
            seen_header = True                          # first table row is the header
            continue
        rows.append(cells)
    return rows


def progress_has_mistake_archive(progress_text):
    return len(_table_data_rows(_section(progress_text, "错题本"))) >= 1


def progress_has_confusion_row(progress_text):
    return len(_table_data_rows(_section(progress_text, "疑难"))) >= 1


def progress_current_phase(progress_text):
    m = re.search(r"当前[^#]*?阶段\s*(\d+)", progress_text or "", re.S)
    return int(m.group(1)) if m else None


def resume_refers_to_phase(resume_text, phase):
    """A resume message should point at the CURRENT phase (not silently restart at phase 1)."""
    return f"阶段 {phase}" in (resume_text or "")


def count_wiki_reads(transcript_text):
    """best-effort: count read_file events that touch references/wiki/*.md in a JSONL transcript."""
    n = 0
    for line in (transcript_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("tool") == "read_file" and "references/wiki/" in str(ev.get("path", "")):
            n += 1
    return n


def validate_fixture_workspace(path):
    """Run the Tier-1 validator on a workspace. Returns (ok, errors, warnings, stats)."""
    spath = os.path.join(ROOT, "scripts")
    if spath not in sys.path:
        sys.path.insert(0, spath)
    import validate_workspace as V
    errors, warnings, stats = V.validate(path)
    return V._exit_code(errors) == 0, errors, warnings, stats


# ---------------- scenario runner (mock = deterministic) ----------------

def load_scenarios():
    return json.loads(_read(SCENARIOS))


def _p(rel):
    return os.path.join(HERE, rel)


def check_scenario_mock(name, sc, bank_ids):
    """Return (ok, detail) for one scenario using only mock artifacts — no LLM."""
    if name == "quiz_bank_only":
        good = assert_quiz_ids_in_bank(_read(_p(sc["mock_output"])), bank_ids)
        bad = assert_quiz_ids_in_bank(_read(_p(sc["mock_negative"])), bank_ids)
        return (good and not bad), f"good_uses_bank_ids={good} invented_id_caught={not bad}"
    if name == "provenance_labels":
        ok = has_canonical_provenance_labels(_read(_p(sc["mock_output"])))
        return ok, f"all_canonical_labels={ok}"
    if name == "hint_skip_mistake_archive":
        offer = has_hint_skip_offer(_read(_p(sc["mock_output"])))
        arch = progress_has_mistake_archive(_read(_p(sc["progress_after"])))
        return (offer and arch), f"hint_skip_offer={offer} mistake_archived={arch}"
    if name == "confusion_tracking":
        ok = progress_has_confusion_row(_read(_p(sc["mock_output"])))
        return ok, f"confusion_row_written={ok}"
    if name == "checkpoint_recovery":
        ph = progress_current_phase(_read(os.path.join(FIXTURE, "study_progress.md")))
        resume = _read(_p(sc["mock_output"]))
        refers = resume_refers_to_phase(resume, sc["expected_phase"])
        return (ph == sc["expected_phase"] and refers), f"current_phase={ph} resume_refers_current={refers}"
    if name == "no_python_fallback":
        ok = validate_fixture_workspace(_p(sc["fallback_workspace"]))[0]
        return ok, f"hand_authored_workspace_valid={ok}"
    if name == "zero_basic_key_question":
        ok = has_zero_basic_sections(_read(_p(sc["mock_output"])))
        return ok, f"required_sections_present={ok}"
    return False, "unknown scenario"


def run_mock(verbose=True):
    spec = load_scenarios()
    bank_ids = load_quiz_bank_ids(FIXTURE)
    results = []
    for sc in spec["scenarios"]:
        name = sc["name"]
        if sc.get("best_effort"):
            results.append((name, "best-effort (needs LLM/transcript; skipped in --mock)", True))
            continue
        ok, detail = check_scenario_mock(name, sc, bank_ids)
        results.append((name, detail, ok))
    if verbose:
        for name, detail, ok in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return all(ok for _, _, ok in results), results


def check_fixture(verbose=True):
    ok, errors, warnings, stats = validate_fixture_workspace(FIXTURE)
    if verbose:
        print(f"fixture: {FIXTURE}")
        print(f"  valid={ok}  stats={stats}")
        for e in errors:
            print(f"  [error] {e['msg']}")
    return ok


def run_llm():
    """OPT-IN skeleton: real `claude -p` smoke. Never runs in CI, never reads API keys."""
    if os.environ.get("RUN_SKILL_BEHAVIOR_LLM") != "1":
        print("LLM behavioral smoke is OPT-IN and disabled by default.")
        print("To enable you must set env RUN_SKILL_BEHAVIOR_LLM=1 AND pass --llm. Refusing to run.")
        return 2
    # Skeleton only — T2 ships the harness, not the paid runs. The real path would, per scenario:
    #   1) copy FIXTURE into a tempdir, 2) run `claude -p <scenario.prompt>` (subscription, no API key),
    #   3) capture output/files into RESULTS_DIR, 4) apply the SAME deterministic detectors as --mock.
    print("RUN_SKILL_BEHAVIOR_LLM=1 detected — LLM smoke harness skeleton (no model wired in this PR).")
    print("Scenarios available for the opt-in run:",
          ", ".join(s["name"] for s in load_scenarios()["scenarios"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Tier 2 behavioral smoke — deterministic by default, LLM smoke opt-in")
    ap.add_argument("--mock", action="store_true",
                    help="run deterministic detectors on mock outputs (no LLM, no network)")
    ap.add_argument("--check-fixture", action="store_true",
                    help="validate the mini-course fixture workspace (Tier 1)")
    ap.add_argument("--llm", action="store_true",
                    help="real claude -p smoke; requires RUN_SKILL_BEHAVIOR_LLM=1 (off in CI)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.llm:
        return run_llm()
    if args.check_fixture:
        return 0 if check_fixture() else 1
    if args.mock:
        ok, _ = run_mock()
        print("结论:", "✓ 全部行为冒烟通过" if ok else "✗ 有失败")
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
