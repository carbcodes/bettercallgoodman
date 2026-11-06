# 11 · Instructions for Devin: 3D printing and 3-axis CNC checkers

Paste everything below the line into Devin, as a second task next to the case generation in `specs/09`.

---

## Goal

In the public repo `carbcodes/bettercallgoodman`, build two geometry checkers that take a **STEP file** of a part and report whether it can be made. One covers FDM 3D printing, the other 3-axis CNC milling. Work on a new branch `devin/printing-cnc` and open a pull request. Don't push to `main`.

Why STEP input: the project's headline is now "AI designs the part, Goodman checks it." ChatGPT writes build123d code, Goodman runs it and gets a `part.step` (another session is building that runner in `goodman/checkers/cad.py`). Your checkers will be called on those STEP files, so they must work on any solid, not only on parts we describe.

Read first: `README.md`, `specs/00-overview.md`, `specs/01-formats.md` (result format and statuses), `specs/05-printing.md` and `specs/06-cnc.md` (the rule tables, which are your spec), and `goodman/materials.yaml`.

## What to build

1. **Rules as data:** `goodman/rules/fdm.yaml` and `goodman/rules/cnc_3axis.yaml`, holding every threshold from specs 05 and 06 (overhang angle, minimum wall, bridge length, hole undersize, inside corner radius vs tool, pocket depth/tool ratio, hole depth/diameter, thin wall in aluminium, and so on). Cite a source next to each number (a slicer's docs, a machining handbook, or a well-known DFM guide).
2. **`goodman/dfm/printing.py`:** `check_printing(step_path, build_dir=(0, 0, 1), printer=None) -> dict`, where `build_dir` is the up direction on the print bed. It reports:
   - overhang faces: the area and the worst angle of faces pointing down more than the limit, ignoring faces on the bed
   - minimum wall thickness: ray-cast or sample through the solid, reporting the location and value
   - bed contact: the flat area on the lowest plane
   - bridges: horizontal down-facing spans longer than the limit
   - small vertical holes that will print undersize (cylindrical faces with an axis along `build_dir`)
   - build volume fit
3. **`goodman/dfm/cnc.py`:** `check_cnc(step_path, setups=[(0, 0, 1)], material="Al6061-T6") -> dict`. It reports:
   - inside vertical edges: sharp ones that can't be milled, and radii smaller than practical tools
   - pocket depth vs the tool diameter that the smallest corner radius allows
   - faces unreachable from every listed setup direction (undercuts)
   - hole depth/diameter
   - thin walls
   - the number of setups needed
4. **Output format:** both functions return `{"verdict": "printable"|"not_printable"` (or `"machinable"|"not_machinable"`), `"findings": [{"rule", "value", "limit", "location": [x, y, z], "why"}]}`. Each `why` is one plain sentence a judge can read, for example "Overhang of 62° under the hook tip at (41, 0, 18); FDM limit 45° without support."
5. **CLI:** `python -m goodman.dfm printing <part.step> [--up 0 0 1]` and `python -m goodman.dfm cnc <part.step> [--setups ...]`, printing the findings.
6. **Geometry stack:** use build123d / OCP (`.venv/bin/pip install build123d`; add it to requirements as optional). Keep the code self-contained in `goodman/dfm/`.

## Test parts (your evidence)

Under `tests/fixtures/dfm/`, write small build123d scripts that generate STEP parts with known answers, plus `tests/test_dfm.py`:

- **Printing:** a 60° overhang lip (fail), a 40° chamfered version (pass), a 0.5 mm wall (fail), a 1.2 mm wall (pass), a 3.0 mm M3 hole (warn undersize), a bracket that prints cleanly (pass, the control).
- **CNC:** a square-cornered pocket (fail), the same pocket with a 3 mm corner radius at 10 mm depth (pass), a 1 mm corner radius on a 25 mm-deep pocket (fail on depth/tool), a T-slot undercut from the top setup (fail), a 3 mm hole 40 mm deep (fail), a plate with through holes and generous radii (pass, the control).

Every fixture states its expected verdict and the key finding. All tests must pass, including the existing ones (`.venv/bin/python -m pytest -q`).

## Don't touch

`goodman/checkers/cad.py`, `goodman/verdict.py`, `goodman/cli.py`, `ui/`, anything under `tasks/`, or `specs/` other than adding a short "Implementation" note at the end of 05 and 06. Another session and the main team are editing those right now.

## Pull request

The PR description lists every rule with its threshold and source, the fixture table (part → expected → actual), the test output line, and the known limits (e.g. the wall-thickness sampling resolution). End the description with the usual attribution line.
