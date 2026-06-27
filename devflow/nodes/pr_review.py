"""Implementation + review phase nodes (all dry-run / simulated)."""

from __future__ import annotations

from devflow.state import DevflowState
from devflow.tools.github_cli import DryRunGitHub


def apply_approved_changes(state: DevflowState) -> dict:
    """Simulate applying the approved changes. NO files are edited in this scaffold."""
    planned = ["devflow/<scaffold files>"]  # representative, not an actual edit
    return {
        "files_changed": planned,
        "event_log": ["[apply_approved_changes] dry-run: would apply approved edits — "
                      "no files actually modified."],
    }


def run_checks(state: DevflowState) -> dict:
    """Dry-run: does NOT execute any checks, so it must not claim any passed.

    Records what *would* run under ``checks_not_run`` with an explicit dry-run note.
    """
    return {
        "checks_not_run": [
            "unit tests (dry-run: not executed)",
            "lint (dry-run: not executed)",
        ],
        "event_log": ["[run_checks] dry-run: checks NOT executed (recorded as not-run)."],
    }


def commit_push_branch(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    gh.create_branch(state.get("branch_name") or "devflow/scaffold")
    gh.push_branch(state.get("branch_name") or "devflow/scaffold")
    return {"event_log": [f"[commit_push_branch] dry-run: would commit & push "
                          f"'{state.get('branch_name')}' — not pushed."]}


def create_draft_pr(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    res = gh.create_pr(head=state.get("branch_name") or "devflow/scaffold", base="main",
                       title=f"[devflow] {state['task_type']}", body="dry-run scaffold", draft=True)
    return {
        "pr_number": res["number"], "pr_url": res["url"],
        "event_log": [f"[create_draft_pr] dry-run: would open DRAFT PR -> {res['url']}"],
    }


def request_codex_review(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    gh.comment("pr", state.get("pr_number") or 0, "@codex review this PR.")
    return {"codex_review_status": "requested",
            "event_log": ["[request_codex_review] dry-run: would post '@codex review' — not posted."]}


def wait_for_codex_review(state: DevflowState) -> dict:
    """Simulate Codex returning a review. ``state['_simulate']['review']`` can be:
    'clean' (no blocking), 'blocking' (default), or 'timeout'."""
    sim = (state.get("_simulate") or {}).get("review", "blocking")
    if sim == "timeout":
        return {"codex_review_status": "timeout",
                "errors": ["codex review did not arrive within the (simulated) bound"],
                "event_log": ["[wait_for_codex_review] dry-run: simulated TIMEOUT."]}
    blocking = [] if sim == "clean" else [
        {"path": "devflow/graph.py", "note": "simulated: handle empty advisory packet"},
    ]
    non_blocking = [{"path": "docs/devflow-langgraph.md", "note": "simulated: add a diagram"}]
    deferred = [{"note": "simulated: real GitHub backend in a later PR"}]
    return {
        "codex_review_status": "ready",
        "blocking_comments": blocking,
        "non_blocking_comments": non_blocking,
        "deferred_followups": deferred,
        "event_log": [f"[wait_for_codex_review] dry-run: simulated review "
                      f"({len(blocking)} blocking, {len(non_blocking)} non-blocking)."],
    }


def summarize_review(state: DevflowState) -> dict:
    nb = len(state.get("non_blocking_comments", []))
    b = len(state.get("blocking_comments", []))
    summary = {"blocking": b, "non_blocking": nb,
               "deferred": len(state.get("deferred_followups", []))}
    return {"review_summary": summary,
            "event_log": [f"[summarize_review] {b} blocking / {nb} non-blocking comments."]}


def fix_blocking_comments(state: DevflowState) -> dict:
    """Simulate addressing blocking comments (no real edits)."""
    fixed = [c.get("path", "?") for c in state.get("blocking_comments", [])]
    return {
        "files_changed": [f"fix:{p}" for p in fixed],
        "event_log": [f"[fix_blocking_comments] dry-run: would address {len(fixed)} blocking "
                      f"comment(s) — no files modified."],
    }


def request_codex_rereview(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    gh.comment("pr", state.get("pr_number") or 0, "@codex re-review after fixes.")
    return {"codex_review_status": "rereview_requested",
            "event_log": ["[request_codex_rereview] dry-run: would request re-review — not posted."]}
