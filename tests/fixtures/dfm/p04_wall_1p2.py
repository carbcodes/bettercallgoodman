"""Printing: the same wall at 1.2 mm (three nozzle widths).

Expected: printable. Key finding: min_wall 1.2 mm, info (limit 0.8 mm).
"""
from build123d import Align, Box, Pos

EXPECTED = {"checker": "printing", "verdict": "printable", "key_rule": "min_wall", "key_severity": "info",
            "key_value": 1.2, "key": "1.2 mm wall passes the 0.8 mm minimum"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build(t=1.2):
    return Box(30, 20, 3, align=A) + Pos(0, 0, 3) * Box(t, 20, 15, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p04_wall_1p2.step")
