# 00 · Overview and plan

## The challenge

Mercor Hack Day: AI agents now do specialized work, and checking that their output is correct is still unsolved, especially outside math and code. Build something that tells a right AI output from a wrong one, in a field we know.

Rules that shape everything below:

- Pick **one AI** and use it for every task.
- Start a **new conversation per task**, and never show it our answers or our check.
- Keep its **first answer** unchanged, saving the model, date and exact prompt.
- Hand in: code, the correct answers (with why each is right), the check accepting right answers and catching wrong ones, the AI attempts, and a short write-up.
- **Submissions close at 4:00 sharp.** The demo is 3 minutes plus 2 minutes of questions.

Grading (100 points): problem quality and realism 25, correctness and fairness 25, verification quality 25, experimental evidence 10, technical communication 15. Ties are broken by correctness, then verification, then problem.

## The idea

An AI's design answer is a bundle of **claims**: numbers ("max stress 32 MPa"), verdicts ("safe", "no collision") and omissions (it never mentions buckling). Goodman turns that bundle into checks:

```
task.yaml ─► AI (fresh chat) ─► attempt.json
                                   │
                          claim extraction (02)
                                   │
                         claims.json (reviewed)
                                   │
       ┌────────────┬──────────────┼──────────────┬────────────┐
   strength (03) collision (04) printing (05)  cnc (06)   ...
       └────────────┴──────────────┼──────────────┴────────────┘
                                   │
                       result.json + report (per claim)
```

Each checker computes the true value **independently of the AI** (closed-form engineering, FEA, exact geometry) and compares it to the claim. Every flag has to say *why*, for example "claimed 32 MPa, actual 71 MPa: missed the Kt = 2.2 stress concentration at the 1 mm fillet".

What makes this more than "ask a second AI": the AI only ever extracts what the answer *said*. Deciding whether it's *right* is always done by physics or geometry code, which we can show judges line by line.

## Who does what

| Person | Core (must ship) | After the core |
| --- | --- | --- |
| Carlos | Strength checker (03) and strength cases | Write-up and demo (07) |
| Fabian | Collision checker (04) and collision cases | 3D printing (05), then CNC (06) |
| Together | Formats (01), claim extraction (02), runner, results table | Final run, submission |

Each person writes their own cases **and** their correct answers. Whoever writes a case has to be the one who can defend its answer.

## Timeline

| Time | Carlos | Fabian |
| --- | --- | --- |
| 11:30–11:50 | Together: agree on the formats in 01 and stub the runner | |
| 11:50–1:15 | 5 strength cases + hand calcs | 5 collision cases + geometry |
| 1:15–2:15 | Strength checker | Collision checker |
| 2:15–2:45 | Run the AI on every task (fresh chat each), save attempts | Claim extraction on all attempts, review claims |
| 2:45–3:15 | Together: run all checks, fix false flags, results table | |
| 3:15–3:50 | Write-up + demo rehearsal | Printing / CNC if the core is green; otherwise help polish |
| 3:50 | Zip and submit at hackerhousecampus.com/mercor/submit | |

**Hard rule:** don't start stretch work until all core cases run end to end.

## Case mix (per area)

- 5 cases at minimum: **3–4 with a trap** the AI is likely to miss, plus **1 control** that is genuinely fine. The control shows the check doesn't just flag everything (fairness).
- Realistic framing: write tasks as real jobs ("size the wall thickness for this camera mount"), not quiz questions ("what is the bending stress formula?").
- Before writing all cases, run 1–2 drafts through the AI. If it gets them right, make the trap subtler instead of more obscure.

## Repo layout

```
goodman/                 Python package
  cli.py                 python -m goodman check|run|report
  claims.py              claim extraction (02)
  verdict.py             compare claims to truth, build result.json
  checkers/
    strength.py          (03)
    collision.py         (04)
    printing.py          (05)
    cnc.py               (06)
tasks/<area>/<id>/       one folder per case (see 01)
results/                 generated: result.json per task + summary.md
specs/                   these documents
```

Python 3.11+. Dependencies are kept small: `numpy`, `pyyaml`, `build123d` (geometry for collisions), and the chosen AI's SDK for claim extraction.

**Mechy code:** we may borrow ideas from Mechy's FEA, assembly and print checks, but this repo is public. Only copy code we're fine publishing.
