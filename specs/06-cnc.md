# 06 · CNC milling checker (stretch)

**Owner:** Fabian · **File:** `goodman/checkers/cnc.py`
**Start only when** printing is done or skipped.

Check whether an AI's machining notes or its claim that a part is "ready to mill" hold up for 3-axis milling.

Write tasks as real jobs ("write the machining notes for this aluminum bracket so we can get a quote"), not "is this machinable?". Models know the textbook rules when asked directly and miss them when the problem is buried in a spec.

## Checks

| Check | Rule (3-axis, aluminum) | Method |
| --- | --- | --- |
| Inside corners | a vertical inside edge needs a radius ≥ the tool radius, and sharp corners can't be milled | concave vertical edges, fillet radius |
| Pocket depth | depth ≤ ~4× tool diameter, and the tool diameter is limited by the smallest inside radius | pocket depth vs min corner radius |
| Thin walls | aluminum walls under 0.8 mm chatter and deflect | wall thickness |
| Undercuts | faces that can't be reached from any of the stated setup directions | face normals vs setup axes |
| Hole depth | drilled holes deeper than ~10× diameter are unreliable | hole depth / diameter |
| Threads | thread depth ≤ drilled depth minus ~1.5 pitch, and blind taps need chip room | thread vs hole depth |
| Tolerances | tighter than ±0.025 mm on non-critical features drives cost | tolerance callouts in the task |

Cite where each threshold comes from. Thresholds go in a YAML file.

## Case ideas (pick 3: 2 traps + 1 control)

1. **Sharp-cornered pocket**: the AI's notes say "pocket 20×20×15 mm" with square corners and no mention of the radius.
2. **Deep small corner radius**: a 1 mm corner radius forces a 2 mm tool, but the pocket is 25 mm deep (12× the tool diameter).
3. **Control**: a plate with through holes and 3 mm corner radii on 10 mm pockets.

Bonus demo case: a bracket that fails **both** strength (sharp corner → stress concentration) and CNC (sharp corner → can't be milled). One fix, a proper fillet, solves both.
