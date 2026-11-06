from gen import kgf, LBF, IN, LB
M = "cantilever_root_fillet"
CASES = [
dict(slug="pla-blower-wall-hook", model=M, title="PLA wall hook for a 4 kg leaf blower, printed upright",
 trap="[layer_direction] Printed standing on the wall plate's end, so the bending at the root pulls the print apart across its stacked passes: PLA across-layer 30 MPa gives SF {sf:.2f}; the 50 MPa datasheet value would give {sf_in:.2f}",
 mm=["layer_direction_strength"],
 inputs=dict(material="PLA", print_orientation="upright_layers_horizontal", load_n=round(kgf(4.0), 2), lever_mm=75,
             section=dict(type="rect", width_mm=25, thickness_mm=6), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""I'm 3D printing a hook to hang my cordless leaf blower (4.0 kg) in the garage. It's a simple L shape in PLA at 100% infill:
 a flat plate screws to the wall and an arm sticks straight out 75 mm from the wall face, with the blower's handle hanging at the end of the arm.
 Plate and arm are both 25 mm wide and 6 mm thick, and the inside corner where they meet has a 3 mm radius. To avoid supports I printed it
 standing up, with the bottom end of the wall plate on the bed, so the plate is vertical on the printer and the arm grows out sideways near the top.
 I'd like a safety factor of 2. Will it hold?"""),
dict(slug="petg-spool-holder-arm", model=M, title="PETG spool holder arm printed standing up",
 trap="[layer_direction] The arm was printed pointing up, so its bending stress acts across the print's stacked passes: PETG interlayer strength 18 MPa gives SF {sf:.2f}, while the 47 MPa datasheet figure would give {sf_in:.2f}",
 mm=["layer_direction_strength"],
 inputs=dict(material="PETG", print_orientation="upright_layers_horizontal", load_n=round(kgf(3.0), 2), lever_mm=90,
             section=dict(type="rect", width_mm=20, thickness_mm=8), fillet_mm=4.0, required_safety_factor=2.0),
 prompt="""We're adding an external spool holder to the lab's printer enclosure. The holder is a PETG part (100% infill): a base plate bolts flat
 to the side panel and an arm sticks out horizontally, and the spool hangs on it with its weight acting about 90 mm out from the panel. Worst case is
 a 3 kg spool. The arm is 20 mm wide and 8 mm deep (the 8 mm is vertical in use), with a 4 mm radius where it joins the base plate. It was printed
 with the base plate flat on the bed and the arm pointing straight up. We want a safety factor of 2 on it. Is it OK?"""),
dict(slug="petg-rover-camera-mast", model=M, title="PETG camera mast bracket on a rover, printed upright",
 trap="[layer_direction] Printed with the arm vertical, so the bending stress pulls the PETG apart across its passes (18 MPa interlayer, SF {sf:.2f}); with the 47 MPa datasheet value it looks fine at {sf_in:.2f}",
 mm=["layer_direction_strength"],
 inputs=dict(material="PETG", print_orientation="upright_layers_horizontal", load_n=round(kgf(0.9) * 3, 2), lever_mm=60,
             section=dict(type="rect", width_mm=30, thickness_mm=5), fillet_mm=2.5, required_safety_factor=2.0),
 prompt="""Our field rover carries a 0.9 kg stereo camera on a 3D-printed PETG bracket. The bracket's base is bolted flat to the top deck and a
 cantilevered arm reaches 60 mm out over the front edge, with the camera at its end. The arm section is 30 mm wide and 5 mm thick, thickness vertical,
 and there's a 2.5 mm radius at the root. Driving over rough ground, we design for 3 g vertical, so treat the camera as three times its weight. The part was
 printed at 100% infill with the base on its back face, so the arm stood straight up on the printer. Safety factor 2 required. Will the bracket survive?"""),
dict(slug="pla-ring-light-arm", model=M, title="PLA ring light arm for a desk, printed upright",
 trap="[layer_direction] Printed upright, so the root bending acts across PLA's stacked passes (30 MPa): SF {sf:.2f}; the 50 MPa datasheet number gives {sf_in:.2f}",
 mm=["layer_direction_strength"],
 inputs=dict(material="PLA", print_orientation="upright_layers_horizontal", load_n=round(kgf(2.2), 2), lever_mm=200,
             section=dict(type="rect", width_mm=24, thickness_mm=8), fillet_mm=4.0, required_safety_factor=2.5),
 prompt="""I'm printing a desk-edge arm for a 2.2 kg ring light (with its battery pack). A clamp block grips the desk and a straight arm sticks out horizontally from it;
 the light hangs 200 mm from the block. The arm is 24 mm wide and 8 mm tall, with a 4 mm radius where it leaves the clamp block. It's PLA at 100% infill,
 printed with the clamp block sitting on the bed and the arm going straight up from it, which needed no supports. Because people will bump it,
 I want a safety factor of 2.5. Can I trust it?"""),
dict(slug="abs-tool-holder-arm", model=M, title="ABS cordless drill holder printed upright with a 1 mm corner",
 trap="[layer_direction] Printed upright: the root bending acts across ABS's stacked passes (29.7 MPa) and the 1 mm corner adds Kt {kt:.2f}; SF {sf:.2f}",
 mm=["layer_direction_strength", "stress_concentration"],
 inputs=dict(material="ABS", print_orientation="upright_layers_horizontal", load_n=round(kgf(3.0), 2), lever_mm=85,
             section=dict(type="rect", width_mm=30, thickness_mm=6), fillet_mm=1.0, required_safety_factor=2.0),
 prompt="""For the makerspace tool wall I printed holders for our cordless hammer drills (3.0 kg each with battery) in ABS, 100% infill. Each one is an L:
 a back plate screwed to the pegboard and a 30 mm wide, 6 mm thick shelf arm that sticks out; the drill hangs with its weight about 85 mm from the board.
 The inside corner between back plate and arm has a 1 mm radius. We printed them standing up on the end of the back plate, so the plate is vertical on
 the printer. I'd like a safety factor of 2 against breaking. Are these holders OK?"""),
dict(slug="al-sensor-bracket-tight-corner", model=M, title="6061 sensor bracket milled with a 0.4 mm inside corner",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f} looks comfortable, but the 0.4 mm inside corner gives Kt {kt:.2f}: SF {sf:.2f}",
 mm=["stress_concentration"],
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=round(kgf(8.0), 2), lever_mm=150,
             section=dict(type="rect", width_mm=20, thickness_mm=6), fillet_mm=0.4, required_safety_factor=2.0),
 prompt="""On our test rig an 8.0 kg load cell assembly hangs from an L-bracket machined out of a single block of 6061-T6 aluminum (yield 276 MPa).
 The vertical leg is bolted to the frame and the horizontal leg reaches out 150 mm, with the assembly hanging at its end. Both legs are 20 mm wide and 6 mm thick;
 the machinist left the inside corner between the legs at a 0.4 mm radius. We need a safety factor of 2 on yield. Is the bracket good?"""),
dict(slug="steel-hoist-arm-corner", model=M, title="1018 steel jib arm with a 0.5 mm inside radius",
 trap="[stress_concentration] Nominal stress gives SF {sf_nom:.1f}; the 0.5 mm root radius raises it by Kt {kt:.2f} to SF {sf:.2f}",
 mm=["stress_concentration"],
 inputs=dict(material="1018_CR", yield_mpa=370, load_n=round(150 * LBF, 1), lever_mm=round(10 * IN, 1),
             section=dict(type="rect", width_mm=round(1.5 * IN, 1), thickness_mm=round(0.5 * IN, 1)), fillet_mm=0.5, required_safety_factor=2.0),
 prompt="""I'm making a small jib arm for lifting engine parts onto my workbench. The arm is milled from a 1018 cold-rolled steel plate (yield
 370 MPa, about 53.7 ksi) as one piece with its mounting flange, and sticks out 10 in from the flange. The arm section is 1.5 in wide and 0.5 in deep
 (depth vertical). Where the arm meets the flange the inside corner radius is only 0.5 mm because we used a small end mill. Max hook load is 150 lbf at the end.
 I want a safety factor of 2 against yield. Is the arm strong enough?"""),
dict(slug="7075-drone-arm-root", model=M, title="7075 drone arm machined with a sharp root corner",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f}, but the 0.3 mm corner where the arm leaves the hub has Kt {kt:.2f}: SF {sf:.2f}",
 mm=["stress_concentration"],
 inputs=dict(material="Al7075-T6", yield_mpa=503, load_n=round(kgf(3.2) * 2, 2), lever_mm=220,
             section=dict(type="rect", width_mm=10, thickness_mm=6), fillet_mm=0.3, required_safety_factor=1.5),
 prompt="""We're building a heavy-lift hexacopter. Each arm is CNC-cut from 7075-T6 plate (yield 503 MPa) together with its hub block, so it is one piece.
 The arm is a solid 10 mm wide by 6 mm deep bar (depth vertical) and the motor sits 220 mm from the hub block. Each motor makes up to 3.2 kg of thrust,
 and for hard manoeuvres we design for twice that. The inside corners where the arm leaves the hub block were cut with a 0.3 mm radius. We want a safety factor
 of 1.5 on yield. Are the arms OK?"""),
dict(slug="ss304-flowmeter-bracket", model=M, title="304 stainless flowmeter bracket with a 0.5 mm corner",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f}; the 0.5 mm inside corner (Kt {kt:.2f}) brings it to SF {sf:.2f}",
 mm=["stress_concentration"],
 inputs=dict(material="SS304", load_n=round(kgf(12), 1), lever_mm=125,
             section=dict(type="rect", width_mm=30, thickness_mm=6), fillet_mm=0.5, required_safety_factor=2.0),
 prompt="""At the brewery we hang a 12 kg flowmeter off a wall bracket machined from annealed 304 stainless. The bracket is an L cut out of solid bar:
 the upright leg bolts to the wall and the other leg sticks out 125 mm, with the meter's weight at its end. Both legs are 30 mm wide and 6 mm thick,
 and the inside corner was machined to a 0.5 mm radius. Use a safety factor of 2 against yield. Is it safe?"""),
dict(slug="al-shelf-bracket-hook-offset", model=M, title="Aluminum bracket with a hanging hook beyond its tip",
 trap="[lever_arm] The bag hangs from a hook 90 mm beyond the bracket's end, so the lever is {inp[lever_mm]:g} mm, not 110 mm: SF {sf:.2f}",
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=round(kgf(15), 1), lever_mm=200,
             section=dict(type="rect", width_mm=25, thickness_mm=6), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""I'm putting up a 6061-T6 aluminum L-bracket (yield 276 MPa) in the shop to hang a 15 kg bag of welding rods. The bracket's horizontal leg
 is 110 mm long from the wall and 25 mm wide by 6 mm thick; the inside corner has a 3 mm radius. The bag hangs from an S-hook on a short steel extension
 rod bolted to the end of the leg, which puts the hook 90 mm further out than the end of the bracket. I'd like a safety factor of 2. Will it hold?"""),
dict(slug="steel-camera-arm-cg-offset", model=M, title="Steel camera arm with the camera CG forward of the arm end",
 trap="[lever_arm] The camera's centre of mass sits 120 mm forward of the arm's end on its quick-release plate, so the lever is {inp[lever_mm]:g} mm, not 120 mm: SF {sf:.2f}",
 inputs=dict(material="mild_steel", yield_mpa=250, load_n=round(kgf(6.5), 1), lever_mm=240,
             section=dict(type="rect", width_mm=20, thickness_mm=6), fillet_mm=3.0, required_safety_factor=2.5),
 prompt="""For a fixed overhead product-shot rig I'm mounting a 6.5 kg cinema camera on a mild steel arm (yield 250 MPa) that sticks out horizontally
 120 mm from a vertical post. The arm is a 20 mm wide, 6 mm deep flat bar welded to a post plate and blended to a 3 mm radius at the root. The camera sits on a
 quick-release plate and a riser at the end of the arm, and its centre of mass ends up 120 mm further forward than the end of the arm. We use a safety factor of
 2.5 for anything overhead. Is the arm OK?"""),
dict(slug="steel-pipe-hanger-offset", model=M, title="Steel hanger arm with the pipe clamp hanging past its tip",
 trap="[lever_arm] The pipe's centreline is 80 mm past the end of the arm (clamp offset), so the lever is {inp[lever_mm]:g} mm: SF {sf:.2f}",
 inputs=dict(material="1018_CR", yield_mpa=370, load_n=round(50 * LBF, 1), lever_mm=round(4 * IN + 80, 1),
             section=dict(type="rect", width_mm=round(1.0 * IN, 1), thickness_mm=round(0.25 * IN, 2)), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""We're hanging a water-filled 2 in pipe run off the side of a machine frame with cantilever hangers made from 1 in x 1/4 in 1018 cold-rolled
 flat bar (yield 370 MPa), 1/4 in dimension vertical. Each hanger sticks out 4 in from the frame, with a 3 mm radius at its root. The pipe clamp bolts under
 the tip of the hanger on a drop bracket that puts the pipe's centreline 80 mm further out than the end of the bar. Each hanger carries 50 lbf. Safety factor
 of 2 on yield. Are the hangers OK?"""),
dict(slug="steel-flatbar-gate-latch", model=M, title="Mild steel flat bar mounted flat, loaded on its wide face",
 trap="[weak_axis] The 40 x 5 bar is mounted flat, so it bends about its 5 mm depth (Z = {Z:.0f} mm³, SF {sf:.2f}); using 40 mm as the depth gives SF ~{sf_strong:.0f}",
 post=["Using the 40 mm width as the depth (on edge) would give Z = 5·40²/6 = 1333 mm³ and SF ≈ {sf_strong:.1f}: that is not how the bar is mounted."],
 inputs=dict(material="mild_steel", yield_mpa=250, load_n=400, lever_mm=200,
             section=dict(type="rect", width_mm=40, thickness_mm=5), fillet_mm=4.0, required_safety_factor=2.0),
 prompt="""A farm gate rests its latch end on a cantilevered stop made from a 40 mm x 5 mm mild steel flat bar (yield 250 MPa). The bar is welded flat
 against the post plate, wide face up, sticking out 200 mm, and the weld is ground to a 4 mm radius. When someone leans on the closed gate, up to 400 N comes down
 on the very end of the bar. Safety factor 2 on yield. Is the stop strong enough?"""),
# ---------------- controls
dict(slug="steel-shelf-support-control", model=M, title="Mild steel shelf support with a generous root radius (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f} with a {inp[fillet_mm]:g} mm root radius (Kt {kt:.2f})",
 inputs=dict(material="mild_steel", yield_mpa=250, load_n=350, lever_mm=180,
             section=dict(type="rect", width_mm=50, thickness_mm=10), fillet_mm=6.0, required_safety_factor=2.0),
 prompt="""I'm adding a steel support under a workbench extension. It's a mild steel bar (yield 250 MPa), 50 mm wide and 10 mm thick with the thickness
 vertical, sticking out 180 mm from a welded base plate; the root is ground to a 6 mm radius. The worst load is 350 N at the free end. I want a safety factor of 2
 against yield. Is it safe?"""),
dict(slug="petg-cable-tray-arm-control", model=M, title="PETG cable tray arm printed flat (control)", control=True,
 trap="[control] none, genuinely safe: printed on its side, so the bending runs along the extruded paths (47 MPa); SF {sf:.1f}",
 inputs=dict(material="PETG", print_orientation="on_side", load_n=round(kgf(0.8), 2), lever_mm=80,
             section=dict(type="rect", width_mm=15, thickness_mm=8), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""Under my standing desk I'm hanging a cable tray from PETG brackets (100% infill). Each bracket is an L: one leg screws to the underside of the desk,
 the other comes down and turns out, and the tray's share of weight (0.8 kg per bracket) sits 80 mm from the screwed leg. The legs are 15 mm wide and 8 mm thick,
 with a 3 mm inside radius. I printed them lying on their side, so the whole L outline is flat on the bed. Safety factor of 2. Are they fine?"""),
dict(slug="al-robot-sensor-arm-control", model=M, title="6061 sensor arm on a mobile robot (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}; the 4 mm root radius keeps Kt at {kt:.2f}",
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=round(kgf(1.2) * 2, 1), lever_mm=130,
             section=dict(type="rect", width_mm=25, thickness_mm=8), fillet_mm=4.0, required_safety_factor=2.0),
 prompt="""Our warehouse robot carries a 1.2 kg lidar on an arm machined from 6061-T6 (yield 276 MPa) that sticks out 130 mm ahead of the chassis.
 The arm is 25 mm wide and 8 mm deep (vertical), machined as one piece with its mounting block, with a 4 mm radius at the root. We design for 2 g vertical
 to cover bumps. Safety factor of 2 on yield. Is the arm OK?"""),
dict(slug="pla-headphone-hook-control", model=M, title="PLA headphone hook printed on its side (control)", control=True,
 trap="[control] none, genuinely safe: printed on its side, so bending acts along the extruded paths (50 MPa); SF {sf:.1f}",
 inputs=dict(material="PLA", print_orientation="on_side", load_n=round(kgf(0.45), 2), lever_mm=60,
             section=dict(type="rect", width_mm=20, thickness_mm=6), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""I'm printing an under-desk headphone hook in PLA at 100% infill. It's an L: a 20 mm wide, 6 mm thick plate screws to the underside of the desk
 and a hook arm of the same section comes out of it, with my 450 g headphones hanging 60 mm from the plate. The inside corner has a 3 mm radius.
 I print it lying on its side so the L outline is flat on the bed. I'd like a safety factor of 2. Will it be fine?"""),
dict(slug="abs-router-shelf-control", model=M, title="ABS router shelf bracket printed flat (control)", control=True,
 trap="[control] none, genuinely safe: printed lying flat, bending along the extruded paths (33.4 MPa); SF {sf:.1f}",
 inputs=dict(material="ABS", print_orientation="flat", load_n=round(kgf(1.1) / 2, 2), lever_mm=90,
             section=dict(type="rect", width_mm=25, thickness_mm=6), fillet_mm=3.0, required_safety_factor=2.0),
 prompt="""I printed two ABS brackets (100% infill) to hold a 1.1 kg Wi-Fi router on a wall; each bracket carries half the weight at 90 mm from the wall.
 Each bracket is an L with legs 25 mm wide and 6 mm thick and a 3 mm inside radius. They were printed lying flat, with the L outline on the bed.
 Safety factor of 2, please. Is that enough bracket?"""),
]
