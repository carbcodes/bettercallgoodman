from gen import kgf, LBF, IN, LB
M = "thermal_column"
SRC = "CTE and E: ASM Aerospace Specification Metals / MatWeb (6061-T6 and 7075-T6 23.6e-6/°C, AISI 304 17.3e-6/°C, carbon steel ~12e-6/°C)"
ALPHA = {"mild_steel": 12.0e-6, "1018_CR": 12.0e-6, "Al6061-T6": 23.6e-6, "Al7075-T6": 23.6e-6, "SS304": 17.3e-6}
EY = {"mild_steel": (200000, 250), "1018_CR": (200000, 370), "Al6061-T6": (68900, 276), "Al7075-T6": (71700, 503), "SS304": (193000, 215)}
def th(mat, d, L, end, dT, req=None):
    E, Sy = EY[mat]
    x = dict(material=mat, E_mpa=E, yield_mpa=Sy, alpha_per_c=ALPHA[mat], diameter_mm=d, length_mm=L, end_condition=end, delta_t_c=dT)
    if req: x["required_safety_factor"] = req
    return x
TB = "[thermal_restraint] Restrained thermal stress {s:.0f} MPa is well under yield, but the restrained force {F:.0f} N exceeds P_cr {pcr:.0f} N: the rod bows above about +{dTc:.0f} °C"
TY = "[thermal_restraint] Nobody applies a load, but fully restrained heating gives σ = EαΔT = {s:.0f} MPa: yield SF {sfs:.2f}"
TE = "[end_condition] Pinned ends (K 1): P_cr {pcr:.0f} N < restrained force {F:.0f} N, SF {sfb:.2f}; assuming fixed ends gives P_cr {pcr_fixed_fixed:.0f} N and a false pass"
def case(slug, title, inp, prompt, trap, mm=None, control=False):
    c = dict(slug=slug, model=M, title=title, inputs=inp, prompt=prompt, trap=trap, src=SRC)
    if mm: c["mm"] = mm
    if control: c["control"] = True
    return c
CASES = [
case("al-camera-rail-sun", "6061 camera rail clamped at both ends in the sun", th("Al6061-T6", 10, 800, "fixed_fixed", 30),
 """Our rooftop time-lapse rig has a 10 mm 6061-T6 aluminum guide rod (E 68.9 GPa, yield 276 MPa, expansion 23.6e-6 per °C), 800 mm long, clamped solidly at both
 ends into a steel frame that stays shaded. It was installed at 15 °C and in direct sun the rod reaches 45 °C. The rod has to stay straight for the carriage.
 Will it be OK?""", TB, ["buckling"]),
case("steel-oven-tie-rod-yield", "Mild steel tie rod heated 150 °C between massive blocks", th("mild_steel", 20, 200, "fixed_fixed", 150),
 """Inside our curing-oven test rig, a 20 mm mild steel rod (E 200 GPa, yield 250 MPa, expansion 12e-6 per °C), 200 mm long, is welded between two massive steel
 blocks that sit outside the hot zone and don't move. In operation the rod heats up 150 °C above assembly temperature while the blocks stay near room temperature.
 It mustn't yield. Is it OK?""", TY),
case("ss304-dryer-rail", "304 stainless rail in a food dryer", th("SS304", 12, 1200, "fixed_fixed", 40),
 """A food dehydrator line has a 12 mm annealed 304 stainless guide rail (E 193 GPa, yield 215 MPa, expansion 17.3e-6 per °C), 1.2 m long, rigidly clamped at both
 ends to the cool outer frame. In production the rail runs 40 °C above the frame. It must stay straight. Will it?""", TB, ["buckling"]),
case("steel-clevis-rod-sunlit", "Steel rod with clevis ends between fixed brackets", th("mild_steel", 10, 600, "pinned_pinned", 25),
 """In a greenhouse automation frame a 10 mm mild steel rod (E 200 GPa, yield 250 MPa, expansion 12e-6 per °C) is mounted between two immovable brackets with a
 clevis pin at each end, 600 mm between pins. The sun heats the rod 25 °C above the temperature at assembly; the brackets don't move. Will the rod stay
 straight and unyielded?""", TE, ["buckling"]),
case("al-pin-ended-strut-heat", "6061 strut on pins between rigid walls", th("Al6061-T6", 8, 500, "pinned_pinned", 20),
 """A sensor rack inside an environmental chamber uses an 8 mm 6061-T6 rod (E 68.9 GPa, yield 276 MPa, expansion 23.6e-6 per °C), 500 mm between two shoulder
 bolts (one at each end, through cross-drilled holes) anchored in the thick chamber walls, which don't move. During a test the rod warms 20 °C more than the
 walls. Does it stay straight?""", TE, ["buckling"]),
case("1018-heat-fixture-yield", "1018 rod clamped in a heat-treat fixture", th("1018_CR", 25, 150, "fixed_fixed", 120, 2.0),
 """In a brazing fixture a 25 mm 1018 cold-rolled steel rod (E 200 GPa, yield 370 MPa, expansion 12e-6 per °C), 150 mm long, is clamped hard between two
 water-cooled jaws that don't move. During the cycle the rod heats 120 °C above the jaws. We want a safety factor of 2 against yield. Is that met?""", TY),
case("steel-furnace-guide-rail", "Steel guide rail near a furnace", th("mild_steel", 16, 1500, "fixed_fixed", 45),
 """Next to our heat-treat furnace a transfer cart runs on a 16 mm mild steel guide rod (E 200 GPa, yield 250 MPa, expansion 12e-6 per °C), 1.5 m long, bolted
 rigidly at both ends to a cool concrete-mounted frame. Radiant heat warms the rod 45 °C above the frame. It needs to stay straight. Will it?""", TB, ["buckling"]),
case("al-solar-frame-rail", "6061 rail in a solar test frame", th("Al6061-T6", 12, 1000, "fixed_fixed", 35),
 """On a solar panel test frame a 12 mm 6061-T6 rod (E 68.9 GPa, yield 276 MPa, expansion 23.6e-6 per °C), 1.0 m long, is clamped rigidly at both ends to a
 steel base that stays cool in the shade. In summer the rod gets 35 °C hotter than the base. Is it OK?""", TB, ["buckling"]),
case("ss304-autoclave-pinned-rod", "304 rod on pins in an autoclave rack", th("SS304", 10, 400, "pinned_pinned", 40),
 """An autoclave sample rack has a 10 mm annealed 304 stainless rod (E 193 GPa, yield 215 MPa, expansion 17.3e-6 per °C), 400 mm between pins, held between two
 heavy end plates by a single pin at each end. Each cycle the rod heats 40 °C more than the end plates, which don't move apart. Is the rod OK?""", TE, ["buckling"]),
case("ss304-steam-rack-yield", "304 tie rod clamped in a steam sterilizer", th("SS304", 20, 250, "fixed_fixed", 100),
 """In a steam sterilizer rack, a 20 mm annealed 304 stainless rod (E 193 GPa, yield 215 MPa, expansion 17.3e-6 per °C), 250 mm long, is welded between two thick
 outer plates that stay near room temperature. Steam heats the rod 100 °C above the plates. It mustn't yield. Is it OK?""", TY),
# ---- controls
case("steel-short-stub-control", "Short 20 mm steel stub, small warm-up (control)", th("mild_steel", 20, 300, "fixed_fixed", 20),
 """A 20 mm mild steel spacer rod (E 200 GPa, yield 250 MPa, expansion 12e-6 per °C), 300 mm long, is welded between two rigid frame plates. In use it warms 20 °C
 above the plates. Will it be OK?""", "[control] none, genuinely OK: σ {s:.0f} MPa (SF {sfs:.1f}), restrained force {F:.0f} N vs P_cr {pcr:.0f} N", control=True),
case("al-short-rod-control", "Short 12 mm 6061 rod, 15 °C (control)", th("Al6061-T6", 12, 300, "fixed_fixed", 15),
 """A 12 mm 6061-T6 rod (E 68.9 GPa, yield 276 MPa, expansion 23.6e-6 per °C), 300 mm long, is clamped rigidly at both ends in a lab fixture and warms 15 °C above
 the fixture. Is that OK?""", "[control] none, genuinely OK: SF {sf:.1f}", control=True),
case("ss304-stout-rod-control", "Stout 16 mm 304 rod, 25 °C (control)", th("SS304", 16, 400, "fixed_fixed", 25),
 """In a washdown frame, a 16 mm annealed 304 stainless rod (E 193 GPa, yield 215 MPa, expansion 17.3e-6 per °C), 400 mm long, is welded at both ends to a rigid
 frame and gets 25 °C warmer than the frame during cleaning. Will it be fine?""", "[control] none, genuinely OK: SF {sf:.1f}", control=True),
case("1018-pinned-short-control", "Short 1018 rod on pins, 30 °C (control)", th("1018_CR", 10, 200, "pinned_pinned", 30),
 """A 10 mm 1018 cold-rolled steel rod (E 200 GPa, yield 370 MPa, expansion 12e-6 per °C), 200 mm between pins, links two rigid brackets and warms 30 °C more than
 they do. Is it OK?""", "[control] none, genuinely OK: SF {sf:.1f}", control=True),
case("7075-short-rod-control", "Short 10 mm 7075 rod, 30 °C (control)", th("Al7075-T6", 10, 250, "fixed_fixed", 30),
 """A drone test stand has a 10 mm 7075-T6 rod (E 71.7 GPa, yield 503 MPa, expansion 23.6e-6 per °C), 250 mm long, clamped rigidly at both ends in a steel frame.
 Motor heat warms it 30 °C above the frame. Is it OK?""", "[control] none, genuinely OK: SF {sf:.1f}", control=True),
]
