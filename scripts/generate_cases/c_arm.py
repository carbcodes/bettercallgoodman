from gen import kgf, LBF, IN, LB
M = "arm_torque"
OZIN = 0.0720078  # 1 oz·in in kg·cm
def arm(stall, L, ma, mt, req): return dict(stall_torque_kgcm=stall, arm_length_mm=L, arm_mass_kg=ma, tip_mass_kg=mt, required_margin=req)
SU = "[stall_vs_usable] Needed {tk:.1f} kg·cm is below the {stall:g} kg·cm stall rating, so it looks fine, but the required margin of {req:g} needs {need:.1f} kg·cm: margin only {m:.2f}"
CASES = [
dict(slug="ds3218-elbow-margin", model=M, title="20 kg·cm servo on a robot elbow, margin 2", trap=SU,
 inputs=arm(20, 200, 0.08, 0.65, 2.0),
 prompt="""For a desktop robot arm I'm using a DS3218 servo at the elbow; the datasheet says 20 kg·cm stall torque at 6.8 V. The forearm is 200 mm from the
 servo shaft to the wrist, weighs 80 g spread evenly, and the wrist, gripper and payload together are 650 g at the end. We size joints so the servo has a margin
 of 2 over the holding torque with the arm straight out horizontally. Will the servo do?"""),
dict(slug="gimbal-tilt-35kgcm", model=M, title="35 kg·cm servo tilting a camera on an arm", trap=SU,
 inputs=arm(35, 250, 0.1, 1.1, 2.0),
 prompt="""Our pan-tilt camera head uses a 35 kg·cm (stall, 7.4 V) servo for tilt. The camera, 1.1 kg, sits on an aluminum arm 250 mm from the tilt axis, and
 the arm weighs 100 g spread evenly. At full tilt the arm is horizontal. Our rule is a margin of 2 on the servo's rating. Will it hold the camera level?"""),
dict(slug="wrist-servo-9kgcm", model=M, title="9.4 kg·cm servo at a gripper wrist", trap=SU,
 inputs=arm(9.4, 120, 0.05, 0.55, 2.0),
 prompt="""Robotics club question: the wrist joint of our arm uses an MG996R, rated 9.4 kg·cm stall at 4.8 V (that's our supply). From the wrist axis to the
 gripper is 120 mm; the link is 50 g, spread evenly, and the gripper holding a can is 550 g at the end. We want a margin of 2. Will the wrist hold horizontal?"""),
dict(slug="ds5160-shoulder-60kgcm", model=M, title="60 kg·cm servo on a large arm shoulder", trap=SU,
 inputs=arm(60, 300, 0.35, 1.3, 2.0),
 prompt="""We're building a larger hobby arm with a DS5160 servo at the shoulder (60 kg·cm stall at 8.4 V). The upper arm plus everything beyond it acts like a
 300 mm arm weighing 350 g spread evenly, with 1.3 kg concentrated at the end (elbow motor, forearm, gripper and payload lumped together). We design for a
 margin of 2. Can it hold the arm out horizontally?"""),
dict(slug="ds3225-boom-25kgcm", model=M, title="25 kg·cm servo lifting a sensor boom", trap=SU,
 inputs=arm(25, 220, 0.12, 0.75, 2.0),
 prompt="""Our crop-scanning robot raises a sensor boom with a DS3225 servo (25 kg·cm at 6.8 V, stall). The boom is 220 mm from the servo shaft to the sensor,
 weighs 120 g spread evenly, and the sensor head is 750 g at the tip. The boom has to be held horizontal while scanning, with a margin of 2. Will it work?"""),
dict(slug="nm-rated-servo-lb-in", model=M, title="Servo rated in N·m with a payload given in pounds and inches",
 trap="[torque_units] The rating is 1.8 N·m = {stall:.1f} kg·cm (not 18 or 180 kg·cm); need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5", mm=["unit_conversion"],
 inputs=arm(round(1.8 / 0.0981, 2), round(9 * IN, 1), 0.1, round(1.6 * LB, 3), 1.5),
 prompt="""I bought a servo listed at 1.8 N·m stall torque for the shoulder of a camera slider's pan arm. The arm is 9 in from the servo axis to the end, weighs
 0.1 kg spread evenly, and the camera hanging at the end is 1.6 lb. I want a margin of 1.5. Will it hold the arm horizontal?"""),
dict(slug="oz-in-rated-arm", model=M, title="400 oz·in servo with a 12 in arm",
 trap="[torque_units] 400 oz·in = {stall:.1f} kg·cm = {stall_nm:.2f} N·m; need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5", mm=["unit_conversion"],
 inputs=arm(round(400 * OZIN, 2), round(12 * IN, 1), round(0.25 * LB, 3), round(2.0 * LB, 3), 1.5),
 prompt="""Our test rig flips a part on a 12 in long arm driven by a servo rated 400 oz-in of stall torque. The arm weighs 0.25 lb spread evenly and the part plus
 fixture at the end weigh 2.0 lb. It has to hold the arm horizontal with a margin of 1.5. Is the servo big enough?"""),
dict(slug="n-cm-rated-servo", model=M, title="Servo rated in N·cm on a 180 mm arm",
 trap="[torque_units] 245 N·cm is {stall:.1f} kg·cm (divide by 9.81), not 245 kg·cm; need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5", mm=["unit_conversion"],
 inputs=arm(round(245 / 9.81, 2), 180, 0.12, 1.2, 1.5),
 prompt="""A European catalogue lists our servo's stall torque as 245 N·cm. It drives a 180 mm arm (120 g, spread evenly) on a lab sample changer, with a 1.2 kg
 sample holder at the end. We require a margin of 1.5 when the arm is horizontal. Will it hold?"""),
dict(slug="shaft-behind-bracket", model=M, title="Arm length measured from the bracket face instead of the servo shaft",
 trap="[lever_arm] The servo shaft is 80 mm behind the bracket face, so the lever is {inp[arm_length_mm]:g} mm, not 170 mm: need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5",
 inputs=arm(20, 250, 0.1, 0.7, 1.5),
 prompt="""We're lifting a 0.7 kg inspection camera on a robot arm driven by a 20 kg·cm (stall) servo. Measured from the front face of the servo bracket, the arm
 sticks out 170 mm to the camera, but the servo's output shaft sits 80 mm back inside the bracket, so the arm actually starts at the shaft. The arm weighs 100 g,
 spread evenly from the shaft to the camera. We want a margin of 1.5 holding it horizontal. Is the servo enough?"""),
dict(slug="payload-cg-beyond-wrist", model=M, title="Payload centre of mass beyond the end of the arm",
 trap="[lever_arm] The bottle's centre of mass is 100 mm beyond the 150 mm arm, so the lever is {inp[arm_length_mm]:g} mm: need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5",
 inputs=arm(15, 250, 0, 0.55, 1.5),
 prompt="""Our drink-serving robot has a light carbon-fibre arm (treat its weight as negligible) that reaches 150 mm from a 15 kg·cm (stall) servo to the gripper
 mount. The gripper holds a 0.55 kg bottle, and with the gripper's long fingers the bottle's centre of mass ends up 100 mm beyond the gripper mount. The arm must
 hold the bottle out horizontally with a margin of 1.5. Will the servo manage?"""),
# ---- controls
dict(slug="35kgcm-light-arm-control", model=M, title="35 kg·cm servo with a light arm (control)", control=True,
 trap="[control] none, genuinely holds: need {tk:.2f} kg·cm, margin {m:.2f} vs {req:g}", inputs=arm(35, 150, 0.1, 0.6, 2.0),
 prompt="""A 35 kg·cm (stall) servo drives a 150 mm arm weighing 100 g, spread evenly, with a 0.6 kg gripper and part at the end. We need a margin of 2 holding it
 horizontal. Will it hold?"""),
dict(slug="2nm-servo-short-arm-control", model=M, title="2.0 N·m servo with a 4 in arm (control)", control=True,
 trap="[control] none, genuinely holds: 2.0 N·m = {stall:.1f} kg·cm, need {tk:.2f} kg·cm, margin {m:.2f}", inputs=arm(round(2.0 / 0.0981, 2), round(4 * IN, 1), 0.05, 0.5, 2.0),
 prompt="""A servo rated 2.0 N·m (stall) tilts a 4 in arm on a sorting machine. The arm weighs 50 g spread evenly and the paddle at its end is 0.5 kg. We need a margin
 of 2 with the arm horizontal. Is the servo OK?"""),
dict(slug="60kgcm-shoulder-control", model=M, title="60 kg·cm shoulder servo with margin to spare (control)", control=True,
 trap="[control] none, genuinely holds: need {tk:.1f} kg·cm, margin {m:.2f} vs 1.5", inputs=arm(60, 300, 0.3, 0.8, 1.5),
 prompt="""Our arm's shoulder uses a 60 kg·cm (stall) servo. The arm reaches 300 mm, weighs 300 g spread evenly, and carries 0.8 kg at the end. We want a margin
 of 1.5 when the arm is straight out. Will it hold?"""),
dict(slug="13kgcm-pan-arm-control", model=M, title="13 kg·cm servo on a short sensor arm (control)", control=True,
 trap="[control] none, genuinely holds: need {tk:.2f} kg·cm, margin {m:.2f} vs 2", inputs=arm(13, 100, 0.03, 0.25, 2.0),
 prompt="""A 13 kg·cm (stall) servo swings a 100 mm arm (30 g, spread evenly) holding a 250 g distance sensor at its end on our rover. We want a margin of 2 with
 the arm horizontal. Good enough?"""),
dict(slug="oz-in-light-paddle-control", model=M, title="400 oz·in servo with a light paddle (control)", control=True,
 trap="[control] none, genuinely holds: 400 oz·in = {stall:.1f} kg·cm, need {tk:.2f} kg·cm, margin {m:.2f}", inputs=arm(round(400 * OZIN, 2), round(8 * IN, 1), round(0.15 * LB, 3), round(0.75 * LB, 3), 2.0),
 prompt="""We use a 400 oz-in (stall) servo to swing an 8 in diverter arm on a parcel line. The arm weighs 0.15 lb spread evenly and the paddle at the end is 0.75 lb.
 We size for a margin of 2 with the arm horizontal. Is the servo fine?"""),
]
