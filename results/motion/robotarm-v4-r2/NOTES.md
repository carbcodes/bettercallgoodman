# v4 robot arm, second iteration: range-of-motion sweep

**Input:** the live Mechy `24-hourrobotarm/design/v4` as of 2026-11-06 15:03. That's commit `9cac2a2` plus an uncommitted `joints.yaml`.
- 119 parts; `wrist-flange` is new.
- The GLB sha256 `aa44280c…` matches `joints.yaml`.
- `assembly.yaml` and `geometry.py` were picked up, so the reach rule is on.

The run took 160 s. 147,631 reachable poses were checked, the same sample set as run 1. Of 7,021 part pairs, 5,574 were swept.

**Verdict: `collisions`, 48 part pairs (run 1 had 39).** All 39 from run 1 are still there, none are fixed, and 9 are new.

## What changed in the design, and what it did

**The design changes:**
- New `wrist-flange`. It collides with nothing.
- The gripper mount screws, wrist pulley and bearing, deck screws and nuts, and yaw motor screws moved slightly.
- **`uno-usb-keepout` grew** from about 46 × 15 × 26 mm to about 115 × 53 × 46 mm. It now covers the whole Uno footprint: x −164 to −49, y 36 to 89, z 8 to 54.
- `uno-cnc-shield` dropped 2 mm.

**The 9 new findings all come from the larger USB keepout.** They involve `uno-usb-keepout` against `gripper-base`, `gripper-servo`, both idler links, `idler-pivot-nut-b`, `j1-nut-b`, `j2-nut-b` and `j2-pin-b`, plus `uno-cnc-shield` against `idler-pivot-nut-b`. It's the same problem as before, the gripper reaching into the electronics bay, now caught on a bigger keepout.

## Still open (unchanged from run 1)

- **A. The gripper reaches into the electronics bay** (now 41 pairs).
  - Pose: yaw past about 111–118° (or below −148°), shoulder 32–72°, elbow folded −84° to −132°.
  - The reach rule bounds only the wrist point and fingertip, while the gripper body hangs 80–90 mm lower.
- **B. A folded elbow clips the shoulder** (6 pairs). Contact starts at elbow −133° to −134°, inside the −135° limit.
- **C. `jaw-b` hits `base`** with the arm swung back at shoulder 139°, elbow +94°, near the elbow's +100° limit.

## How the findings were checked

Each finding's first-contact and worst pose was re-posed independently and re-collided:
- All 96 poses pass the reach rule.
- 93 of 96 collide. The 3 exceptions are tiny pin and nut parts (`j1-pin-b`, `j2-pin-a` first contact, and `j2-nut-b` worst pose). Each re-checks as just clear after the JSON's 0.01° rounding, which means a grazing contact there.
