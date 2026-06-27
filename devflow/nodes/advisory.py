"""Advisory phase nodes — create an advisory issue, ask Codex for an advisory, wait for it,
and summarize it. All GitHub/Codex interactions are simulated (dry-run)."""

from __future__ import annotations

from devflow.state import DevflowState
from devflow.tools.github_cli import DryRunGitHub


def create_advisory_issue(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    res = gh.create_issue(
        title=f"[advisory] {state['task_type']}",
        body="Dry-run advisory request. (No real issue is created in this scaffold.)",
        labels=["devflow", "advisory"],
    )
    return {
        "issue_number": res["number"], "issue_url": res["url"],
        "event_log": [f"[create_advisory_issue] dry-run: would open issue -> {res['url']}"],
    }


def request_codex_advisory(state: DevflowState) -> dict:
    gh = DryRunGitHub(state["repo"])
    gh.comment("issue", state.get("issue_number") or 0,
               "@codex please provide an implementation advisory for this task.")
    return {
        "codex_advisory_status": "requested",
        "event_log": ["[request_codex_advisory] dry-run: would post '@codex' advisory request "
                      "comment — not posted."],
    }


def wait_for_codex_advisory(state: DevflowState) -> dict:
    """Simulate polling for Codex's advisory.

    Honours an injected ``state['_simulate']['advisory'] == 'timeout'`` to exercise the
    bounded-wait/stop routing without any real polling.
    """
    sim = (state.get("_simulate") or {}).get("advisory", "ready")
    if sim == "timeout":
        return {
            "codex_advisory_status": "timeout",
            "errors": ["codex advisory did not arrive within the (simulated) bound"],
            "event_log": ["[wait_for_codex_advisory] dry-run: simulated TIMEOUT waiting for Codex."],
        }
    packet = {
        "task_type": state["task_type"],
        "recommended_steps": [
            "scope the change to a dry-run scaffold",
            "model the workflow as a typed state graph",
            "add tests + docs; avoid real side effects",
        ],
        "risks": ["scope creep into product runtime", "accidental real GitHub mutations"],
        "source": "simulated-codex-advisory",
    }
    return {
        "codex_advisory_status": "ready", "advisory_packet": packet,
        "event_log": ["[wait_for_codex_advisory] dry-run: simulated Codex advisory received."],
    }


def summarize_advisory(state: DevflowState) -> dict:
    packet = state.get("advisory_packet") or {}
    steps = packet.get("recommended_steps", [])
    summary = "Advisory: " + "; ".join(steps) if steps else "Advisory: (empty)"
    return {
        "advisory_packet": {**packet, "summary": summary},
        "event_log": [f"[summarize_advisory] {summary}"],
    }
