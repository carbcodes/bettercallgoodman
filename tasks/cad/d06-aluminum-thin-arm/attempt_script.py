
from math import pi
from build123d import *

# --------------------------------------------------
# Cantilever arm - 6061-T6 aluminium
# All dimensions in mm
#
# Coordinate system:
#   x = arm length, positive away from wall
#   y = width
#   z = vertical
#   mounting face at x = 0
# --------------------------------------------------

# Geometry
ARM_LENGTH = 400.0
ARM_WIDTH = 30.0
ARM_HEIGHT = 10.0

# Mounting interface:
# Four M3 x 0.5 tapped holes in the x=0 face.
# Actual threads are represented by tap-drill bores.
M3_TAP_DRILL = 2.5
MOUNT_TAP_DEPTH = 10.0

MOUNT_HOLE_Y = (
    -10.0,
    -10.0 / 3.0,
     10.0 / 3.0,
     10.0,
)

# --------------------------------------------------
# Build the part as one solid
# --------------------------------------------------

with BuildPart() as arm:

    # Main rectangular cantilever.
    # x spans 0 to 400.
    # y spans -15 to +15.
    # z spans -5 to +5.
    Box(
        ARM_LENGTH,
        ARM_WIDTH,
        ARM_HEIGHT,
        align=(Align.MIN, Align.CENTER, Align.CENTER),
    )

    # Blind mounting holes drilled from x=0
    # and extending in the positive x direction.
    for y in MOUNT_HOLE_Y:
        with Locations((MOUNT_TAP_DEPTH / 2.0, y, 0)):
            Cylinder(
                radius=M3_TAP_DRILL / 2.0,
                height=MOUNT_TAP_DEPTH,
                rotation=(0, 90, 0),
                align=(
                    Align.CENTER,
                    Align.CENTER,
                    Align.CENTER,
                ),
                mode=Mode.SUBTRACT,
            )

# Obtain the resulting single solid.
part = arm.part

if len(part.solids()) != 1:
    raise RuntimeError("Part must contain exactly one solid.")

# Export STEP into the current working directory.
export_step(part, "part.step")

# --------------------------------------------------
# Nominal engineering calculations
# --------------------------------------------------

G = 9.81                 # m/s^2
DENSITY = 2700.0         # kg/m^3
ELASTIC_MODULUS = 69000.0  # MPa
YIELD_MIN = 240.0        # MPa

INSTRUMENT_MASS = 10.0

# Instrument load.
load_N = INSTRUMENT_MASS * G

# Conservative arm self-weight (gross volume).
volume_mm3 = ARM_LENGTH * ARM_WIDTH * ARM_HEIGHT
mass_kg = volume_mm3 * 1e-9 * DENSITY

distributed_load = mass_kg * G / ARM_LENGTH  # N/mm

# Total root bending moment, including arm weight.
root_moment = (
    load_N * ARM_LENGTH
    + distributed_load * ARM_LENGTH**2 / 2.0
)

# Second moment of area about the y axis.
# Include the four longitudinal tap-drill bores
# in the mounting region.
r = M3_TAP_DRILL / 2.0

I_y = (
    ARM_WIDTH * ARM_HEIGHT**3 / 12.0
    - len(MOUNT_HOLE_Y) * pi * r**4 / 4.0
)

# Maximum nominal bending stress.
section_extreme = ARM_HEIGHT / 2.0
bending_stress = root_moment * section_extreme / I_y

# Yield safety factor.
safety_factor = YIELD_MIN / bending_stress

# Conservative tip deflection using the reduced
# root-section inertia over the entire beam.
tip_deflection = (
    load_N * ARM_LENGTH**3
    / (3.0 * ELASTIC_MODULUS * I_y)
    + distributed_load * ARM_LENGTH**4
    / (8.0 * ELASTIC_MODULUS * I_y)
)

print("STEP exported: part.step")
print(f"Root bending moment: {root_moment / 1000:.2f} Nm")
print(f"Root bending stress: {bending_stress:.2f} MPa")
print(f"Yield safety factor: {safety_factor:.2f}")
print(f"Estimated tip deflection: {tip_deflection:.2f} mm")
print(f"Section inertia Iy: {I_y:.2f} mm^4")
