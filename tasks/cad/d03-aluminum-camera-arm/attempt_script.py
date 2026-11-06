from build123d import *

# ============================================================
# Cantilever camera arm
# Material: 6061-T6 aluminium
# Units: millimetres
#
# Coordinate system:
#   x = 0 : wall mounting face
#   +x    : direction of cantilever
#   z     : vertical upwards
#   -z    : gravity
# ============================================================

# ------------------------------------------------------------
# Material properties (conservative design assumptions)
# ------------------------------------------------------------

YIELD_STRENGTH_MPA = 240.0
ELASTIC_MODULUS_MPA = 69000.0

# ------------------------------------------------------------
# Camera loading
# ------------------------------------------------------------

CAMERA_MASS_KG = 1.0
GRAVITY = 9.81
CAMERA_X = 200.0

# 10% allowance for arm and mounting-boss dead weight
DEAD_LOAD_FACTOR = 1.10

# Screening allowance for local stress concentration
KT_SCREEN = 3.0

# ------------------------------------------------------------
# Mounting plate
# ------------------------------------------------------------

PLATE_T = 8.0
PLATE_WIDTH_Y = 80.0
PLATE_HEIGHT_Z = 80.0

MOUNT_HOLE_D = 6.5
BOLT_SPACING_Y = 50.0
BOLT_SPACING_Z = 50.0

# ------------------------------------------------------------
# Cantilever arm cross-section
# ------------------------------------------------------------

ARM_WIDTH_Y = 16.0
ARM_HEIGHT_Z = 12.0

# Small overlap ensures reliable solid fusion
ROOT_OVERLAP = 0.5

ARM_START_X = PLATE_T - ROOT_OVERLAP

# ------------------------------------------------------------
# Camera mounting boss
# ------------------------------------------------------------

PAD_LENGTH_X = 24.0
PAD_WIDTH_Y = 24.0
PAD_HEIGHT_Z = 14.0

PAD_OVERLAP = 1.0

# Camera mounting hole is centred exactly 200 mm
# from the wall mounting face.
PAD_CENTER_X = CAMERA_X

ARM_END_X = PAD_CENTER_X + PAD_LENGTH_X / 2.0
ARM_LENGTH_X = ARM_END_X - ARM_START_X

PAD_BOTTOM_Z = ARM_HEIGHT_Z / 2.0 - PAD_OVERLAP
PAD_TOP_Z = PAD_BOTTOM_Z + PAD_HEIGHT_Z

# 1/4-20 UNC tap drill
CAMERA_TAP_DRILL_D = 5.1

# Blind threaded-hole depth, approximately 2 x diameter
TAP_START_Z = ARM_HEIGHT_Z / 2.0
TAP_DEPTH = PAD_TOP_Z - TAP_START_Z

# ------------------------------------------------------------
# Structural calculation
# ------------------------------------------------------------

design_load_N = (
    CAMERA_MASS_KG * GRAVITY * DEAD_LOAD_FACTOR
)

bending_moment_Nmm = design_load_N * CAMERA_X

# Second moment of area for rectangular section,
# bending about the y axis.
I_y_mm4 = (
    ARM_WIDTH_Y * ARM_HEIGHT_Z**3 / 12.0
)

section_modulus_mm3 = (
    I_y_mm4 / (ARM_HEIGHT_Z / 2.0)
)

nominal_stress_MPa = (
    bending_moment_Nmm / section_modulus_mm3
)

screening_stress_MPa = KT_SCREEN * nominal_stress_MPa

safety_factor = (
    YIELD_STRENGTH_MPA / screening_stress_MPa
)

assert safety_factor >= 3.0, (
    f"Insufficient yield safety factor: {safety_factor:.2f}"
)

print(f"Nominal bending stress: {nominal_stress_MPa:.2f} MPa")
print(f"Screening stress:       {screening_stress_MPa:.2f} MPa")
print(f"Expected safety factor: {safety_factor:.2f}")

# ------------------------------------------------------------
# Build the part
# ------------------------------------------------------------

with BuildPart() as bracket:

    # 1. Integral vertical mounting flange.
    #    Front mounting face is exactly x = 0.
    Box(
        PLATE_T,
        PLATE_WIDTH_Y,
        PLATE_HEIGHT_Z,
        align=(
            Align.MIN,
            Align.CENTER,
            Align.CENTER,
        ),
    )

    # 2. Horizontal cantilever arm.
    #    Rectangular section: 16 mm wide x 12 mm high.
    with Locations((ARM_START_X, 0, 0)):
        Box(
            ARM_LENGTH_X,
            ARM_WIDTH_Y,
            ARM_HEIGHT_Z,
            align=(
                Align.MIN,
                Align.CENTER,
                Align.CENTER,
            ),
        )

    # 3. Raised camera mounting boss.
    #    The boss overlaps the arm by 1 mm.
    #    Its centre is at x = 200 mm.
    with Locations((PAD_CENTER_X, 0, PAD_BOTTOM_Z)):
        Box(
            PAD_LENGTH_X,
            PAD_WIDTH_Y,
            PAD_HEIGHT_Z,
            align=(
                Align.CENTER,
                Align.CENTER,
                Align.MIN,
            ),
        )

    # 4. Vertical 1/4-20 tapped mounting hole.
    #    Modelled as a 5.1 mm tap-drill blind hole.
    #    13 mm nominal thread engagement.
    with Locations((PAD_CENTER_X, 0, TAP_START_Z)):
        Cylinder(
            radius=CAMERA_TAP_DRILL_D / 2.0,
            height=TAP_DEPTH,
            align=(
                Align.CENTER,
                Align.CENTER,
                Align.MIN,
            ),
            mode=Mode.SUBTRACT,
        )

    # 5. Four M6 clearance holes through mounting flange.
    #    Cylinders are rotated so their axes are parallel to X.
    for y in (
        -BOLT_SPACING_Y / 2.0,
        BOLT_SPACING_Y / 2.0,
    ):
        for z in (
            -BOLT_SPACING_Z / 2.0,
            BOLT_SPACING_Z / 2.0,
        ):
            with Locations((PLATE_T / 2.0, y, z)):
                Cylinder(
                    radius=MOUNT_HOLE_D / 2.0,
                    height=PLATE_T + 0.5,
                    rotation=(0, 90, 0),
                    align=(
                        Align.CENTER,
                        Align.CENTER,
                        Align.CENTER,
                    ),
                    mode=Mode.SUBTRACT,
                )

# ------------------------------------------------------------
# Validate single-solid construction
# ------------------------------------------------------------

part = bracket.part

solid_count = len(part.solids())

if solid_count != 1:
    raise RuntimeError(
        f"Expected one solid, found {solid_count}"
    )

# ------------------------------------------------------------
# Export STEP
# ------------------------------------------------------------

export_step(part, "part.step")

print("STEP export successful: part.step")