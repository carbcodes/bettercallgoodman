# PLA L-bracket, vertical leg on the wall, arm 150 mm long, 20 wide, 6 thick, sharp inside corner
from build123d import *
leg = Box(6, 20, 80, align=(Align.MIN, Align.CENTER, Align.MIN))
arm = Pos(0, 0, 74) * Box(155, 20, 6, align=(Align.MIN, Align.CENTER, Align.MIN))
export_step(leg + arm, "part.step")
