# -*- coding: utf-8 -*-
"""Tier 4 long-horizon drift harness — DETERMINISTIC REPLAY (default; no LLM / network / API keys / deps).

Replays a SCRIPTED multi-turn tutoring transcript (JSONL) + workspace snapshots against a self-authored
fixture and computes drift metrics over a longer review session, then checks them against the scenario's
thresholds:

  * goal retention            — does the assistant stay on the exam-prep goal, or wander off?
  * plan adherence            — is study_plan.md's phase sequence left intact (no silent delete/reorder/add)?
  * quiz-bank fidelity         — are quizzed items real bank ids, in the requested phase, and not invented?
  * checkpoint recovery       — on resume, does it continue from the current phase (not restart at phase 1)?
  * provenance fidelity       — do later explanation turns still carry the canonical 🟢/🟡/⚠️ labels?
  * mistake/confusion persistence — are archived rows added and never silently dropped across the session?
  * wiki lazy-load / overread — reads scoped to the phase's chapter; optional token/cost accounting.

This is DETERMINISTIC REPLAY of a scripted transcript. It does NOT run a real agent — so it measures
whether a *recorded* session drifts, not whether a live model will. Real long-session LLM runs remain a
future/opt-in path (`--llm`, gated by RUN_SKILL_DRIFT_LLM=1) that is a SKELETON here and never returns
success. Nothing in this file calls a model, reads a key, hits the network, or runs a paid benchmark.

Exit codes: 0 = all scenarios pass their thresholds · 1 = a threshold failed · 2 = malformed input / bad file.

    python benchmark/drift/run_drift.py --scenario benchmark/drift/scenarios/long_session_basic.json \
                                        --transcript benchmark/drift/transcripts/good_session.jsonl
    python benchmark/drift/run_drift.py --all
    python benchmark/drift/run_drift.py --all --json-out /tmp/drift_summary.json
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                      # repo root (…/benchmark/drift → repo)

# canonical provenance labels — mirror T2 / docs/language-policy.md (single source of truth)
CANON_LABELS = ["🟢 来自资料", "🟡 AI补充，可能与你老师讲的不完全一致", "⚠️ AI生成答案，非老师/教材提供"]

# sensible defaults (a scenario may override any of these)
DEFAULT_GOAL_MARKERS = ["期末", "复习", "备考", "考试", "exam", "review"]
DEFAULT_UNRELATED_PHRASES = [
    "switch course", "换一门课", "换个科目", "new study plan unrelated", "与考试无关", "放弃这次考试",
    "不用管考试", "咱们聊点别的", "let's talk about something else", "改学别的", "别复习了", "别刷题了",
    "别管期末", "这门课不重要", "以后用不上", "抛开这门课", "随它去", "写代码项目", "去做副业", "聊聊人生",
    "职业规划", "forget about studying", "don't study", "tell you a story",
]
DEFAULT_REFUSAL_PHRASES = ["我不能继续这个复习", "无法继续原计划", "拒绝按考试计划", "i won't continue the exam plan"]
EXPLAIN_TRIGGERS = re.compile(r"解释|讲讲|讲一下|说明|为什么|讲解|explain|why")
QUIZ_TRIGGERS = re.compile(r"考我|再考|出题|测测|刷题|(?:再来一|来一|下一|再出一)(?:道题?|题)"
                           r"|quiz me|quiz from|test me|next question", re.I)
RESUME_TRIGGERS = re.compile(r"我回来了|继续复习|接着上次|回来继续|resume|continue where|接着复习")
RESTART_PHRASES = re.compile(r"从头开始|重新开始|从头再来|重头|restart|start over|从第?1章重新|从阶段1重新")
PLAN_CHANGE_REQUEST = re.compile(r"改计划|调整计划|重新规划|换个计划|change.*plan|revise.*plan")


class DriftError(Exception):
    """Malformed input — surfaces as exit code 2."""


# ---------------- IO ----------------

def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_jsonl(path, label):
    if not os.path.isfile(path):
        raise DriftError("找不到%s文件: %s" % (label, path))
    rows = []
    for ln, line in enumerate(_read(path).splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            d = json.loads(line)
        except ValueError as e:
            raise DriftError("%s 第 %d 行不是合法 JSON: %s" % (label, ln, e))
        if not isinstance(d, dict):
            raise DriftError("%s 第 %d 行必须是 JSON 对象" % (label, ln))
        rows.append(d)
    return rows


def load_scenario(path):
    if not os.path.isfile(path):
        raise DriftError("找不到 scenario 文件: %s" % path)
    try:
        sc = json.loads(_read(path))
    except ValueError as e:
        raise DriftError("scenario 不是合法 JSON: %s" % e)
    for k in ("name", "fixture", "thresholds"):
        if k not in sc:
            raise DriftError("scenario 缺必需字段 %r" % k)
    if not isinstance(sc["thresholds"], dict):
        raise DriftError("scenario.thresholds 必须是对象")
    return sc


def _resolve(path):
    """Resolve a scenario-relative path against the repo root (paths are repo-relative)."""
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


# ---------------- fixture parsing ----------------

def _as_phase(v):
    """Normalize a phase value to int — accepts int or a numeric string ('2'); else None. (docs/
    file-format.md and the validator allow quiz_bank `phase` to be an int OR a string.)"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def parse_plan_phases(text):
    """Ordered (deduped) list of phase numbers from a study_plan.md. Accepts BOTH this harness's simple
    headings ('## 阶段2：…' / '## Phase 2') AND the real scripts/ingest.py template, where phases live in
    a Markdown table ('| **阶段 1** | … |') and/or a checklist ('- [ ] **阶段 1**：…'). The table and the
    checklist repeat the same phases, so we dedupe while preserving first-seen order."""
    phases = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not (s.startswith("#") or s.startswith("|") or re.match(r"[-*]\s", s)):
            continue                                               # only structural lines define phases
        m = re.search(r"(?:阶段|Phase|phase)\s*(\d+)", s)
        if m:
            n = int(m.group(1))
            if n not in phases:
                phases.append(n)
    return phases


_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")                  # a Markdown table separator row
_TABLE_HDR_WORDS = ("错题id", "关联章节", "题目内容", "错误原因", "序号", "疑难点", "解答要点", "状态")
_ROW_PLACEHOLDER = re.compile(r"（暂无）|（清空重来）|（无）|^\s*[-*]\s*$")


def _is_table_header(line):
    low = line.lower()
    return sum(1 for w in _TABLE_HDR_WORDS if w in low) >= 2


def parse_progress(text):
    """{'phase': int|None, 'mistake_rows': [...], 'confusion_rows': [...]} from a study_progress.md.

    Accepts BOTH this harness's simple format ('当前阶段：1', '- ' bullets) AND the real ingest template
    ('当前进行阶段：阶段 1：…', mistake/confusion stored as Markdown TABLE rows). Rows are the non-placeholder
    bullets OR table DATA rows under each section (header/separator rows excluded), whitespace-normalized so
    a row can be tracked across snapshots to detect additions and silent deletions."""
    t = text or ""
    pm = re.search(r"(?:当前进行阶段|当前阶段|current\s*phase)\D*?(\d+)", t, re.I)
    phase = int(pm.group(1)) if pm else None
    mistake, confusion, cur = [], [], None
    for ln in t.splitlines():
        h = ln.strip()
        is_heading = bool(re.match(r"^\s{0,3}(#{1,4}\s|\*\*)", ln))
        if is_heading and re.search(r"错题|mistake", h):
            cur = mistake
            continue
        if is_heading and re.search(r"疑难|困惑|confusion", h):
            cur = confusion
            continue
        if re.match(r"^\s{0,3}#{1,4}\s", ln):                      # any OTHER heading ends the section
            cur = None
            continue
        if cur is None:
            continue
        if re.match(r"^\s*[-*]\s+\S", ln) and not _ROW_PLACEHOLDER.search(h):
            cur.append(re.sub(r"\s+", " ", h))
        elif h.startswith("|") and not _TABLE_SEP.match(ln) and not _is_table_header(ln):
            cells = [c.strip() for c in h.strip("|").split("|")]
            if any(c and c != "-" for c in cells):                 # a table DATA row with real content
                cur.append(re.sub(r"\s+", " ", h))
    return {"phase": phase, "mistake_rows": mistake, "confusion_rows": confusion}


# ---------------- provenance + quiz (mirror T2 semantics) ----------------

def has_content_label(text):
    """True iff at least one canonical label ANNOTATES content — prefix `label：内容` OR suffix `内容（label）`
    — rather than sitting in a bare legend. Same rule as T2's has_canonical_provenance_labels."""
    t = text or ""
    for lbl in CANON_LABELS:
        for m in re.finditer(re.escape(lbl), t):
            if re.match(r"[ \t]*[:：][ \t]*\S", t[m.end():m.end() + 24]):                 # label：内容
                return True
            if re.search(r"[^）)\s][ \t]*[（(][ \t]*$", t[max(0, m.start() - 16):m.start()]):  # 内容（label
                return True
    return False


def extract_quiz_ids(text):
    return re.findall(r"\[#([^\]\s]+)\]", text or "")


def _row_key(row):
    """Identity of an archived progress row for persistence tracking: its [#id] when present (so
    rewording a row isn't a false 'loss'), else its whitespace-normalized text."""
    ids = extract_quiz_ids(row)
    return "id:" + ids[0] if ids else "tx:" + re.sub(r"\s+", "", row)


_NUM_ITEM_RE = re.compile(r"^\s*(?:\d+\s*[.、)）]|[Qq]\d*\s*[.、:：)）]|第\s*[一二三四五六七八九十\d]+\s*题)")
_OPTION_RE = re.compile(r"^\s*[-*•]?\s*(?:[A-Da-d]|[一二三四甲乙丙丁]|[①②③④⑤⑥])\s*[.、)）.]")


def looks_like_question(line):
    if _OPTION_RE.match(line):
        return False
    if _NUM_ITEM_RE.match(line):
        return True
    return bool(re.match(r"^\s*[-*•]\s", line) and re.search(r"[？?]\s*$", line))


# ---------------- metrics ----------------

def _phase_of_turn(turn):
    if isinstance(turn.get("phase_context"), int):
        return turn["phase_context"]
    m = re.search(r"(?:阶段|phase)\s*(\d+)", turn.get("user", ""), re.I)
    return int(m.group(1)) if m else None


def _wiki_chapter_phase(path):
    m = re.search(r"ch(\d+)", os.path.basename(path or ""))
    return int(m.group(1)) if m else None


def _snapshots(turns, key, base_text):
    """Ordered list of a workspace file's contents across the session (base fixture first, then each
    turn's files_after[key] when present)."""
    snaps = [base_text] if base_text is not None else []
    for t in turns:
        fa = t.get("files_after") or {}
        if key in fa:
            snaps.append(fa[key])
    return snaps


def compute_metrics(scenario, fixture_dir, turns):
    goal_markers = scenario.get("goal_markers", DEFAULT_GOAL_MARKERS)
    unrelated = scenario.get("unrelated_goal_phrases", DEFAULT_UNRELATED_PHRASES)
    refusals = scenario.get("refusal_phrases", DEFAULT_REFUSAL_PHRASES)

    plan_text = _read(os.path.join(fixture_dir, "study_plan.md"))
    bank_path = os.path.join(fixture_dir, "references", "quiz_bank.json")
    bank = json.loads(_read(bank_path))
    bank_phase = {str(q["id"]): _as_phase(q.get("phase")) for q in bank if isinstance(q, dict) and "id" in q}
    bank_ids = set(bank_phase)
    init_progress = _read(os.path.join(fixture_dir, "study_progress.initial.md"))

    assistant_turns = [t for t in turns if t.get("assistant")]
    canon = parse_plan_phases(plan_text)

    # RUNNING PHASE CONTEXT — carried forward so the wrong-phase / over-read checks can't be silently
    # disabled by omitting `phase_context`: a turn without an explicit phase inherits the session's
    # current phase (initial checkpoint → prior explicit phases / progress snapshots).
    running = parse_progress(init_progress)["phase"] or (canon[0] if canon else None)
    turn_phase = []
    for t in turns:
        explicit = _phase_of_turn(t)
        eff = explicit if explicit is not None else running
        turn_phase.append(eff)
        if eff is not None:
            running = eff
        pr = (t.get("files_after") or {}).get("study_progress.md")
        if pr is not None and parse_progress(pr)["phase"] is not None:
            running = parse_progress(pr)["phase"]

    # 1) goal retention — an assistant turn is off-goal if it wanders off / refuses to continue. This is a
    #    COARSE KEYWORD heuristic (blocklist) — it can't catch every paraphrase; full semantic goal-drift
    #    detection is the opt-in LLM path. `goal_marker_seen` is a cheap POSITIVE signal (did the session
    #    ever reference the exam goal at all), enforceable via the optional `goal_marker_min` threshold.
    on_goal = 0
    for t in assistant_turns:
        txt = t.get("assistant", "").lower()                       # case-insensitive (English phrases too)
        drifted = any(p.lower() in txt for p in unrelated) or any(p.lower() in txt for p in refusals)
        on_goal += 0 if drifted else 1
    goal_retention = round(on_goal / len(assistant_turns), 4) if assistant_turns else 1.0
    goal_marker_seen = int(any(any(g in t.get("assistant", "") for g in goal_markers) for t in assistant_turns))

    # 2) plan adherence — walk study_plan.md snapshots; a phase delete/add/reorder is a mutation UNLESS
    #    the mutating turn (or the immediately preceding user turn) explicitly asked to change the plan.
    #    Authorization is scoped to the change, NOT a session-wide latch.
    plan_mutations = 0
    prev_plan, prev_user = canon, ""
    for t in turns:
        u = t.get("user", "")
        fa = t.get("files_after") or {}
        if "study_plan.md" in fa:
            cur_plan = parse_plan_phases(fa["study_plan.md"])
            removed = [p for p in prev_plan if p not in cur_plan]
            added = [p for p in cur_plan if p not in prev_plan]
            reordered = 1 if (set(cur_plan) == set(prev_plan) and cur_plan != prev_plan) else 0
            diff = len(removed) + len(added) + reordered
            authorized = bool(PLAN_CHANGE_REQUEST.search(u) or PLAN_CHANGE_REQUEST.search(prev_user))
            if diff and not authorized:
                plan_mutations += diff
            prev_plan = cur_plan
        if u:
            prev_user = u
    plan_adherence = 1.0 if plan_mutations == 0 else max(0.0, round(1 - plan_mutations / max(1, len(canon)), 4))

    # 3) quiz-bank fidelity / invention — checked against the RUNNING phase (not an opt-in field)
    quiz_items = bank_backed = invented = untagged = wrong_phase = 0
    for i, t in enumerate(turns):
        if not t.get("assistant"):
            continue
        is_quiz = t.get("kind") == "quiz" or bool(QUIZ_TRIGGERS.search(t.get("user", "")))
        if not is_quiz:
            continue                                               # only QUIZ turns are scored — a progress
        ids = extract_quiz_ids(t.get("assistant", ""))             # summary that mentions [#id] isn't a quiz
        want_phase = turn_phase[i]
        for qid in ids:
            quiz_items += 1
            if qid in bank_ids:
                bank_backed += 1
                if want_phase is not None and bank_phase.get(qid) is not None and bank_phase[qid] != want_phase:
                    wrong_phase += 1
            else:
                invented += 1
        if is_quiz and not ids:
            # asked to quiz but produced NO bank-tagged item → count the question-like lines, or the whole
            # turn if it's prose, so a wholesale prose "quiz" with no [#id] tag isn't silently clean.
            q_lines = sum(1 for ln in t.get("assistant", "").splitlines() if looks_like_question(ln))
            untagged += max(1, q_lines)
    invention_rate = round(invented / quiz_items, 4) if quiz_items else 0.0

    # 4) checkpoint recovery — EVERY resume turn must continue from the current phase, not restart earlier.
    reset_count, resumed_phase, expected_phase = 0, None, None
    run_ck = parse_progress(init_progress)["phase"] or (canon[0] if canon else None)
    for t in turns:
        is_resume = t.get("kind") == "resume" or RESUME_TRIGGERS.search(t.get("user", ""))
        if is_resume:
            exp, a = run_ck, t.get("assistant", "")
            m = re.search(r"(?:阶段|phase)\s*(\d+)", a, re.I)
            rp = int(m.group(1)) if m else None
            restart = bool(RESTART_PHRASES.search(a))
            reset_count += int((rp is not None and exp is not None and rp < exp) or (restart and (exp or 1) > 1))
            if expected_phase is None:                            # report the FIRST resume's phases
                expected_phase, resumed_phase = exp, rp
        pr = (t.get("files_after") or {}).get("study_progress.md")
        if pr is not None and parse_progress(pr)["phase"] is not None:
            run_ck = parse_progress(pr)["phase"]
    reset_detected = reset_count

    # 5) provenance fidelity — a turn is an EXPLANATION turn whenever the USER asked to explain (or it is
    #    tagged kind="explanation"); NOT escapable by giving the turn some other `kind` value.
    expl = [t for t in turns if t.get("assistant")
            and (t.get("kind") == "explanation" or EXPLAIN_TRIGGERS.search(t.get("user", "")))]
    labeled = sum(1 for t in expl if has_content_label(t.get("assistant", "")))
    provenance_fidelity = round(labeled / len(expl), 4) if expl else 1.0

    # 6) mistake / confusion persistence — track rows by their [#id] when present (so rewording an existing
    #    row isn't a false 'loss'); rows without an id fall back to normalized text.
    prog_snaps = _snapshots(turns, "study_progress.md", init_progress)
    mistake_added = confusion_added = rows_lost = 0
    parsed = [parse_progress(s) for s in prog_snaps]
    for prev, cur in zip(parsed, parsed[1:]):
        for field, is_m in (("mistake_rows", True), ("confusion_rows", False)):
            pset = {_row_key(r) for r in prev[field]}
            cset = {_row_key(r) for r in cur[field]}
            gained, lost = len(cset - pset), len(pset - cset)
            if is_m:
                mistake_added += gained
            else:
                confusion_added += gained
            rows_lost += lost

    # 7) wiki lazy-load / overread — read events checked against the RUNNING phase (see turn_phase)
    wiki_reads = 0
    seen_wiki, overread = set(), 0
    for i, t in enumerate(turns):
        want_phase = turn_phase[i]
        for ev in (t.get("events") or []):
            if ev.get("type") == "read_file" and str(ev.get("path", "")).startswith("references/wiki/"):
                wiki_reads += 1
                seen_wiki.add(ev["path"])
                ch_phase = _wiki_chapter_phase(ev["path"])
                if want_phase is not None and ch_phase is not None and ch_phase != want_phase:
                    overread = 1                                  # a phase-scoped turn read another phase's chapter
    wiki_files = len(seen_wiki)

    tok_in = [t["tokens_in"] for t in turns if isinstance(t.get("tokens_in"), (int, float))]
    tok_out = [t["tokens_out"] for t in turns if isinstance(t.get("tokens_out"), (int, float))]
    costs = [t["cost_usd"] for t in turns if isinstance(t.get("cost_usd"), (int, float))]
    cost = {
        "has_token_accounting": bool(tok_in or tok_out or costs),
        "total_tokens_in": sum(tok_in), "total_tokens_out": sum(tok_out),
        "total_cost_usd": round(sum(costs), 6),
        # simple context-growth proxy: last vs first tokens_in (>1 means the context grew turn-over-turn)
        "context_growth_ratio": round(tok_in[-1] / tok_in[0], 4) if len(tok_in) >= 2 and tok_in[0] else None,
    }

    return {
        "turns": len(turns), "assistant_turns": len(assistant_turns),
        "goal_retention": goal_retention, "goal_marker_seen": goal_marker_seen,
        "plan_adherence": plan_adherence, "plan_mutations": plan_mutations,
        "quiz_items": quiz_items, "bank_backed": bank_backed, "invented": invented,
        "untagged_questions": untagged, "wrong_phase_quiz": wrong_phase, "invention_rate": invention_rate,
        "resumed_phase": resumed_phase, "expected_phase": expected_phase, "reset_detected": reset_detected,
        "explanation_turns": len(expl), "provenance_fidelity": provenance_fidelity,
        "mistake_rows_added": mistake_added, "confusion_rows_added": confusion_added,
        "progress_rows_lost": rows_lost,
        "wiki_reads": wiki_reads, "unique_wiki_files": wiki_files, "overread_flag": overread,
        "cost": cost,
    }


# ---------------- thresholds ----------------

# threshold key -> (metric key, comparator: 'min' means metric>=value, 'max' means metric<=value)
THRESHOLD_RULES = {
    "goal_retention_min": ("goal_retention", "min"),
    "goal_marker_min": ("goal_marker_seen", "min"),   # positive signal: exam goal referenced ≥ N times (0/1)
    "plan_mutations_max": ("plan_mutations", "max"),
    "quiz_invention_rate_max": ("invention_rate", "max"),
    "untagged_questions_max": ("untagged_questions", "max"),
    "wrong_phase_quiz_max": ("wrong_phase_quiz", "max"),
    "checkpoint_reset_max": ("reset_detected", "max"),
    "provenance_fidelity_min": ("provenance_fidelity", "min"),
    "progress_rows_lost_max": ("progress_rows_lost", "max"),
    "wiki_unique_files_max": ("unique_wiki_files", "max"),
    "overread_max": ("overread_flag", "max"),
}


def check_thresholds(metrics, thresholds):
    """Return (passed, [failure dicts]). Unknown threshold keys are a malformed-scenario error."""
    failures = []
    for key, want in thresholds.items():
        if key not in THRESHOLD_RULES:
            raise DriftError("scenario.thresholds 出现未知阈值 %r" % key)
        mkey, cmp = THRESHOLD_RULES[key]
        got = metrics[mkey]
        ok = (got >= want) if cmp == "min" else (got <= want)
        if not ok:
            failures.append({"threshold": key, "metric": mkey, "got": got, "want": want, "cmp": cmp})
    return (not failures, failures)


def evaluate(scenario, transcript_path):
    fixture_dir = _resolve(scenario["fixture"])
    if not os.path.isdir(fixture_dir):
        raise DriftError("找不到 fixture 目录: %s" % fixture_dir)
    turns = load_jsonl(transcript_path, "transcript")
    if not turns:
        raise DriftError("transcript 为空: %s" % transcript_path)
    if not any(t.get("assistant") or t.get("files_after") or t.get("events") for t in turns):
        # a user-only transcript exercises NOTHING measurable — every metric would default to a perfect
        # value and vacuously PASS, which would make the harness a useless regression gate. Reject it.
        raise DriftError("transcript 没有任何可评估内容（assistant/files_after/events 全空），无法度量漂移")
    metrics = compute_metrics(scenario, fixture_dir, turns)
    passed, failures = check_thresholds(metrics, scenario["thresholds"])
    return {"scenario": scenario["name"], "transcript": os.path.basename(transcript_path),
            "passed": passed, "failures": failures, "metrics": metrics}


# ---------------- CLI ----------------

def _fmt(result):
    m = result["metrics"]
    tag = "PASS" if result["passed"] else "FAIL"
    lines = ["[%s] %s ← %s" % (tag, result["scenario"], result["transcript"]),
             "   goal_retention=%.2f plan_mutations=%d invention_rate=%.2f wrong_phase=%d "
             "reset=%d provenance=%.2f rows_lost=%d wiki_unique=%d overread=%d"
             % (m["goal_retention"], m["plan_mutations"], m["invention_rate"], m["wrong_phase_quiz"],
                m["reset_detected"], m["provenance_fidelity"], m["progress_rows_lost"],
                m["unique_wiki_files"], m["overread_flag"])]
    if m["cost"]["has_token_accounting"]:
        lines.append("   tokens_in=%d tokens_out=%d cost_usd=%s growth=%s"
                     % (m["cost"]["total_tokens_in"], m["cost"]["total_tokens_out"],
                        m["cost"]["total_cost_usd"], m["cost"]["context_growth_ratio"]))
    for f in result["failures"]:
        lines.append("   ✗ %s: got %s, want %s %s" % (f["threshold"], f["got"], f["cmp"], f["want"]))
    return "\n".join(lines)


def run_llm_skeleton():
    """Opt-in real-agent long-session mode — NOT IMPLEMENTED. Never returns success (exit 0)."""
    if os.environ.get("RUN_SKILL_DRIFT_LLM") != "1":
        sys.stderr.write("run_drift: --llm 需 RUN_SKILL_DRIFT_LLM=1 显式开启（真 agent 长会话，opt-in）\n")
        return 2
    sys.stderr.write("run_drift: 真 LLM 长会话漂移测量尚未实现（本 PR 只交付确定性 replay）；不接入、不计成功\n")
    return 3


def main(argv=None):
    for s in ("stdout", "stderr"):
        try:
            getattr(sys, s).reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Tier 4 长程漂移 harness（确定性 replay，无 LLM/网络/依赖）。")
    ap.add_argument("--scenario", help="scenario JSON 路径")
    ap.add_argument("--transcript", help="transcript JSONL 路径（覆盖 scenario 里的默认 transcript）")
    ap.add_argument("--all", action="store_true", help="跑 scenarios/ 下所有 scenario 各自的 transcript")
    ap.add_argument("--json-out", default=None, help="把汇总写到显式路径的 JSON（默认只打印，不写任何 results 目录）")
    ap.add_argument("--llm", action="store_true", help="opt-in 真 agent 长会话（未实现的 skeleton，绝不计成功）")
    args = ap.parse_args(argv)

    if args.llm:
        return run_llm_skeleton()

    results = []
    try:
        if args.all:
            files = sorted(glob.glob(os.path.join(HERE, "scenarios", "*.json")))
            if not files:
                raise DriftError("scenarios/ 下没有任何 scenario")
            for sf in files:
                sc = load_scenario(sf)
                tr = args.transcript or sc.get("transcript")
                if not tr:
                    raise DriftError("scenario %s 没有 transcript 字段，--all 无法确定要 replay 哪个" % sc["name"])
                results.append(evaluate(sc, _resolve(tr)))
        else:
            if not args.scenario:
                raise DriftError("需要 --scenario（或用 --all）")
            sc = load_scenario(args.scenario)
            tr = args.transcript or sc.get("transcript")
            if not tr:
                raise DriftError("未提供 --transcript，且 scenario 无 transcript 字段")
            results.append(evaluate(sc, _resolve(tr)))
    except DriftError as e:
        sys.stderr.write("run_drift: " + str(e) + "\n")
        return 2

    for r in results:
        print(_fmt(r))
    if args.json_out:
        out_dir = os.path.dirname(os.path.abspath(args.json_out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"results": results, "all_passed": all(r["passed"] for r in results)},
                      f, ensure_ascii=False, indent=2)
        print("[+] drift 汇总 →", args.json_out)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
