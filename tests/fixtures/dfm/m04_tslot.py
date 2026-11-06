"""CNC: a T-slot through a block (6 mm neck, 14 mm wide slot under it), milled from the top setup only.

Expected: not_machinable. Key finding: undercut faces under the neck shoulders.
"""
from build123d import Align, Box, Pos

EXPECTED = {"checker": "cnc", "verdict": "not_machinable", "key_rule": "undercut", "key_severity": "fail",
            "key": "the T's undersides and wide walls are hidden from +Z"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build():
    block = Box(40, 40, 20, align=A)
    return block - Pos(0, 0, 12) * Box(6, 40, 8, align=A) - Pos(0, 0, 6) * Box(14, 40, 6, align=A)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m04_tslot.step")
