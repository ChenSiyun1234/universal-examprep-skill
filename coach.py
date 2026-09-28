#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Developer shortcut: run the skill's CLI from a clone of the repository.

The installable skill lives in skills/universal-exam-cram-coach/ (that folder is what
`npx skills add` copies). `python coach.py …` here is the same as
`python skills/universal-exam-cram-coach/coach.py …`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills", "universal-exam-cram-coach"))

from coach.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
