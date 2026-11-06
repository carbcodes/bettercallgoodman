# Desktop robot arm 5-DOF ("Aster 320"): range-of-motion sweep

**Input:** `desktop-robot-arm-5dof/`, with `assembly.yaml` and `geometry.py` picked up, so the reach rule is on. That rule uses the same `W_Z_MIN`, `W_Z_NEAR`, `NEAR_R`, `TIP_Z_MIN` and `TOOL` constants as the design's own `check_motion.py`.
- 7 joints: 6 independent, 1 coupled.
- 214,904 reachable poses checked.
- 20,569 of 27,966 part pairs swept.
- The run took 347 s.

**Verdict: `collisions`, 231 part pairs.**

**The design's own claim:** `motion-checks.json` says `safe_samples_clear: true`. It sampled 599 poses, but it moves one joint at a time plus straight paths from home to the named poses. It never moves several joints together.

**What Goodman finds:**
- With the elbow folded far back (first contact at elbow −105° to −125°, where the limit is −125°) and the wrist pitched down, the gripper swings into the base. It hits the yaw turntable, the bearing carrier, the base plate, the base columns and the shoulder cradle and clamps.
- 219 of the 231 pairs involve gripper parts. The rest involve the gear guard (8) and jaws (4).
- The deepest overlap is 30 mm.

**Cross-check against the design's own code:** every worst pose was re-posed with the design's `validate.transforms` and tested with its reach rule (`scratchpad/xcheck.py`).
- All 231 pairs intersect.
- 190 worst poses pass the design's rule exactly.
- The other 41 miss it by less than 0.1 mm. Goodman's worst-pose search sits on the rule boundary with 0.1 mm of slack.
- The first-contact poses of all 231 pairs pass the design's rule.

These are real collisions in poses that the design's own firmware rule allows.
