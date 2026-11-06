# 02 · Claim extraction

**Owner:** both (build together during 11:30–11:50, finish during 2:15–2:45)

Turn an AI's free-text answer into `claims.json` (see 01). This is the only step that uses an AI, and that AI only **reads**. It never judges whether anything is right.

## How

1. Send the extractor the `answer` from `attempt.json` plus the list of quantities this area understands (below). Do **not** send `truth.yaml`.
2. Ask for JSON only: the verdict, each numeric claim with its unit and an **exact quote**, and which `must_mention` topics show up at all.
3. Validate in code:
   - each `quote` must appear verbatim in the answer, or the claim is dropped
   - units get converted to the units in 01 (kg·cm → N·mm, psi → MPa, inches → mm)
   - unknown quantities are kept as `cannot_check`, never silently dropped
4. **A human reviews every claims.json** before checking and sets `reviewed_by`. With ~10–20 tasks that takes a few minutes, and it means a bad extraction can never become a false flag.

Use a different model for extraction than the one being tested (or the same model in a fresh chat with only the extraction prompt), and say which in the write-up.

## Quantities by area

| Area | Quantities |
| --- | --- |
| strength | `max_stress_mpa`, `safety_factor`, `deflection_mm`, `buckling_load_n`, `fatigue_sf`, `load_n`, `moment_nmm`, `material_strength_mpa` |
| collision | `fits` (bool), `min_clearance_mm`, `interference` (bool), `reach_deg`, `collision_angle_deg` |
| printing | `printable` (bool), `max_overhang_deg`, `min_wall_mm`, `needs_support` (bool) |
| cnc | `machinable` (bool), `min_inside_radius_mm`, `max_pocket_depth_mm`, `setups` (int), `tolerance_mm` |

Verdict words map to: `safe | not_safe`, `fits | does_not_fit`, `printable | not_printable`, `machinable | not_machinable`, or `unclear` when the answer never commits (which counts as wrong).

## Edge cases

- **Ranges** ("20–30 MPa"): keep `low` and `high`. It's confirmed if the true value falls within the range ± tolerance.
- **Multiple values for one quantity**: keep the one in the final summary and note the others.
- **Hedged verdicts** ("should be fine if printed upright"): record the condition. If the task fixes the orientation and it differs, the hedge doesn't help.
