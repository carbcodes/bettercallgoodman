# Range-of-motion collision checker: design

**Owner:** Fabian · **Date:** 2026-11-06 · **Status:** draft for review

## Why

AI-generated assemblies often pass a static interference check at home and at a few hand-picked poses, then collide somewhere in between: an elbow folded while the shoulder is low, a gripper jaw swinging into its own mount. Mechy's current check (`design/v4/check_poses.py` in the robot-arm project) only looks at the 15 named poses in `joints.yaml`. This checker looks at the **whole range of motion** and reports every collision it finds, with the pose where it happens.

It's a Goodman checker, built in this repo. It's separate from Mechy for now and may later run on top of it.

## Goals

- Input: a Mechy `assembly.glb` plus its Mechy motion file (`joints.yaml`). Two optional extras from the same Mechy design folder: `assembly.yaml` (for its `allow_contact` list) and `geometry.py` (for the reach rule). Without them it still runs.
- Explore every combination of the independent joints within their limits **and the reach rule**, not one joint at a time.
- Output a verdict, `no_collisions` or `collisions`. For each collision: which two parts, the joint values where it happens, and where on the parts it happens.
- Run time: minutes on a laptop is fine. Results are computed **before** the demo and shown there; nothing runs live.

## Non-goals

- **A proof of no collision.** "We sampled densely and found none" is good enough for now (Fabian's call). The distance-bound method that would give a guarantee (Schwarzer, Saha & Latombe, *IEEE T-RO* 2005) is noted as a later upgrade.
- **Static fit at home.** Same-body interference, clearance and fit at the home pose are Mechy's existing check. This one is only about motion.
- **New formats.** The motion file stays exactly Mechy's `joints.yaml`, and we don't define our own.
- **Prismatic joints, dynamics, timing, joint speeds.** Only revolute joints are swept, kinematically.
- **The table as an obstacle.** Only part-against-part collisions are checked. The table only shows up through the reach rule.
- **Paths between poses.** Mechy's firmware also checks 16 points along each move. We check poses, not moves.
- **Converting the simple-solid tasks in `tasks/collision/` (spec 04) into GLB inputs.** That's possible later, but not part of this work.

## Anti-goals (would make this a failure even if it runs)

- **Flagging contacts that exist by design**: bolts in nuts, bearings in housings, belts on pulleys. A wall of false alarms makes the real hit invisible.
- **Pose maths that silently disagrees with Mechy.** Every reported pose must be one Mechy would build from the same joint values.
- **Copying Mechy source code.** This repo is public. Reimplement; don't paste.

## Inputs

Example pair: `~/Mechy Projects/24-hourrobotarm/design/v4/assembly.glb` and `.../design/v4/joints.yaml`.

**`assembly.glb`** (exported by Open CASCADE through Mechy):
- One root node named `assembly`, with rotation quaternion `[-0.7071, 0, 0, 0.7071]`: the Z-up to Y-up conversion. All 118 parts are direct children, each with one mesh, and the node **name is the part id**. There's no hierarchy and no joint data in the file.
- Child node translations are in **metres** in the Z-up assembly frame. For example, `s-axle` sits at z = 0.116 m, matching the shoulder origin z = 116 mm in `joints.yaml`.
- The GLB is the arm at its **home pose** (every joint at its `home` value).
- 154k triangles in total. The largest parts are `upper-shank` and `lower-shank` at about 20k each.

**`joints.yaml`** (Mechy's format, lengths in mm, angles in degrees, Z-up assembly frame):
- `joints[]`: `id`, `type: revolute`, `parent` (joint id or null), `origin` [mm], `axis`, `parts` (part ids carried by this joint), `home`, `limits` [min, max], optional `coupled: [{joint, ratio}]`, optional `label`.
- `poses[]`: named poses giving values for the independent joints.
- `checked.poses[]`: Mechy's own record of the named poses it verified.
- Parts listed in no joint are fixed to the ground (for example `base`, `yaw-motor`).

**`assembly.yaml` (optional, Mechy's own).** If a file with this name sits next to the GLB, read its `allow_contact` list: pairs of part ids that are meant to touch, 138 in the arm. Those pairs are never reported. This matters for contacts that only happen near a limit, like `yaw-switch` against `yaw-pulley`. Nothing else in the file is used.

**`geometry.py` (optional, Mechy's own, `--geometry <file>`).** Mechy's arm firmware (`clearOk` in `firmware/arm_v4`) refuses some poses that are inside the joint limits. The rule's constants live in `design/v4/geometry.py`, line 25: `W_Z_MIN, W_Z_NEAR, NEAR_R, TIP_Z_MIN = 45.0, 95.0, 200.0, 3.0`, plus `TOOL = 89.0` on line 15.
- The wrist point W must be at least `W_Z_MIN` (45) mm above the table everywhere.
- W must be at least `W_Z_NEAR` (95) mm above the table within `NEAR_R` (200) mm of the yaw axis, where the turret, base, Uno and yaw motor are.
- The fingertip must be at least `TIP_Z_MIN` (3) mm above the table.

How the checker uses it:
- **Never execute it.** It's AI-generated Python. Parse it with `ast` and read only those five names, via `ast.literal_eval`. Plain and tuple-unpacking assignments both work. If any name is missing, stop with an error naming it.
- **Fixed meanings.** These follow Mechy's arm conventions:
  - W = the `wrist` joint's origin, posed.
  - The yaw axis = the `yaw` joint's axis.
  - The table = the plane z = 0 in the Z-up assembly frame. The builder should confirm that's the base's bottom face.
  - Fingertip = `TOOL` mm from W along the gripper axis. At home (`wr = -90`, gripper pointing straight down) that axis is −z, and it turns with the `wrist` joint's posed rotation.
- **Not reimplemented.** The firmware's own `clearOk` lives in C code we don't read.

Without `--geometry`, the sweep covers the full joint-limit box.

**Keepouts are solid.** Parts named `*-keepout` (motor plug and Uno USB clearance volumes) are checked like any other part. A link passing through one means the cable or plug gets hit.

**Independent vs coupled joints.** A joint with a `coupled` list is driven by the joints it names. In the arm, the `*-stack`, `*-pin` and `mount-*` joints counter-rotate bolts and nuts so they keep a fixed orientation, and `crank-b`, `idler-*` and `jaw-*` follow `crank-a`. Only the joints **without** `coupled` are swept. In this arm that's `yaw` [-150, 150], `shoulder` [20, 140], `elbow` [-135, 100], `wrist` [-95, 95] and `crank-a` [-10, 50]: 5 DOF.

## How a pose is built

Given values for the independent joints:
1. Each coupled joint's value comes from its drivers. Builder's assumption to verify: `value = home + Σ ratio · (driver − driver.home)`.
2. Each joint applies a rotation of `(value − home)` degrees about `axis` through `origin`, composed down the `parent` chain (a child joint's origin and axis move with its parent).
3. Each part takes the transform of the joint that lists it, applied on top of its home placement from the GLB. Ground parts don't move.

**Must be checked against Mechy before anything else.** `design/v4/poses/<name>/assembly.yaml` holds Mechy's placement of every part (position in mm, Euler rotation in degrees) for each of the 15 named poses. Our pose builder must reproduce these to within about 0.01 mm and 0.01°.
- The pose folders match the pose names in `joints.yaml` one to one.
- `glb_sha256` in `joints.yaml` equals the hash of `assembly.glb`, so the pair is consistent. Warn if they differ.
- The pose files' notes use the arm's absolute angles, not `joints.yaml`'s relative ones: `th1 = shoulder`, `th2 = shoulder + elbow`, `wr = th2 + wrist`, `grip = (crank-a + 10)/60`. The checker itself only uses `joints.yaml` values.
- The Euler convention has to be worked out from the files. Home `lower-shank` is quaternion `[0.5, -0.5, 0.5, 0.5]` in the GLB, and at `reach-table` (shoulder 20) it's Euler `[90, -20, 0]`.
- If the conventions in step 1 or 2 turn out to be different, fix them until the 15 poses match.

## Which pairs are checked

Parts are grouped into **bodies**, one per joint plus the ground. Two parts on the same body never change their relative position, so they're never checked. The static check already covers them.

For every pair of parts on different bodies:
- **Relevant joints.** Find the independent joints that change their relative position: walk both bodies' joint chains up to their common ancestor and map the joints on that path through `coupled` to their drivers. Only those joints are varied for that pair; the rest stay at home. In the arm, of the 276 body pairs, 27 depend on 1 independent joint, 15 on 2, 80 on 3, 144 on 4 and 10 on all 5.
- **Allowed contact.** A pair is skipped and listed under `ignored_pairs` (with the reason) if either:
  - it's in `allow_contact` (when `assembly.yaml` is present), or
  - it already touches or overlaps at the home pose: bolt in nut, bearing on axle, belt on pulley.

  Known gap: a designed-contact pair that collides in some *other* way elsewhere in the range is missed. Accepted for now.
- **Quick reject.** If the pair's distance at home is larger than the farthest any point on either part can travel relative to the other over the relevant joint ranges (a bound: the distance from each joint axis times the joint's range, summed), skip it as unable to collide.

## How each pair is explored (sampling, good enough)

Per remaining pair, over its relevant joints only:
- **1 joint:** a grid at 0.5° across the full range.
- **2 joints:** a 2° × 2° grid.
- **3–5 joints:** a low-discrepancy sample (Halton or Sobol) of about 20,000 poses over the box of joint limits, always including the corners of the box and the 15 named poses.
- **Refinement on a hit:** from each colliding sample, bisect toward the nearest collision-free sample to find the first-contact pose to about 0.1°. Then search nearby (a small local grid) for the pose with the deepest penetration.
- A hit means the two meshes intersect, using FCL's mesh-mesh collision query.

**Reach rule during sampling.** The rule depends on the whole arm, but a pair only varies its relevant joints. A sample for a pair counts as **reachable** if some setting of the *other* independent joints satisfies the rule: try their home values first, then a few hundred random settings. Then:
- Collisions are only checked, and only reported, at reachable poses, and the reported pose includes the other joints' values that made it reachable.
- Unreachable samples are dropped and counted in `stats.poses_unreachable`.
- Bisection and the worst-pose search stay inside the reachable region. A collision that only exists at unreachable poses isn't reported.
- The grid and Halton counts above are counts *before* rejection. If more than half of a pair's samples are rejected, top up with more Halton points until about 20,000 are reachable.

Grouping hits: collisions for the same pair are merged into one finding. That finding reports the range of each relevant joint over which colliding samples were seen, the first-contact pose and the worst pose.

Prior art this follows:
- [MoveIt's self-collision matrix](https://moveit.picknik.ai/main/doc/examples/setup_assistant/setup_assistant_tutorial.html): dense random sampling per link pair, accepted as incomplete.
- [Schwarzer, Saha & Latombe](https://typeset.io/pdf/adaptive-dynamic-collision-checking-for-single-and-multiple-1nf1vuonxs.pdf): the motion bound behind the quick reject, and the later upgrade to a guarantee.

## Output

A `motion_result.json`:

```json
{
  "verdict": "collisions",
  "inputs": {"glb": "...", "joints": "...", "assembly_yaml": "... or null", "geometry_py": "... or null", "reach_rule": {"W_Z_MIN": 45.0, "W_Z_NEAR": 95.0, "NEAR_R": 200.0, "TIP_Z_MIN": 3.0, "TOOL": 89.0}, "glb_sha256": "...", "joints_sha256": "..."},
  "swept_joints": {"yaw": [-150, 150], "shoulder": [20, 140], "elbow": [-135, 100], "wrist": [-95, 95], "crank-a": [-10, 50]},
  "collisions": [
    {
      "parts": ["upper-shank", "base"],
      "joints": ["yaw", "shoulder", "elbow"],
      "first_contact": {"yaw": 0.0, "shoulder": 24.3, "elbow": -131.8},
      "worst": {"pose": {"yaw": 0.0, "shoulder": 20.0, "elbow": -135.0}, "penetration_mm": 3.1},
      "contact_point_mm": [62.4, 0.0, 41.0],
      "colliding_range": {"shoulder": [20, 31], "elbow": [-135, -118]},
      "render": "renders/upper-shank__base.png",
      "why": "upper-shank hits base at shoulder 24.3°, elbow -131.8°; contact near (62, 0, 41) mm on the base's top-front edge"
    }
  ],
  "ignored_pairs": [{"parts": ["yaw-bolt", "yaw-nut"], "reason": "allow_contact"}, {"parts": ["...", "..."], "reason": "in contact at home"}],
  "stats": {"pairs_total": 0, "pairs_same_body": 0, "pairs_ignored": 0, "pairs_rejected_far": 0, "pairs_sampled": 0, "poses_checked": 0, "poses_unreachable": 0, "seconds": 0}
}
```

- `contact_point_mm` is in the Z-up assembly frame, in mm.
- Every finding gets a PNG render of its worst pose, with the two colliding parts highlighted and everything else faded.
- The CLI also prints a short summary: verdict, number of collisions, then one `why` line per collision.

## Validation (done when)

1. **Kinematics:** all 15 named poses reproduce Mechy's `poses/<name>/assembly.yaml` placements within 0.01 mm and 0.01°.
2. **Reach rule:** at Mechy's `fold-low` pose, W comes out 200 mm from the yaw axis and 53 mm high; at `reach-low`, W is 45 mm high (the poses' own notes say so). Both count as reachable, and nudging `reach-low` down by 1° makes it unreachable.
3. **Planted collision:** a small synthetic GLB and `joints.yaml` matching task `c01-arm-tilt-base` (base box 60 × 60 × 40 mm, link 120 × 15 × 20 mm pivoting at z = 55 mm, swept down to −30°). The checker reports first contact at 9.22° below horizontal, within the ±0.05° tolerance in that task's `truth.yaml`. So refinement for 1-joint pairs goes to 0.01°, not 0.1°.
4. **Planted control:** the same file with the pivot raised so the link clears the base through the full range. Result: `no_collisions`.
5. **The real arm:** runs end to end on the v4 robot arm in under 30 minutes, and writes `motion_result.json` plus renders. Whatever it finds gets spot-checked by posing the arm at the reported values (a posed GLB export makes this easy).

## Decided

- **Fabian:**
  - Inputs are Mechy's `assembly.glb` and `joints.yaml`, as they are today.
  - Sampling is good enough; no proof required.
  - Only pairs that can actually move relative to each other are checked.
  - Results are computed ahead of the demo.
  - It lives in this repo, separate from Mechy.
  - Honour the arm's reach rule.
  - Keepouts count as solid.
  - Read `allow_contact` from `assembly.yaml` when it's there.
  - No table obstacle for now.
  - `geometry.py` is an input, and the reach rule comes from it.
- **Claude** (Fabian to check):
  - Python 3.11+, with `trimesh` for loading the GLB and `python-fcl` for collision queries.
  - Pairs touching at home are also treated as designed contacts, on top of `allow_contact`.
  - `geometry.py` is parsed, never run, and only the five reach-rule constants are read.
  - The fixed meanings of W, the yaw axis, the table at z = 0, and the fingertip as `TOOL` mm along the gripper axis (−z at home).
  - A pair's pose is reachable if *some* setting of the other joints satisfies the rule.
  - The sample densities above (0.5°, 2°, 20k reachable), with 0.01° refinement for 1-joint pairs.
  - The JSON shape above.
  - CLI entry point: `python -m goodman motion <assembly.glb> <joints.yaml> [--assembly <assembly.yaml>] [--geometry <geometry.py>] --out <dir>`. If the flags are left out, both optional files are also picked up from the GLB's folder when present.
  - Code location: `goodman/checkers/motion.py`, alongside the planned `collision.py`.

## Left to the builder

- How to render: matplotlib on decimated meshes, or a posed GLB plus a screenshot.
- How to cache FCL models and per-body transforms for speed.
- Parallelism across pairs.
- Exact refinement and local-search details, as long as they hit about 0.1°.
- The Euler convention, as worked out from Mechy's pose files.
