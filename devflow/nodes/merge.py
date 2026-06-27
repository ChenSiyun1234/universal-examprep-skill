"""Merge phase nodes. The merge is NEVER executed in this scaffold."""

from __future__ import annotations

from devflow.state import DevflowState, APPROVED, REJECTED
from devflow.tools.github_cli import DryRunGitHub


def _derive_halt(state: DevflowState):
    """Infer a human-readable safe-stop reason from the state, if the run did not complete."""
    if state.get("codex_advisory_status") == "timeout":
        return "codex advisory timed out"
    if state.get("human_approval") == REJECTED:
        return "advisory implementation rejected"
    if state.get("fix_approval") == REJECTED:
        return "blocking-fix rejected"
    if state.get("codex_review_status") == "timeout":
        return "codex review timed out"
    if state.get("merge_approval") == REJECTED:
        return "merge rejected"
    if state.get("review_summary") is not None and not state.get("merge_readiness_ready"):
        return "not merge-ready"
    return None


def merge_readiness(state: DevflowState) -> dict:
    """Assess readiness: no unresolved blocking comments and review is ready."""
    blocking = state.get("blocking_comments", [])
    # In dry-run, fix_blocking_comments doesn't remove items; treat 'fix:' files_changed as resolution.
    resolved = any(str(f).startswith("fix:") for f in state.get("files_changed", []))
    ready = (not blocking) or resolved
    return {
        "merge_readiness_ready": ready,
        "event_log": [f"[merge_readiness] ready={ready} "
                      f"(blocking={len(blocking)}, fixes_applied={resolved})."],
    }


def claude_execute_merge(state: DevflowState) -> dict:
    """Would execute the merge — but in this scaffold it is a recorded no-op."""
    gh = DryRunGitHub(state["repo"])
    res = gh.merge_pr(state.get("pr_number") or 0)
    return {
        "status": "running",
        "event_log": [f"[claude_execute_merge] dry-run: merge NOT executed ({res['note']})."],
    }


def post_merge_report(state: DevflowState) -> dict:
    """Terminal node: build a readable final report covering whatever path was taken
    (completed, or safely stopped at a rejected gate / timeout)."""
    merged = state.get("merge_approval") == APPROVED and bool(state.get("merge_readiness_ready"))
    halt = state.get("halt_reason") or _derive_halt(state)
    lines = [
        "================ devflow dry-run report ================",
        f"task_type        : {state.get('task_type')}",
        f"thread_id        : {state.get('thread_id')}",
        f"repo             : {state.get('repo')}",
        f"branch_name      : {state.get('branch_name')}",
        f"issue            : #{state.get('issue_number')} {state.get('issue_url')}",
        f"pr               : #{state.get('pr_number')} {state.get('pr_url')}",
        f"advisory_status  : {state.get('codex_advisory_status')}",
        f"review_status    : {state.get('codex_review_status')}",
        f"advisory_approval: {state.get('human_approval')}",
        f"fix_approval     : {state.get('fix_approval')}",
        f"merge_approval   : {state.get('merge_approval')}",
        f"blocking         : {len(state.get('blocking_comments', []))}",
        f"non_blocking     : {len(state.get('non_blocking_comments', []))}",
        f"checks_run       : {state.get('checks_run', [])}",
        f"checks_not_run   : {state.get('checks_not_run', [])}",
        f"files_changed    : {state.get('files_changed', [])}",
        f"errors           : {state.get('errors', [])}",
        f"merge performed  : NO (dry-run scaffold; merges are never executed)",
        f"outcome          : {'stopped: ' + halt if halt else ('would-merge' if merged else 'completed (no merge)')}",
        "-------------------------------------------------------",
        "event log:",
    ]
    lines += [f"  {i+1:2d}. {e}" for i, e in enumerate(state.get("event_log", []))]
    lines.append("=======================================================")
    report = "\n".join(lines)
    return {"final_report": report, "status": "done",
            "event_log": ["[post_merge_report] final report generated."]}
