"""Printing: a 0.5 mm wall standing on a base plate.

Expected: not_printable. Key finding: min_wall 0.5 mm (limit 0.8 mm).
"""
from build123d import Align, Box, Pos

EXPECTED = {"checker": "printing", "verdict": "not_printable", "key_rule": "min_wall", "key_severity": "fail",
            "key_value": 0.5, "key": "0.5 mm wall; FDM minimum 0.8 mm"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build(t=0.5):
    return Box(30, 20, 3, align=A) + Pos(0, 0, 3) * Box(t, 20, 15, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p03_wall_0p5.step")
