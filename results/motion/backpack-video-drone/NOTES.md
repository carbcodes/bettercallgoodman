# Backpack video drone: range-of-motion sweep

**Input:** `backpack-video-drone/`.
- 10 revolute joints: 4 arm folds, 4 rotor phases, the camera servo and the camera link.
- `geometry.py` has no reach constants, so the full joint-limit box is swept.
- 518,959 poses checked.
- 9,633 of 23,005 part pairs swept.
- The run took 77 s.

**Verdict: `collisions`, 6 part pairs, all on the front arms.**
- Left: `fl-propeller` hits `side-panel-left`, `deck-1-spacer` and `deck-1-bolt-upper`.
- Right: `fr-propeller` hits the mirrored set.
- Contact starts in the last 6–12° of the fold, before the stop at ±123°. The deepest overlap is 5.3 mm.

**This is conditional.** The README says to fold "with props kept parallel to the body", parking the rotor phase at −fold angle. That is a manual operator step, not a mechanism.
- At the design's own `stowed` pose, every pair clears by 16.7–20.9 mm.
- At full fold, 172 of 360 rotor phases collide on the left arm and 178 of 360 on the right.
- The parked phase sits in a safe window about 95° wide.

The design's motion audit (`validation.json`) only sampled the parked folding, so it never saw this.

**Finding:** fold a front arm without lining the prop up first, and the blade hits the side panel and the deck stack. Nothing in the hardware prevents it.
