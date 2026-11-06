from build123d import *

# All dimensions in mm
# Mounting face: x = 0
# Hook projects in +x
# Gravity acts in -z
#
# Print orientation: place the X-Z side profile flat
# on the print bed, with the build direction along Y.

# -------------------------
# Main dimensions
# -------------------------

PLATE_THICKNESS = 6.0
PLATE_WIDTH = 44.0       # Along Y
PLATE_HEIGHT = 72.0      # Along Z

HOOK_WIDTH = 28.0        # Along Y
HOOK_DEPTH = 16.0        # Minimum vertical arm depth

MAX_PROJECTION = 58.0

HOLE_DIAMETER = 4.5      # M4 clearance
HOLE_SPACING = 44.0

# -------------------------
# Back plate and hook
# -------------------------

# Plane normal points in -Y.
# Extruding 28 mm therefore centers the hook on Y=0.
profile_plane = Plane(
    origin=(0, HOOK_WIDTH / 2, 0),
    x_dir=(1, 0, 0),
    z_dir=(0, -1, 0),
)

with BuildPart() as assembly:

    # Flat mounting plate: x=0 to x=6
    Box(
        PLATE_THICKNESS,
        PLATE_WIDTH,
        PLATE_HEIGHT,
        align=(Align.MIN, Align.CENTER, Align.CENTER),
    )

    # Hook side profile, including reinforced root.
    with BuildSketch(profile_plane):

        with BuildLine():

            # Lower edge, outer hook tip, and upper edge
            Polyline(
                (3, -16),
                (13, -8),
                (50, -8),
                (58, 0),
                (58, 24),
                (44, 24),
                (44, 12),
            )

            # Rounded inside corner, radius 4 mm
            ThreePointArc(
                (44, 12),
                (42.828427, 9.171573),
                (40, 8),
            )

            # Shallow downward-sloping saddle.
            # Lowest inside region: x=36 to x=40, z=8.
            Polyline(
                (40, 8),
                (36, 8),
                (13, 10),
                (3, 16),
                (3, -16),
            )

        make_face()

    # Extrude the hook across its width.
    # It overlaps the mounting plate, forming one solid.
    extrude(amount=HOOK_WIDTH)

    # -------------------------
    # Two M4 mounting holes
    # -------------------------

    with Locations(
        (PLATE_THICKNESS / 2, 0, -HOLE_SPACING / 2),
        (PLATE_THICKNESS / 2, 0, HOLE_SPACING / 2),
    ):
        Cylinder(
            radius=HOLE_DIAMETER / 2,
            height=PLATE_THICKNESS + 2,
            rotation=(0, 90, 0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )

# -------------------------
# Validate and export
# -------------------------

part = assembly.part

# Ensure the result is a single connected solid.
assert len(part.solids()) == 1, "Part is not a single solid!"

# Verify the projection constraint.
assert part.bounding_box().max.X <= 60.0

export_step(part, "part.step")

print("Exported part.step")
print(f"Maximum projection: {part.bounding_box().max.X:.1f} mm")

# -------------------------
# Conservative bending estimate
# -------------------------

mass_kg = 0.300
gravity = 9.81

service_force = mass_kg * gravity

# Conservative estimate:
# Use the full wall-to-saddle distance as the lever,
# despite the reinforced root reducing the actual
# unsupported length.
lever_arm = 38.0

# Rectangular arm section
section_width = HOOK_WIDTH
section_depth = HOOK_DEPTH

section_modulus = (
    section_width * section_depth**2 / 6
)

bending_stress = (
    service_force * lever_arm / section_modulus
)

# Conservative assumed in-plane PLA allowable stress.
allowable_stress = 15.0  # MPa = N/mm^2

safety_factor = allowable_stress / bending_stress

print(f"Estimated bending stress: {bending_stress:.3f} MPa")
print(f"Estimated safety factor: {safety_factor:.1f}")
print(f"Safety factor at 2x load: {safety_factor / 2:.1f}")