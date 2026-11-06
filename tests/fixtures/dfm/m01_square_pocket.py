"""CNC: 20 x 20 x 15 mm pocket with square (sharp) inside corners.

Expected: not_machinable. Key finding: 4 sharp vertical inside corners.
"""
from build123d import Align, Box, Pos

EXPECTED = {"checker": "cnc", "verdict": "not_machinable", "key_rule": "sharp_inside_corner", "key_severity": "fail",
            "key": "4 square vertical inside corners can't be milled"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build():
    return Box(40, 40, 20, align=A) - Pos(0, 0, 5) * Box(20, 20, 15, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m01_square_pocket.step")
