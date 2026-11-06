from build123d import *
import math

# All dimensions in mm
PLATE_T = 6.0
WIDTH = 12.0
PLATE_H = 76.0

# Hook profile
ROOT_X = 5.5       # Overlaps back plate by 0.5 mm
SEAT_X = 42.0
BEAM_H = 6.0       # 12 mm total vertical section depth

R_OUTER = 12.0
R_INNER = 6.0
R_TIP = 3.0
TIP_Z = 20.0

OUTER_X = SEAT_X + R_OUTER       # 54 mm
INNER_X = OUTER_X - 2 * R_TIP   # 48 mm
SQRT2 = math.sqrt(2.0)

# Sketch plane: x-z profile at y=+6, normal pointing in -y.
# This produces a 12 mm-wide hook centered on y=0.
profile_plane = Plane(
    origin=(0, WIDTH / 2, 0),
    x_dir=(1, 0, 0),
    z_dir=(0, -1, 0),
)

with BuildPart() as model:

    # Wall mounting plate: wall face is x=0.
    with Locations((PLATE_T / 2, 0, 0)):
        Box(PLATE_T, WIDTH, PLATE_H)

    # Continuous J-hook profile.
    with BuildSketch(profile_plane):
        with BuildLine():

            # Bottom of cantilever arm
            Polyline(
                (ROOT_X, -BEAM_H),
                (SEAT_X, -BEAM_H),
            )

            # Outer quarter-circle, radius 12
            ThreePointArc(
                (SEAT_X, -BEAM_H),
                (
                    SEAT_X + R_OUTER / SQRT2,
                    BEAM_H - R_OUTER / SQRT2,
                ),
                (OUTER_X, BEAM_H),
            )

            # Outer vertical hook wall
            Polyline(
                (OUTER_X, BEAM_H),
                (OUTER_X, TIP_Z),
            )

            # Rounded hook tip
            ThreePointArc(
                (OUTER_X, TIP_Z),
                (SEAT_X + R_OUTER - R_TIP, TIP_Z + R_TIP),
                (INNER_X, TIP_Z),
            )

            # Inner vertical wall
            Polyline(
                (INNER_X, TIP_Z),
                (INNER_X, BEAM_H + R_INNER),
            )

            # Inner quarter-circle, radius 6
            ThreePointArc(
                (INNER_X, BEAM_H + R_INNER),
                (
                    SEAT_X + R_INNER / SQRT2,
                    BEAM_H + R_INNER - R_INNER / SQRT2,
                ),
                (SEAT_X, BEAM_H),
            )

            # Top of arm and closing edge
            Polyline(
                (SEAT_X, BEAM_H),
                (ROOT_X, BEAM_H),
                (ROOT_X, -BEAM_H),
            )

        make_face()

    # Extrude across the full 12 mm width.
    # The 0.5 mm root overlap fuses hook and backplate.
    extrude(
        amount=WIDTH,
        dir=(0, -1, 0),
    )

    # Two M4 clearance holes through the backplate.
    # Hole axes are parallel to X (normal to the wall).
    for screw_z in (-24.0, 24.0):
        with Locations((PLATE_T / 2, 0, screw_z)):
            Cylinder(
                radius=2.2,
                height=PLATE_T + 0.4,
                rotation=(0, 90, 0),
                mode=Mode.SUBTRACT,
            )

# Verify that the finished geometry is one solid.
part = model.part
assert len(part.solids()) == 1, "Part must contain exactly one solid"

# Export STEP in millimetres.
export_step(part, "part.step")