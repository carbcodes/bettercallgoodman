"""Strength of a real part, measured from its STEP file.

Frame (fixed by every design prompt): the wall / mounting face is x = 0, the part extends
in +x, z is up, the load F acts straight down at the load point (x_L, z_L).

Beam model on the measured geometry:
  * arm sections: cut the solid with planes x = const between the wall and the load point.
    Each cut gives area, centroid, I about the horizontal axis and the outer-fibre distance c.
    M(x) = F (x_L - x), sigma = M c / I, stress along x.
  * wall-leg sections: cut with planes z = const through the part of the solid that hugs the
    wall (a back plate or the vertical leg of an L), near where the arm joins it.
    M = F (x_L - x_centroid), sigma = M c / I + F / A, stress along z.
  * stress concentration: where an arm section is much shallower than the section just
    towards the wall (a junction), Kt comes from the Peterson shoulder-fillet fit with the
    measured depths and the fillet radius found there (a sharp corner counts as r = 0.25 mm).
  * printed parts: stress that pulls the print layers apart uses the across-layer strength.
APPROXIMATIONS: beam theory, no FEA; screws and the wall are rigid; self-weight ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from build123d import Face, GeomType, Plane, Vector, Vertex, import_step
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from ..checkers.strength import kt_shoulder_bending, load_materials

G = 9.81
SHARP_R = 0.25  # mm, effective radius of an "unfilleted" printed or milled inside corner
AXES = {"x": 0, "y": 1, "z": 2}


@dataclass
class Section:
    kind: str           # "arm" (x = const) or "leg" (z = const)
    at: float           # x or z of the cut, mm
    area: float
    centroid: tuple
    I: float            # mm^4 about the bending axis through the centroid
    c: float            # mm, outer fibre distance
    depth: float        # mm, section extent in the bending direction
    M: float = 0.0
    sigma_nom: float = 0.0
    kt: float = 1.0
    kt_note: str = ""
    sigma: float = 0.0
    strength: float = 0.0
    sf: float = 0.0
    point: tuple = ()


@dataclass
class DesignResult:
    verdict: str
    sf: float
    critical: Section | None
    load_point: tuple
    lever_mm: float
    bbox: tuple
    volume: float
    solids: int
    notes: list = field(default_factory=list)
    sections: list = field(default_factory=list)


def _section_props(faces) -> tuple[float, tuple, list]:
    props = GProp_GProps()
    for f in faces:
        BRepGProp.SurfaceProperties_s(f.wrapped, props)
    c = props.CentreOfMass()
    return props.Mass(), (c.X(), c.Y(), c.Z()), props


def _cut(solid, plane: Plane, size: float):
    big = Face.make_rect(size, size, plane)
    try:
        res = solid.intersect(big)
    except Exception:
        return []
    if not res:
        return []
    return [f for f in res.faces()] if hasattr(res, "faces") else []


def _second_moment(faces, centroid, axis_dir: int) -> float:
    """I = integral of (coord - centroid)^2 dA along axis_dir, by sampling each face's own props."""
    total = 0.0
    for f in faces:
        p = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f.wrapped, p)
        cf = p.CentreOfMass()
        m = p.MatrixOfInertia()
        a = p.Mass()
        d = (cf.X(), cf.Y(), cf.Z())[axis_dir] - centroid[axis_dir]
        # own second moment along axis_dir: I_own = sum of the other two diagonal terms minus... use
        # integral of u^2 = (I_vv + I_ww - I_uu)/2 for the in-face axes (planar face, third coordinate constant)
        ii = [m.Value(1, 1), m.Value(2, 2), m.Value(3, 3)]
        u = axis_dir
        v, w = [k for k in range(3) if k != u]
        own = (ii[v] + ii[w] - ii[u]) / 2
        total += own + a * d * d
    return total


def _extent(faces, axis_dir: int) -> tuple[float, float]:
    lo, hi = math.inf, -math.inf
    for f in faces:
        bb = f.bounding_box()
        lo = min(lo, (bb.min.X, bb.min.Y, bb.min.Z)[axis_dir])
        hi = max(hi, (bb.max.X, bb.max.Y, bb.max.Z)[axis_dir])
    return lo, hi


def _make_section(kind, at, faces) -> Section | None:
    if not faces:
        return None
    area, cen, _ = _section_props(faces)
    if area < 1e-3:
        return None
    bend = AXES["z"] if kind == "arm" else AXES["x"]
    I = _second_moment(faces, cen, bend)
    lo, hi = _extent(faces, bend)
    c = max(hi - cen[bend], cen[bend] - lo)
    return Section(kind, at, area, cen, I, c, hi - lo)


def find_load_point(solid, rule: str, inputs: dict) -> tuple[tuple, str]:
    bb = solid.bounding_box()
    if rule == "lowest_inside":
        # the strap rests on the lowest upward-facing surface away from the back plate
        best = None
        for f in solid.faces():
            for u in (0.1, 0.3, 0.5, 0.7, 0.9):
                for v in (0.1, 0.3, 0.5, 0.7, 0.9):
                    try:
                        p = f.position_at(u, v)
                        n = f.normal_at(p)
                    except Exception:
                        continue
                    if n.Z > 0.7 and p.X > bb.min.X + 0.3 * (bb.max.X - bb.min.X):
                        if best is None or p.Z < best.Z - 1e-6:
                            best = p
        if best is not None:
            return (best.X, best.Y, best.Z), "lowest upward-facing surface away from the wall (where the strap rests)"
        return (bb.max.X, 0.0, bb.max.Z), "no upward-facing hook surface found; load at the farthest point (conservative)"
    if rule == "fixed_x":
        x = float(inputs["load_x_mm"])
        note = f"load centre at x = {x:g} mm, as specified"
        if x > bb.max.X + 0.5:
            note += f" (the part only reaches x = {bb.max.X:.1f} mm)"
        return (x, 0.0, bb.max.Z), note
    return (bb.max.X, 0.0, bb.max.Z), "load at the farthest point from the wall"


def _strength(mat: dict, stress_axis: str, layer_normal: str | None) -> tuple[float, str]:
    if mat.get("printed"):
        if layer_normal == stress_axis:
            return mat["across_layer_strength_mpa"], "across layers"
        return mat["in_layer_strength_mpa"], "along layers"
    return mat["yield_mpa"], "yield"


def _nearest_fillet_radius(solid, point: tuple, within: float) -> float | None:
    v = Vertex(*point)
    best = None
    for f in solid.faces():
        if f.geom_type in (GeomType.CYLINDER,):
            try:
                d = v.distance_to(f)
            except Exception:
                continue
            if d <= within:
                r = BRepAdaptor_Surface(f.wrapped).Cylinder().Radius()
                if r < 30 and (best is None or d < best[0]):
                    best = (d, r)
    return best[1] if best else None


def analyze(step_path, inputs: dict) -> DesignResult:
    shape = import_step(str(step_path))
    solids = shape.solids()
    notes = []
    if not solids:
        return DesignResult("not_safe", 0.0, None, (), 0.0, (), 0.0, 0, ["the STEP file has no solid"])
    solid = solids[0] if len(solids) == 1 else shape
    if len(solids) > 1:
        notes.append(f"{len(solids)} separate solids; checked them together")
    bb = solid.bounding_box()
    if abs(bb.min.X) > 1.0:
        notes.append(f"the part's wall side is at x = {bb.min.X:.1f} mm, not 0; measured from x = {bb.min.X:.1f}")
    x0 = bb.min.X
    mats = load_materials()
    mat = dict(mats[inputs["material"]])
    for k in ("yield_mpa", "in_layer_strength_mpa", "across_layer_strength_mpa"):
        if k in inputs:
            mat[k] = inputs[k]
    layer_normal = inputs.get("layer_normal")  # "x" | "y" | "z" | None
    F = float(inputs["load_n"])
    req = float(inputs["required_safety_factor"])
    lp, lp_note = find_load_point(solid, inputs.get("load_rule", "farthest"), inputs)
    notes.append(lp_note)
    xL = lp[0]
    L = xL - x0
    size = 4 * max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z) + 50
    secs: list[Section] = []

    # arm sections, wall -> load point
    xs = [x0 + 0.3] + [x0 + L * i / 80 for i in range(1, 80)]
    for x in xs:
        sec = _make_section("arm", x, _cut(solid, Plane.YZ.offset(x), size))
        if sec is None:
            continue
        sec.M = F * (xL - x)
        sec.sigma_nom = sec.M * sec.c / sec.I if sec.I > 0 else math.inf
        secs.append(sec)
    # junction: where the deep part at the wall (leg / back plate) turns into the arm proper.
    # The arm starts at the first cut no deeper than 1.1x the shallowest cut beyond it.
    for i, sec in enumerate(secs):
        rest = [t.depth for t in secs[i:]]
        if sec.depth <= 1.1 * min(rest) and i > 0 and max(t.depth for t in secs[:i]) > 1.25 * sec.depth:
            D = min(max(t.depth for t in secs[:i]), 3 * sec.depth)
            y = sec.centroid[1]
            probes = [(sec.at - 0.5 * sec.depth, y, sec.centroid[2] + sgn * sec.c) for sgn in (1, -1)]
            radii = [r for r in (_nearest_fillet_radius(solid, p, within=1.5 * sec.depth) for p in probes) if r]
            r = max(radii) if radii else None
            kt = kt_shoulder_bending(D, sec.depth, r or SHARP_R)
            note = f"junction ({D:.1f} -> {sec.depth:.1f} mm deep), " + (f"{r:.1f} mm fillet" if r else "sharp inside corner")
            for t in secs[i:]:
                if t.at - sec.at > sec.depth:
                    break
                t.kt, t.kt_note = kt, note
            break

    # wall-leg sections, only where the solid hugs the wall, near the arm's height
    arm_ref = next((s for s in secs if s.at > x0 + 0.5 * L), None)
    if arm_ref is not None:
        za0, za1 = arm_ref.centroid[2] - arm_ref.depth / 2, arm_ref.centroid[2] + arm_ref.depth / 2
        span = max(3 * arm_ref.depth, 8.0)
        for i in range(41):
            z = (za0 - span) + (za1 - za0 + 2 * span) * i / 40
            if za0 - 0.2 <= z <= za1 + 0.2:
                continue  # inside the arm itself: that's an arm cut, not a leg cut
            faces = _cut(solid, Plane.XY.offset(z), size)
            if not faces or _extent(faces, 0)[1] > x0 + 0.35 * L:
                continue
            s = _make_section("leg", z, faces)
            if s is None:
                continue
            s.M = F * (xL - s.centroid[0])
            s.sigma_nom = (s.M * s.c / s.I if s.I > 0 else math.inf) + F / s.area
            near = min(abs(z - za0), abs(z - za1))
            if near < max(2.0, arm_ref.depth):
                pt = (x0 + s.depth, s.centroid[1], za1 if z > za1 else za0)
                r = _nearest_fillet_radius(solid, pt, within=max(1.5, 0.6 * arm_ref.depth))
                s.kt = kt_shoulder_bending(2 * s.depth, s.depth, r or SHARP_R)
                s.kt_note = "inside corner where the arm meets the wall leg, " + \
                    (f"{r:.1f} mm fillet" if r else "sharp")
            secs.append(s)

    for s in secs:
        axis = "x" if s.kind == "arm" else "z"
        s.strength, how = _strength(mat, axis, layer_normal)
        s.sigma = s.sigma_nom * s.kt
        s.sf = s.strength / s.sigma if s.sigma > 0 else math.inf
        s.kt_note = (s.kt_note + "; " if s.kt_note else "") + f"stress along {axis}, {how}"
    if not secs:
        return DesignResult("not_safe", 0.0, None, lp, L, _bb(bb), solid.volume, len(solids),
                            notes + ["no material between the wall and the load point"])
    crit = min(secs, key=lambda s: s.sf)
    verdict = "safe" if crit.sf >= req else "not_safe"
    return DesignResult(verdict, crit.sf, crit, lp, L, _bb(bb), solid.volume, len(solids), notes, secs)


def _bb(bb) -> tuple:
    return (round(bb.min.X, 2), round(bb.min.Y, 2), round(bb.min.Z, 2), round(bb.max.X, 2), round(bb.max.Y, 2), round(bb.max.Z, 2))


def describe(sec: Section) -> str:
    where = f"x = {sec.at:.1f} mm" if sec.kind == "arm" else f"z = {sec.at:.1f} mm (wall leg)"
    kt = f" x Kt {sec.kt:.2f}" if sec.kt > 1.001 else ""
    return (f"{where}: {sec.area:.0f} mm² section, {sec.depth:.1f} mm deep, M = {sec.M:.0f} N·mm, "
            f"sigma = {sec.sigma_nom:.1f}{kt} = {sec.sigma:.1f} MPa vs {sec.strength:.0f} MPa -> SF {sec.sf:.2f}")
