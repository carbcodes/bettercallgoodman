"""Printing: block with a lip whose underside overhangs 60° from vertical.

Expected: not_printable. Key finding: overhang ~60° under the lip (limit 45°).
"""
import math

from build123d import Plane, Polyline, extrude, make_face

EXPECTED = {"checker": "printing", "verdict": "not_printable", "key_rule": "overhang", "key_severity": "fail",
            "key_value": 60.0, "key": "60° overhang under the lip; FDM limit 45° without support"}


def build(angle_deg=60.0):
    lip, z0, top = 8.0, 18.0, 32.0
    zt = z0 + lip / math.tan(math.radians(angle_deg))
    pts = [(0, 0), (20, 0), (20, z0), (20 + lip, zt), (20 + lip, top), (0, top), (0, 0)]
    return extrude(make_face(Polyline(*pts)).moved(Plane.XZ.location), amount=-20)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p01_overhang_60.step")
