# Same bracket, 12 mm thick, with a 6 mm inside fillet
from build123d import *
leg = Box(12, 20, 80, align=(Align.MIN, Align.CENTER, Align.MIN))
arm = Pos(0, 0, 68) * Box(155, 20, 12, align=(Align.MIN, Align.CENTER, Align.MIN))
part = leg + arm
inner = part.edges().filter_by(Axis.Y).filter_by_position(Axis.X, 11.9, 12.1).filter_by_position(Axis.Z, 67.9, 68.1)
part = fillet(inner, radius=6)
export_step(part, "part.step")
