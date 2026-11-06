from build123d import *

# All dimensions in mm.
# Coordinate system: wall at x=0, projection in +x, gravity in -z.
# Print upright with z vertical and horizontal XY layers.
# Set 100% infill in the slicer.

# Mounting plate
plate_t = 5.5
plate_width = 14.8
plate_height = 68.0

# Hook profile dimensions
# Root section: 15 mm thick, tapering to a 10 mm load-carrying section.
hook_width = plate_width

# Custom XZ sketch plane, centered across the y-width.
# Its normal points in -y.
profile_plane = Plane(
    origin=(0, hook_width / 2, 0),
    x_dir=(1, 0, 0),
    z_dir=(0, -1, 0),
)

with BuildPart() as build:

    # Flat wall mounting plate: x = 0 to 5.5.
    with Locations((plate_t / 2, 0, 0)):
        Box(plate_t, plate_width, plate_height)

    # Continuous curved hook profile.
    # The inside bottom of the U is at approximately (27, -7.5).
    with BuildSketch(profile_plane):

        with BuildLine():

            # Root and tapered upper arm.
            Polyline(
                (4.5, 4.5),
                (4.5, 19.5),
                (12.0, 17.0),
            )

            # Outer upper quarter-circle, R = 12.5.
            ThreePointArc(
                (12.0, 17.0),
                (20.838835, 13.338835),
                (24.5, 4.5),
            )

            # Left inner leg.
            Polyline(
                (24.5, 4.5),
                (24.5, -5.0),
            )

            # Rounded inside bottom, R = 2.5.
            ThreePointArc(
                (24.5, -5.0),
                (27.0, -7.5),
                (29.5, -5.0),
            )

            # Upturned retaining tip.
            Polyline(
                (29.5, -5.0),
                (29.5, 4.5),
            )

            # Rounded tip, R = 5.
            ThreePointArc(
                (29.5, 4.5),
                (34.5, 9.5),
                (39.5, 4.5),
            )

            # Outer right leg.
            Polyline(
                (39.5, 4.5),
                (39.5, -5.0),
            )

            # Outer bottom curve, R = 12.5.
            ThreePointArc(
                (39.5, -5.0),
                (27.0, -17.5),
                (14.5, -5.0),
            )

            # Left outer leg.
            Polyline(
                (14.5, -5.0),
                (14.5, 4.5),
            )

            # Inner upper quarter-circle, R = 2.5.
            ThreePointArc(
                (14.5, 4.5),
                (13.767767, 6.267767),
                (12.0, 7.0),
            )

            # Tapered lower root transition.
            Polyline(
                (12.0, 7.0),
                (4.5, 4.5),
            )

        make_face()

    # Extrude the hook across the complete width.
    # The 1 mm overlap with the mounting plate ensures fusion.
    extrude(amount=hook_width)

    # Two M4 clearance holes with recessed screw heads.
    hole_diameter = 4.5
    counterbore_diameter = 8.0
    counterbore_depth = 3.0

    screw_positions_z = (-25.5, 25.5)

    for z_pos in screw_positions_z:

        # Through hole, axis perpendicular to the wall.
        with Locations((plate_t / 2, 0, z_pos)):
            Cylinder(
                radius=hole_diameter / 2,
                height=plate_t + 0.4,
                rotation=(0, 90, 0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )

        # Counterbore on the front face.
        with Locations(
            (plate_t - counterbore_depth / 2, 0, z_pos)
        ):
            Cylinder(
                radius=counterbore_diameter / 2,
                height=counterbore_depth,
                rotation=(0, 90, 0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )


# Validate that the result is one connected solid.
part = build.part

if len(part.solids()) != 1:
    raise RuntimeError(
        f"Expected one solid, found {len(part.solids())}"
    )

# Export to the current working directory.
export_step(part, "part.step")