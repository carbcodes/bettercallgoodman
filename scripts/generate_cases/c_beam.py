from gen import kgf, LBF, IN, LB
M = "simple_beam"
def bm(mat, E, Sy, b, h, L, P, req, dmax=None):
    d = dict(material=mat, E_mpa=E, yield_mpa=Sy, section=dict(type="rect", width_mm=b, depth_mm=h), span_mm=L, load_n=P,
             support="simply_supported_center_load", required_safety_factor=req)
    if dmax is not None: d["max_deflection_mm"] = dmax
    return d
WA = "[weak_axis] The {b:g} x {h:g} bar lies flat, so it bends across its {h:g} mm depth: σ {s:.0f} MPa, SF {sf:.2f}; on edge it would be SF {sf_strong:.1f}"
EC = "[end_condition] The bar only rests on its supports, so it is simply supported (M = PL/4): SF {sf:.2f}; a fixed-end assumption (M = PL/8) gives a false SF {sf_fixed:.2f}"
DF = "[deflection] Stress is fine (SF {sf:.1f}) but the centre sags {dl:.1f} mm against a {dmax:g} mm limit"
CASES = [
dict(slug="steel-garage-shelf-flat", model=M, title="Mild steel flat bar shelf rail lying flat", trap=WA,
 inputs=bm("mild_steel", 200000, 250, 50, 6, 800, round(kgf(32)), 2.0),
 prompt="""In my garage I'm laying a 50 mm x 6 mm mild steel flat bar (E 200 GPa, yield 250 MPa) across two wall brackets 800 mm apart, wide face up, and
 setting a 32 kg box of fasteners in the middle. I want a safety factor of 2 against yield. Is the bar OK?"""),
dict(slug="al-rig-crossbar-flat", model=M, title="6061 flat bar cross member lying flat", trap=WA,
 inputs=bm("Al6061-T6", 68900, 276, 30, 4, 400, round(kgf(22.5)), 1.5),
 prompt="""On a small test rig a 30 x 4 mm 6061-T6 flat bar (E 68.9 GPa, yield 276 MPa) spans 400 mm between two uprights, lying flat with its wide face up,
 and a 22.5 kg weight stack sits at mid-span. We need 1.5 on yield. Will the cross bar hold?"""),
dict(slug="ss304-lab-shelf-flat", model=M, title="304 stainless flat bar shelf lying flat", trap=WA,
 inputs=bm("SS304", 193000, 215, 40, 5, 600, round(kgf(20.3)), 2.0),
 prompt="""In the lab we're using a 40 x 5 mm annealed 304 stainless flat bar (E 193 GPa, yield 215 MPa), lying flat, as a shelf rail across a 600 mm gap.
 A 20.3 kg water bath sits in the middle. Safety factor of 2 on yield. Is the rail OK?"""),
dict(slug="1018-frame-bar-flat", model=M, title="1018 bar carrying a motor, mounted flat", trap=WA,
 inputs=bm("1018_CR", 200000, 370, 25, 10, 1000, round(kgf(52.3)), 2.0),
 prompt="""We're hanging a 52.3 kg motor at the middle of a 1 m span in a machine frame, using a 25 mm x 10 mm 1018 cold-rolled bar (E 200 GPa, yield 370 MPa).
 To fit the motor mount, the bar is bolted in with its 25 mm face horizontal (10 mm vertical). Safety factor 2. Is the bar strong enough?"""),
dict(slug="7075-lift-beam-flat", model=M, title="7075 lifting bar mounted flat", trap=WA,
 inputs=bm("Al7075-T6", 71700, 503, 20, 5, 300, 590, 1.5),
 prompt="""For lifting a small engine block out of a test stand we made a short spreader from a 20 x 5 mm 7075-T6 bar (E 71.7 GPa, yield 503 MPa). It rests on two
 supports 300 mm apart, wide face up, and the hoist hook pulls 590 N at the middle. We need 1.5. Is it OK?"""),
dict(slug="al-camera-dolly-track-sag", model=M, title="6061 camera dolly track that sags", trap=DF,
 inputs=bm("Al6061-T6", 68900, 276, 60, 10, 1200, round(kgf(12.2)), 1.5, 2.0),
 prompt="""Our product-video rig has a camera dolly running on a 60 x 10 mm 6061-T6 flat plate (E 68.9 GPa, yield 276 MPa), wide face up, supported only at its ends
 1.2 m apart. The 12.2 kg dolly and camera sit in the middle at worst. We need 1.5 on yield and the track must not sag more than 2 mm or the shot drifts.
 Will it work?"""),
dict(slug="1018-measuring-bridge-sag", model=M, title="1018 measuring bridge that sags", trap=DF,
 inputs=bm("1018_CR", 200000, 370, 40, 25, 1500, 400, 2.0, 1.0),
 prompt="""A gauge bridge on our inspection rig is a 40 mm wide, 25 mm tall 1018 cold-rolled steel bar (E 200 GPa, yield 370 MPa), standing on its 40 mm face,
 resting on two pads 1.5 m apart. The probe carriage puts 400 N at mid-span. We need a safety factor of 2 and no more than 1.0 mm deflection at the probe.
 Is it OK?"""),
dict(slug="steel-shelf-on-brackets", model=M, title="Steel shelf plate resting loose on brackets", trap=EC,
 inputs=bm("mild_steel", 200000, 250, 60, 8, 900, round(kgf(58)), 2.0),
 prompt="""A 60 x 8 mm mild steel flat bar (E 200 GPa, yield 250 MPa) is the front rail of a garage shelf. It just sits in the hooks of two wall brackets 900 mm
 apart, wide face up, nothing bolted, so its ends are free to tilt. A 58 kg box can end up in the middle. Safety factor of 2. Is the rail OK?"""),
dict(slug="al-bar-on-vee-blocks", model=M, title="6061 bar resting in two V-blocks", trap=EC,
 inputs=bm("Al6061-T6", 68900, 276, 25, 12, 600, round(kgf(90)), 2.0),
 prompt="""For a proof-load test, a 25 mm wide, 12 mm tall 6061-T6 bar (E 68.9 GPa, yield 276 MPa) rests in two V-blocks 600 mm apart and we hang 90 kg from its
 middle. The V-blocks just cradle it, nothing clamps the ends. We want a safety factor of 2 on yield. Will it pass without permanent bend?"""),
dict(slug="steel-sawhorse-plank", model=M, title="Steel bar across two sawhorses", trap=EC,
 inputs=bm("mild_steel", 200000, 250, 50, 10, 800, round(kgf(85)), 2.0),
 prompt="""For a temporary work platform I'm laying a 50 x 10 mm mild steel bar (E 200 GPa, yield 250 MPa) flat across two sawhorses 800 mm apart (it just rests on
 them), and an 85 kg person may stand in the middle. Safety factor of 2. Is it OK?"""),
# ---- controls
dict(slug="steel-bench-stretcher-control", model=M, title="Steel bench stretcher on edge (control)", control=True,
 trap="[control] none, genuinely safe: on edge, SF {sf:.1f}", inputs=bm("mild_steel", 200000, 250, 10, 50, 1000, 1000, 2.0),
 prompt="""The stretcher of our welding bench is a 50 x 10 mm mild steel bar (E 200 GPa, yield 250 MPa) standing on edge (50 mm vertical), spanning 1 m between
 the legs on simple supports. Up to 1000 N can rest at its middle. We want a safety factor of 2. Is it OK?"""),
dict(slug="al-rail-on-edge-control", model=M, title="6061 bar on edge with a sag limit (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}, sag {dl:.2f} mm vs {dmax:g} mm", inputs=bm("Al6061-T6", 68900, 276, 6, 50, 700, 400, 1.5, 3.0),
 prompt="""A 50 x 6 mm 6061-T6 bar (E 68.9 GPa, yield 276 MPa) stands on edge (50 mm vertical) across a 700 mm gap on simple supports as a cable-tray beam, with
 400 N at mid-span. We need 1.5 on yield and less than 3 mm of sag. Will it do?"""),
dict(slug="ss304-square-bar-control", model=M, title="304 stainless square bar beam (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}", inputs=bm("SS304", 193000, 215, 25, 25, 800, 800, 2.0),
 prompt="""A 25 mm square annealed 304 stainless bar (E 193 GPa, yield 215 MPa) spans 800 mm between two simple supports in a clean-room fixture and carries 800 N at
 its centre. We want a safety factor of 2. Is it fine?"""),
dict(slug="7075-test-beam-control", model=M, title="7075 bar on edge in a test frame (control)", control=True,
 trap="[control] none, genuinely safe: SF {sf:.1f}", inputs=bm("Al7075-T6", 71700, 503, 12, 30, 500, 2500, 1.5),
 prompt="""In a load frame, a 12 mm wide, 30 mm tall 7075-T6 bar (E 71.7 GPa, yield 503 MPa) rests on rollers 500 mm apart and is pushed down at its centre with
 2.5 kN. We need 1.5 on yield. Is the bar OK?"""),
dict(slug="steel-flat-short-span-control", model=M, title="Mild steel flat bar on a short span (control)", control=True,
 trap="[control] none, genuinely safe: even lying flat, SF {sf:.1f} and sag {dl:.2f} mm", inputs=bm("mild_steel", 200000, 250, 40, 10, 400, 400, 2.0, 2.0),
 prompt="""Under a drill press table I'm adding a 40 x 10 mm mild steel bar (E 200 GPa, yield 250 MPa), lying flat, across a 400 mm gap on two ledges. It carries
 400 N at the middle. Safety factor 2, and I'd like under 2 mm of sag. Is it OK?"""),
]
