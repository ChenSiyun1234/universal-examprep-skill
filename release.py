#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build the installable skill bundle and its checksum.

    python release.py                 # dist/universal-exam-cram-coach-flash.zip + dist/SHA256SUMS.txt
    python release.py path/to/out.zip

The zip holds exactly one folder, `universal-exam-cram-coach/`, with the same files that
`npx skills add ZeKaiNie/universal-examprep-skill` installs: SKILL.md, coach.py, coach/,
LICENSE. Unzip it into an agent's skills directory and the skill is installed.
"""
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "universal-exam-cram-coach"
SKILL_DIR = os.path.join(ROOT, "skills", NAME)
DEFAULT_OUT = os.path.join(ROOT, "dist", NAME + "-flash.zip")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible archives: same files -> same bytes


def skill_files():
    out = []
    for base, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith("."))
        for f in sorted(files):
            if f.endswith((".pyc", ".pyo")) or f.startswith("."):
                continue
            full = os.path.join(base, f)
            out.append((full, os.path.relpath(full, SKILL_DIR).replace(os.sep, "/")))
    return out


def build(out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    names = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
        for full, rel in skill_files():
            with open(full, "rb") as fh:
                data = fh.read().replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo("%s/%s" % (NAME, rel), FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED  # no zlib: identical bytes on every OS and Python
            info.create_system = 3                  # Unix, whatever OS builds it
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
            names.append(rel)
    digest = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
    with open(os.path.join(os.path.dirname(os.path.abspath(out_path)), "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("%s  %s\n" % (digest, os.path.basename(out_path)))
    return names, digest


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    names, digest = build(out)
    print("%s (%d files, %.0f KB)" % (out, len(names), os.path.getsize(out) / 1024))
    print("sha256 %s" % digest)
    for n in names:
        print("  " + n)
