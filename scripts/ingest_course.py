#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One command: preflight -> build -> ingest -> visual index -> validate.

No dependency is installed here.  Exit 10 means the engineering pipeline
completed but content readiness is blocked by explicit review/validation work.
"""

import argparse
import json
import os
import subprocess
import sys

try:
    import build_raw_input_from_workspace as builder
    from ingestion import is_link_or_reparse, safe_workspace_entry
    from ingestion.storage import atomic_write_json
except ImportError:
    from scripts import build_raw_input_from_workspace as builder
    from scripts.ingestion import is_link_or_reparse, safe_workspace_entry
    from scripts.ingestion.storage import atomic_write_json


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _run(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _emit(payload, as_json):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("process_success=%s readiness=%s" % (
            str(payload.get("process_success")).lower(),
            payload.get("readiness") or "unknown",
        ))
        for step in payload.get("steps", []):
            print("[%s] %s" % (step.get("status"), step.get("name")))
        if payload.get("workspace"):
            print("workspace=%s" % payload["workspace"])


def run(argv=None, backend=None):
    parser = argparse.ArgumentParser(
        description="Official lightweight course ingestion orchestrator"
    )
    parser.add_argument("--materials", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--course-name")
    parser.add_argument("--lang", choices=("zh", "en"))
    parser.add_argument(
        "--artifact-mode", choices=("chat", "visual"), default=None,
        help="explicit standing preference; omitted means keep existing/default chat",
    )
    parser.add_argument("--render-pages", choices=("never", "auto", "required"), default="auto")
    parser.add_argument("--visual-index", choices=("never", "auto", "required"), default="auto")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    materials = os.path.abspath(args.materials)
    workspace = os.path.abspath(args.workspace)
    steps = []
    payload = {
        "process_success": False,
        "readiness": "unknown",
        "materials": materials,
        "workspace": workspace,
        "steps": steps,
    }
    if not os.path.isdir(materials):
        payload["error"] = "materials directory does not exist"
        _emit(payload, args.as_json)
        return 2
    materials_real = os.path.realpath(materials)
    workspace_real = os.path.realpath(workspace)
    try:
        workspace_inside_materials = (
            os.path.commonpath((materials_real, workspace_real)) == materials_real
        )
    except ValueError:
        workspace_inside_materials = False
    if workspace_inside_materials:
        payload["error"] = (
            "workspace must not equal or live inside materials; reruns would ingest generated files"
        )
        _emit(payload, args.as_json)
        return 2
    if os.path.lexists(workspace) and is_link_or_reparse(workspace):
        payload["error"] = "workspace must not be a symbolic link, junction, or reparse point"
        _emit(payload, args.as_json)
        return 2
    os.makedirs(workspace, exist_ok=True)
    try:
        # Validate every parent before the builder gets its first output path.
        # This prevents a pre-existing .ingest/references junction from turning
        # an apparently local build into an external write.
        safe_workspace_entry(workspace, ".ingest")
        safe_workspace_entry(workspace, "references/assets")
    except Exception as exc:
        payload["error"] = "unsafe workspace output tree: %s" % exc
        _emit(payload, args.as_json)
        return 2

    preflight = _run([
        sys.executable,
        os.path.join(SCRIPT_DIR, "check_deps.py"),
        "--materials", materials,
        "--artifact-mode", args.artifact_mode or "chat",
    ])
    steps.append({
        "name": "dependency_preflight",
        "status": "passed" if preflight.returncode == 0 else "failed",
        "exit_code": preflight.returncode,
    })
    if preflight.returncode != 0:
        payload["error"] = (preflight.stderr or preflight.stdout).strip()
        _emit(payload, args.as_json)
        return preflight.returncode

    raw_path = os.path.join(workspace, ".ingest", "source_raw_input.json")
    report_path = os.path.join(workspace, ".ingest", "parse_report.json")
    asset_root = os.path.join(workspace, "references", "assets")
    build_args = builder.build_arg_parser().parse_args([
        "--materials", materials,
        "--out", raw_path,
        "--report", report_path,
        "--asset-root", asset_root,
        "--render-pages", args.render_pages,
        "--extract-lecture-questions", "auto",
        "--extract-homework", "auto",
    ] + (["--course-name", args.course_name] if args.course_name else []))
    code, raw_input, report = builder.run(build_args, backend=backend)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    atomic_write_json(report_path, report or {})
    steps.append({
        "name": "material_build",
        "status": "passed" if code == 0 else "failed",
        "exit_code": code,
        "warnings": len((report or {}).get("warnings", [])),
        "review_entries": len((report or {}).get("ai_review", [])),
    })
    if code != 0:
        payload["error"] = (raw_input or {}).get("error", "material build failed")
        _emit(payload, args.as_json)
        return code
    atomic_write_json(raw_path, raw_input)
    atomic_write_json(
        os.path.join(workspace, ".ingest", "ai_review_manifest.json"),
        {
            "note": "Legacy view only; canonical lifecycle is .ingest/review_queue.jsonl.",
            "entries": report.get("ai_review", []),
        },
    )

    ingest_command = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "ingest.py"),
        "--input", raw_path,
        "--output-dir", workspace,
    ]
    if args.lang:
        ingest_command.extend(("--lang", args.lang))
    ingested = _run(ingest_command)
    steps.append({
        "name": "workspace_compile",
        "status": "passed" if ingested.returncode == 0 else "failed",
        "exit_code": ingested.returncode,
    })
    if ingested.returncode != 0:
        payload["error"] = (ingested.stderr or ingested.stdout).strip()
        _emit(payload, args.as_json)
        return ingested.returncode

    state_path = os.path.join(workspace, "study_state.json")
    if not os.path.isfile(state_path):
        initialized = _run([
            sys.executable,
            os.path.join(SCRIPT_DIR, "update_progress.py"),
            "--workspace", workspace,
            "init",
        ])
        steps.append({
            "name": "study_state_init",
            "status": "passed" if initialized.returncode == 0 else "failed",
            "exit_code": initialized.returncode,
        })
        if initialized.returncode != 0:
            payload["error"] = (initialized.stderr or initialized.stdout).strip()
            _emit(payload, args.as_json)
            return initialized.returncode
    if args.artifact_mode is not None:
        preference = _run([
            sys.executable,
            os.path.join(SCRIPT_DIR, "update_progress.py"),
            "--workspace", workspace,
            "set", "--artifact-mode", args.artifact_mode,
        ])
        steps.append({
            "name": "artifact_preference",
            "status": "passed" if preference.returncode == 0 else "failed",
            "exit_code": preference.returncode,
        })
        if preference.returncode != 0:
            payload["error"] = (preference.stderr or preference.stdout).strip()
            _emit(payload, args.as_json)
            return preference.returncode

    if args.visual_index != "never":
        visual = _run([
            sys.executable,
            os.path.join(SCRIPT_DIR, "build_visual_index.py"),
            "--workspace", workspace,
            "--materials", materials,
            "--apply",
            "--apply-wiki",
        ])
        visual_ok = visual.returncode == 0
        steps.append({
            "name": "visual_index",
            "status": "passed" if visual_ok else (
                "warning" if args.visual_index == "auto" else "failed"
            ),
            "exit_code": visual.returncode,
        })
        recompiled = _run([
            sys.executable,
            os.path.join(SCRIPT_DIR, "ingest_review.py"),
            "--workspace", workspace,
            "rebuild",
        ])
        steps.append({
            "name": "post_visual_recompile",
            "status": "passed" if recompiled.returncode == 0 else "failed",
            "exit_code": recompiled.returncode,
        })
        if recompiled.returncode != 0:
            payload["error"] = (recompiled.stderr or recompiled.stdout).strip()
            _emit(payload, args.as_json)
            return recompiled.returncode
        if not visual_ok and args.visual_index == "required":
            payload["error"] = (visual.stderr or visual.stdout).strip()
            _emit(payload, args.as_json)
            return visual.returncode or 1

    validated = _run([
        sys.executable,
        os.path.join(SCRIPT_DIR, "validate_workspace.py"),
        workspace,
        "--json",
    ])
    try:
        validation = json.loads(validated.stdout)
    except ValueError:
        validation = {
            "readiness": "blocked",
            "errors": [{"msg": (validated.stderr or validated.stdout).strip()}],
            "warnings": [],
        }
    readiness = validation.get("readiness") or "blocked"
    steps.append({
        "name": "workspace_validation",
        "status": "passed" if readiness in ("ready", "usable_with_gaps") else "blocked",
        "exit_code": validated.returncode,
        "readiness": readiness,
        "errors": len(validation.get("errors") or []),
        "warnings": len(validation.get("warnings") or []),
    })
    payload["process_success"] = True
    payload["readiness"] = readiness
    payload["validation"] = validation
    _emit(payload, args.as_json)
    return 10 if readiness == "blocked" else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(run())
