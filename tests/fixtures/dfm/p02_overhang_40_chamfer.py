"""Printing: the same lip with its underside chamfered to 40° from vertical (the fix).

Expected: printable. Key finding: no overhang over 45°.
"""
import math

from build123d import Plane, Polyline, extrude, make_face

EXPECTED = {"checker": "printing", "verdict": "printable", "key_rule": "overhang", "key_severity": None,
            "key": "40° chamfer is self-supporting (limit 45°), no overhang finding"}


def build(angle_deg=40.0):
    lip, z0, top = 8.0, 18.0, 32.0
    zt = z0 + lip / math.tan(math.radians(angle_deg))
    pts = [(0, 0), (20, 0), (20, z0), (20 + lip, zt), (20 + lip, top), (0, top), (0, 0)]
    return extrude(make_face(Polyline(*pts)).moved(Plane.XZ.location), amount=-20)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p02_overhang_40_chamfer.step")
