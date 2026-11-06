"""Printing: block with a sealed internal cavity (a 20 x 20 x 10 mm void inside a 30 x 30 x 20 mm block).

Expected: not_printable even with supports. Key finding: enclosed_cavity, the support or loose
material inside can never be removed.
"""
from build123d import Box

EXPECTED = {"checker": "printing", "verdict": "not_printable", "key_rule": "enclosed_cavity", "key_severity": "fail",
            "key_value": 4000.0, "key": "sealed 4000 mm³ cavity; nothing inside it can be removed"}


def build():
    return Box(30, 30, 20) - Box(20, 20, 10)


if __name__ == "__main__":
    from _common import main
    main(build, EXPECTED, "p07_enclosed_cavity.step")
