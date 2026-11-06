from build123d import *

# All dimensions in millimetres.
# Print orientation: Z vertical, XY horizontal layer planes.
# Slice in PLA with 100% infill.

# --------------------------------------------------
# Main dimensions
# --------------------------------------------------

WIDTH = 24.0
PLATE_T = 10.0
PLATE_HEIGHT = 110.0

ARM_REACH = 150.0
ARM_TOP = 90.0
ARM_BOTTOM = 64.0
ARM_DEPTH = ARM_TOP - ARM_BOTTOM

# Triangular reinforcing gusset
GUSSET_START_Z = 15.0
GUSSET_END_X = 59.0

FILLET_R = 3.0

# M4 clearance holes
HOLE_DIAMETER = 4.5
HOLE_RADIUS = HOLE_DIAMETER / 2
HOLE_POSITIONS_Z = (10.0, 100.0)
HOLE_OVERLAP = 0.2

# --------------------------------------------------
# Side profile in XZ plane
# --------------------------------------------------

profile = [
    (0.0, 0.0),
    (PLATE_T, 0.0),
    (PLATE_T, GUSSET_START_Z),
    (GUSSET_END_X, ARM_BOTTOM),
    (ARM_REACH, ARM_BOTTOM),
    (ARM_REACH, ARM_TOP),
    (PLATE_T, ARM_TOP),
    (PLATE_T, PLATE_HEIGHT),
    (0.0, PLATE_HEIGHT),
]

with BuildPart() as bracket:

    # Create one continuous solid, centred across Y.
    with BuildSketch(Plane.XZ.offset(WIDTH / 2)):
        Polygon(*profile, align=None)

    extrude(amount=-WIDTH)

    # Round the three important internal corners.
    fillet_targets = [
        (PLATE_T, GUSSET_START_Z),
        (GUSSET_END_X, ARM_BOTTOM),
        (PLATE_T, ARM_TOP),
    ]

    longitudinal_edges = bracket.edges().filter_by(Axis.Y)

    edges_to_round = [
        edge
        for edge in longitudinal_edges
        if any(
            abs(edge.center().X - x) < 1e-4
            and abs(edge.center().Z - z) < 1e-4
            for x, z in fillet_targets
        )
    ]

    if len(edges_to_round) != len(fillet_targets):
        raise RuntimeError("Could not locate all gusset/root fillet edges.")

    fillet(edges_to_round, radius=FILLET_R)

    # --------------------------------------------------
    # Wall mounting holes, drilled along X
    # --------------------------------------------------

    for z_position in HOLE_POSITIONS_Z:

        with Locations((-HOLE_OVERLAP, 0.0, z_position)):
            Cylinder(
                radius=HOLE_RADIUS,
                height=PLATE_T + 2 * HOLE_OVERLAP,
                rotation=(0, 90, 0),
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

# --------------------------------------------------
# Verify single-solid construction
# --------------------------------------------------

if len(bracket.part.solids()) != 1:
    raise RuntimeError("Bracket must consist of exactly one solid.")

# --------------------------------------------------
# Conservative static strength estimate
# --------------------------------------------------

LOAD_KG = 2.0
GRAVITY = 9.81
LOAD_OFFSET = 150.0

# Assumed effective allowable strength of printed PLA.
PLA_ALLOWABLE_MPA = 5.0

# Approximate local stress concentration allowance.
STRESS_CONCENTRATION = 2.0

# Approximate PLA density: 1.24 g/cm^3.
PLA_DENSITY_KG_MM3 = 1.24e-6

# Include the bracket's own weight.
part_mass_kg = bracket.part.volume * PLA_DENSITY_KG_MM3
part_centre_x = bracket.part.center().X

load_moment = LOAD_KG * GRAVITY * LOAD_OFFSET
self_weight_moment = part_mass_kg * GRAVITY * part_centre_x

total_moment = load_moment + self_weight_moment

# Rectangular arm section modulus.
section_modulus = WIDTH * ARM_DEPTH**2 / 6.0

nominal_stress = total_moment / section_modulus
local_stress = STRESS_CONCENTRATION * nominal_stress

safety_factor = PLA_ALLOWABLE_MPA / local_stress

if safety_factor < 2.0:
    raise RuntimeError(
        f"Insufficient calculated safety factor: {safety_factor:.2f}"
    )

print(f"Bracket mass: {part_mass_kg * 1000:.1f} g")
print(f"Nominal bending stress: {nominal_stress:.3f} MPa")
print(f"Estimated local stress: {local_stress:.3f} MPa")
print(f"Estimated safety factor: {safety_factor:.2f}")

# --------------------------------------------------
# Export STEP in millimetres
# --------------------------------------------------

export_step(bracket.part, "part.step", unit=Unit.MM)

print("Exported part.step successfully.")