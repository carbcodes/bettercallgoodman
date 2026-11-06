"""CNC: a Ø3 mm blind hole drilled 40 mm deep (13.3x diameter).

Expected: not_machinable. Key finding: hole_depth 13.3x (limit 10x).
"""
from build123d import Align, Box, Cylinder, Pos

EXPECTED = {"checker": "cnc", "verdict": "not_machinable", "key_rule": "hole_depth", "key_severity": "fail",
            "key_value": 40 / 3, "key": "Ø3 x 40 mm hole is 13.3x diameter"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build():
    return Box(20, 20, 50, align=A) - Pos(0, 0, 10) * Cylinder(1.5, 40, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m05_deep_hole.step")
