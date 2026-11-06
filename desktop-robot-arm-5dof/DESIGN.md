# Aster 320 — five-axis desktop robot arm

Design target: carry **150 g**, with **310.35 mm horizontal reach from the yaw axis** while the gripper points down. The structure uses 160 mm upper and forearm links, a 135 mm shoulder height, and a 135 mm wrist-to-fingertip envelope. The four-hole 220 x 180 mm base must be bolted to a rigid desk. This is a dimensional engineering prototype, not a bench-tested load rating.

## Deliverables and rebuild

`assembly.glb` is the home assembly. `joints.yaml` has five positioning revolutes plus a gripper drive and one coupled follower (seven joints, six independent actuators). `assembly.yaml` lists intended contact pairs. `geometry.py` contains literal mm/degree constants. Individual print-ready, mm-unit solids are in `stl/`; `print-manifest.yaml` records their orientations and dimensions. `bom.csv` contains every modeled component. `validation.json` is generated from the exported GLB, not the in-memory design. `preview.png` and `drawing.svg` show the arrangement.

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py
.venv/bin/python validate.py
```

Use the pinned versions and Python 3.11. The generator needs no network, fixes polygon resolution, and does not use randomness, timestamps, or external assets. Generated files are hashed in `manifest.sha256.json`. The source files are the rebuild inputs. Do not edit generated meshes manually.

## Actuation and purchased hardware

| Axis | Motor | 12 V vendor stall torque | Planning torque budget |
|---|---|---:|---:|
| Yaw | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Shoulder | XM540-W270-T | 10.60 Nm | 3.180 Nm |
| Elbow | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Wrist pitch | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Tool roll | XC330-T288-T | 1.00 Nm | 0.300 Nm |
| Gripper | XC330-T288-T | 1.00 Nm | 0.200 Nm holding target |

The 30% stall-torque planning allowance is an explicit design assumption, **not a manufacturer continuous rating**. Commission with current-based position control, current/temperature telemetry, 20 degrees/s joint speed and 40 degrees/s² acceleration caps. Apply a 1.25 factor to static loads for slow-motion sizing. Verify the thermal duty cycle with 150 g before unattended use. Shoulder and elbow are backdrivable on power loss; support the arm before releasing torque.

Yaw uses two 6808-2RS bearings (40 x 52 x 7 mm) separated by 13 mm; a hollow printed spindle transfers torque while the bearings react overturning load. Each pitch joint has a separately supported steel 8 mm idler axle and a 608-2RS (8 x 22 x 7 mm) bearing opposite the metal servo horn. The follower jaw uses a 5 x 10 x 4 mm bearing and 5 mm axle. Aluminum OEM output horns transmit torque; printed splines are not used. Standard M2, M2.5, M3 and M4 socket screws, hex nuts, collars and brass board standoffs are separate meshes.

Purchased servo housings, connectors, bearings and boards are **envelope models**, not vendor CAD. Motor internals, actual thread helices and bearing balls are omitted. Servo body clamps use envelope dimensions and do not depend on case screw patterns. Shaft offsets and horn integration dimensions are integration assumptions; confirm against the ordered hardware before printing all parts. HN13 uses a 22 mm pitch circle with M2.5 fasteners; HN12 uses 16 mm / M2; HNX330 is modeled with an 11 mm / M2 pattern. Confirm the HNX330 variant and drill a test coupon first. Holes and bearing seats include FDM clearance; ream journals/seats to fit.

## Load calculation

The generator computes gravitational moments from each exported part's center of mass and assigned mass. Purchased motor masses are 165/82/23 g (XM540/XM430/XC330). Printed parts use the full solid volume at 1.20 g/cm³, conservatively exceeding a hollow/infilled print. Fasteners use steel density. A 150 g payload is applied at the nominal fingertip point. Wiring mass is represented by retained runs; allow extra margin for the flexible service loops. Total modeled mass: **2027.3 g**.

| Pose | Wrist radius mm | Wrist z mm | Nominal tip z mm | Shoulder Nm | Elbow Nm | Wrist Nm |
|---|---:|---:|---:|---:|---:|---:|
| home | 160.00 | 295.00 | 160.00 | 0.880 | 0.880 | 0.006 |
| reach-310mm | 310.35 | 189.72 | 54.72 | 2.139 | 0.880 | 0.006 |
| table-pick | 235.70 | 145.29 | 10.29 | 1.620 | 0.673 | 0.006 |
| stowed | 122.57 | 237.85 | 102.85 | 0.594 | 0.827 | 0.006 |
| handoff | 225.19 | 252.23 | 117.23 | 1.430 | 0.864 | 0.009 |

The reach pose has `shoulder=20`, `elbow=-20`, `wrist=-90`: radius = 160 cos(20°) + 160 = 310.35 mm; wrist z = 135 + 160 sin(20°) = 189.72 mm. Tip z = 54.72 mm. Reach is measured from the yaw axis, not the front edge of the base.

For a first structural estimate, the two upper rails each have 6 mm thickness and 30 mm width before the central relief. Treat the relieved section conservatively as two 7 mm edge ribs per rail: total section I about the bending axis = 2 x 6 x (30³ - 16³) / 12 = 22,904 mm⁴. At 3.18 Nm, nominal bending stress = M c / I = 2.08 MPa; a 3x local concentration allowance gives 6.25 MPa. Use a minimum coupon-qualified 15 MPa printed allowable at operating temperature. This is a beam screening calculation; it does not validate clamp preload, bearing creep, layer adhesion, or long-term fatigue.

For 0.20 Nm gripper input and two 41 mm lever arms, ideal force is 2.44 N per jaw. With 0.5 pad friction and a 25% force loss allowance, vertical capacity is 1.83 N, exceeding the 1.47 N weight of 150 g. Grip only near the lower pad center; verify actual pad/object friction. The fingers rotate and therefore are **not parallel jaws**. At home the inner pad gap is 15 mm; opening/closing changes both gap and contact angle. The gear pair is module 1, 28/28 teeth, 20-degree involute, 0.20 mm tooth thinning. Its exact relation is `jaw-r = -grip`; the follower has no second motor.

## Motion convention and limits

All joints use degrees. Origins and axes are in the common home frame, and rotation is `(value - home)` by the right-hand rule. Yaw is +Z; shoulder, elbow and wrist pitch are -Y; roll is -Z at home. Shoulder is absolute elevation above +X, elbow is relative bend and wrist is relative pitch. The home angles are 0, 90, -90, -90, 0. The gripper points down at home. This is a five-DOF positioning arm, so arbitrary six-DOF tool poses are not achievable.

The joint limits are cable/clearance controller bounds, not a claim that every Cartesian combination is safe. Yaw ±150°, shoulder 20…115°, elbow -125…5°, wrist -110…60°, roll ±120°, gripper -10…25°, follower -25…10°. Use software limits before torque enable; no continuous rotation through cable loops. Swept links, exposed hardware, the payload and cable slack require collision checking during path planning.

The mandatory safe-pose constants are wrist z >=95 mm; if wrist radius <145 mm, wrist z >=230 mm; nominal tip z >=5 mm. The check uses the `wrist` pitch frame and a -Z tool vector. Rotating fingers have off-axis corners, so validation additionally reports the actual pad's lowest vertex. Never treat the three scalar reach constraints as a complete collision checker.

## Printing and assembly

Print structural parts in dry PA12-CF, 0.2 mm layers, 6 perimeters, 6 top/bottom layers, 50% gyroid and 100% local infill around bearings, clamp ears and horn patterns. Use a 0.6 mm hardened nozzle. PETG is suitable for fit prototypes; do not assign it the same stiffness/creep rating. STL files are in millimetres and are rotated onto a useful print face; support may still be required under clamp bridges. Print the two pads in TPU 95A. Fit coupons are required for bearing bores and axle clearance. Split parts fit a 220 x 220 mm bed; the base is exactly 220 mm wide and needs a larger bed or no brim at the edges.

1. Finish the bearing seats and clearance holes. Install base columns, the yaw motor clamp, two bearings, spindle and deck. Retain the yaw bearing races axially without preloading them through printed material.
2. Install the shoulder motor in its split cradle. Assemble the metal horn, drive spacer, rear axle bracket, bearing and two upper rails. Bolt in both cross ties.
3. Add the elbow motor and its cradle to the upper rails. Install the elbow horn/spacer, rear idler and forearm rails; fit the two forearm cross ties.
4. Install the wrist pitch motor, fork, rear idler and roll bridge. Fit roll motor, horn and palm. Align servo encoder centers mechanically before configuring software home offsets.
5. Fit the gripper motor, geared jaws, follower axle/bearing and guard. Phase the right gear by half a tooth. Bond TPU pads and set closed-current limit before holding an object.
6. Install the power hub and U2D2 on standoffs. Run 12 V / GND / half-duplex TTL data through the chain. Use a regulated 12 V 8 A external supply, 7.5 A fuse, and DC-rated normally closed emergency-stop contacts in the motor supply feed. Do not carry motor current over USB. Verify connector polarity; XC330-T is the 12 V variant, not the 5 V M variant.
7. Route loose 50–80 mm service loops at the joints, secure fixed runs, and keep 15 mm minimum bend radius. Flexing spans are intentionally absent from rigid-body GLB geometry. Wire yaw with a service loop, not unlimited rotation. Use a host PC with DYNAMIXEL Protocol 2.0 through U2D2; assign IDs 1…6 in joint order. No motor firmware is supplied.
8. Bolt the base through its four 5.5 mm holes (196 x 156 mm pattern) to a rigid table using suitable M5 fasteners and washers. Desk fasteners and the external PSU are procurement items outside the assembly model. Do not operate the arm freestanding.

## Validation scope

Generated with Python 3.11.12. **237 parts, 7 joints, 46,570 triangles**, 44 structural print pieces and 2 pads. GLB root rotation, metre conversion, direct-child structure, unique names, references, parent/coupling graphs, home identity, mesh closure/winding, SHA-256 and safe-pose rules are checked by `validate.py`. `validation.json` records FCL contact results for every named pose: no unlisted contacts, including fixed-body fits. `motion-checks.json` checks six single-axis sweeps and four home-to-pose paths at no more than 2 degrees per sample. Every sampled configuration admitted by the safe-pose rules and every sampled path is clear. Rejected low-shoulder configurations are recorded, not hidden. This is a sampled check, not a continuous or full combinatorial workspace certificate. `mating-features.json` records material removed for the real hardware interfaces, including cable openings and captive-nut pockets. Mesh detail is intentionally modest to stay below 50,000 triangles. This deliverable does not replace physical fit, thermal, cyclic load or fabrication testing.

## Manufacturer references

- [XM540-W270 documentation](https://emanual.robotis.com/docs/en/dxl/x/xm540-w270/): 33.5 x 58.5 x 44 mm, 165 g, 10.6 Nm stall at 12 V.
- [XM430-W350 documentation](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/): 28.5 x 46.5 x 34 mm, 82 g, 4.1 Nm stall at 12 V.
- [XC330-T288 documentation](https://emanual.robotis.com/docs/en/dxl/x/xc330-t288/): 20 x 34 x 26 mm, 23 g, 1.0 Nm stall at 12 V; current-based position mode.
- [OEM horn drawings](https://en.robotis.com/service/downloadpage.php?ca_id=7020): purchase original metal horns, confirm interfaces against the current drawing.
- [U2D2](https://emanual.robotis.com/docs/en/parts/interface/u2d2/): 48 x 18 x 14.9 mm, USB to TTL interface; external motor power required.
- [U2D2 Power Hub](https://robotis.us/u2d2-power-hub-board-set/): 48 x 57 mm, 10 A maximum.

Manufacturer specifications checked 2026-11-06. The reduced CAD models and all custom structure are authored by this generator.
