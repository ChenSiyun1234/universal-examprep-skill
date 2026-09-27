# -*- coding: utf-8 -*-
"""Put the installable skill folder first on sys.path so `import coach` finds the package."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skills", "universal-exam-cram-coach")
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)
