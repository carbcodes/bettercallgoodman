"""CNC: the same 20 x 20 pocket with R3 corners, 10 mm deep (Ø6 end mill, 1.7x diameter).

Expected: machinable. Key finding: pocket_depth_vs_tool 1.67x, info (limit 4x).
"""
from build123d import Align, Box, Pos, RectangleRounded, extrude

EXPECTED = {"checker": "cnc", "verdict": "machinable", "key_rule": "pocket_depth_vs_tool", "key_severity": "info",
            "key_value": 10 / 6, "key": "R3 corners allow a Ø6 tool; 10 mm deep = 1.7x diameter"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build(r=3.0, depth=10.0, height=20.0):
    pocket = Pos(0, 0, height - depth) * extrude(RectangleRounded(20, 20, r), amount=depth)
    return Box(40, 40, height, align=A) - pocket


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m02_pocket_r3_10deep.step")
