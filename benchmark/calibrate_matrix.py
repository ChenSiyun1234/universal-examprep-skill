#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B5 判分校准（通用）：对 run_matrix 的**任意课程**输出做「人工 vs 裁判」Cohen's kappa 校准。

取代 calibrate.py 硬编码的 algo/psyc——直接读 B4 `run_matrix` 的 results_dir（answers.jsonl + scores.jsonl）
配 config 的金标，任意课程可用。流程：
  1) sample —— 抽**分层**样本（一半裁判判对、一半判错，避免 kappa 退化），写出**隐藏裁判判定**的待填表；
              你只看 question + gold + reference_span 判 model_answer 对不对（越界题以「是否老实弃答」为准），
              在 human_correct 列填 1/0。
  2) kappa  —— 填完后算 Cohen's kappa(human, judge) + 原始一致率 + 列出人机分歧（裁判最可能错的地方）。

    python calibrate_matrix.py sample --results-dir <dir> --config <config.json> --n 30 [--seed 7]
    python calibrate_matrix.py kappa  --results-dir <dir>

诚实：kappa < ~0.6 时别信任裁判数字（先改裁判/题目）。**跨家族裁判**：裁判与生成器同模型家族（都 Claude）
有自我偏好嫌疑——sample 会警告，建议换个不同家族的裁判重判再校准。纯 stdlib、零依赖。
"""
import argparse
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_matrix as RM   # noqa: E402  复用 load_config/load_items
import stats as S         # noqa: E402  cohen_kappa

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

# 待填表**不含 model/arm**——标注者看到答案来自 skill/closedbook/某模型会带偏判断（隐藏在 key 里，留作后续按臂分析）
_FIELDS = ["ref_id", "course", "answerable", "question", "gold_answer",
           "reference_span", "model_answer", "human_correct"]


def _die(msg, code=2):
    sys.stderr.write("calibrate_matrix: " + msg + "\n")
    raise SystemExit(code)


def _flat(s):
    return " ".join(str(s or "").split())


def _model_family(model):
    m = (model or "").lower()
    if any(t in m for t in ("opus", "sonnet", "haiku", "claude")):
        return "claude"
    if "gemini" in m:
        return "gemini"
    if any(t in m for t in ("gpt", "o1", "o3", "openai")):
        return "openai"
    if "deepseek" in m:
        return "deepseek"
    if "mock" in m:
        return "mock"
    return m or "unknown"


def _load_jsonl(path):
    out = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    try:
                        out.append(json.loads(s))
                    except ValueError:
                        continue
    return out


def build_pool(results_dir, cfg):
    """把 answers.jsonl + scores.jsonl + config 金标 join 成校准池（只留有裁判判定的项）。"""
    ans_rows = _load_jsonl(os.path.join(results_dir, "answers.jsonl"))
    score_rows = _load_jsonl(os.path.join(results_dir, "scores.jsonl"))
    if not ans_rows or not score_rows:
        _die("results_dir 里没有 answers.jsonl / scores.jsonl（先跑 run_matrix 生成）：%s" % results_dir)
    # 金标：course → {id: item}
    gold = {}
    for c in cfg["courses"]:
        gold[c["name"]] = {str(it["id"]): it for it in RM.load_items(c)}

    def key(r):
        return (r.get("course"), r.get("model"), r.get("arm"), str(r.get("item_id")))
    answers = {key(r): r.get("answer", "") for r in ans_rows}
    pool = []
    for sc in score_rows:
        if sc.get("judge_error"):                      # 判分失败：没有有效裁判判定，不进校准池
            continue
        k = key(sc)
        item = gold.get(sc.get("course"), {}).get(str(sc.get("item_id")))
        if item is None or k not in answers:
            continue
        pool.append({
            "course": sc.get("course"), "model": sc.get("model"), "arm": sc.get("arm"),
            "id": str(sc.get("item_id")),
            "answerable": bool(item.get("answerable", True)),
            "answer_type": item.get("answer_type", "factual"),
            "scored_by": sc.get("scored_by"),
            "question": item.get("question", ""), "gold_answer": item.get("gold_answer", ""),
            "reference_span": item.get("supporting_span", ""), "answer": answers[k],
            "judge_correct": 1 if sc.get("correct") else 0,
        })
    return pool


def _is_deterministic(p):
    """数值题(check_numeric)与词法快路(scored_by=lexical)是确定性判分——它们天然一致会灌水 kappa，
    不测被校准的 LLM 裁判，校准时排除。"""
    return p.get("answer_type") == "numeric" or p.get("scored_by") == "lexical"


def _sheet_paths(out_dir):
    return (os.path.join(out_dir, "calibration_sheet.csv"),
            os.path.join(out_dir, ".calibration_key.jsonl"))


def cmd_sample(args):
    cfg = RM.load_config(args.config)
    pool = build_pool(args.results_dir, cfg)
    if not pool:
        _die("没有可抽样的条目（answers/scores 与 config 金标对不上，或题集为空）")

    # 只校准 LLM 裁判真正判的项——排除确定性判分（numeric/lexical 快路），它们天然一致会灌高 kappa。
    judged = [p for p in pool if not _is_deterministic(p)]
    det_n = len(pool) - len(judged)
    if judged:
        pool = judged
        if det_n:
            print("[i] 已排除 %d 条确定性判分（numeric/词法快路）——它们不测 LLM 裁判、会灌水 kappa。" % det_n)
    else:
        print("[i] 池里全是确定性判分（numeric/词法快路），无 LLM 裁判判定可校准——照抽以验流程，但 kappa 对裁判无意义。")

    rng = random.Random(args.seed)
    pos = [p for p in pool if p["judge_correct"] == 1]
    neg = [p for p in pool if p["judge_correct"] == 0]
    rng.shuffle(pos); rng.shuffle(neg)
    half = args.n // 2
    pick = pos[:half] + neg[:args.n - half]
    if len(pick) < args.n:                              # 一层不够就用另一层补满
        extra = (pos[half:] + neg[args.n - half:])
        rng.shuffle(extra)
        pick += extra[:args.n - len(pick)]
    rng.shuffle(pick)

    out_dir = args.out_dir or os.path.join(args.results_dir, "calibration")
    os.makedirs(out_dir, exist_ok=True)
    sheet, keyp = _sheet_paths(out_dir)
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f, open(keyp, "w", encoding="utf-8") as kf:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for i, p in enumerate(pick, 1):
            ref = "cal_%03d" % i
            note = "" if p["answerable"] else "  ←【越界题：材料无答案，正确=老实弃答】"
            w.writerow({"ref_id": ref, "course": p["course"],
                        "answerable": int(p["answerable"]),
                        "question": _flat(p["question"]) + note, "gold_answer": _flat(p["gold_answer"]),
                        "reference_span": _flat(p["reference_span"]),
                        "model_answer": _flat(p["answer"]), "human_correct": ""})
            # model/arm 藏进 key（不进待填表，避免带偏标注），留作后续按臂/模型分析
            kf.write(json.dumps({"ref_id": ref, "judge_correct": p["judge_correct"],
                                 "model": p["model"], "arm": p["arm"]}, ensure_ascii=False) + "\n")

    n_pos = sum(1 for p in pick if p["judge_correct"] == 1)   # 实际抽到的判对/判错数（一层空时补满会打破半分）
    print("[+] 抽样 %d 条（裁判判对 %d / 判错 %d），已写待填表：\n    %s"
          % (len(pick), n_pos, len(pick) - n_pos, sheet))
    if n_pos == len(pick) or n_pos == 0:
        print("    注：这批裁判判定全同（分层不成）——真校准需 answers/scores 里判对判错都有（真跑数据）。")
    tail = "" if not args.out_dir else " --out-dir %s" % args.out_dir   # 自定义 out-dir 也带进续跑命令
    print("    用 Excel/编辑器打开，给 human_correct 列填 1（对/可接受）或 0（错）；填完跑："
          "python calibrate_matrix.py kappa --results-dir %s%s" % (args.results_dir, tail))
    _warn_self_preference(args.results_dir, pool)
    return 0


def _warn_self_preference(results_dir, pool):
    """裁判与生成器同家族 → 自我偏好嫌疑。裁判模型从 summary.json 读，生成器家族从 pool 的 model 推。"""
    judge_model = None
    sp = os.path.join(results_dir, "summary.json")
    if os.path.isfile(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                judge_model = json.load(f).get("judge_model")
        except ValueError:
            pass
    if not judge_model:
        return
    jf = _model_family(judge_model)
    gen_families = {_model_family(p["model"]) for p in pool}
    if jf in gen_families and jf not in ("mock", "unknown"):
        print("    ⚠️ 跨家族提醒：裁判(%s，家族=%s) 与生成器家族 %s 重叠——有自我偏好嫌疑；"
              "建议用不同家族的裁判重判后再校准，或在报告里注明。"
              % (judge_model, jf, "/".join(sorted(gen_families))))


def cmd_kappa(args):
    out_dir = args.out_dir or os.path.join(args.results_dir, "calibration")
    sheet, keyp = _sheet_paths(out_dir)
    if not (os.path.isfile(sheet) and os.path.isfile(keyp)):
        _die("找不到 calibration_sheet.csv / .calibration_key.jsonl（先跑 sample）：%s" % out_dir)
    key = {d["ref_id"]: d["judge_correct"] for d in _load_jsonl(keyp)}
    with open(sheet, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    human, judge, disagree, blank, unmatched = [], [], [], 0, 0
    for r in rows:
        hv = (r.get("human_correct") or "").strip()
        if hv not in ("0", "1"):
            blank += 1
            continue
        ref = r["ref_id"]
        if ref not in key:
            unmatched += 1                             # 填了但 ref_id 对不上 key（表被改/串了）——别静默丢
            continue
        h, j = int(hv), int(key[ref])
        human.append(h); judge.append(j)
        if h != j:
            disagree.append((ref, j, h, (r.get("question", "") or "")[:70]))
    n = len(human)
    if n == 0:
        _die("还没有已填的 human_correct（%d 行为空，%d 行 ref_id 对不上 key）。先在 %s 填好再跑。"
             % (blank, unmatched, sheet), 1)
    if unmatched:
        sys.stderr.write("calibrate_matrix: ⚠️ %d 行已填但 ref_id 对不上 .calibration_key.jsonl（表可能被改/换过）"
                         "——这些行未计入 kappa。\n" % unmatched)
    agree = sum(1 for h, j in zip(human, judge) if h == j) / n
    k = S.cohen_kappa(human, judge)
    print("=== 人工 vs 裁判一致性（n=%d，未填 %d，未匹配 %d）===" % (n, blank, unmatched))
    print("  原始一致率 agreement = %.1f%%" % (agree * 100))
    print("  Cohen's kappa        = %.3f   ->  %s"
          % (k, "可信(>=0.6)" if k >= 0.6 else "偏低，先改进裁判/题目再信任数字"))
    if disagree:
        print("\n  人机分歧 %d 条（judge=裁判判, human=你判；这些是裁判最可能错的地方）：" % len(disagree))
        for ref, j, h, q in disagree:
            print("    %s: judge=%d human=%d | %s" % (ref, j, h, q))
    else:
        print("\n  无分歧 —— 裁判与你完全一致。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="通用判分校准（人工 vs 裁判 kappa，源自 run_matrix 输出）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("sample", help="抽分层样本、生成待填校准表")
    sp.add_argument("--results-dir", required=True, help="run_matrix 的 results_dir")
    sp.add_argument("--config", required=True, help="对应的 config.json（读金标）")
    sp.add_argument("--n", type=int, default=30)
    sp.add_argument("--seed", type=int, default=7)
    sp.add_argument("--out-dir", default=None, help="待填表输出目录（默认 results_dir/calibration）")
    kp = sub.add_parser("kappa", help="读已填表算 Cohen's kappa")
    kp.add_argument("--results-dir", required=True)
    kp.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "sample":
        return cmd_sample(args)
    return cmd_kappa(args)


if __name__ == "__main__":
    raise SystemExit(main())
