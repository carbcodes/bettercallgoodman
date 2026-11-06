# FIELD / 65 — backpack video quadcopter

A folding 3S quadcopter with four 65 mm two-blade propellers and a landscape-mounted RunCam Thumb Pro W on a servo-driven pitch cradle. **195.0 × 195.0 × 73.3 mm** deployed, including the entire rotating propeller discs. **133.9 × 105.5 × 73.3 mm** stowed, including attached, correctly parked propellers and the camera. Both fit the requested 200 × 200 × 100 mm box.

**215 parts, 10 joints (1 driven), 38,924 triangles.** All meshes are closed and outward-oriented. `validation.json` records the GLB reload checks and measured pose bounds. The build also runs 140 sampled motion configurations using solid Boolean intersection checks (including each hinge individually, coordinated folding, camera travel and deployed rotor phases); no unexpected moving-body intersections over 0.01 mm³ were found. This is a sampled check, not a continuous-motion certificate. `preview.png` shows flight and backpack poses. Open `viewer.html` for an offline assembly explorer with poses, independent joint sliders, orbit, zoom, and removable panels. The actual interchange GLB contains only the home pose and has no animation or hierarchy beyond the required assembly root.

## Rebuild

Use Python **3.11**:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate.py
```

`generate.py` rebuilds `assembly.glb`, `joints.yaml`, `assembly.yaml`, `geometry.py`, `parts.csv`, `validation.json`, `preview.png`, `viewer.html`, `README.md`, and the ZIP. Keep both source templates alongside it. Outputs have no timestamp or randomness; ZIP entry times are fixed. The pinned Python/package environment is the reproducibility target. `geometry.py` contains only literal assignments. The GLB is written explicitly: one scene, one `assembly` root, the exact requested quaternion, one mesh on each direct part child, metre-based local vertices and placements. YAML uses mm and degrees.

## Mechanism and packaging

- +X is forward, +Y is right, +Z is up. FL/FR are front left/right; RL/RR are rear left/right. Landing skids touch z = 0.
- Motor centres at (±65, ±65) give a **195 × 195 mm swept rotor envelope**. Adjacent disc edge clearance is 65 mm; the camera sits ahead of the 76 × 40 mm central chassis, below the propeller planes and inside their lateral clearance.
- Four independent vertical hinges at (±28, ±30). Front arm centre planes are z = 27; rear planes z = 53. That 26 mm stagger allows one arm/motor/parked propeller set to pass beneath the other. It is a packaging tradeoff, and its aerodynamics need flight testing.
- Each 50.931 mm arm uses a 4 mm carbon plate, 8 mm web, 21 mm motor flange, actual clearance bores, a 3 mm shoulder axle and a flanged bronze bushing. A 6061 double-shear clevis and two 3 mm stop dowels establish travel. The pivot nut supplies clamp preload; loosen for folding and tighten for operation. Quantifying preload retention and vibration loosening is a prototype test, not a solved flight qualification.
- Arms fold approximately 123° inward and backward/forward along the body's sides. The signed exact endpoints are in `joints.yaml`. The opposite signs are mirror geometry, not a mechanical coupling. Each hinge is independently hand-operated.
- A 3 mm idler axle runs in an MR63 3 × 6 × 2.5 mm bearing. The other side of the camera cradle keys to a Hitec HS-40 horn. `camera-tilt` is **driven** by `camera-servo` with ratio 1.0. Camera home depression is 20°; servo home is 0°. Servo travel ±40° gives camera elevation 20° upward through depression 60° downward. The camera is landscape mounted; rotate footage orientation in the camera/post workflow as supported.
- Each motor bell, shaft, propeller and its two screws share one rotor joint, parented to that arm hinge. Rotor ±180° is one periodic phase interval, **not a physical motor stop**. The schema has no continuous-joint flag. Wrap phase to this interval for simulation; these BLDC motors turn continuously in use. The counter-rotating diagonal pairs are represented by opposite-handed blade profiles, not a false mechanical coupling between independent motors.

## Real components and dimension sources

Purchased components are simplified envelope models, **not manufacturer manufacturing CAD**. Interface dimensions are explicit. Where vendor internals or case details were unavailable, the model uses typical geometry and marks it as nominal in `parts.csv`.

| Component | Quantity | Selected envelope / interface | Source |
|---|---:|---|---|
| HappyModel EX1404 4800KV, 3S | 4 | Ø17.8 × 17.6; 14 × 4 stator; 1.5 shaft; M2 on Ø9 PCD | [HappyModel product page](https://www.happymodel.cn/index.php/2021/01/07/happymodel-ex1404-kv2750-kv3500-kv4800-brushless-motor/) |
| HQProp T65, opposite-handed two-blade pairs | 4 | 65 diameter; 1.5 inch pitch; Ø9.8 × 5 hub; T-mount | [HQProp manufacturer](https://www.hqprop.com/); blade section is an original approximate envelope, not its aerodynamic tooling |
| SpeedyBee F405 Mini / BLS 35A Mini V2 stack | 1 | FC 30 × 32; ESC 35 × 30; 20 × 20 hole spacing; 1.6 mm FR4 | [Manufacturer manual](https://spcdn.speedybee.cn/cdn/117513656576512000.pdf?attname=SpeedyBee-f405-mini-stack-Manual-en.pdf) |
| RunCam Thumb Pro W | 1 | 54 × 25.5 × 21; 16 g; 5 V, up to 500 mA; onboard gyro | [RunCam product](https://shop.runcam.com/runcam-thumb-pro-w/) |
| Hitec HS-40 servo | 1 | 20 × 8.6 × 17; 4.8 g; 4.8–6 V; ±40° rated pulse travel | [Hitec datasheet](https://www.hiteccs.com/public/uploads/data_sheet/HS-40-DataSheet-1642817842.pdf) |
| Tattu 650 mAh 3S 75C XT30 | 1 | 58 × 31 × 16; 59 g | [Tattu catalogue](https://www.genstattu.com/content/instock/rc_product_brochure.pdf) |
| Matek M10Q-5883 GNSS module | 1 | 20 × 20 × 12.4; 15 × 15 × 4 ceramic patch; 8 g | [Matek dimensions](https://www.mateksys.com/?portfolio=m10q-5883) |
| HappyModel EP2 ExpressLRS receiver | 1 | nominal 10 × 10 board with ceramic antenna | Envelope reserved; connector/harness details require board-in-hand confirmation |
| Mounting and connections | As listed | M2 and M3 screws/nuts; MR63 idler; bronze hinge bushes; XT30; JST-SH, JST-GH, JST-XH and servo plugs | Detailed individual inventory in `parts.csv` |

The stack is deliberately spaced wider than its factory assembly to expose wiring, allow 20 mm screws and provide clearance. PCB packages, connector interiors, thread helices, servo gears, motor magnets and exact winding shapes are omitted. Motor bearing internals are nominal 1.5 × 4 × 2 envelope rings; confirm the actual motor before service. Cable strands are grouped into simple jackets. Electronics are individually supported by decks, grommets, spacers, shelves or pads; cosmetic mounting surfaces may be idealized.

## Operation and service sequence

1. Disconnect the XT30 battery connector. The camera and rotors must not run during folding.
2. Loosen each hinge clamp, leaving the axle and nut captive.
3. Fold with props kept parallel to the body: as arm angle changes by α, manually change rotor phase by −α. This is an operator action, **not a coupled joint**. `folding-midway` and `stowed` encode that parked orientation. Arbitrary spinning of rotors in the folded configuration is not an intended mode.
4. Set camera servo to +20° relative to its home (camera depression 40°) for the stowed pose. Secure the assembly in a protective pouch; tighten transport clamps.
5. To deploy, reverse the sequence, seat all four deployed stops, tighten the clamps and inspect phase-wire slack before connecting power.

Named poses are `flight` (home, camera down 20°), `stowed`, `selfie` (camera level), `look-down` (camera down 60°) and `folding-midway`. Poses list only independent coordinates; the driven camera angle is computed from the servo. The viewer permits arbitrary independent joint motion for inspection, not as an assertion that every combination is a valid operating mode.

## Build and validation boundaries

This is a mechanical packaging and kinematics design, not a flight-ready release. The video camera records; it does not itself provide subject recognition. RC control is the initial operating concept. Autonomous follow-me filming would require a supported navigation/vision system, firmware, ground controls and separate flight validation. No endurance, payload rating or thrust-to-weight ratio is claimed. The provisional all-up mass budget is approximately 190–230 g, to be weighed and checked on a thrust stand with the actual 65 mm propellers.

Camera and servo loads fit a plausible 5 V power budget, but peak current, FC firmware servo support and UART allocation must be checked on the chosen board revision. Keep the GNSS compass disabled at this compact mounting location: Matek requests 100 mm separation from power electronics/motors/iron, which this body cannot provide. That limitation prevents claiming compass-based autonomous navigation from the installed envelope alone. M10Q-5883 is EOL; confirm procurement or substitute a module after checking its actual outline.

The rigid-body schema cannot model flexible harness deformation or screw helical motion. Moving arm phase wires and the camera tail are separate rigid end segments; unmodeled service loops must be routed with sufficient bend radius and slack. Screw tightening is a service operation outside the revolute-joint model. CAD thread surfaces and interference fits are idealized.

`allow_contact` lists intended interfaces such as bush/axle, nut/bolt, bearing/shaft, propeller/hub, clamp/arm, board/grommet and electrical mating surfaces. It does not blanket-exempt entire moving subassemblies. Actual clearances, material thickness, press fits, propeller balance, structural fatigue, hinge clamp torque, motor temperature, RF interference, cable fatigue and flight stability remain prototype engineering work.
