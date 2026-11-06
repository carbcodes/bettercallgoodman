"""CNC control: 80 x 60 x 8 plate, rounded outer corners, four Ø6.6 through holes (M6 clearance)
and a 30 x 20 x 4 mm pocket with R4 corners. Everything reachable from the top.

Expected: machinable. Key finding: 1 setup, no fails.
"""
from build123d import Align, Axis, Box, Cylinder, Pos, RectangleRounded, extrude, fillet

EXPECTED = {"checker": "cnc", "verdict": "machinable", "key_rule": "setups", "key_severity": "info",
            "key_value": 1, "key": "plate with through holes and R4 pocket: one setup, nothing fails"}

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build():
    plate = Box(80, 60, 8, align=A)
    plate = fillet(plate.edges().filter_by(Axis.Z), 5)
    for x in (-30, 30):
        for y in (-20, 20):
            plate -= Pos(x, y, 0) * Cylinder(3.3, 8, align=A)
    return plate - Pos(0, 0, 4) * extrude(RectangleRounded(30, 20, 4), amount=4)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "m06_plate_control.step")
