# Candy crank dispenser: range-of-motion sweep

**Input:** `candy-crank-dispenser/`.
- 4 revolute joints: crank/metering drum (one full turn), an agitator geared to the crank, a free-spinning grip and the refill lid.
- `geometry.py` has no reach constants, so the full joint-limit box is swept.
- 64,201 poses checked.
- 1,472 of 6,328 part pairs swept.
- The run took 18 s.

**Verdict: `no_collisions`.** This agrees with the design's own `motion-validation.json`, which reports `PASS` from 58 sampled poses. Goodman checked about 1,100 times as many poses and found nothing.
