"""CNC: 20 x 20 pocket with R1 corners, 25 mm deep. R1 forces a Ø2 tool; 25 mm is 12.5x its diameter.

Expected: not_machinable. Key finding: pocket_depth_vs_tool 12.5x (limit 4x).
"""
from m02_pocket_r3_10deep import build as _pocket

EXPECTED = {"checker": "cnc", "verdict": "not_machinable", "key_rule": "pocket_depth_vs_tool", "key_severity": "fail",
            "key_value": 12.5, "key": "R1 corner, 25 mm deep: Ø2 tool at 12.5x diameter"}


def build():
    return _pocket(r=1.0, depth=25.0, height=30.0)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m03_pocket_r1_25deep.step")
