# Candy / Crank

A hand-powered, refillable dispenser for **plain chocolate M&M's**. The 50 mm crank
turns a six-pocket drum on sealed bearings. An 18:36 involute gear pair counter-rotates
a flexible agitator at half speed. A replaceable six-lobe click cam and PETG leaf
give six tactile index positions per revolution. A bearing-supported grip turns
freely in your hand. A clear gear guard covers the teeth.

This is an engineered printable **prototype**, with geometric validation. Actual
dose count, feeding reliability, crank force and service life have not been measured.

## Files

- `assembly.glb`: complete home assembly, metres, exact requested frame and hierarchy.
- `joints.yaml`: four revolute joints, coupled agitator, five named poses and GLB hash.
- `assembly.yaml`: explicit intended contact pairs.
- `geometry.py`: literal millimetre/degree constants only.
- `stl/`: 21 separate printable parts in **millimetres**, oriented on z = 0.
- `bom.csv`: one row per physical part; buy, print and metal fabrication distinguished.
- `validation.json`: reloaded-GLB topology, structure, naming, units, limits and hash checks.
- `motion-validation.json`: reproducible sampled solid-intersection checks.
- `preview.png`: home and exposed-mechanism views; the guard is hidden for clarity.
- `generate.py`, `requirements.txt`: reproducible source and pinned dependencies.

## Rebuild

Use Python **3.11**. From this folder:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate.py
```

The generator overwrites all generated outputs, including STLs, preview, BOM,
documentation and validation reports. It needs no network after dependency installation.
Source files (`generate.py`, `geometry.py`, `requirements.txt`) are the build inputs.
No randomness or timestamps are embedded. Use the pinned versions and the same
platform for byte-identical regeneration; CAD triangulation can vary across platforms.

## Dimensions and operation

| Feature | Nominal size |
| --- | --- |
| Base footprint | 144 x 172 mm |
| Complete home envelope | 144 x 203 x 251 mm |
| Metering drum | 64 diameter x 36 wide |
| Six blind radial pockets | 19 diameter, 11 central depth, 60 degrees apart |
| Assumed candy envelope | 14.5 diameter x 8.5 thick; measure your batch |
| Drum housing clearance | 0.65 radial; 0.50 at each end |
| Hopper inlet / top opening | 36 x 33 / 108 x 82 |
| Internal hopper volume | Approximately 300 mL before candy voids and hardware |
| Main / agitator axes | z = 112 / 166; both along +Y |
| Gears | module 2; 18/36 teeth; 20 degree pressure angle; 8 face |
| Gear centre spacing / backlash | 54 / 0.30 mm total tangential backlash |
| Main / agitator stainless shafts | 8 diameter x 99 / 78 long |
| Main shaft bearings | Four 608-2RS, 8 x 22 x 7 |
| Grip bearings | Two 625-2RS, 5 x 16 x 5 |
| Crank / grip | 50 centre distance; 22 diameter x 30 grip |
| Lid travel | 0 to 105 degrees; integral hard stops |

Front is -Y. The crank is on +Y. Positive crank angles follow the right-hand rule
about +Y: the top pocket moves toward +X, past the flexible cutoff wiper, around
the closed sleeve, then out through the bottom opening. The chute leads forward
into a removable catch tray. Prime through approximately 180 degrees before the
first filled pocket reaches the outlet. Subsequently each 60-degree click brings
another pocket to the outlet. The intended dose is a small portion, typically one
plain candy; it is not an exact-count mechanism. Thin pieces may double-load.
Peanut, pretzel and other large varieties require different pocket geometry.

The `crank` and `grip` limits 0..360 represent one periodic revolution, **not physical
stops**. Reset the coordinate at the end of a turn to continue. The driven agitator
has value `-0.5 * crank`; its two-fold-symmetric paddle repeats after 180 degrees.
The agitator is ground-mounted, so its parent is null; it is driven by the crank,
not carried spatially by it. The grip is a child of the crank and spins independently.
Named poses use counter-rotation of the grip to keep its orientation steady.
Only the lid has physical angular end stops. Its positive axis is -X.

## Printing and fits

Use PETG for structural parts, gears and the click flexure. Use TPU 95A for the
agitator paddle and inlet wiper. Transparent PETG is suggested for the guard; the
GLB tint is illustrative and does not promise optical clarity from FDM.
Start with a 0.4 mm nozzle, 0.20 mm layers, 4-5 perimeters, and 30-40% infill.
Print the gears solid around their hubs. Print the thin click leaf flat with its
length in the XY plane. All supplied STLs fit within a 220 mm build envelope.
Inspect slicer previews: cheek feet, hopper hinge barrels, drum pocket ceilings,
chute and guard bosses can require local supports. These are not support-free parts.

Nominal bearing seats are 22.10 and 16.10 mm; D bores are 8.30 with the flat at
x = 3.25. Shaft flats are x = 3.10. These are starting tolerances for a calibrated
printer, not universal press-fit guarantees. Print fit coupons before the large
parts. Sand or ream bearing seats; press bearings by the outer race. Deburr every
candy-facing edge. Adjust the shell clearance only after measuring printed parts.
The 0.65 radial gap is between the drum and sleeve, not a candy size tolerance.

Food-facing printed parts require an appropriate material, surface finish and
cleaning process. This model is not food-contact certified. Keep bearing lubricant
outside the hopper, and make the hopper, drum, paddle, wiper, chute and tray easy
to remove and clean. Treat suitability for actual food use as a separate material
and finishing decision, not something established by mesh validation.

## Hardware and fabrication

`bom.csv` is authoritative for every screw, nut, spacer, bearing and printed part.
Bearing boundary dimensions follow SKF's deep-groove bearing catalogue:
[SKF catalogue](https://cdn.skfmediahub.skf.com/api/public/0901d196802809de/pdf_preview_medium/0901d196802809de_pdf_preview_medium.pdf).

Shaft coordinates below are world Y coordinates, in mm, with z at the shaft axis.
Use ground stainless 8 mm rod, preserving round journals at the bearing locations.
File or mill the indicated D flats to x = 3.10 relative to the shaft centre:

- Main: ends -41 and +58; flats -41..-28, -18..+18, +30.5..+58.
  Drill and tap the -Y end M3, 10 mm minimum usable depth, for the cam retaining screw.
- Agitator: ends -35 and +43; flats -35..-28, -14..+14, +30.5..+43.
- Lid pin: 3 mm stainless rod cut to 122, with two push-on retaining caps.
- Grip axle: precision 5 mm shoulder x 30, M4 tip x 10, head 9 diameter x 4.
  Match this shoulder screw or machine the specified geometry; ordinary fully
  threaded M5 screws are not equivalent bearing journals.
- The two compact end collars are fabricated/matched items: 8 bore, 14 OD;
  crank collar 5 wide with M3 radial grub, agitator collar 3 wide with M2 grub.
- Inner-race spacers use the sizes in the BOM. Their small OD clears the fixed
  bearing retainers. Do not substitute broad washers that rub the retainers.

Threads are represented by nominal envelopes and pilot holes, not helical threads.
Tap the 2.6 mm printed pilot holes M3 for the chute, click leaf and wiper fixings;
use light hand torque. The structural joints use through-bolts and captive nuts.
Retainer nuts fit into the inner cheek pockets. Short custom spacers and collars
are explicitly listed as hardware/fabrication rather than claimed to be prints.

## Assembly order

1. Print, deburr and dry-fit the parts. Fit the captive M3 bearing and guard nuts
   into the cheeks, and the captive M4 base nuts from underneath the base.
2. Seat the four 608 bearings against their 1 mm shoulders. Fit the outer-race
   retainers with M3 x 10 screws. Leave the right cheek loose during shaft assembly.
3. Place the drum inside the sleeve and the TPU paddle inside the throat. Insert
   their D shafts through the left bearing, moving part and right bearing.
   Close the cheeks around the hopper. Four M3 x 60 tie bolts use the 3 mm left
   spacers and washers shown; this keeps their ends clear of the large gear.
4. Fit the left inner-race spacers and shaft collars, leaving the rotating collars
   clear of the stationary retainers. Add the right inner-race spacers and phased
   18/36-tooth gears. At home the small gear has a tooth pointing up, and the large
   gear has a gap pointing down. Keep the pocket at top dead centre.
5. Fit the click cam, its 1.5 mm inner spacer, large end washer and axial M3 screw.
   Attach the click leaf to its external bracket. Its tip has about 0.3 mm initial
   geometric preload and about 1.3 mm peak lobe deflection. Flexure deformation
   is intentionally absent from the rigid GLB; its cam contact is allow-listed.
6. Fit the TPU wiper at the +X cutoff edge. Fit the clear guard with four recessed
   M3 x 25 screws. Their heads must sit flush with the front of the guard.
7. Install the crank spacer, arm and end collar. Press the two 625 bearings into
   the grip with the 20 mm inner spacer between them. Install the 5 mm shoulder
   axle, 2 mm M4 inboard spacer and captive M4 nut. The grip must rotate freely
   without axial rattle after tightening.
8. Attach the chute to its tapped base holes. Set the catch tray in front. Fit
   the lid, hinge pin and retaining caps; check opening to its 105-degree stop.
   Add four adhesive silicone feet.

Turn the empty mechanism through several revolutions first. Check that the drum
does not scrape its housing, the gears remain clear of screws, and the grip turns
freely. Then test a small batch of measured candies, followed by a fuller hopper.
Record doubles, misses and jams over at least 100 clicks before changing pocket
depth or claiming a particular dose. If a candy wedges, reverse gently and clear
it; do not increase force. Adjust click feel by changing leaf thickness or preload.

## What the checks establish

The build reloads the actual GLB and validates all required part, parent, driver
and SHA-256 references; closed/outward meshes; direct-child node structure; joint
limits; and the triangle budget. It checks undeclared solid overlaps at home and
samples crank travel at 10-degree steps and lid travel at 5-degree steps. The
meshing gears and lid/hopper are tested despite their contact declarations; the
lid stop is also checked to engage at 106 degrees. Sampling is not continuous
collision certification. Compliant leaves, rolling elements, candy motion, loads,
print distortion, wear and food suitability are outside that geometric check.

Build: 113 parts, 4 joints, 46,892 triangles, 21 printable parts.
