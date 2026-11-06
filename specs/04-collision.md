# 04 · Collision checker

**Owner:** Fabian · **File:** `goodman/checkers/collision.py`

Build the real geometry for a task, then measure fit, clearance and motion directly. The AI only sees a text description (with dimensions) or a drawing. Goodman sees the geometry.

## Geometry input

`tasks/collision/<id>/geometry/assembly.yaml`: simple solids are enough for most cases, with STEP files for anything else.

```yaml
parts:
  - id: base
    shape: {box: [80, 60, 10]}          # mm
    position: [0, 0, 0]
  - id: link1
    shape: {box: [100, 15, 8]}
    position: [0, 0, 30]
    joint: {axis: [0, 1, 0], origin: [0, 0, 30], range_deg: [-10, 120]}
  - id: pcb
    step: pcb.step
    position: [5, 5, 12]
min_clearance_mm: 0.5
```

Use `build123d` with OCC's `BRepExtrema_DistShapeShape` for distance and `BRepAlgoAPI_Common` for overlap volume, the same approach Mechy's assembly check uses (reimplement it here, since this repo is public).

## What it computes

1. **Static fit**: every part pair gets a minimum distance and an overlap volume. Overlap above 0.01 mm³ counts as `interference`, and a distance below `min_clearance_mm` counts as `too_tight`.
2. **Motion sweep**: for each joint, step through `range_deg` (1° steps, then 0.1° near a hit) and record the first collision angle and the minimum clearance across the sweep.
3. **Assembly order (if time)**: can each part be inserted along a straight path without passing through already-placed parts?

## Output

For claims like `fits`, `min_clearance_mm`, `collision_angle_deg` and `reach_deg`: true value, status, and a `why` with the exact pair and location, for example "link1 hits base at 97°, 23° before the claimed 120° limit; contact at the base's top-front edge". Save a render of the collision pose for the demo.

## Case ideas (pick 5: 4 traps + 1 control)

1. **Arm range of motion**: the AI checks link lengths but forgets link thickness, so the arm hits the base before its claimed limit.
2. **PCB in an enclosure**: fits by outer dimensions, but a tall capacitor or USB connector hits the lid.
3. **Screw head in a counterbore**: the counterbore fits the head diameter but not the depth, so the head sticks out into a mating part.
4. **Gear pair**: center distance from pitch diameters is fine, but the outside diameter of one gear hits a shaft boss.
5. **Hinged lid**: closed and open poses are both fine, but the lid's corner clips the wall *mid-swing*.
6. **Control**: the same enclosure with a properly sized lid that actually fits with 1 mm clearance.

## Done when

- `python -m goodman check tasks/collision/<id>` writes `result.json` for every collision case
- the control case comes out `accepted`
- every caught case has a saved render of the collision
