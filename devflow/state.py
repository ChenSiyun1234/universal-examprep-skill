"""Typed workflow state for the devflow orchestrator.

The state is a ``TypedDict`` so it works directly as a LangGraph state schema. List-valued
fields are annotated with an ``operator.add`` reducer so concurrent / sequential node updates
*append* rather than overwrite — LangGraph honours these reducers natively, and the pure-stdlib
fallback runner in :mod:`devflow.graph` reads the same annotations to merge identically.

Nothing here performs side effects; it only describes the shape of the data that flows through
the graph.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict

# ---- approval gate identifiers (one per human-in-the-loop interrupt) ----
GATE_ADVISORY = "advisory_implementation"   # approve implementing the Codex advisory
GATE_FIX = "blocking_fix"                    # approve fixing blocking review comments
GATE_MERGE = "merge"                         # approve the final merge
APPROVAL_GATES = (GATE_ADVISORY, GATE_FIX, GATE_MERGE)

# decision values
APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"


class DevflowState(TypedDict, total=False):
    """Everything the workflow needs to carry between nodes.

    Fields with an ``Annotated[list, operator.add]`` reducer accumulate across nodes;
    scalar fields are last-write-wins.
    """

    # --- request / identity ---
    task_type: str
    thread_id: str
    repo: str
    branch_name: Optional[str]

    # --- GitHub artifacts (populated as simulated values in dry-run) ---
    issue_number: Optional[int]
    issue_url: Optional[str]
    pr_number: Optional[int]
    pr_url: Optional[str]

    # --- Codex interaction status ---
    codex_advisory_status: str   # "" | "requested" | "ready" | "timeout"
    codex_review_status: str     # "" | "requested" | "ready" | "timeout"
    advisory_packet: Optional[dict]
    review_summary: Optional[dict]

    # --- review findings ---
    blocking_comments: Annotated[list, operator.add]
    non_blocking_comments: Annotated[list, operator.add]
    deferred_followups: Annotated[list, operator.add]

    # --- human decisions ---
    human_approval: Optional[str]   # APPROVED | REJECTED | PENDING
    merge_approval: Optional[str]

    # --- checks / changes ---
    checks_run: Annotated[list, operator.add]
    checks_not_run: Annotated[list, operator.add]
    files_changed: Annotated[list, operator.add]

    # --- diagnostics ---
    errors: Annotated[list, operator.add]
    event_log: Annotated[list, operator.add]

    # --- control / dry-run plumbing (not GitHub data) ---
    dry_run: bool
    # approvals supplied up front (gate -> APPROVED/REJECTED). Used by the fallback runner and
    # as default resume values; with real LangGraph these come from interrupt()/Command(resume=).
    approvals: dict
    # gate at which to deliberately PAUSE (raise an interrupt) instead of auto-deciding.
    pause_at: Optional[str]
    status: str                     # "running" | "paused" | "stopped" | "done"
    halt_reason: Optional[str]
    final_report: Optional[str]

    # --- control channels that nodes/routers read (declared so the real LangGraph StateGraph
    #     does not drop them; LangGraph filters node updates to known channels) ---
    fix_approval: Optional[str]         # decision at the blocking-fix gate
    merge_readiness_ready: bool         # merge_readiness verdict
    rereview_done: bool                 # a re-review completed after fixes
    rereview_blocking: bool             # re-review still found blocking issues
    _simulate: dict                     # dry-run simulation hooks {advisory, review}
    _force_fallback: bool               # force DevflowInterrupt even if langgraph is installed
    paused_at_gate: Optional[str]
    paused_at_node: Optional[str]
    interrupt_payload: dict


def new_state(task_type: str, thread_id: str, repo: str = "ZeKaiNie/universal-examprep-skill",
              approvals: Optional[dict] = None, pause_at: Optional[str] = None,
              dry_run: bool = True) -> DevflowState:
    """Build a fresh initial state. ``dry_run`` is True and cannot be disabled in this scaffold."""
    return DevflowState(
        task_type=task_type,
        thread_id=thread_id,
        repo=repo,
        branch_name=None,
        issue_number=None, issue_url=None, pr_number=None, pr_url=None,
        codex_advisory_status="", codex_review_status="",
        advisory_packet=None, review_summary=None,
        blocking_comments=[], non_blocking_comments=[], deferred_followups=[],
        human_approval=PENDING, merge_approval=PENDING,
        checks_run=[], checks_not_run=[], files_changed=[],
        errors=[], event_log=[],
        dry_run=True,                      # hard-wired: this scaffold never leaves dry-run
        approvals=dict(approvals or {}),
        pause_at=pause_at,
        status="running", halt_reason=None, final_report=None,
    )


# keys whose values accumulate (append) — derived from the Annotated reducers above so the
# fallback runner stays in sync with the schema automatically.
def append_keys() -> set:
    import typing
    keys = set()
    # get_type_hints(..., include_extras=True) resolves the string annotations produced by
    # `from __future__ import annotations` back into real Annotated objects with metadata.
    hints = typing.get_type_hints(DevflowState, include_extras=True)
    for name, hint in hints.items():
        meta = getattr(hint, "__metadata__", None)
        if meta and operator.add in meta:
            keys.add(name)
    return keys
