# v4 robot arm: range-of-motion sweep

**Input:** Mechy `24-hourrobotarm` at commit `f6953e4`: `design/v4/assembly.glb` (118 parts), `joints.yaml`, `assembly.yaml` (`allow_contact`) and `geometry.py` (reach rule on). The live v4 folder has since changed: `wrist-flange` was added and the GLB re-exported, but `joints.yaml` hasn't been regenerated. Re-run once Mechy writes a matching `joints.yaml`.

**Command:**

```bash
python -m goodman motion <v4>/assembly.glb <v4>/joints.yaml --out results/motion/robotarm-v4
```

The run took 6 min 45 s on a laptop:
- 147,631 reachable poses were checked, and 5,232 sampled poses were rejected by the reach rule.
- Of the 6,903 part pairs: 1,047 sit on the same body, 62 are designed contacts, 351 can never reach each other, and 5,443 were swept.

**Verdict: `collisions`, 39 part pairs.**

## How the findings were checked

- **Re-posed independently:** each finding's worst pose and first-contact pose was re-built with the kinematics (which match Mechy's 15 saved poses to 0.01 mm) and re-collided.
  - Every worst pose collides and passes the reach rule.
  - 38 of 39 first-contact poses collide. The exception is `uno-cnc-shield`/`j2-pin-a`, which re-checks as just clear. First contact sits on the boundary, and the JSON rounds angles to 0.01°.
- **Looked at:** only two renders by eye (`uno-cnc-shield__jaw-a`, `lower-shank__gripper-base`). For the rest, use the renders or open `poses/*.glb`.

## What it found

**A. The gripper reaches down into the electronics bay (32 pairs).**
- Pose: yaw past about 118° (or below −148°), shoulder 32–71°, elbow folded −84° to −132°.
- Parts hit: `uno-cnc-shield` (17), `uno-usb-keepout` (7), `yaw-motor-plate` (3), `base` (2), `buck-converter`, `belt-yaw` and `yaw-plate-screw-1`. They're hit by the jaws, crank gears, idler links, jaw pins and nuts, `gripper-base` and `gripper-servo`. Penetration is up to about 36 mm.
- Why the firmware allows it: the reach rule only bounds the wrist point (≥ 95 mm high within 200 mm of the yaw axis) and the fingertip (≥ 3 mm). The gripper body hangs 80–90 mm below the wrist point, right over the Uno at x ≈ −118 mm. **Real; the reach rule doesn't protect the electronics bay.**

**B. A folded elbow clips the shoulder inside its allowed range (6 pairs).**
- Pose: yaw 0, elbow −133° to −134°, wrist −80° to −89°.
- Parts hit: `gripper-base` and `gripper-servo` hit `lower-shank` and `belt-sh2`, and `jaw-a` hits `turret` and `yaw-pulley`.
- `geometry.py` says the gripper meets the lower shank *past* −135°. Contact actually starts around −133°, inside the limit. **Real; the elbow limit has no margin at these wrist angles.**

**C. Swung back over the base (1 pair).** `jaw-b` hits `base` at shoulder 139°, elbow +94°, wrist 73°, near the elbow's +100° limit. **Real.**

No false alarms were found among the checked findings. Designed contacts from `allow_contact`, and anything already touching at home, were excluded before the sweep.
