# Checker issues found while building d13–d42

None of these were fixed: the checkers were left alone (goodman/dfm, goodman/design, goodman/rules unchanged).
Items marked **(expected)** were spotted by reading the code before any ChatGPT run. Confirm or remove them once the
cases have results.

## 1. Each case should be judged on one process, but the code runs both (confirmed in code)

- `python -m goodman design check` always runs the FDM printing check and saves it in `result.json["printing"]`,
  for CNC cases too (`goodman/design/__main__.py`, `_printing`).
- `python -m goodman export` runs both printing and CNC on every `part.step` (`goodman/export.py`, `_dfm`), so the UI
  shows a printing verdict on aluminum parts and a CNC verdict on PLA parts.
- `task.yaml` now has `process: printing | cnc`, but nothing reads it yet. For d13–d42, only the check named by
  `process:` counts. The other one is ignored.

## 2. `result.json["outcome"]` only covers strength (confirmed in code)

`outcome` (`accepted` / `caught`) comes from the strength and envelope checks alone. The DFM verdict never changes it.
For d13–d42 the overall verdict is strength AND the DFM check for that case's process, worked out by hand from
the two outputs.

## 3. CNC always runs as Al6061-T6 (confirmed in code)

`export.py` hard-codes `material="Al6061-T6"`, and the CLI command in the run instructions doesn't pass `--material`.
d38 is mild steel. `cnc_3axis.yaml` gives steel the same 0.8 mm minimum wall, so its verdict shouldn't change.

## 4. Threads and tolerances aren't checked (confirmed in rules: `checked: false`)

A STEP solid has no thread callouts, so d32 (a blind M8 thread 23 mm deep in a 25 mm bar) gets caught only if
ChatGPT models the drilled hole deep enough to leave a floor under 0.8 mm. **(expected)**: probably missed.

## 5. Open-ended T-slots and dovetails may count as reachable **(expected)**

Reachability is a ray test per setup direction. A slot that runs out through one end of the part lets rays from
the ±x setups travel along it, so the faces under the lips may count as "seen". A straight end mill along x can't
cut them. This affects d29 (T-slot open at the tip) and possibly d41 (a dovetail open at the frame end).

## 6. Printing orientation (note, not a bug)

The `goodman.dfm printing` CLI command in the run instructions uses the default `--up 0 0 1`. `design check` builds
up along `layer_normal`. All new printing cases print z-up (`layer_normal: z`), so the two agree.
