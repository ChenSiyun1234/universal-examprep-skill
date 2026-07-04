#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Universal Tier-3 full-course matrix runner (B4) — any course, config-driven.

Replaces gen.py's hardcoded algo/psyc `COURSES` dict: describe your course(s) in a config and this
drives the whole T3 pipeline — generate (blind answers per model × arm) → score (judge) → aggregate
(bridges to the tested aggregate_matrix.py) → summary.json that report_matrix.py renders.

Arms (configurable; default 3 operationally-sound ones):
  · closedbook — model answers from prior knowledge only (prior-knowledge floor; should abstain on OOS)
  · rawfiles   — fair no-skill agentic baseline: reads the course's raw files on demand (Read/Glob/Grep)
  · skill      — runs inside the skill workspace (references/wiki lazy-load, the anti-hallucination regime)
  (the whole-material "dump" arm is intentionally omitted by default — operationally infeasible: it burns
   quota and overflows context on big courses; add "material" to arms if you want it.)

Run it WITHOUT spending any Claude quota first — the shipped fixture course runs end-to-end offline:
    python run_matrix.py --mock                    # fixture course, deterministic, no claude/network/keys
    python run_matrix.py --mock --config myconfig.json
Then for real (uses your logged-in Claude Code subscription; resumable, quota-aware):
    python run_matrix.py --config myconfig.json    # (mock defaults false in your config)

--mock is a DETERMINISTIC STAND-IN: it fabricates placeholder answers (gold for answerable, abstain for
OOS) and scores them with judge.mock_judge, so the whole pipeline runs and a sample summary.json is
produced — it measures NOTHING (same honest posture as run_benchmark.py --mock / judge.mock_judge).

Pure stdlib + reuses gen.py (run_claude/classify) and judge.py / aggregate_matrix.py; no new deps.
"""
import argparse
import json
import os
import hashlib
import subprocess
import sys
import time

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen                              # noqa: E402  复用 run_claude/classify/arm 提示词
import judge as J                       # noqa: E402  judge_answer / mock_judge

DEFAULT_ARMS = ["closedbook", "rawfiles", "skill"]
DEFAULT_MODELS = ["opus", "sonnet", "haiku"]
KNOWN_ARMS = {"closedbook", "rawfiles", "material", "skill"}
_FIXTURE_CONFIG = os.path.join(HERE, "fixtures", "mini_course_matrix", "config.json")


def _die(msg, code=2):
    sys.stderr.write("run_matrix: " + msg + "\n")
    raise SystemExit(code)


# ---------------- config ----------------

def _resolve(base_dir, p):
    """config 里的相对路径按 **config 文件所在目录** 解析（不是 cwd）。"""
    if not isinstance(p, str) or not p or os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(base_dir, p))


def load_config(path):
    if not os.path.isfile(path):
        _die("找不到 config: %s" % path)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except ValueError as e:
        _die("config 不是合法 JSON: %s" % e)
    if not isinstance(cfg, dict):
        _die("config 顶层必须是对象")
    courses = cfg.get("courses")
    if not isinstance(courses, list) or not courses:
        _die("config.courses 必须是非空数组（每门课含 name/combined/items/skill_ws/raw_ws）")
    base = os.path.dirname(os.path.abspath(path))
    seen = set()
    for c in courses:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"].strip():
            _die("每门课必须有非空字符串 name")
        if c["name"] in seen:
            _die("课程 name 重复: %s" % c["name"])
        seen.add(c["name"])
        for k in ("combined", "items", "skill_ws", "raw_ws"):
            if c.get(k):
                c[k] = _resolve(base, c[k])
    # 只在 key 缺席时用默认；显式 "arms":[] / "models":[] 不当"缺席"（否则空矩阵会悄悄跑满全默认臂×模型）
    cfg["arms"] = cfg["arms"] if "arms" in cfg else DEFAULT_ARMS
    cfg["models"] = cfg["models"] if "models" in cfg else DEFAULT_MODELS
    # arms/models 必须是非空字符串数组——否则 "skill"（漏了方括号）会被逐字符迭代成 s/k/i/l 假臂
    for _k in ("arms", "models"):
        v = cfg[_k]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
            _die("config.%s 必须是非空字符串数组（别漏方括号）" % _k)
    bad = [a for a in cfg["arms"] if a not in KNOWN_ARMS]
    if bad:
        _die("未知 arm: %s（应为 %s 的子集）" % ("/".join(bad), "/".join(sorted(KNOWN_ARMS))))
    for _k in ("arms", "models"):
        if len(cfg[_k]) != len(set(cfg[_k])):
            _die("config.%s 有重复项：%s（重复会造出同 key 的任务、聚合时撞重复）" % (_k, cfg[_k]))
    # 选了某臂就必须声明对应路径 key（存在性在真跑前 _preflight_real 再查——mock 不读这些）
    _ARM_PATH = {"rawfiles": "raw_ws", "skill": "skill_ws", "material": "combined"}
    for c in courses:
        for arm in cfg["arms"]:
            k = _ARM_PATH.get(arm)
            if k and not c.get(k):
                _die("课程 %s 选了 %s 臂，但缺 %s 路径" % (c["name"], arm, k))
    cfg["results_dir"] = _resolve(base, cfg.get("results_dir") or "results/matrix_run")
    cfg["_courses_by_name"] = {c["name"]: c for c in courses}
    names = list(cfg["_courses_by_name"])
    cfg["primary_course"] = cfg.get("primary_course") or names[0]
    if cfg["primary_course"] not in cfg["_courses_by_name"]:
        _die("primary_course 不在 courses 里: %s" % cfg["primary_course"])
    if cfg.get("secondary_course") and cfg["secondary_course"] not in cfg["_courses_by_name"]:
        _die("secondary_course 不在 courses 里: %s" % cfg["secondary_course"])
    return cfg


def load_items(course):
    path = course.get("items")
    if not path or not os.path.isfile(path):
        _die("课程 %s 的 items 找不到: %s" % (course.get("name"), path))
    items, seen = [], {}
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                d = json.loads(s)
            except ValueError as e:                    # 坏行明确报 exit-2 + 行号，不抛原生 traceback
                _die("课程 %s 的 items 第 %d 行不是合法 JSON: %s" % (course.get("name"), ln, e))
            if not (isinstance(d, dict) and d.get("id") and d.get("question")):
                # 题集定义评测全集，坏行不能静默丢（会缩小分母、伪装成"看着正常"的更小摘要）
                _die("课程 %s 的 items 第 %d 行缺 id 或 question——拒绝静默丢弃" % (course.get("name"), ln))
            # 必须是**金标**：要有 answer_type + answerable；可答题还要有 gold_answer。
            # 否则误指到 *_q.jsonl（只 id+question 的盲测题面）会拿空 gold 判分甚至数值题崩。
            if "answer_type" not in d or "answerable" not in d:
                _die("课程 %s 的 items 第 %d 行缺 answer_type/answerable——像是问题-only 文件（*_q.jsonl），"
                     "请指向带金标的 items 文件" % (course.get("name"), ln))
            if d.get("answerable") is not False and not str(d.get("gold_answer", "")).strip():
                _die("课程 %s 的 items 第 %d 行 answerable 但无 gold_answer——金标缺失，无法判分"
                     % (course.get("name"), ln))
            rid = str(d["id"])
            if rid in seen:
                _die("课程 %s 的 items 第 %d 行 id 重复：%s（首见于第 %d 行）"
                     % (course.get("name"), ln, rid, seen[rid]))
            seen[rid] = ln
            items.append(d)
    return items


# ---------------- generate ----------------

def _read(path):
    return open(path, encoding="utf-8").read() if path and os.path.isfile(path) else ""


def mock_answer(arm, item):
    """确定性占位作答（无 claude）：可答题回 gold（judge→correct），越界探针回弃答标记。
    诚实：这只验管线通不通，不测量任何正确率。"""
    if item.get("answerable") is False:
        return J.ABSTAIN_MARKERS[0]                    # "材料中未涵盖" → 判为正确弃答
    return str(item.get("gold_answer", "")) or J.ABSTAIN_MARKERS[0]


def real_answer(cfg, course, model, arm, item):
    """真跑：按臂 shell claude（复用 gen.run_claude）。生成端只见 question，绝不见 gold。"""
    q = item["question"]
    if arm == "closedbook":
        return gen.run_claude(gen.CLOSEDBOOK.format(q=q), model)
    if arm == "material":
        return gen.run_claude(gen.MATERIAL.format(material=_read(course.get("combined")), q=q), model)
    if arm == "rawfiles":
        return gen.run_claude(gen.RAWFILES.format(q=q), model,
                              cwd=os.path.relpath(course["raw_ws"], HERE), skill=True)
    if arm == "skill":
        return gen.run_claude(gen.SKILL.format(q=q), model,
                              cwd=os.path.relpath(course["skill_ws"], HERE), skill=True)
    _die("未知 arm: %s" % arm)


def _preflight_real(cfg):
    """真跑前校验所选臂需要的路径**存在**——否则 material 臂拿空材料作答仍标 material（伪造该臂），
    或 raw_ws/skill_ws 打错只表现为可重试的 API Error 被无限重试。存在性只对真跑要求（mock 不读）。"""
    checks = {"material": ("combined", os.path.isfile),
              "rawfiles": ("raw_ws", os.path.isdir),
              "skill": ("skill_ws", os.path.isdir)}
    for c in cfg["courses"]:
        for arm in cfg["arms"]:
            if arm not in checks:
                continue
            key, exists = checks[arm]
            p = c.get(key)
            if not p or not exists(p):
                _die("课程 %s 的 %s 臂需要 %s 存在，但路径缺失/不存在：%s" % (c["name"], arm, key, p))


def build_tasks(cfg):
    """确定性任务序：course × arm × model × item。返回 [(course_name, model, arm, item)]。"""
    tasks = []
    for c in cfg["courses"]:
        items = load_items(c)
        for arm in cfg["arms"]:
            for model in cfg["models"]:
                for it in items:
                    tasks.append((c["name"], model, arm, it))
    return tasks


# ---------------- score ----------------

def score_row(course_name, model, arm, item, answer, mock, judge_model="haiku"):
    """返回 (score_row, judge_infra_failed)。judge_infra_failed=True 表示判分侧 claude 撞了配额/超时/API 错
    （不是裁判真判不了）——这种 score 不该落盘当"已完成"，否则永远不会重判。"""
    infra = {"failed": False}
    if mock:
        ask = lambda p: J.mock_judge(p)
    else:
        def ask(p):
            out = _real_ask_judge(p, judge_model)
            if _classify(out) != "ok":                  # 判分侧撞配额/超时/API 错
                infra["failed"] = True
            return out
    verdict = J.judge_answer(item, answer, ask, judge_repeats=1)
    f = verdict.get("faithfulness")                     # judge_error 时可能为 None——原样透传（aggregate 接受 None/缺省）
    row = {"course": course_name, "model": model, "arm": arm, "item_id": item["id"],
           "answerable": bool(item.get("answerable", True)),
           "correct": bool(verdict.get("correct")),
           "hallucinated": int(verdict.get("hallucinated", 0)),
           "abstained": bool(verdict.get("abstained")),
           "judge_error": int(verdict.get("judge_error", 0)),
           "faithfulness": (None if f is None else float(f)),
           "scored_by": verdict.get("scored_by", "mock" if mock else "llm")}
    return row, infra["failed"]


def _real_ask_judge(prompt, judge_model):               # 真跑判分：shell claude（用 config 指定的裁判模型）
    out, _cost = gen.run_claude(prompt, judge_model)
    return out


# ---------------- run ----------------

def _cache_key(course, model, arm, item_id):
    # json 化的元组身份——避免课程名/题号里带 '|' 时两个不同任务碰撞成同一 key
    return json.dumps([course, model, arm, str(item_id)], ensure_ascii=False)


_PUBLISHED = os.path.normcase(os.path.realpath(os.path.join(HERE, "results", "matrix")))


def _assert_not_published(results_dir):
    if os.path.normcase(os.path.realpath(results_dir)) == _PUBLISHED:
        _die("results_dir 指向已发布的 results/matrix——拒绝覆盖已提交的真实结果，请换一个 --results-dir")


def _classify(answer):
    # gen.classify + TIMEOUT 归入 transient（可重试）——否则 900s 超时会被当正常答案判成"答错"
    if (answer or "").strip() == "TIMEOUT":
        return "transient"
    return gen.classify(answer)


def _generate_real(cfg, course, model, arm, item):
    """真跑一题：瞬时错误/超时按 gen.py 退避重试 3 次。返回 (answer, cost, kind)。"""
    ans, cost = "", 0.0
    for attempt in range(3):
        ans, cost = real_answer(cfg, course, model, arm, item)
        kind = _classify(ans)
        if kind in ("ok", "hard"):
            return ans, cost or 0.0, kind
        time.sleep(5 * (attempt + 1) ** 2)             # 5s, 20s, 45s（仅真跑触发）
    return ans, cost or 0.0, _classify(ans)


def _load_answers_map(ans_path):
    """已作答的行 {key: row}——崩溃后"有答案没判分"的任务据此**重判**（而非当 judge_error 永久钉死），
    且重判只写 score 不重写 answer，避免重复 answer 行卡死 aggregate。"""
    m = {}
    if os.path.isfile(ans_path):
        with open(ans_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                    m[_cache_key(d["course"], d["model"], d["arm"], d["item_id"])] = d
                except (ValueError, KeyError):
                    continue
    return m


def _scored_keys(score_path):
    """已判分的任务 key —— 完全完成（答案+判分都在）的集合，跳过之。"""
    keys = set()
    if os.path.isfile(score_path):
        with open(score_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                    keys.add(_cache_key(d["course"], d["model"], d["arm"], d["item_id"]))
                except (ValueError, KeyError):
                    continue
    return keys


def _config_fingerprint(cfg):
    """决定任务集 + 判分的配置指纹：课程名/各路径、模型、臂、主/次课程。改了任一 → 指纹变。"""
    sig = {
        "courses": sorted((c["name"], c.get("items"), c.get("combined"),
                           c.get("skill_ws"), c.get("raw_ws")) for c in cfg["courses"]),
        "models": sorted(cfg["models"]),
        "arms": sorted(cfg["arms"]),
        "primary": cfg["primary_course"],
        "secondary": cfg.get("secondary_course"),
    }
    return hashlib.md5(json.dumps(sig, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _assert_run_meta(results_dir, mock, cfg):
    """同一 results_dir 的产物必须同 mock/real **且**同 config——否则：
    ① 先 --mock 后 --real 同目录会把占位当已完成、真跑 todo=0 不打 claude、按真裁判标签聚合占位行；
    ② 改了 config（课程/题集/模型/臂）复用旧目录，旧 answers/scores 会和新配置混聚出对不上的摘要。"""
    mode = "mock" if mock else "real"
    fp = _config_fingerprint(cfg)
    meta_path = os.path.join(results_dir, ".run_meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                prev = json.load(f)
        except ValueError:
            prev = {}
        if prev.get("mode") and prev["mode"] != mode:
            _die("results_dir 已有 %s 运行的产物，拒绝与 %s 混用——请换一个 --results-dir（mock/real 别同目录）"
                 % (prev["mode"], mode))
        if prev.get("fingerprint") and prev["fingerprint"] != fp:
            _die("results_dir 的产物来自**不同的 config**（课程/题集/模型/臂变了）——旧 answers/scores 会和新配置"
                 "混聚出对不上的摘要；请换一个干净的 --results-dir")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"mode": mode, "fingerprint": fp}, f, ensure_ascii=False)


def _answers_has_course(ans_path, course):
    if not os.path.isfile(ans_path):
        return False
    with open(ans_path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                if json.loads(s).get("course") == course:
                    return True
            except ValueError:
                continue
    return False


def run(cfg, mock, limit=0):
    results_dir = cfg["results_dir"]
    _assert_not_published(results_dir)
    if not mock:
        _preflight_real(cfg)                            # 真跑前校验各臂路径存在（mock 不读）
    os.makedirs(results_dir, exist_ok=True)
    _assert_run_meta(results_dir, mock, cfg)            # mock/real 不混 + config 指纹不匹配即拒
    ans_path = os.path.join(results_dir, "answers.jsonl")
    score_path = os.path.join(results_dir, "scores.jsonl")
    summary_path = os.path.join(results_dir, "summary.json")
    judge_label = "mock" if mock else (cfg.get("judge_model") or "haiku")

    answered = _load_answers_map(ans_path)              # 已作答（可能没判分）
    scored = _scored_keys(score_path)                   # 已判分（完全完成）

    tasks = build_tasks(cfg)
    if limit:
        tasks = tasks[:limit]
    todo = [t for t in tasks if _cache_key(t[0], t[1], t[2], t[3]["id"]) not in scored]
    print("[matrix] 任务 %d，已判分 %d，本次待处理 %d（%s）"
          % (len(tasks), len(tasks) - len(todo), len(todo), "mock 占位" if mock else "real"))

    total_cost = 0.0
    n_ok = n_rescore = n_skip = hard_streak = 0
    t0 = time.time()
    quota_stop = False
    af = open(ans_path, "a", encoding="utf-8")
    sf = open(score_path, "a", encoding="utf-8")
    try:
        for cname, model, arm, item in todo:
            key = _cache_key(cname, model, arm, item["id"])
            course = cfg["_courses_by_name"][cname]
            if key in answered:
                # 崩溃后"有答案没判分"——只重判、不重新生成、不重写 answer（防重复行）
                srow, jf = score_row(cname, model, arm, item, answered[key].get("answer", ""), mock, judge_label)
                if jf:                                  # 判分侧撞配额/超时 → 不落 score，下次 resume 重判
                    n_skip += 1
                    continue
                sf.write(json.dumps(srow, ensure_ascii=False) + "\n"); sf.flush()
                n_rescore += 1
                continue
            if mock:
                answer, cost = mock_answer(arm, item), 0.0
            else:
                answer, cost, kind = _generate_real(cfg, course, model, arm, item)
                if kind == "hard":
                    hard_streak += 1
                    n_skip += 1                         # 硬失败也是跳过——计数，让"未完成不聚合"守卫触发
                    if hard_streak >= 6:
                        quota_stop = True
                        print("[matrix] 连撞订阅配额上限，停在此（已作答的都存好了）——配额恢复后再跑续。")
                        break
                    continue                            # 不写 → 下次续跑重试
                hard_streak = 0
                if kind != "ok" or not (answer or "").strip():
                    n_skip += 1                         # 瞬时/超时重试后仍失败 → 不写，下次 resume 重试
                    continue
            # 写 answer（真答案不浪费）；判分侧若撞配额/超时则不落 score，下次 resume 重判
            total_cost += cost or 0.0
            arow = {"course": cname, "model": model, "arm": arm, "item_id": item["id"],
                    "answerable": bool(item.get("answerable", True)), "status": "ok",
                    "answer": answer, "cost_usd": cost or 0.0}
            af.write(json.dumps(arow, ensure_ascii=False) + "\n"); af.flush()
            srow, jf = score_row(cname, model, arm, item, answer, mock, judge_label)
            if jf:
                n_skip += 1
                continue
            sf.write(json.dumps(srow, ensure_ascii=False) + "\n"); sf.flush()
            n_ok += 1
    finally:
        af.close(); sf.close()

    print("[matrix] 新作答 %d（重判 %d，跳过/待续 %d），累计成本 $%.4f，用时 %ds"
          % (n_ok, n_rescore, n_skip, total_cost, int(time.time() - t0)))

    # 主课程还没有任何作答行 → 跳过聚合、报可续、退 0
    if not _answers_has_course(ans_path, cfg["primary_course"]):
        print("[matrix] 主课程 %s 暂无作答行——跳过聚合（%s）。"
              % (cfg["primary_course"], "配额未恢复，稍后再跑 --real 续" if quota_stop else "先补齐作答再聚合"))
        return None

    # 真跑未完成（撞配额 / 有失败跳过，且非 --limit 的有意部分跑）→ 不聚合，别把半截跑伪装成完成的测量
    if not mock and not limit and (quota_stop or n_skip > 0):
        print("[matrix] 真跑未完成（%s）——跳过聚合，避免把更小分母伪装成完成的测量；恢复后再跑到 0 剩余再聚合。"
              % ("撞配额停" if quota_stop else "有 %d 个任务失败待重试" % n_skip))
        return None

    # 桥接到 aggregate_matrix.py（那套 honest 聚合规则的唯一实现）
    agg = [sys.executable, os.path.join(HERE, "aggregate_matrix.py"),
           "--answers", ans_path, "--scores", score_path, "--out", summary_path,
           "--primary-course", cfg["primary_course"], "--judge-model", judge_label]
    if cfg.get("secondary_course") and _answers_has_course(ans_path, cfg["secondary_course"]):
        agg += ["--secondary-course", cfg["secondary_course"]]   # 有该课作答行才聚合它（部分跑不硬失败）
    r = subprocess.run(agg, capture_output=True, text=True, encoding="utf-8")
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        _die("aggregate_matrix 失败：%s" % (r.stderr or "").strip(), 1)
    print("[matrix] -> %s（%s）" % (summary_path, "mock 占位摘要，未测量正确率" if mock else "已聚合"))
    return summary_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="通用 Tier-3 全量矩阵 runner（B4）")
    ap.add_argument("--config", default=None, help="课程矩阵 config.json（缺省用自带 fixture 课程）")
    ap.add_argument("--mock", action="store_true", help="确定性离线干跑（无 claude/网络/密钥）")
    ap.add_argument("--real", action="store_true", help="真跑（shell claude；resumable、配额感知）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个任务（快速冒烟）")
    ap.add_argument("--results-dir", dest="results_dir", default=None,
                    help="输出目录（覆盖 config.results_dir；按 cwd 解析）")
    args = ap.parse_args(argv)

    cfg = load_config(args.config or _FIXTURE_CONFIG)
    if args.results_dir is not None:
        cfg["results_dir"] = os.path.abspath(args.results_dir)
    mock = True
    if args.real:
        mock = False
    if args.mock:
        mock = True
    if not args.real and not args.mock:
        mock = bool(cfg.get("mock", True))              # 缺省看 config，默认 mock
    run(cfg, mock=mock, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
