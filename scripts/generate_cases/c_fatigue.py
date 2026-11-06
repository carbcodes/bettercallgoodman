import math
from gen import kgf, LBF, IN, LB
M = "cantilever_fatigue"
STEEL = {"1018_CD": (370, 440), "1035_CD": (460, 550), "1040_CD": (490, 590), "1045_CD": (530, 630), "1050_CD": (580, 690), "1035_HR": (270, 500)}
SRC = "Steel Sy/Sut: Shigley 10th ed. Table A-20 (deterministic ASTM minimum strengths)"
def fat(mat, surf, d, L, sigma, rev, hz, req, step=5):
    Sy, Sut = STEEL[mat]; Z = math.pi * d**3 / 32
    F = round(sigma * Z / L / step) * step
    return dict(material=mat, yield_mpa=Sy, ultimate_mpa=Sut, surface=surf, diameter_mm=d, lever_mm=L,
                load_min_n=-F if rev else 0, load_max_n=F, frequency_hz=hz, required_safety_factor=req)
FT = "[fatigue] Static SF {sfs:.2f} passes, but the cyclic bending fails modified Goodman: Se {Se:.0f} MPa, n_f {n:.2f} (Gerber {ng:.2f}) vs {req:g}"
def case(slug, title, inp, prompt, control=False):
    c = dict(slug=slug, model=M, title=title, inputs=inp, prompt=prompt.format(F=inp["load_max_n"], Fl=round(inp["load_max_n"] / LBF)), src=SRC)
    if control:
        c.update(control=True, trap="[control] none, genuinely safe: static SF {sfs:.1f}, n_f {n:.2f} vs {req:g}")
    else:
        c.update(trap=FT, mm=["fatigue"])
    return c
CASES = [
case("feeder-pin-reversed", "1018 vibrating feeder pin, fully reversed",
 fat("1018_CD", "machined", 10, 60, 230, True, 50, 1.5),
 """A vibrating sieve hangs from four 10 mm pins of cold-drawn 1018 steel (yield 370 MPa, tensile 440 MPa), machined finish, each clamped in a thick block and
 sticking out 60 mm. The shaker swings the load on each pin tip ±{F} N, back and forth, 50 times a second, all day. The clamp edge is well radiused, so treat
 the pin as a plain bar. We need a safety factor of 1.5. Are the pins OK?"""),
case("forged-tow-pin-zero-max", "Forged 1045 tow pin loaded 0 to max",
 fat("1045_CD", "as_forged", 20, 80, 230, False, 2, 2.0, step=50),
 """Our test-track trailer uses a 20 mm drop-forged 1045 steel pin (yield 530 MPa, tensile 630 MPa), left as forged, that sticks out 80 mm from a welded boss.
 The drawbar loads its tip from 0 up to {F} N and back on every stop-start, roughly twice a second over long test runs. The pin has a smooth blend at the boss.
 We want a safety factor of 2. Is the pin OK?"""),
case("hr-shaker-arm-reversed", "Hot-rolled 1035 shaker arm, reversed bending",
 fat("1035_HR", "hot_rolled", 16, 90, 175, True, 25, 1.5),
 """We made the drive arm of a paint-can shaker from 16 mm hot-rolled 1035 round bar (yield 270 MPa, tensile 500 MPa), left with its mill scale. It is clamped
 at one end and the crank pushes and pulls its tip ±{F} N, 25 times a second, 90 mm from the clamp. The clamp is radiused, so treat it as a plain bar.
 Safety factor of 1.5 required. Is it OK?"""),
case("1050-test-spring-blade", "1050 cantilever flexure on a vibration table",
 fat("1050_CD", "machined", 12, 100, 330, True, 60, 1.5),
 """For a vibration test fixture we hold a 12 mm cold-drawn 1050 steel rod (yield 580 MPa, tensile 690 MPa), machined, as a cantilever 100 mm long. The table
 drives the tip ±{F} N, fully reversed, at 60 Hz for multi-day tests. The clamp edge is radiused, so consider the bar plain. We need 1.5. Will it last?"""),
case("ground-pivot-pin-reversed", "Ground 1018 pivot pin in a rocking fixture",
 fat("1018_CD", "ground", 8, 40, 240, True, 10, 1.5),
 """A rocking test fixture pivots on an 8 mm ground cold-drawn 1018 pin (yield 370 MPa, tensile 440 MPa) that sticks out 40 mm from its bore. The link on the
 pin pulls up and down on its end with ±{F} N, ten cycles a second, around the clock. Treat the pin as plain (big radius at the bore). We want 1.5. Is it OK?"""),
case("1045-crank-pin-reversed", "1045 crank pin with reversed bending, SF 2",
 fat("1045_CD", "machined", 14, 70, 252, True, 15, 2.0),
 """A wiper-motor test rig has a 14 mm cold-drawn 1045 steel crank pin (yield 530 MPa, tensile 630 MPa), machined, sticking out 70 mm from the crank disc.
 The connecting rod pushes and pulls its end ±{F} N, 15 times a second, for weeks at a time. The root blend is generous, so take the pin as plain.
 Safety factor 2 required. Is the pin OK?"""),
case("forged-1018-hook-zero-max", "As-forged 1018 hook arm loaded 0 to max",
 fat("1018_CD", "as_forged", 18, 75, 230, False, 1, 1.5, step=25),
 """On a conveyor that carries parts on hooks, each hook arm is a forged 18 mm bar of 1018 steel (yield 370 MPa, tensile 440 MPa) left as forged, sticking
 out 75 mm from its trolley. Each loading station hangs a part that loads the arm tip from 0 to {F} N and it is unloaded later, about once a second, all day,
 for years. The root is well blended. We want 1.5. Is the hook arm OK?"""),
case("1040-agitator-paddle-arm", "1040 agitator paddle arm, reversed",
 fat("1040_CD", "machined", 12, 80, 300, True, 12, 1.5),
 """Our mixer's paddle is carried on a 12 mm cold-drawn 1040 steel arm (yield 490 MPa, tensile 590 MPa), machined, sticking out 80 mm from the hub. The
 paddle pushes back and forth on the arm's end with ±{F} N, 12 times a second, around the clock. The hub radius is generous. Safety factor 1.5. Is it OK?"""),
case("ground-1035-cam-follower-arm", "Ground 1035 cam-follower arm, reversed",
 fat("1035_CD", "ground", 10, 50, 290, True, 30, 1.5),
 """A packaging machine has a cam follower on a 10 mm ground cold-drawn 1035 steel stud (yield 460 MPa, tensile 550 MPa), 50 mm from its clamp to the roller.
 The cam pushes the roller ±{F} N each way, 30 times a second, two shifts a day. The clamp edge is generously radiused, so treat the stud as plain.
 We need 1.5. Will it hold up?"""),
case("forged-1045-press-arm-zero-max", "Forged 1045 press-fixture arm loaded 0 to max",
 fat("1045_CD", "as_forged", 25, 120, 300, False, 0.5, 1.5, step=50),
 """A crimping press fixture uses a forged 25 mm 1045 steel arm (yield 530 MPa, tensile 630 MPa), left as forged, sticking out 120 mm from its base. Each crimp
 loads the arm tip from 0 to {F} N (about {Fl} lbf) and releases, every two seconds, for years of production. The base blend is smooth. We want 1.5.
 Is the arm OK?"""),
case("forged-1040-rocker-reversed", "As-forged 1040 rocker stub, reversed, SF 2",
 fat("1040_CD", "as_forged", 16, 70, 200, True, 8, 2.0),
 """A walking-beam test machine has a forged 16 mm 1040 steel stub (yield 490 MPa, tensile 590 MPa), left as forged, sticking out 70 mm from the beam. The link
 on it pushes and pulls its end ±{F} N, eight times a second, for months. The root blend is generous. We need a safety factor of 2. Is it OK?"""),
# ---- controls
case("1018-feeder-pin-control", "1018 feeder pin at low stress (control)", fat("1018_CD", "machined", 12, 50, 60, True, 50, 1.5),
 """A vibratory bowl feeder sits on 12 mm machined cold-drawn 1018 steel pins (yield 370 MPa, tensile 440 MPa) that stick out 50 mm from their clamps. The drive
 swings each pin tip ±{F} N at 50 Hz, all day. Clamp edges are radiused, so treat the pins as plain. We want 1.5. Are they OK?""", control=True),
case("1045-lever-zero-max-control", "1045 lever loaded 0 to max at low stress (control)", fat("1045_CD", "machined", 16, 80, 90, False, 5, 2.0),
 """A test-rig lever is a 16 mm machined cold-drawn 1045 steel bar (yield 530 MPa, tensile 630 MPa) sticking out 80 mm from its clamp. Every cycle loads its tip
 from 0 to {F} N and back, five times a second, continuously. The clamp is well radiused. We need a safety factor of 2. Is it OK?""", control=True),
case("1050-ground-spindle-stub-control", "Ground 1050 stub loaded 0 to max (control)", fat("1050_CD", "ground", 20, 60, 110, False, 3, 2.0, step=25),
 """An indexing table carries a ground 20 mm cold-drawn 1050 steel stub (yield 580 MPa, tensile 690 MPa) sticking out 60 mm. Each index loads its end from 0 to
 {F} N and back, three times a second, for years. Generous root radius. We want 2. Is it OK?""", control=True),
case("1035-shaker-rod-control", "1035 shaker rod at low reversed stress (control)", fat("1035_CD", "machined", 10, 60, 70, True, 20, 1.5),
 """A lab sample shaker drives its tray through a 10 mm machined cold-drawn 1035 steel rod (yield 460 MPa, tensile 550 MPa) that sticks out 60 mm from a clamp.
 The tray pushes and pulls its tip ±{F} N, 20 times a second, around the clock. Radiused clamp, so treat it as plain. We need 1.5. Is it OK?""", control=True),
case("1040-gate-arm-control", "1040 gate arm loaded 0 to max (control)", fat("1040_CD", "machined", 14, 90, 80, False, 0.2, 2.0),
 """A test rig's swing gate is held by a 14 mm machined cold-drawn 1040 steel arm (yield 490 MPa, tensile 590 MPa), sticking out 90 mm from its post. Each
 cycle loads the arm tip from 0 to {F} N and back, about every five seconds, for years. Root well radiused. Safety factor 2. Is it OK?""", control=True),
]
