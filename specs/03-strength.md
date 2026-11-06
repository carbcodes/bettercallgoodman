# 03 · Strength checker

**Owner:** Carlos · **File:** `goodman/checkers/strength.py`

Recompute the stress state from `task.yaml` inputs on our own, then compare the result to the AI's claims.

## What it computes

Closed-form first, because it's fast and easy to show line by line:

| Model | Formula | Used for |
| --- | --- | --- |
| Cantilever / simply supported beam | σ = M·c / I, δ = F·L³ / (3·E·I) etc. | brackets, arms, shelves |
| Rect / round / tube sections | I, Z, A from dimensions | all beams |
| Stress concentration | σ_max = Kt·σ_nom, Kt from Peterson fits (shoulder fillet, hole in plate, notch) | sharp corners, holes |
| Column buckling | P_cr = π²·E·I / (K·L)², Johnson for short columns | struts, legs, standoffs |
| Bolt / pin shear and bearing | τ = F / (n·A), σ_b = F / (d·t) | joints |
| Fatigue | Goodman line: σa/Se + σm/Sut = 1/n | anything cycling: motors, arms, vibration |
| Combined loading | von Mises from σ and τ | shafts in bending + torsion |

Optional: a voxel FEA run on the STL to cross-check a closed-form answer and produce the **stress heatmap for the demo**. Only for the demo case, since closed-form is the reference.

Materials table (`goodman/materials.yaml`): E, yield, ultimate, endurance, density, and for printed plastics **separate in-layer and across-layer strength**. Cite a source for every number.

## Output

For each claim: true value, status (see 01) and a one-line `why` naming the specific mistake. The `why` comes from comparing intermediate steps: if the AI's σ matches σ_nom but not σ_max, it's "missed Kt"; if it matches σ but the SF is off, it's "wrong material strength".

## Case ideas (pick 5: 4 traps + 1 control)

1. **Shelf bracket, PLA printed flat**: uses datasheet strength, but the load acts across layers (~50% weaker).
2. **Aluminum arm with a sharp inside corner**: the AI ignores Kt ≈ 2–3 at a 0.5 mm radius.
3. **Long thin strut in compression**: the stress check passes but it buckles first.
4. **Motor bracket under vibration**: static SF = 3, but the Goodman fatigue SF is under 1.
5. **Unit trap**: servo torque given in kg·cm, the AI treats it as N·m or N·cm.
6. **Hollow vs solid tube**: the AI uses the outer diameter in I for a thin-wall tube.
7. **Control**: a steel bracket at a plain SF ≈ 4 with generous fillets. It's genuinely safe, and the AI should say so.

Write each `why` in `truth.yaml` with the full hand calc and a reference (Shigley, Roark, Peterson, or a material datasheet).

## Done when

- `python -m goodman check tasks/strength/<id>` writes `result.json` for every strength case
- the control case comes out `accepted`
- each `why` names the specific mistake, not just "wrong"
