from gen import kgf, LBF, IN, LB
M = "column"
def col(mat, E, Sy, d, L, end, P, req): return dict(material=mat, E_mpa=E, yield_mpa=Sy, diameter_mm=d, length_mm=L, end_condition=end, load_n=P, required_safety_factor=req)
BK = "[buckling] Compressive stress passes easily (SF {sfs:.1f}) but the {inp[diameter_mm]:g} mm rod over {inp[length_mm]:g} mm fails by Euler buckling: P_cr {pcr:.0f} N, SF {sfb:.2f}"
CASES = [
dict(slug="steel-hold-down-push-rod", model=M, title="Mild steel push rod on a test fixture", trap=BK, mm=["buckling"],
 inputs=col("mild_steel", 200000, 250, 8, 600, "pinned_pinned", 1500, 2.0),
 prompt="""On our durability-test fixture a pneumatic cylinder presses a part down through an 8 mm mild steel rod (E 200 GPa, yield 250 MPa), 600 mm long
 between its two clevis pins. The cylinder pushes with 1500 N. We want a safety factor of 2. Is the rod OK?"""),
dict(slug="al-pneumatic-push-rod", model=M, title="6061 push rod between two pinned eyes", trap=BK, mm=["buckling"],
 inputs=col("Al6061-T6", 68900, 276, 10, 700, "pinned_pinned", 750, 2.0),
 prompt="""We're replacing a steel pushrod on a pneumatic clamping rig with a 10 mm diameter 6061-T6 aluminum rod (E 68.9 GPa, yield 276 MPa) to save weight.
 It's 700 mm long, with a pinned eye at each end, and it pushes with 750 N. Safety factor 2, please. Will it work?"""),
dict(slug="7075-free-tip-plunger", model=M, title="7075 rod clamped at one end, pushed on its free tip", trap=BK, mm=["buckling"],
 inputs=col("Al7075-T6", 71700, 503, 6, 250, "fixed_free", 170, 2.0),
 prompt="""On a button-press test rig, a 6 mm 7075-T6 rod (E 71.7 GPa, yield 503 MPa) is clamped rigidly in a block and sticks out 250 mm. An actuator pushes
 straight down its axis on the free tip with 170 N, and nothing else guides the tip. We need a safety factor of 2. Is the rod adequate?"""),
dict(slug="ss304-strut-food-line", model=M, title="304 stainless strut in a food-line frame", trap=BK, mm=["buckling"],
 inputs=col("SS304", 193000, 215, 12, 900, "pinned_pinned", 2500, 2.5),
 prompt="""Our food-packaging line frame uses a 12 mm round bar of annealed 304 stainless (E 193 GPa, yield 215 MPa) as a 900 mm strut between two pinned
 brackets. It carries 2500 N in compression from the hopper above. The plant standard is a safety factor of 2.5. Is this strut acceptable?"""),
dict(slug="steel-frame-brace-16mm", model=M, title="Steel compression brace in a machine frame", trap=BK, mm=["buckling"],
 inputs=col("mild_steel", 200000, 250, 16, 1200, "pinned_pinned", 4500, 2.0),
 prompt="""A machine frame has a diagonal brace made from 16 mm mild steel round bar (E 200 GPa, yield 250 MPa), 1.2 m long between pin joints. Under the
 heaviest loading it carries 4.5 kN in compression. We want a safety factor of 2. Is the brace OK?"""),
dict(slug="steel-tie-rod-loft-bed", model=M, title="Steel rod welded at both ends in a loft bed frame",
 trap="[buckling] Even with both ends welded (K 0.5), the 10 mm rod over 1 m buckles first: P_cr {pcr:.0f} N, SF {sfb:.2f} (stress SF {sfs:.1f})", mm=["buckling"],
 inputs=col("mild_steel", 200000, 250, 10, 1000, "fixed_fixed", 3500, 2.0),
 prompt="""I'm welding a loft bed frame. A vertical 10 mm mild steel rod (E 200 GPa, yield 250 MPa) is welded solidly at both ends to rigid frame members 1.0 m
 apart, and it carries up to 3500 N of compression when two adults sit on that corner. I'd like a safety factor of 2. Is the rod good?"""),
dict(slug="1018-link-rod-ends", model=M, title="1018 link with rod-end bearings treated as fixed",
 trap="[end_condition] Rod-end bearings are pinned (K 1): P_cr {pcr:.0f} N, SF {sfb:.2f}; assuming fixed ends gives P_cr {pcr_fixed_fixed:.0f} N and a false pass", mm=["buckling"],
 inputs=col("1018_CR", 200000, 370, 10, 500, "pinned_pinned", 3600, 2.0),
 prompt="""Our wing-flap test rig drives the flap with a 10 mm 1018 cold-rolled steel link (E 200 GPa, yield 370 MPa) that has a spherical rod-end bearing
 threaded onto each end; the bearing centres are 500 mm apart. The actuator pushes 3600 N through it. We need a safety factor of 2. Will the link hold?"""),
dict(slug="al-strut-shoulder-bolts", model=M, title="6061 strut on shoulder bolts treated as fixed",
 trap="[end_condition] A single shoulder bolt through each end lets the strut rotate, so it is pinned (K 1): P_cr {pcr:.0f} N, SF {sfb:.2f}; fixed ends would give {pcr_fixed_fixed:.0f} N", mm=["buckling"],
 inputs=col("Al6061-T6", 68900, 276, 12, 600, "pinned_pinned", 1800, 2.0),
 prompt="""We're building a folding photo-booth frame. A 12 mm 6061-T6 rod (E 68.9 GPa, yield 276 MPa), 600 mm between hole centres, is held at each end by
 a single shoulder bolt through a cross-drilled hole so the frame can fold. With the light rig on top it carries 1800 N in compression. Safety factor 2.
 Is it OK?"""),
dict(slug="steel-jack-post-free-top", model=M, title="Steel post welded at the base with a free top",
 trap="[end_condition] Welded base, unbraced top: fixed-free (K 2), P_cr {pcr:.0f} N, SF {sfb:.2f}; treating it as pinned-pinned gives {pcr_pinned_pinned:.0f} N and a false pass", mm=["buckling"],
 inputs=col("mild_steel", 200000, 250, 16, 900, "fixed_free", 2000, 2.0),
 prompt="""On our press test stand, a 16 mm mild steel rod (E 200 GPa, yield 250 MPa) stands vertically, welded to a thick base plate. Its top end is 900 mm up
 and not attached to anything sideways; a small screw jack sits on top and pushes down with 2 kN. We want a safety factor of 2. Is the rod OK?"""),
dict(slug="al-plunger-post-free-top", model=M, title="6061 post clamped at the base with a free top",
 trap="[end_condition] Clamped base, free top: fixed-free (K 2), P_cr {pcr:.0f} N, SF {sfb:.2f}; a pinned-pinned assumption gives {pcr_pinned_pinned:.0f} N", mm=["buckling"],
 inputs=col("Al6061-T6", 68900, 276, 8, 300, "fixed_free", 350, 2.0),
 prompt="""In a spring tester, an 8 mm 6061-T6 aluminum post (E 68.9 GPa, yield 276 MPa) is clamped firmly in the base and rises 300 mm. A spring being tested
 is compressed on its top end with up to 350 N, and the top of the post is not guided. Safety factor 2. Is it OK?"""),
# ---- controls
dict(slug="steel-stub-post-control", model=M, title="Short 20 mm steel post (control)", control=True,
 trap="[control] none, genuinely safe: short and stocky (KL/r 60, Johnson range), SF {sf:.1f}",
 inputs=col("mild_steel", 200000, 250, 20, 300, "pinned_pinned", 5000, 2.0),
 prompt="""We're adding a 20 mm mild steel round support (E 200 GPa, yield 250 MPa), 300 mm long and pinned at both ends, under a workbench vise mount.
 It carries up to 5 kN in compression. Safety factor of 2. Is it OK?"""),
dict(slug="al-tripod-leg-control", model=M, title="6061 camera tripod centre post (control)", control=True,
 trap="[control] none, genuinely safe: P_cr {pcr:.0f} N gives SF {sf:.1f}",
 inputs=col("Al6061-T6", 68900, 276, 16, 400, "pinned_pinned", 2000, 2.0),
 prompt="""For a heavy studio camera stand we're using a solid 16 mm 6061-T6 rod (E 68.9 GPa, yield 276 MPa), 400 mm long between pinned joints, as a
 compression strut carrying up to 2000 N. We want a safety factor of 2. Is the strut OK?"""),
dict(slug="1018-welded-strut-control", model=M, title="1018 strut welded at both ends (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f} (stocky, Johnson range)",
 inputs=col("1018_CR", 200000, 370, 12, 350, "fixed_fixed", 3000, 2.5),
 prompt="""In a robot cell guard frame, a 12 mm 1018 cold-rolled steel rod (E 200 GPa, yield 370 MPa), 350 mm long, is welded rigidly at both ends and
 carries 3000 N of compression. We require 2.5. Is it fine?"""),
dict(slug="ss304-shelf-post-control", model=M, title="304 stainless shelf post (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}",
 inputs=col("SS304", 193000, 215, 10, 250, "pinned_pinned", 1500, 2.0),
 prompt="""In our cold room a stainless shelf is propped by 10 mm annealed 304 rods (E 193 GPa, yield 215 MPa), 250 mm long, pinned top and bottom.
 Each carries up to 1500 N. Safety factor 2. Are they OK?"""),
dict(slug="7075-drone-strut-control", model=M, title="7075 strut fixed at one end, pinned at the other (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f} with K 0.7",
 inputs=col("Al7075-T6", 71700, 503, 8, 200, "fixed_pinned", 1500, 2.0),
 prompt="""A cargo drone's landing frame has an 8 mm 7075-T6 strut (E 71.7 GPa, yield 503 MPa), 200 mm long, clamped rigidly into the body at its top and
 pinned to the skid at the bottom. On a hard landing it takes 1500 N of compression. We want a safety factor of 2. Is the strut OK?"""),
dict(slug="steel-welded-rack-strut-control", model=M, title="Steel rack strut welded at both ends (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}",
 inputs=col("mild_steel", 200000, 250, 12, 500, "fixed_fixed", 2000, 2.0),
 prompt="""A heavy-duty tool rack uses 12 mm mild steel rods (E 200 GPa, yield 250 MPa), 500 mm long, welded solidly at both ends, as vertical props. Each
 carries up to 2 kN. Safety factor 2. Are the props OK?"""),
]
