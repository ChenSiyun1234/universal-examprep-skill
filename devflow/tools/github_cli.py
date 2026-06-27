"""DRY-RUN GitHub CLI wrapper.

This module is the single chokepoint for anything that *would* touch GitHub (issues, PRs,
branches, merges). In this scaffold every method is a no-op that records the command it would
have run and returns a deterministic simulated result. **No `gh`/`git` subprocess is ever
executed here** — that is asserted by the tests.

A future PR can add a real backend behind the same interface, gated behind an explicit,
non-default ``live=True`` plus credentials. The default is, and in this PR must remain, dry-run.
"""

from __future__ import annotations

from typing import Optional


class DryRunGitHub:
    """Records intended GitHub operations without performing them."""

    def __init__(self, repo: str):
        self.repo = repo
        self.calls: list[dict] = []        # audit trail of what *would* have happened
        self._issue_seq = 1000
        self._pr_seq = 2000

    # -- internal --
    def _record(self, op: str, **kwargs) -> dict:
        entry = {"op": op, "repo": self.repo, **kwargs, "executed": False, "dry_run": True}
        self.calls.append(entry)
        return entry

    # -- simulated operations (return simulated identifiers/urls) --
    def create_issue(self, title: str, body: str, labels: Optional[list] = None) -> dict:
        self._issue_seq += 1
        n = self._issue_seq
        self._record("create_issue", title=title, labels=labels or [])
        return {"number": n, "url": f"https://github.com/{self.repo}/issues/{n}", "simulated": True}

    def comment(self, target: str, number: int, body: str) -> dict:
        # target in {"issue", "pr"}; body may contain an "@codex ..." mention in real usage.
        self._record("comment", target=target, number=number, body_preview=body[:80])
        return {"posted": False, "simulated": True}

    def create_branch(self, name: str, base: str = "main") -> dict:
        self._record("create_branch", name=name, base=base)
        return {"branch": name, "base": base, "simulated": True}

    def push_branch(self, name: str) -> dict:
        self._record("push_branch", name=name)
        return {"pushed": False, "simulated": True}

    def create_pr(self, head: str, base: str, title: str, body: str, draft: bool = True) -> dict:
        self._pr_seq += 1
        n = self._pr_seq
        self._record("create_pr", head=head, base=base, title=title, draft=draft)
        return {"number": n, "url": f"https://github.com/{self.repo}/pull/{n}",
                "draft": draft, "simulated": True}

    def merge_pr(self, number: int, method: str = "squash") -> dict:
        # Intentionally a no-op in this scaffold: merges are never executed.
        self._record("merge_pr", number=number, method=method)
        return {"merged": False, "simulated": True, "note": "dry-run: merge not executed"}
