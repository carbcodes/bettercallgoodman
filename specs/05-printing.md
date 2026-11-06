# 05 · 3D printing checker (stretch)

**Owner:** Fabian · **File:** `goodman/checkers/printing.py`
**Start only when** all strength and collision cases run end to end.

Check whether an AI's claim that a part is printable (on FDM, with PLA) holds up on the real geometry.

## Checks

| Check | Rule (FDM, 0.4 mm nozzle) | Method |
| --- | --- | --- |
| Overhangs | faces facing down at more than 45° from vertical need support | face normals vs build direction |
| Thin walls | under 0.8 mm (2 nozzle widths) won't print reliably | ray-cast thickness on the mesh |
| Bed contact | the part must have a flat face on the bed in the chosen orientation | lowest-Z face area |
| Bridges | over 10 mm unsupported sags | horizontal downward faces with support only at their ends |
| Small holes | vertical holes print ~0.2–0.3 mm undersize, so a "5 mm hole for an M5" is too tight | hole diameter vs fastener |
| Build volume | must fit the stated printer | bounding box |

Cite where each threshold comes from. Thresholds go in a YAML file, not in the code.

## Case ideas (pick 3: 2 traps + 1 control)

1. **"No supports needed"**: a part with a 60° overhang hidden under a lip.
2. **M3 holes drawn at exactly 3.0 mm**: screws won't go in without drilling.
3. **Control**: a bracket with chamfered overhangs under 45° that prints cleanly.

## Implementation

Built as `goodman/dfm/printing.py` (`check_printing(step_path, build_dir, printer)`, CLI `python -m goodman.dfm printing part.step --up 0 0 1`), working on any STEP solid. Thresholds and their sources are in `goodman/rules/fdm.yaml`. Supports are allowed by default: overhangs, ledges, ceilings and long bridges are `needs_support` warnings (area and support height) and the verdict is `printable_with_supports`; they fail only when the support could not be removed (sealed cavity, no open path) or would stand in a bore under 5 mm. `supports=False` / `--no-supports` makes every overhang past the limit a failure. Test parts with known answers: `tests/fixtures/dfm/p0*.py`, run by `tests/test_dfm.py`.
