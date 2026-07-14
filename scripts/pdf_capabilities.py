#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Single declarative registry for optional PDF parsing/rendering adapters.

The dependency preflight and the runtime detector both consume these records;
neither is allowed to advertise a compound adapter unless every import in that
candidate is present.
"""


PDF_TEXT_CANDIDATES = (
    ("pypdf", ("pypdf",), "pypdf"),
    ("pymupdf", ("fitz",), "pymupdf"),
)

PDF_RENDER_CANDIDATES = (
    ("pymupdf", ("fitz",), "pymupdf"),
    ("pypdfium2", ("pypdfium2", "PIL"), "pypdfium2 Pillow"),
)


def dependency_candidates(records):
    """Return the check_deps ``(imports, display packages)`` shape."""

    return tuple((imports, packages) for unused, imports, packages in records)


__all__ = (
    "PDF_RENDER_CANDIDATES",
    "PDF_TEXT_CANDIDATES",
    "dependency_candidates",
)
