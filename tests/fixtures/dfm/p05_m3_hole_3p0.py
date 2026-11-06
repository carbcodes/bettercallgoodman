"""Printing: a plate with an "M3 hole" drawn at exactly 3.0 mm.

Expected: printable, with a warning. Key finding: hole_undersize (prints ~2.7-2.8 mm; use 3.4 mm).
"""
from build123d import Align, Box, Cylinder

EXPECTED = {"checker": "printing", "verdict": "printable", "key_rule": "hole_undersize", "key_severity": "warn",
            "key_value": 3.0, "key": "Ø3.0 vertical hole prints undersize, too tight for M3"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build(d=3.0):
    return Box(30, 30, 5, align=A) - Cylinder(d / 2, 5, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p05_m3_hole_3p0.step")
