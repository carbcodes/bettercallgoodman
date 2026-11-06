from build123d import *
part = Box(100, 20, 6, align=(Align.MIN, Align.CENTER, Align.CENTER))
export_step(part, "part.step")
