# 08 · Next step: automatic setup

**Status:** planned, start only after all 10 core cases run end to end (claims → check → result).
**Owner:** whoever finishes their core first.

## The gap today

Goodman doesn't work out on its own what kind of part it's looking at. For every case, a person writes `task.yaml`: which model to use (cantilever, step, column, servo arm, clearance) and the numbers (length, load, section, material). The checker then runs the math for that setup.

That's fine for our own cases, but it means Goodman can't check a brand-new question without someone setting it up first.

## The upgrade

Let Goodman read the question (`prompt.md`) and build the setup itself:

```
prompt.md ─► setup extractor ─► proposed task.yaml (model + inputs)
                                      │
                       compare to hand-written task.yaml
                                      │
                         setup accuracy: N of 10 correct
```

1. **Extract:** an AI (not the one being tested) reads only `prompt.md` and fills in `model` and `inputs` using the schema the checkers already accept. The output is JSON only, and every number must quote the sentence it came from, the same as claim extraction (02).
2. **Validate in code:** units get converted, required inputs must be present, and a model outside the known list becomes `cannot_check`.
3. **Measure:** our hand-written `task.yaml` files are the answer key. Report how many setups match: right model, and every input within 1%.
4. **Run the checker on the proposed setup**, and confirm it reaches the same verdict as the hand-written one.

## Rules

- The extractor never sees `truth.yaml`, the AI's answer, or the claims. It sets up the problem; physics code still decides what's right.
- If a setup is wrong, the result says so instead of producing a confident verdict from a bad model.
- Hand-written `task.yaml` stays the reference. Auto-setup is something we measure, not something we trust blindly.

## Done when

- `python -m goodman setup tasks/<area>/<id>` writes `task.auto.yaml`
- `python -m goodman report` adds a "setup accuracy" line per area
- the write-up shows the setup accuracy next to the checker results

## Later

- **FEA cross-check:** run a finite-element stress solve (scikit-fem, or Mechy's solver outside this repo) on one demo part and show the stress heatmap next to the hand calculation. When both agree, it shows the simple model is trustworthy.
- **Real CAD input:** check parts from STEP files instead of text descriptions, which needs FEA and geometry checks instead of hand formulas.
