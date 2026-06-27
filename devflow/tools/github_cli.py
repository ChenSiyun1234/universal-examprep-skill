"""GitHub tool layer for devflow.

Two clearly separated pieces:

* :class:`DryRunGitHub` — *write* operations (issue/PR/branch/merge). In this scaffold these are
  recorded no-ops; a future, explicitly-flagged PR will add a real backend.
* Read-only layer (:class:`ReadOnlyGitHub` + :func:`check_gh_available`) — inspects issues, PRs,
  comments and reviews via the ``gh`` CLI. **Strictly read-only**: every ``gh`` invocation passes
  through :func:`_assert_read_only`, which refuses anything that is not an allow-listed read shape
  (and refuses ``gh api`` with a non-GET method or write-style ``-f/--field`` flags). There is no
  code path here that can create, comment, push, or merge.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Optional


# ======================================================================================
# Write layer (recorded no-ops in this scaffold) — unchanged from the initial scaffold
# ======================================================================================
class DryRunGitHub:
    """Records intended GitHub *write* operations without performing them."""

    def __init__(self, repo: str):
        self.repo = repo
        self.calls: list[dict] = []
        self._issue_seq = 1000
        self._pr_seq = 2000

    def _record(self, op: str, **kwargs) -> dict:
        entry = {"op": op, "repo": self.repo, **kwargs, "executed": False, "dry_run": True}
        self.calls.append(entry)
        return entry

    def create_issue(self, title: str, body: str, labels: Optional[list] = None) -> dict:
        self._issue_seq += 1
        n = self._issue_seq
        self._record("create_issue", title=title, labels=labels or [])
        return {"number": n, "url": f"https://github.com/{self.repo}/issues/{n}", "simulated": True}

    def comment(self, target: str, number: int, body: str) -> dict:
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
        self._record("merge_pr", number=number, method=method)
        return {"merged": False, "simulated": True, "note": "dry-run: merge not executed"}


# ======================================================================================
# Read-only layer
# ======================================================================================
class GhError(RuntimeError):
    """Raised for gh unavailability, auth failure, refused (non-read-only) commands, or gh errors."""


# allow-listed read-only command shapes (matched on the leading 1-2 tokens)
_ALLOWED_READ_PREFIXES = {
    ("auth", "status"),
    ("repo", "view"),
    ("issue", "view"),
    ("pr", "view"),
    ("pr", "diff"),
    ("pr", "list"),
    ("issue", "list"),
    ("api",),  # GET only — enforced below
}
# flags that turn `gh api` into a write (gh api defaults to POST when any field is supplied)
_API_WRITE_FLAGS = {"-f", "--field", "-F", "--raw-field", "--input"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _assert_read_only(args: list[str]) -> None:
    """Refuse any gh invocation that is not an allow-listed read. The single safety chokepoint."""
    if not args:
        raise GhError("empty gh command")
    if args[0] == "api":
        for i, tok in enumerate(args):
            base = tok.split("=", 1)[0]               # handle both `--field x` and `--field=x`
            if base in _API_WRITE_FLAGS:
                raise GhError(f"refused: write-style `gh api` flag {tok!r}")
            if base in ("-X", "--method"):
                method = (tok.split("=", 1)[1] if "=" in tok
                          else (args[i + 1] if i + 1 < len(args) else "")).upper()
                if method in _WRITE_METHODS:
                    raise GhError(f"refused: `gh api` method {method}")
        return
    if tuple(args[:2]) in _ALLOWED_READ_PREFIXES or (args[0],) in _ALLOWED_READ_PREFIXES:
        return
    raise GhError(f"refused: non-read-only gh command: {' '.join(args[:3])}…")


def _run_gh(args: list[str], timeout: int = 60) -> str:
    """Run an allow-listed read-only ``gh`` command and return stdout. Raises :class:`GhError`."""
    _assert_read_only(args)               # safety gate BEFORE any process is spawned
    if shutil.which("gh") is None:
        raise GhError("gh CLI not found on PATH. Install it and run `gh auth login`.")
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as e:  # pragma: no cover - covered by shutil.which guard
        raise GhError(f"gh CLI not found: {e}")
    except subprocess.TimeoutExpired:
        raise GhError(f"gh command timed out after {timeout}s: {' '.join(args[:3])}…")
    if proc.returncode != 0:
        raise GhError((proc.stderr or proc.stdout or "gh command failed").strip())
    return proc.stdout


def _gh_json(args: list[str], timeout: int = 60):
    out = _run_gh(args, timeout=timeout)
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError as e:
        raise GhError(f"could not parse gh JSON output: {e}")


def _flatten_pages(slurped):
    """`gh api --paginate --slurp` yields one JSON array whose elements are per-page responses
    (each itself an array). Flatten one level. Tolerant of an already-flat list."""
    if isinstance(slurped, list) and slurped and isinstance(slurped[0], list):
        return [item for page in slurped for item in page]
    if isinstance(slurped, list):
        return slurped
    return [] if slurped is None else [slurped]


def _gh_json_paginated(path: str, timeout: int = 60):
    """Paginated GET that stays valid JSON across pages via ``--slurp`` (then flattened)."""
    return _flatten_pages(_gh_json(["api", path, "--paginate", "--slurp"], timeout=timeout))


def check_gh_available() -> dict:
    """Report gh availability + authentication. Never raises — returns a structured status."""
    if shutil.which("gh") is None:
        return {"available": False, "authenticated": False,
                "error": "gh CLI not found on PATH. Install GitHub CLI and run `gh auth login`."}
    try:
        out = _run_gh(["auth", "status"])
    except GhError as e:
        return {"available": True, "authenticated": False,
                "error": f"gh is installed but not authenticated: {e}"}
    account = None
    m = re.search(r"account\s+(\S+)", out) or re.search(r"Logged in to \S+ account (\S+)", out)
    if m:
        account = m.group(1)
    return {"available": True, "authenticated": True, "account": account, "error": None}


# -- Codex detection / parsing ---------------------------------------------------------
# Exact, trusted Codex/ChatGPT-connector logins. We match EXACTLY (case-insensitive) rather than
# "login contains codex/chatgpt", because on a public repo anyone could pick a login like
# "codex-fan" and spoof the integration.
_TRUSTED_CODEX_LOGINS = {
    "chatgpt-codex-connector[bot]", "chatgpt-codex-connector",
    "codex", "codex[bot]",
}


def is_codex_author(login: Optional[str]) -> bool:
    return bool(login) and login.strip().lower() in _TRUSTED_CODEX_LOGINS


def parse_review_packet(body: str, state: Optional[str] = None) -> dict:
    """Light, defensive parse of a Codex review body into a structured-ish packet.

    Heuristics only (no model call): a review is treated as *blocking* if its review state is
    CHANGES_REQUESTED or the body mentions blocking language. Bullet lines are collected as items.
    """
    text = body or ""
    low = text.lower()
    # word-boundary match; the negative lookbehind keeps "non-blocking" from counting as blocking
    blocking = (state or "").upper() == "CHANGES_REQUESTED" or bool(
        re.search(r"(?<!non-)\bblocking\b|\bmust fix\b|\brequired change\b|\brequest changes\b", low))
    bullets = [ln.strip(" -*\t") for ln in text.splitlines() if ln.strip().startswith(("-", "*"))]
    return {
        "state": state,
        "blocking": blocking,
        "items": bullets,
        "body": text,
    }


class ReadOnlyGitHub:
    """Read-only inspection of a repo's issues, PRs, comments, and reviews via ``gh``."""

    def __init__(self, repo: Optional[str] = None):
        self._repo = repo

    # repo resolution -------------------------------------------------------------------
    def resolve_repo(self) -> str:
        if not self._repo:
            data = _gh_json(["repo", "view", "--json", "nameWithOwner"])
            self._repo = (data or {}).get("nameWithOwner")
            if not self._repo:
                raise GhError("could not determine repo; pass repo='owner/name' or run inside a repo")
        return self._repo

    def get_repo_info(self) -> dict:
        repo = self._repo or "{owner}/{repo}"
        args = ["repo", "view"] + ([repo] if self._repo else []) + [
            "--json", "nameWithOwner,name,owner,defaultBranchRef,url,isPrivate"]
        data = _gh_json(args) or {}
        return {
            "name_with_owner": data.get("nameWithOwner"),
            "name": data.get("name"),
            "owner": (data.get("owner") or {}).get("login"),
            "default_branch": (data.get("defaultBranchRef") or {}).get("name"),
            "url": data.get("url"),
            "private": data.get("isPrivate"),
        }

    # comments / reviews ----------------------------------------------------------------
    @staticmethod
    def _norm_comments(raw) -> list:
        out = []
        for c in raw or []:
            out.append({
                "author": (c.get("user") or {}).get("login"),
                "body": c.get("body") or "",
                "created_at": c.get("created_at"),
                "url": c.get("html_url"),
            })
        return out

    def get_issue_comments(self, issue_number: int) -> list:
        repo = self.resolve_repo()
        return self._norm_comments(
            _gh_json_paginated(f"repos/{repo}/issues/{int(issue_number)}/comments"))

    def get_pr_comments(self, pr_number: int) -> list:
        # PR conversation comments live on the issues endpoint for the same number
        repo = self.resolve_repo()
        return self._norm_comments(
            _gh_json_paginated(f"repos/{repo}/issues/{int(pr_number)}/comments"))

    def get_pr_review_comments(self, pr_number: int) -> list:
        # file-level (inline) review comments — a separate endpoint from conversation comments
        repo = self.resolve_repo()
        return self._norm_comments(
            _gh_json_paginated(f"repos/{repo}/pulls/{int(pr_number)}/comments"))

    def get_pr_reviews(self, pr_number: int) -> list:
        repo = self.resolve_repo()
        raw = _gh_json_paginated(f"repos/{repo}/pulls/{int(pr_number)}/reviews")
        out = []
        for r in raw or []:
            out.append({
                "author": (r.get("user") or {}).get("login"),
                "body": r.get("body") or "",
                "state": r.get("state"),
                "created_at": r.get("submitted_at"),
                "url": r.get("html_url"),
            })
        return out

    # Codex helpers ---------------------------------------------------------------------
    def find_latest_codex_advisory(self, issue_number: int) -> Optional[dict]:
        comments = [c for c in self.get_issue_comments(issue_number) if is_codex_author(c["author"])]
        if not comments:
            return None
        latest = max(comments, key=lambda c: c.get("created_at") or "")
        return {
            "source": "issue_comment",
            "issue_number": int(issue_number),
            "author": latest["author"],
            "created_at": latest["created_at"],
            "url": latest["url"],
            "body": latest["body"],
        }

    def find_latest_codex_review(self, pr_number: int) -> Optional[dict]:
        candidates = []
        for c in self.get_pr_comments(pr_number):
            if is_codex_author(c["author"]):
                candidates.append({**c, "source": "pr_comment", "state": None})
        for c in self.get_pr_review_comments(pr_number):       # inline/file-level review comments
            if is_codex_author(c["author"]):
                candidates.append({**c, "source": "pr_review_comment", "state": None})
        for r in self.get_pr_reviews(pr_number):
            if is_codex_author(r["author"]):
                candidates.append({**r, "source": "pr_review"})
        if not candidates:
            return None
        latest = max(candidates, key=lambda c: c.get("created_at") or "")
        packet = parse_review_packet(latest["body"], latest.get("state"))
        # Preserve a CHANGES_REQUESTED verdict even if a later (e.g. COMMENTED) entry is newest.
        if any((c.get("state") or "").upper() == "CHANGES_REQUESTED" for c in candidates):
            packet["blocking"] = True
        return {
            "source": latest["source"],
            "pr_number": int(pr_number),
            "author": latest["author"],
            "created_at": latest["created_at"],
            "url": latest.get("url"),
            **packet,
        }
