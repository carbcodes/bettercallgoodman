"""Shared helper: every fixture script builds a part and can write it as STEP.

    python tests/fixtures/dfm/p01_overhang_60.py out.step
"""
import sys
from pathlib import Path

from build123d import export_step


def main(build, expected, default_name):
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(default_name)
    export_step(build(), str(out))
    print(f"wrote {out}  (expected: {expected['verdict']}, key finding: {expected['key_rule']})")
