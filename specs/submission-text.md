# Mercor Hack Day submission text

**Team name:** Better Call Goodman

**Project name:** Better Call Goodman

**One line pitch:** AI says your part is safe. Goodman runs the CAD code it wrote, measures the real geometry, and recomputes the safety factor.

**GitHub repo:** https://github.com/carbcodes/bettercallgoodman

**Built with:** Python, build123d, OpenCascade, NumPy, PyYAML, pytest, React, Three.js, Vite

## The write up

**What we built.** Goodman is a design checker for mechanical parts. We ask ChatGPT (GPT-6, one fresh chat per task) to design a part for a load, for example "a PLA towel hook that holds 1.5 kg at safety factor 2", and to write the CAD as a build123d script. Goodman runs that script and measures the real solid it produces. It never trusts the AI's own numbers.

**How it checks.** The AI only designs. Goodman does the judging, with no AI in the verdict:
1. Run the AI's script and export the STEP solid. Check the hard requirements (single solid, width, reach).
2. Find where the load acts, from the geometry and the prompt (for example the lowest inside point of the hook).
3. Slice the part along its length and compute the bending stress at each section: sigma = M*c/I, times a stress-concentration factor Kt at fillets and steps. Compare to the material strength (PLA is derated for print direction). The weakest section sets the safety factor.
4. Extract the AI's claimed safety factor (quoted from its answer) and compare it to the measured one. Verdicts: confirmed, conservative, refuted (the AI overclaimed), or caught (the part fails the requirement).
5. A 3D view colours the whole part by the checker's stress model and shows the critical section.

Beyond strength, the repo also has checkers for collisions and clearances, FDM printability (overhangs, thin walls, supports) and 3-axis CNC milling (inside corners, undercuts, pocket depth). The 3D printing and CNC checkers are secondary to the strength check.

**What we found.** 12 design tasks, ChatGPT GPT-6 on 2026-11-06, first answer kept, no answers or check shown to it. 7 gave a part we could check. 5 stalled with no usable answer, so we report them but do not count them.
- 6 of 7 parts met the safety-factor requirement. The AI's claimed number was often wrong anyway.
- d08 towel hook (caught): ChatGPT claimed SF 4.7. Goodman measured SF 1.57, below the required 2. Critical section is the 6 mm wall leg, with Kt 2.56 at the fillet. The part would not pass.
- d01 wall hook (refuted): ChatGPT claimed "approximately 160". Measured 42.9. The part is safe, but the claim is off by about 3.7x.
- d04 bag hook (refuted): ChatGPT claimed 2.7. Measured 2.03. This one barely clears the requirement of 2, so a "2.7" would have hidden how little margin there was.
- d02, d03, d07 were conservative (the AI under-claimed). d06 matched (claimed 3.0, measured 3.5).

So the failure mode is not always "unsafe part". The AI states an exact safety factor with confidence, and it has no real basis for it. Goodman accepts parts that hold, flags the claim when it is wrong, and catches the one part that fails.

**Limits.** This is a small sample (7 checked parts from one model). The strength check is closed-form beam theory plus Kt, not FEA. We do not model dynamic loads beyond fatigue, contact friction or print tolerances. The stress colouring in the 3D view is an illustration of the same model, not a simulation.

**Correct answers and AI attempts.** Each task folder in `tasks/cad/` has the exact prompt (`prompt.md`), the AI's script and answer (`attempt*.json`, `attempt_script.py`), the STEP part and the full check (`result.json`, with every requirement and the critical section). `results/chats.md` maps every result to its ChatGPT chat link, model, date and script hash.

## Short fields

- **Demo video:** (record, 2 min; show d08 end to end, then d06 as the control that Goodman accepts)
- **Live demo:** none (runs locally: `npm --prefix ui install` then `npm --prefix ui run dev`)
- **Pictures:** screenshots of the UI for d08 (stress-coloured hook, failing check) and the results table. First one is the cover.
- **Teammates:** Carlos Balbuena, plus Fabian (farevalo6@gatech.edu), already invited.
- **Entry zip:** `zip -r goodman.zip . -x "ui/node_modules/*" ".git/*"` from the repo root (under 100 MB, includes the UI source and README).
