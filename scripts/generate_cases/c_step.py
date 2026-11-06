from gen import kgf, LBF, IN, LB
M = "cantilever_step"
def sec(b, d): return dict(type="rect", thickness_mm=b, depth_mm=d)
def st(D, d, r): return dict(D_mm=D, d_mm=d, r_mm=r)
CASES = [
dict(slug="al-gripper-finger-step", model=M, title="6061 gripper finger with a sharp machined step",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f}; the 0.4 mm step radius (D/d 1.67) gives Kt {kt:.2f}: SF {sf:.2f}", mm=["stress_concentration"],
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=100, lever_mm=150, section=sec(6, 12), step=st(20, 12, 0.4), required_safety_factor=2.0),
 prompt="""Our pick-and-place robot's gripper fingers are machined from 6 mm thick 6061-T6 plate (yield 276 MPa). Each finger is 20 mm deep at its root block
 and steps down to 12 mm deep for the long reach; the step is cut with a 0.4 mm corner radius. The grip force of 100 N acts sideways on the fingertip,
 150 mm from the step, bending the finger across its 12 mm depth. We want a safety factor of 2 on yield. Are the fingers OK?"""),
dict(slug="steel-tool-post-step", model=M, title="1018 tool-post arm stepped with a 0.5 mm radius",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f} passes; the 0.5 mm shoulder radius (D/d 1.67, r/d 0.026) gives Kt {kt:.2f}: SF {sf:.2f}", mm=["stress_concentration"],
 inputs=dict(material="1018_CR", yield_mpa=370, load_n=round(240 * LBF), lever_mm=round(4 * IN, 1), section=sec(12.7, 19.05), step=st(31.75, 19.05, 0.5), required_safety_factor=2.0),
 prompt="""I'm machining a cantilevered tool-holder arm for a lathe fixture from 1/2 in thick 1018 cold-rolled bar (yield about 53.7 ksi / 370 MPa). The arm is
 1.25 in deep where it's clamped and steps down to 0.75 in deep, and the cutting force of 240 lbf acts 4 in from that step, bending the arm across the 0.75 in
 depth. The step was cut square with just a 0.5 mm corner radius. Safety factor of 2 on yield, please. Will it hold?"""),
dict(slug="7075-landing-leg-step", model=M, title="7075 drone landing leg stepped with a 0.3 mm radius",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f} vs 1.5 required; the 0.3 mm step (r/d 0.03) gives Kt {kt:.2f}: SF {sf:.2f}", mm=["stress_concentration"],
 inputs=dict(material="Al7075-T6", yield_mpa=503, load_n=255, lever_mm=120, section=sec(8, 10), step=st(16, 10, 0.3), required_safety_factor=1.5),
 prompt="""Our survey drone's landing legs are cut from 8 mm 7075-T6 plate (yield 503 MPa). Each leg is 16 mm deep where it bolts to the frame and narrows to
 10 mm deep for the rest of its length, with a 0.3 mm radius at the step. On a hard landing each foot can take a 255 N sideways kick, 120 mm from that step,
 bending the leg across its 10 mm depth. We need 1.5 on yield. Are the legs OK?"""),
dict(slug="ss304-pulley-arm-step", model=M, title="304 stainless pulley arm with a 0.3 mm step radius",
 trap="[stress_concentration] Nominal SF {sf_nom:.1f}; the 0.3 mm step radius (D/d 1.8) gives Kt {kt:.2f}: SF {sf:.2f}", mm=["stress_concentration"],
 inputs=dict(material="SS304", load_n=165, lever_mm=80, section=sec(10, 10), step=st(18, 10, 0.3), required_safety_factor=2.0),
 prompt="""On a cable-pull exercise station the top pulley hangs from a short arm made of 10 mm thick annealed 304 stainless. The arm is 18 mm deep at the
 mounting end and steps down to 10 mm deep, with a 0.3 mm corner radius at the step. The cable pulls 165 N on the pulley axle 80 mm from the step, bending
 the arm across its 10 mm depth. We'd like a safety factor of 2 on yield. Is it OK?"""),
dict(slug="pla-clamp-lever-step", model=M, title="PLA clamp lever with a square step, printed flat",
 trap="[stress_concentration] Printed flat so the PLA in-layer 50 MPa applies and nominal SF is {sf_nom:.1f}, but the 0.5 mm step (D/d 2) gives Kt {kt:.2f}: SF {sf:.2f}", mm=["stress_concentration"],
 inputs=dict(material="PLA", print_orientation="flat", load_n=30, lever_mm=50, section=sec(8, 8), step=st(16, 8, 0.5), required_safety_factor=2.0),
 prompt="""I designed a quick-release lever for a woodworking jig and printed it in PLA at 100% infill, lying flat on the bed. The lever is 8 mm thick; it's
 16 mm deep at the hub and steps down to an 8 mm deep handle, and the step has only a 0.5 mm corner radius. You push the handle with about 30 N at 50 mm
 from the step, bending it across the 8 mm depth. Safety factor 2 please. Will the lever survive?"""),
dict(slug="petg-gripper-finger-upright", model=M, title="PETG gripper finger printed standing up",
 trap="[layer_direction] Printed fingertip-up, so bending pulls across the stacked passes: PETG 18 MPa interlayer gives SF {sf:.2f}; the 47 MPa datasheet value would give {sf_in:.2f}", mm=["layer_direction_strength"],
 inputs=dict(material="PETG", print_orientation="upright_layers_horizontal", load_n=30, lever_mm=70, section=sec(12, 10), step=st(16, 10, 3.0), required_safety_factor=2.0),
 prompt="""For a small robot arm I printed the gripper fingers in PETG at 100% infill. Each finger is 12 mm thick; it is 16 mm deep at the base and narrows to
 10 mm deep through a 3 mm radius. The servo squeezes with 30 N at the fingertip, 70 mm from the narrowing, bending the finger across its 10 mm depth.
 To get a clean fingertip I printed them standing on their bases, fingertip pointing up. I want a safety factor of 2. Will they hold?"""),
dict(slug="abs-pegboard-clip-upright", model=M, title="ABS pegboard arm printed upright with a sharp step",
 trap="[layer_direction] Printed upright, so bending acts across ABS's stacked passes (29.7 MPa), and the 0.5 mm step adds Kt {kt:.2f}: SF {sf:.2f}", mm=["layer_direction_strength", "stress_concentration"],
 inputs=dict(material="ABS", print_orientation="upright_layers_horizontal", load_n=round(kgf(1.9), 1), lever_mm=60, section=sec(10, 8), step=st(14, 8, 0.5), required_safety_factor=2.0),
 prompt="""I printed a pegboard arm in ABS (100% infill) to hold a 1.9 kg soldering station. The arm is 10 mm wide; it's 14 mm deep at the pegboard end and
 steps down to 8 mm deep with a 0.5 mm radius, and the station hangs 60 mm from the step. I printed it standing on the pegboard end with the arm vertical,
 which needed no supports. I'd like a safety factor of 2. Is it OK?"""),
dict(slug="al-idler-arm-offset", model=M, title="6061 idler arm with the pulley offset beyond its end",
 trap="[lever_arm] The idler axle sits 90 mm beyond the end of the arm, so the lever from the step is {inp[lever_mm]:g} mm, not 90 mm: SF {sf:.2f}",
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=300, lever_mm=180, section=sec(10, 15), step=st(25, 15, 2.0), required_safety_factor=2.0),
 prompt="""Our conveyor test rig uses a belt idler on a 6061-T6 arm (yield 276 MPa), 10 mm thick, 25 mm deep at the mount, stepping to 15 mm deep through a 2 mm
 radius. From the step to the end of the arm is 90 mm, and the idler is carried on an offset bracket bolted to the end, which puts the idler axle another 90 mm
 further out. Belt tension puts 300 N on the axle, bending the arm across its 15 mm depth. Safety factor of 2. Is the arm OK?"""),
dict(slug="steel-counterweight-arm-offset", model=M, title="1018 counterweight arm with an extension bracket",
 trap="[lever_arm] The weight hangs 100 mm beyond the end of the 80 mm arm, so the lever from the step is {inp[lever_mm]:g} mm: SF {sf:.2f}",
 inputs=dict(material="1018_CR", yield_mpa=370, load_n=round(46 * LBF, 1), lever_mm=180, section=sec(10, 12), step=st(20, 12, 2.0), required_safety_factor=2.5),
 prompt="""On a camera crane test rig, a 46 lb-force counterweight hangs off a stepped 1018 steel arm (yield 370 MPa). The arm is 10 mm thick and 20 mm deep at
 its base, stepping down to 12 mm deep through a 2 mm radius; the step is 80 mm from the arm's end. The weight hangs from an eye on a flat extension plate
 bolted to the end, 100 mm further out. The weight bends the arm across its 12 mm depth. We require a safety factor of 2.5. Will it hold?"""),
dict(slug="al-pedal-arm-flat", model=M, title="6061 pedal arm loaded across its thin direction",
 trap="[weak_axis] The 25 mm wide arm is thinned to 6 mm and pushed on its wide face, so it bends across the 6 mm (Z = {Z:.0f} mm³, SF {sf:.2f}); taking 25 mm as the depth gives SF ~{sf_strong:.1f}",
 post=["Treating 25 mm as the bending depth would give SF ≈ {sf_strong:.1f}, which is wrong for a load on the wide face."],
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=306, lever_mm=100, section=sec(25, 6), step=st(10, 6, 2.0), required_safety_factor=2.0),
 prompt="""On our brake test rig the operator presses a foot pedal on the end of a 6061-T6 arm (yield 276 MPa). The arm is 25 mm wide; it's 10 mm thick at the
 pivot hub and machined down to 6 mm thick for the rest of its length, blended with a 2 mm radius. The foot pushes up to 306 N squarely on the wide face of the
 pedal, 100 mm from where it thins down. We need a safety factor of 2 on yield. Is the arm strong enough?"""),
# ---- controls
dict(slug="steel-press-lever-control", model=M, title="1018 press lever with a generous step radius (control)", control=True,
 trap="[control] none, genuinely safe: 4 mm step radius keeps Kt at {kt:.2f}; SF {sf:.1f}",
 inputs=dict(material="1018_CR", yield_mpa=370, load_n=300, lever_mm=120, section=sec(10, 20), step=st(30, 20, 4.0), required_safety_factor=2.0),
 prompt="""I'm making a hand lever for an arbor press fixture from 10 mm thick 1018 cold-rolled bar (yield 370 MPa). It's 30 mm deep at the hub and steps down
 to 20 mm deep with a 4 mm radius. The operator pulls up to 300 N at 120 mm from the step, bending it across the 20 mm depth. Safety factor of 2 on yield.
 Is it fine?"""),
dict(slug="al-robot-link-control", model=M, title="6061 robot arm link with a 3 mm step radius (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}, Kt {kt:.2f} at the 3 mm step",
 inputs=dict(material="Al6061-T6", yield_mpa=276, load_n=60, lever_mm=200, section=sec(8, 16), step=st(24, 16, 3.0), required_safety_factor=2.0),
 prompt="""Our educational robot arm has a forearm link machined from 8 mm 6061-T6 plate (yield 276 MPa). It is 24 mm deep at the elbow and steps to 16 mm
 deep through a 3 mm radius. The worst-case payload plus gripper puts 60 N at 200 mm from the step, bending it across the 16 mm depth. Safety factor 2 on yield.
 Is the link OK?"""),
dict(slug="petg-camera-arm-control", model=M, title="PETG action-camera arm printed flat (control)", control=True,
 trap="[control] none, genuinely safe: printed flat, bending along the extruded paths (47 MPa); SF {sf:.1f}",
 inputs=dict(material="PETG", print_orientation="flat", load_n=15, lever_mm=60, section=sec(10, 10), step=st(16, 10, 3.0), required_safety_factor=2.0),
 prompt="""I printed an arm in PETG (100% infill, lying flat on the bed) to hold an action camera on my bike's handlebar. It's 10 mm thick, 16 mm deep at the
 clamp and narrows to 10 mm deep through a 3 mm radius. Including bumps I'm designing for 15 N at the camera, 60 mm from the narrowing. Safety factor of 2.
 Good enough?"""),
dict(slug="7075-quad-arm-control", model=M, title="7075 quadcopter arm with a 3 mm step radius (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f} vs 1.5; 3 mm radius gives Kt {kt:.2f}",
 inputs=dict(material="Al7075-T6", yield_mpa=503, load_n=round(kgf(2.5) * 2, 1), lever_mm=200, section=sec(10, 12), step=st(20, 12, 3.0), required_safety_factor=1.5),
 prompt="""Our quadcopter arms are machined from 10 mm 7075-T6 plate (yield 503 MPa): 20 mm deep at the hub, stepping to 12 mm deep through a 3 mm radius.
 Each motor makes up to 2.5 kg of thrust and we design for twice that, acting 200 mm from the step and bending the arm across its 12 mm depth. We need 1.5
 on yield. Are the arms OK?"""),
dict(slug="ss304-probe-arm-control", model=M, title="304 stainless probe arm with a 2 mm step radius (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}, Kt {kt:.2f}",
 inputs=dict(material="SS304", load_n=100, lever_mm=80, section=sec(12, 12), step=st(18, 12, 2.0), required_safety_factor=2.0),
 prompt="""A washdown inspection station holds a probe on an arm of 12 mm thick annealed 304 stainless. The arm is 18 mm deep at the mount and 12 mm deep
 past a 2 mm radius step. The worst push on the probe is 100 N at 80 mm from the step, bending the arm across its 12 mm depth. Safety factor of 2 on yield.
 Is it OK?"""),
]
