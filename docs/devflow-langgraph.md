# devflow — LangGraph development-workflow orchestrator (dry-run scaffold)

`devflow/` is a small orchestrator that models how a change moves through this repository:
advisory → implement → review → merge, with human approval gates and Codex (AI reviewer)
interactions. **This first PR is a dry-run scaffold only**: it builds the graph, runs mock nodes,
simulates Codex responses, and prints a report. It performs **no** real GitHub mutations, network
calls, or AI-provider API calls.

## How this differs from the Exam Prep product runtime

| | Exam Prep product (the skill) | devflow (this package) |
|---|---|---|
| Purpose | Help a student cram for an exam | Automate *development of this repo* |
| Audience | End users / students | Maintainers / CI |
| Runtime deps | Pure Python stdlib (no pip) | stdlib by default; LangGraph optional (dev only) |
| Side effects | Reads/writes the user's study workspace | *Would* touch GitHub — but disabled in this PR |

devflow is **developer tooling**, not part of the product. It must never be imported by, or add
dependencies to, the Exam Prep runtime.

## The state machine

```
start
  → check_environment
  → create_advisory_issue
  → request_codex_advisory
  → wait_for_codex_advisory ──(timeout)──────────────► post_merge_report (safe stop)
  → summarize_advisory
  → human_approval ──────────(rejected)──────────────► post_merge_report (safe stop)
  → apply_approved_changes
  → run_checks
  → commit_push_branch
  → create_draft_pr
  → request_codex_review
  → wait_for_codex_review ───(timeout)───────────────► post_merge_report (safe stop)
  → summarize_review ────────(no blocking comments)──► merge_readiness   (skip fix gate)
  → human_fix_approval ──────(rejected)──────────────► post_merge_report (safe stop)
  → fix_blocking_comments
  → request_codex_rereview
  → merge_readiness ─────────(not ready)─────────────► post_merge_report (safe stop)
  → human_merge_approval ────(rejected)──────────────► post_merge_report (safe stop)
  → claude_execute_merge     (dry-run: NEVER actually merges)
  → post_merge_report → END
```

State is a typed `TypedDict` (`devflow/state.py`). List fields (`event_log`, `errors`,
`blocking_comments`, `files_changed`, …) use an `operator.add` reducer so node updates *append*;
scalar fields are last-write-wins. The fallback runner reads the same annotations so both backends
merge identically. Key fields: `task_type, thread_id, repo, branch_name, issue_number, issue_url,
pr_number, pr_url, codex_advisory_status, codex_review_status, advisory_packet, review_summary,
blocking_comments, non_blocking_comments, deferred_followups, human_approval, merge_approval,
checks_run, checks_not_run, files_changed, errors, event_log`.

## Two interchangeable backends

`devflow/graph.py:build_graph()` returns either:

* **LangGraph backend** — used automatically if `langgraph` is importable. Builds a real
  `StateGraph`, compiles it with a `MemorySaver` checkpointer, and pauses at approval gates with
  native `interrupt()` (resumed via `Command(resume=...)`).
* **Fallback backend** — pure stdlib (the default here, since langgraph is an *optional* dev dep).
  A deterministic runner walks the same node/edge map and pauses by raising `DevflowInterrupt`.

Both expose `.invoke(state)` and the same nodes/routing, so behaviour is identical; only the
interrupt/checkpoint machinery differs.

The CLI **defaults to the stdlib backend** (fully supported). The real LangGraph backend is
opt-in and experimental via `--langgraph` (`pip install langgraph`); when selected, the CLI passes
a `config={"configurable": {"thread_id": …}}` so its `MemorySaver` checkpointer works, and the
fallback runner sets `_force_fallback` so approval gates always use `DevflowInterrupt` rather than
LangGraph's native `interrupt()` when running under the stdlib backend. `DevflowState` declares all
control channels (`fix_approval`, `merge_readiness_ready`, `rereview_done`, `_simulate`, …) so the
real `StateGraph` does not drop them. An explicit `pause_at` always pauses its gate, even if an
approval was seeded. `merge_readiness` requires a **completed** (re-)review — never merge-ready while
a re-review is only "requested".

## How human approval gates work

There are three gates, each calling `request_human_decision(...)` **exactly once per node
invocation** (one interrupt per node — never inside a loop):

1. **advisory implementation** (`human_approval`)
2. **blocking fix** (`human_fix_approval`)
3. **merge** (`human_merge_approval`)

A decision is resolved by (a) a value pre-seeded in `state["approvals"][gate]` — the dry-run policy
or the resume payload — otherwise (b) the workflow pauses: a real `interrupt()` under LangGraph, or
a `DevflowInterrupt` in fallback mode. A rejected gate routes to a safe stop. Approve/reject is never
inferred; the run halts until a decision is supplied.

## What is dry-run in this PR (hard boundaries)

The scaffold **does not**: create GitHub issues, post `@codex` comments, create branches/PRs, push,
or merge; it does not edit product files, add LangGraph to the product runtime, or make any
Claude/Codex/OpenAI/Anthropic API calls. `devflow/tools/github_cli.py` is the single chokepoint for
GitHub operations and every method is a recorded no-op (`executed: False`). `run_checks` does **not**
execute checks and therefore never claims any passed — it records them under `checks_not_run`.
No secrets, no API keys, no paid CI, no GitHub Actions.

## Usage

```bash
# end-to-end dry-run (all gates auto-approved) -> prints a final report
python -m devflow.cli run --task docs-advisory --thread-id demo-1

# demonstrate a human-approval pause (interrupt) then resume
python -m devflow.cli run    --task docs-advisory --thread-id demo-2 --pause-at advisory
python -m devflow.cli resume --thread-id demo-2 --gate advisory --decision approved

# safe-stop routes
python -m devflow.cli run --task docs-advisory --thread-id demo-3 --reject merge
python -m devflow.cli run --task docs-advisory --thread-id demo-4 --simulate-review clean
python -m devflow.cli run --task docs-advisory --thread-id demo-5 --simulate-advisory timeout
```

Tests: `python -m unittest tests.test_devflow_graph`

## Dependency note

The repo has no product dependency file and the product is intentionally stdlib-only. To avoid
silently changing that strategy, LangGraph is declared as an **optional dev dependency** scoped to
this tool in `devflow/requirements-dev.txt`. devflow runs fully without it (stdlib fallback);
installing it only upgrades the orchestrator to the real LangGraph backend.

## Planned next PRs

1. **Read-only GitHub integration** — real `gh`/API reads (issue/PR status) behind the same
   `DryRunGitHub` interface, still no mutations.
2. **GitHub issue/PR write integration** — gated, explicit, non-default mutations (create issue,
   open draft PR) with confirmation.
3. **Codex polling** — replace the simulated advisory/review with real `@codex` request + bounded
   polling for responses.
4. **Merge approval execution** — wire `claude_execute_merge` to a real, human-approved merge.
