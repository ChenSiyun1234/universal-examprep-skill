"""devflow command-line entry point.

    python -m devflow.cli run --task docs-advisory --thread-id demo-1

Everything is dry-run. By default all three human-approval gates auto-approve so the workflow
runs end-to-end and prints a final report. Use the flags to exercise the human-in-the-loop
behaviour:

    --reject GATE        reject a gate (advisory|fix|merge) -> safe stop
    --pause-at GATE      pause at a gate (interrupt) instead of auto-approving
    --simulate-review X  X in {blocking, clean, timeout}
    --simulate-advisory X X in {ready, timeout}

Resume a paused thread:

    python -m devflow.cli resume --thread-id demo-1 --gate advisory --decision approved
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

from devflow.graph import build_graph, GATE_TO_NODE
from devflow.state import (
    new_state, APPROVED, REJECTED, APPROVAL_GATES,
    GATE_ADVISORY, GATE_FIX, GATE_MERGE,
)

# Windows GBK consoles otherwise mangle the report box-drawing / CJK text.
for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

_GATE_ALIASES = {"advisory": GATE_ADVISORY, "fix": GATE_FIX, "merge": GATE_MERGE}

# checkpoint dir for cross-invocation resume (tool's own state — NOT a product/GitHub artifact)
CKPT_DIR = os.path.join(tempfile.gettempdir(), "devflow_runs")


def _ckpt_path(thread_id: str) -> str:
    # append a hash of the ORIGINAL id so distinct ids that sanitize to the same name
    # (e.g. "demo/a" vs "demo_a") never collide and overwrite each other's checkpoint.
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in thread_id)
    digest = hashlib.sha1(thread_id.encode("utf-8")).hexdigest()[:8]
    return os.path.join(CKPT_DIR, f"{safe}-{digest}.json")


def _save_ckpt(state: dict) -> str:
    os.makedirs(CKPT_DIR, exist_ok=True)
    p = _ckpt_path(state["thread_id"])
    serializable = {k: v for k, v in state.items() if k != "interrupt_payload" or isinstance(v, (dict, list, str, int, float, type(None)))}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    return p


def _load_ckpt(thread_id: str) -> dict:
    with open(_ckpt_path(thread_id), "r", encoding="utf-8") as f:
        return json.load(f)


def _approvals_from_args(args) -> dict:
    approvals = {g: APPROVED for g in APPROVAL_GATES}
    for g in (args.reject or []):
        approvals[_GATE_ALIASES[g]] = REJECTED
    if args.pause_at:
        approvals.pop(_GATE_ALIASES[args.pause_at], None)  # not seeded -> will pause/interrupt
    return approvals


def _print_outcome(state: dict) -> None:
    if state.get("final_report"):
        print(state["final_report"])
    if state.get("status") == "paused":
        gate = state.get("paused_at_gate")
        print("\n*** PAUSED at human-approval gate: "
              f"{gate} ***")
        print("Interrupt payload:")
        print(json.dumps(state.get("interrupt_payload", {}), ensure_ascii=False, indent=2))
        alias = next((a for a, full in _GATE_ALIASES.items() if full == gate), gate)
        print(f"\nResume with:\n  python -m devflow.cli resume --thread-id "
              f"{state['thread_id']} --gate {alias} --decision approved")


def _invoke(app, state, start_node=None):
    """Invoke either backend. The real LangGraph backend (opt-in) needs a per-thread config with
    a configurable.thread_id for its MemorySaver checkpointer; the stdlib fallback uses start_node."""
    if getattr(app, "backend", "") == "langgraph":
        return app.invoke(state, config={"configurable": {"thread_id": state.get("thread_id", "devflow")}})
    return app.invoke(state, start_node=start_node) if start_node else app.invoke(state)


def cmd_run(args) -> int:
    state = new_state(
        task_type=args.task, thread_id=args.thread_id, repo=args.repo,
        approvals=_approvals_from_args(args),
    )
    if args.simulate_advisory or args.simulate_review:
        state["_simulate"] = {"advisory": args.simulate_advisory or "ready",
                              "review": args.simulate_review or "blocking"}
    # Default to the fully-supported stdlib backend; --langgraph opts into the experimental one.
    app = build_graph(prefer_fallback=not args.langgraph)
    print(f"[devflow] backend={getattr(app, 'backend', '?')}  dry_run=True  "
          f"task={args.task}  thread={args.thread_id}")
    final = _invoke(app, state)
    if final.get("status") == "paused":
        _save_ckpt(final)
    _print_outcome(final)
    return 0


def cmd_resume(args) -> int:
    try:
        state = _load_ckpt(args.thread_id)
    except FileNotFoundError:
        print(f"[devflow] no checkpoint for thread '{args.thread_id}'. Run it first.\n"
              "Note: `resume` supports the stdlib backend only. A run started with --langgraph "
              "pauses via LangGraph's native interrupt (no JSON checkpoint is written) and must be "
              "resumed through LangGraph's own Command(resume=...) — not wired into this CLI yet.")
        return 1
    gate = _GATE_ALIASES[args.gate]
    decision = APPROVED if args.decision == "approved" else REJECTED
    state.setdefault("approvals", {})[gate] = decision
    start = state.get("paused_at_node") or GATE_TO_NODE.get(gate)
    state["status"] = "running"
    app = build_graph(prefer_fallback=True)  # resume uses the stdlib runner's start_node support
    print(f"[devflow] resume thread={args.thread_id} gate={args.gate} decision={decision}")
    final = app.invoke(state, start_node=start)
    if final.get("status") == "paused":
        _save_ckpt(final)
    else:
        try:
            os.remove(_ckpt_path(args.thread_id))
        except OSError:
            pass
    _print_outcome(final)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="devflow", description="Dry-run LangGraph devflow orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the dry-run workflow")
    r.add_argument("--task", default="docs-advisory", help="task type (e.g. docs-advisory)")
    r.add_argument("--thread-id", required=True, help="thread id for this run")
    r.add_argument("--repo", default="ZeKaiNie/universal-examprep-skill")
    r.add_argument("--reject", action="append", choices=list(_GATE_ALIASES),
                   help="reject a gate (repeatable) -> safe stop")
    r.add_argument("--pause-at", choices=list(_GATE_ALIASES),
                   help="pause (interrupt) at this gate instead of auto-deciding")
    r.add_argument("--simulate-advisory", choices=["ready", "timeout"])
    r.add_argument("--simulate-review", choices=["blocking", "clean", "timeout"])
    r.add_argument("--langgraph", action="store_true",
                   help="use the EXPERIMENTAL real LangGraph backend (requires `pip install "
                        "langgraph`); default is the fully-supported stdlib backend")
    r.set_defaults(func=cmd_run)

    rs = sub.add_parser("resume", help="resume a paused thread with an approval decision")
    rs.add_argument("--thread-id", required=True)
    rs.add_argument("--gate", required=True, choices=list(_GATE_ALIASES))
    rs.add_argument("--decision", required=True, choices=["approved", "rejected"])
    rs.set_defaults(func=cmd_resume)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
