
from build123d import Align, Box, export_step

# ==========================================
# Geometry (all dimensions in mm)
# ==========================================

ARM_LENGTH = 150.0
ARM_WIDTH = 10.0       # Y direction
ARM_HEIGHT = 6.0       # Z direction

# Wall interface: x = 0
# Arm extends in +X
# Gravity acts in -Z

# Single solid rectangular cantilever
part = Box(
    ARM_LENGTH,
    ARM_WIDTH,
    ARM_HEIGHT,
    align=(Align.MIN, Align.CENTER, Align.CENTER)
)

# ==========================================
# Structural screening calculation
# ==========================================

G = 9.80665
LIGHT_MASS = 1.0       # kg
PLA_DENSITY = 1240.0   # kg/m^3

# Conservative PLA tensile strength benchmark
PLA_STRENGTH = 45.5    # MPa

# Allowance for local root stress effects
ROOT_FACTOR = 1.20

# Flexural modulus for side-printed PLA
ELASTIC_MODULUS = 2894.0  # MPa

# Beam self-weight
volume_m3 = ARM_LENGTH * ARM_WIDTH * ARM_HEIGHT * 1e-9
arm_mass = volume_m3 * PLA_DENSITY

# Total bending moment at wall (N.mm)
moment = (
    LIGHT_MASS * G * ARM_LENGTH
    + arm_mass * G * ARM_LENGTH / 2
)

# Rectangular section properties
I = ARM_WIDTH * ARM_HEIGHT**3 / 12
Z = I / (ARM_HEIGHT / 2)

# Maximum nominal bending stress
stress = moment / Z

# Conservative estimated safety factor
safety_factor = PLA_STRENGTH / (stress * ROOT_FACTOR)

# Tip deflection including arm self-weight
distributed_load = arm_mass * G / ARM_LENGTH

tip_deflection = (
    LIGHT_MASS * G * ARM_LENGTH**3
    / (3 * ELASTIC_MODULUS * I)
    + distributed_load * ARM_LENGTH**4
    / (8 * ELASTIC_MODULUS * I)
)

print(f"Nominal bending stress: {stress:.2f} MPa")
print(f"Estimated safety factor: {safety_factor:.2f}")
print(f"Estimated tip deflection: {tip_deflection:.2f} mm")

assert safety_factor >= 1.5, "Safety factor requirement not met!"
assert len(part.solids()) == 1, "Part must be a single solid"

# ==========================================
# Export STEP
# ==========================================

export_step(part, "part.step")

print("STEP exported successfully: part.step")
