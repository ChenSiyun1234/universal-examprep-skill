#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect, claim, validate, apply, and rebuild typed ingestion review work."""

import argparse
import json
import os
import sys

try:
    from ingestion import IngestionStore, ReviewPatch, read_json
    from ingestion.pipeline import (
        BUILD_MANIFEST_PATH,
        compile_review_outputs,
        refresh_build_manifest,
    )
except ImportError:
    from scripts.ingestion import IngestionStore, ReviewPatch, read_json
    from scripts.ingestion.pipeline import (
        BUILD_MANIFEST_PATH,
        compile_review_outputs,
        refresh_build_manifest,
    )


def _die(message, code=2):
    sys.stderr.write("ingest_review: %s\n" % message)
    raise SystemExit(code)


def _store(workspace):
    root = os.path.abspath(workspace)
    if not os.path.isdir(root):
        _die("workspace does not exist: %s" % root)
    manifest_path = os.path.join(root, *BUILD_MANIFEST_PATH.split("/"))
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        _die("cannot read .ingest/build_manifest.json: %s" % exc)
    source_root = manifest.get("source_root") if isinstance(manifest, dict) else None
    if not isinstance(source_root, str) or not os.path.isdir(source_root):
        _die("source_root is missing or no longer exists")
    return root, IngestionStore(root, source_root=source_root)


def _issue_payload(issue):
    return issue.to_dict()


def _template(issue):
    return {
        "instructions": [
            "Use ReviewPatch.create(...) to generate stable patch_id after filling operations.",
            "Keep status=validated only after checking every evidence hash and source page.",
            "Allowed operations never mutate arbitrary workspace paths.",
        ],
        "issue": issue.to_dict(),
        "allowed_operation_shapes": [
            {"op": "add_unit", "unit": "<full ContentUnit object>"},
            {"op": "replace_unit", "unit_id": "<unit_id>", "unit": "<full ContentUnit object>"},
            {
                "op": "assign_chapter", "unit_id": "<unit_id>",
                "chapter": "<label>", "phase": "<label>",
                "chapter_id": "chNN", "phase_id": "phaseNN",
            },
            {
                "op": "pair_qa",
                "question_unit_id": "<unit_id>",
                "answer_unit_id": "<unit_id>",
            },
            {"op": "classify_asset", "unit_id": "<unit_id>", "asset_role": "<role>"},
            {"op": "mark_resolved", "reason": "<what the evidence confirms>"},
            {"op": "mark_unrecoverable", "reason": "<why evidence cannot be recovered>"},
        ],
    }


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Typed AI/human review queue for .ingest workspaces"
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list review issues")
    list_parser.add_argument(
        "--status", action="append",
        help="filter by status (repeatable; default all)",
    )
    show_parser = sub.add_parser("show", help="show one issue and patch operation shapes")
    show_parser.add_argument("issue_id")
    claim_parser = sub.add_parser("claim", help="atomically claim one pending issue")
    claim_parser.add_argument("issue_id")
    validate_parser = sub.add_parser("validate-patch", help="strictly validate a patch JSON")
    validate_parser.add_argument("patch_file")
    apply_parser = sub.add_parser("apply", help="apply a validated patch and rebuild derivatives")
    apply_parser.add_argument("patch_file")
    mark_parser = sub.add_parser(
        "mark-unrecoverable", help="close one issue with an evidence-bound terminal patch"
    )
    mark_parser.add_argument("issue_id")
    mark_parser.add_argument("--reason", required=True)
    mark_parser.add_argument("--reviewer", default="ai")
    resolved_parser = sub.add_parser(
        "mark-resolved", help="confirm from evidence that extraction is already complete"
    )
    resolved_parser.add_argument("issue_id")
    resolved_parser.add_argument("--reason", required=True)
    resolved_parser.add_argument("--reviewer", default="ai")
    sub.add_parser("pending", help="inspect an interrupted review-patch intent")
    sub.add_parser(
        "recover-pending",
        help="idempotently resume the exact interrupted review patch and rebuild",
    )
    sub.add_parser("rebuild", help="recompile wiki/quiz/index from current applied IR")

    args = parser.parse_args(argv)
    workspace, store = _store(args.workspace)

    if args.command == "list":
        statuses = set(args.status or ())
        issues = [
            issue for issue in store.review_queue.issues()
            if not statuses or issue.status in statuses
        ]
        payload = {
            "workspace": workspace,
            "count": len(issues),
            "issues": [_issue_payload(issue) for issue in issues],
        }
    elif args.command == "show":
        issue = store.review_queue.get(args.issue_id)
        if issue is None:
            _die("unknown issue_id: %s" % args.issue_id)
        payload = _template(issue)
    elif args.command == "claim":
        try:
            issue = store.claim_issue(args.issue_id)
            refresh_build_manifest(workspace)
        except Exception as exc:
            _die("claim failed: %s" % exc)
        payload = {"claimed": True, "issue": issue.to_dict()}
    elif args.command in ("validate-patch", "apply"):
        try:
            patch = ReviewPatch.from_dict(read_json(args.patch_file))
        except Exception as exc:
            _die("patch validation failed: %s" % exc)
        if args.command == "validate-patch":
            try:
                store.validate_patch(patch)
            except Exception as exc:
                _die("patch contextual validation failed: %s" % exc)
            payload = {"valid": True, "patch": patch.to_dict()}
        else:
            try:
                result = store.apply_patch(patch)
                compiled = compile_review_outputs(workspace)
            except Exception as exc:
                _die("patch application/rebuild failed: %s" % exc, code=1)
            payload = {
                "applied": result.applied,
                "replayed": result.replayed,
                "changed_operations": result.changed_operations,
                "issue_status": result.issue_status,
                "compiled": compiled,
            }
    elif args.command in ("mark-resolved", "mark-unrecoverable"):
        issue = store.review_queue.get(args.issue_id)
        if issue is None:
            _die("unknown issue_id: %s" % args.issue_id)
        try:
            operation = (
                "mark_resolved" if args.command == "mark-resolved"
                else "mark_unrecoverable"
            )
            patch = ReviewPatch.create(
                issue.issue_id,
                issue.source_id,
                issue.source_sha256,
                [{"op": operation, "reason": args.reason}],
                list(issue.evidence),
                reviewer=args.reviewer,
                status="validated",
            )
            result = store.apply_patch(patch)
            compiled = compile_review_outputs(workspace)
        except Exception as exc:
            _die("%s failed: %s" % (args.command, exc), code=1)
        payload = {
            "patch": patch.to_dict(),
            "issue_status": result.issue_status,
            "compiled": compiled,
        }
    elif args.command == "pending":
        try:
            pending = read_json(store.pending_patch_path, default=None)
        except Exception as exc:
            _die("cannot inspect pending patch: %s" % exc)
        payload = {"pending": pending is not None, "intent": pending}
    elif args.command == "recover-pending":
        try:
            pending = read_json(store.pending_patch_path, default=None)
            if pending is None:
                payload = {"recovered": False, "reason": "no_pending_patch"}
            else:
                expected = {"schema_version", "patch_id", "fingerprint", "patch"}
                if not isinstance(pending, dict) or set(pending) != expected:
                    raise ValueError("pending patch intent has an invalid schema")
                patch = ReviewPatch.from_dict(pending["patch"])
                if patch.patch_id != pending["patch_id"]:
                    raise ValueError("pending patch_id disagrees with embedded patch")
                result = store.apply_patch(patch)
                compiled = compile_review_outputs(workspace)
                payload = {
                    "recovered": True,
                    "applied": result.applied,
                    "replayed": result.replayed,
                    "issue_status": result.issue_status,
                    "compiled": compiled,
                }
        except Exception as exc:
            _die("pending patch recovery failed: %s" % exc, code=1)
    elif args.command == "rebuild":
        try:
            payload = compile_review_outputs(workspace)
        except Exception as exc:
            _die("rebuild failed: %s" % exc, code=1)
    else:
        _die("unknown command")

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(run())
