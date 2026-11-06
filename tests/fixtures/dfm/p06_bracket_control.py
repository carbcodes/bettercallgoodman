"""Printing control: an L bracket printed standing up, inside fillet, M3 clearance holes (3.4 mm),
chamfered top edge. Nothing overhangs, walls are 5 mm.

Expected: printable. Key finding: none failing (bed contact info only).
"""
from build123d import Align, Axis, Box, Cylinder, Pos, chamfer, fillet

EXPECTED = {"checker": "printing", "verdict": "printable", "key_rule": "bed_contact", "key_severity": "info",
            "key": "clean bracket: flat on the bed, no overhang, walls 5 mm, holes at clearance size"}

A = (Align.MIN, Align.MIN, Align.MIN)


def build():
    part = Box(40, 30, 5, align=A) + Box(5, 30, 35, align=A)
    inside = part.edges().filter_by(Axis.Y).filter_by_position(Axis.X, 4.9, 5.1).filter_by_position(Axis.Z, 4.9, 5.1)
    part = fillet(inside, 3)
    top = part.edges().filter_by(Axis.Y).group_by(Axis.Z)[-1]
    part = chamfer(top, 1)
    for y in (8, 22):
        part -= Pos(28, y, 0) * Cylinder(1.7, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return part


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p06_bracket_control.step")
