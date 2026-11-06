# 09 · Instructions for Devin: generate 100–200 test cases

Paste everything below the line into Devin.

---

## Goal

Add 100–200 new **strength** test cases to the public repo `carbcodes/bettercallgoodman`. Each case is a realistic engineering design question with a trap that a strong AI model might miss, plus a correct answer we can defend. Work on a new branch `devin/generated-cases` and open a pull request. Don't push to `main`.

Read these first, since they are the contract: `README.md`, `specs/00-overview.md`, `specs/01-formats.md`, `specs/03-strength.md`. Then study the 8 hand-written examples in `tasks/strength/` (s01–s08) and the checker in `goodman/checkers/strength.py`.

## What one case is

A folder `tasks/strength/g###-<short-name>/` (g001, g002, …) with exactly three files, in the same format as s01–s08:

- `prompt.md`: one paragraph, written as a real job ("I'm mounting…", "We're building…"), giving every number needed in plain words. It ends with the same summary sentence the examples use. **Never hint at the trap.**
- `task.yaml`: `id`, `area: strength`, `model`, `title`, `trap` (a quoted string), `control` (true/false) and `inputs`, using exactly the input keys the existing models read.
- `truth.yaml`: `verdict`, `values` (with `tol`), `must_mention` where relevant, and `why`: a short hand calc a judge can follow line by line.

**Do not create** `attempt.json`, `claims.json` or `result.json`. Those come later.

## Use only the existing models

Each case must be solvable by one of the checker's current models: `cantilever_root_fillet`, `cantilever_step`, `column`, `arm_torque`, `cantilever_fatigue`, `simple_beam`, `thermal_column`. Don't add new models or change checker code.

## Variety (this matters more than count)

- **Spread across models:** at least 12 cases per model.
- **Spread across traps.** Mix these:
  - stress concentration at a small radius
  - print layer direction for PLA, PETG and ABS
  - buckling hidden behind a passing stress check
  - fatigue hidden behind a passing static check
  - weak-axis vs strong-axis orientation
  - kg·cm vs N·m torque units
  - stall torque vs usable torque
  - restrained thermal expansion
  - pinned vs fixed ends
  - lever arm measured from the wrong point
- **Realistic settings:** robotics, 3D-printed fixtures, shelving, machine frames, drones, camera rigs, furniture, test rigs. Use realistic dimensions, materials and loads, so nothing like a 2 m-long 1 mm bracket.
- **Mixed wording:** vary phrasing and units (mm/in, N/lbf/kg, MPa/psi), as long as `task.yaml` inputs stay in mm, N, MPa and kg.
- **Controls:** about 30% of cases are genuinely fine designs (`control: true`). A fair checker must accept correct answers.

## Correctness rules (strict)

1. **Two independent answers per case.** Work out `truth.yaml` by hand (show the steps in `why`). Then run `python -m goodman truth tasks/strength/<id>`. The verdict must say `AGREE` and every value must be `ok`. If they disagree, fix your hand calc or drop the case. Never tune `truth.yaml` just to match the checker.
2. **No borderline cases.** The verdict must stay the same if any one input changes by ±15%, or if a reasonable alternative method is used (for example Gerber instead of Goodman, or Kt off a chart ±10%). Drop any case whose safety factor sits within 15% of the required value.
3. **Cite sources.** Material values come from `goodman/materials.yaml` or a cited datasheet. Kt and fatigue factors come from Shigley, Peterson or Roark.
4. **No duplicates.** Two cases may share a model and trap only if the setting, numbers and wording are clearly different.

## Checks before opening the PR

Write a script `scripts/check_cases.py` that loads every `tasks/strength/g*` folder and fails if any of these hold:

- a file is missing or a YAML file doesn't parse
- `goodman truth` disagrees with `truth.yaml`
- a `prompt.md` mentions the trap's key words (e.g. "buckling", "fatigue", "stress concentration", "Kt", "layer")
- the case is borderline under the ±15% rule (perturb each numeric input and re-run the checker)
- controls make up less than 25% or more than 35% of cases

Also run `pytest`. Everything must pass.

## Pull request

In the PR description include a table with counts per model and per trap, the number of controls, the cases you dropped and why, and the full output of `scripts/check_cases.py`. End the description with the usual attribution line.
