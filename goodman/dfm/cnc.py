"""3-axis CNC millability of a STEP solid (spec 06). Thresholds: goodman/rules/cnc_3axis.yaml.

check_cnc(step_path, setups=[(0, 0, 1)], material="Al6061-T6") -> dict

Each setup is the direction the spindle points away from the part (the tool comes in
along -setup). Stock is the part's axis-aligned bounding box: planar faces lying on that
box need no machining.
"""

from __future__ import annotations

import math

import numpy as np

from .geom import (all_vertices, cylinder_groups, edge_concavity, edge_direction, edge_is_line,
                   edge_points, face_samples, fmt_pt, load_part, load_rules, min_wall, parallel,
                   perpendicular, rule_value, unit)
from .report import finding, result

AXES = [np.array(v, float) for v in [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]]
SHARP_DEG = 5.0


def dir_name(d) -> str:
    for v, n in zip(AXES, ["+Z", "-Z", "+X", "-X", "+Y", "-Y"]):
        if parallel(v, d, 0.01) and v @ d > 0:
            return n
    return "(" + ", ".join(f"{x:.2f}" for x in d) + ")"


def _stock_faces(part) -> set[int]:
    out = set()
    for f in part.faces:
        if f.kind != "plane" or f.plane_n is None or not len(f.verts):
            continue
        for k in range(3):
            if abs(abs(f.plane_n[k]) - 1) > 1e-6:
                continue
            plane = part.bbox_max[k] if f.plane_n[k] > 0 else part.bbox_min[k]
            if np.all(np.abs(f.verts[:, k] - plane) < 1e-3):
                out.add(f.idx)
    return out


class _Reach:
    def __init__(self, part, rules):
        self.part = part
        self.sin_tol = math.sin(math.radians(rule_value(rules, "undercut_normal_tol_deg")))
        self.frac = rule_value(rules, "reach_fraction_min")
        self.samples = {}
        self.cache = {}

    def _pts(self, f):
        if f.idx not in self.samples:
            p, n = face_samples(f.face, spacing=2.0, max_n=8)
            if not len(p) and len(f.tri_pts):
                p, n = f.tri_pts.mean(1), f.tri_n
            self.samples[f.idx] = (p, n)
        return self.samples[f.idx]

    def reachable(self, f, d) -> bool:
        key = (f.idx, tuple(np.round(d, 6)))
        if key not in self.cache:
            p, n = self._pts(f)
            ok = 0
            for q, nv in zip(p, n):
                if nv @ d < -self.sin_tol:
                    continue
                if not self.part.ray_hits(q + 0.01 * nv, d, tmin=1e-4):
                    ok += 1
            self.cache[key] = bool(len(p)) and ok >= self.frac * len(p)
        return self.cache[key]

    def centre(self, f):
        p, _ = self._pts(f)
        return p.mean(0) if len(p) else f.verts.mean(0)


def _wall_limit(rules, material):
    r = rules["rules"]["min_wall_mm"]
    if material in r["by_material"]:
        return r["by_material"][material]
    try:
        import yaml
        from pathlib import Path
        mats = yaml.safe_load((Path(__file__).resolve().parent.parent / "materials.yaml").read_text())
        if mats.get(material, {}).get("printed"):
            return r["by_material"]["plastic"]
    except Exception:
        pass
    return r["default"]


def check_cnc(step_path, setups=((0, 0, 1),), material="Al6061-T6") -> dict:
    rules = load_rules("cnc_3axis.yaml")
    setups = [unit(s) for s in setups]
    if not setups:
        raise ValueError("at least one setup direction is needed")
    part = load_part(step_path)
    verts = all_vertices(part)
    F = []
    setup_names = ", ".join(dir_name(d) for d in setups)

    min_tool = rule_value(rules, "min_tool_diameter_mm")
    ratio_r = rule_value(rules, "inside_corner_radius_vs_tool")
    lim_pocket = rule_value(rules, "pocket_depth_to_tool_max")
    lim_hole = rule_value(rules, "hole_depth_to_diameter_max")

    # ---- sharp vertical inside edges
    sharp = []
    for e, a, b in part.edge_faces:
        if not edge_is_line(e):
            continue
        concave, dihedral = edge_concavity(part, e, a, b)
        if not concave or dihedral < SHARP_DEG:
            continue
        de = edge_direction(e)
        mid = edge_points(e, 3)[1]
        na = part.faces[a].plane_n if part.faces[a].plane_n is not None else None
        nb = part.faces[b].plane_n if part.faces[b].plane_n is not None else None

        def floor_wall(d):
            if na is None or nb is None or not perpendicular(de, d):
                return False
            return ((parallel(na, d) and na @ d > 0 and perpendicular(nb, d)) or
                    (parallel(nb, d) and nb @ d > 0 and perpendicular(na, d)))

        if any(floor_wall(d) for d in setups):
            continue
        along = [d for d in setups if parallel(de, d)]
        if along:
            L = float(np.ptp(edge_points(e, 2) @ along[0]))
            sharp.append((mid, L))
    if sharp:
        mid, L = sharp[0]
        F.append(finding("sharp_inside_corner", 0.0, min_tool / 2, mid,
                         f"{len(sharp)} sharp vertical inside corner{'s' if len(sharp) > 1 else ''} "
                         f"(first at {fmt_pt(mid)}, {L:.0f} mm tall); an end mill always leaves its own "
                         f"radius, so a square inside corner can't be milled.", "fail", count=len(sharp)))

    # ---- inside corner radii and pocket depth vs tool
    top = {tuple(d): float((verts @ d).max()) for d in setups}
    corners = []
    for g in cylinder_groups(part, concave=True):
        if g["is_hole"]:
            continue
        d = next((s for s in setups if parallel(g["axis_d"], s)), None)
        if d is None:
            continue
        r = g["radius"]
        ts = [g["axis_p"] @ d + g["t_min"] * (g["axis_d"] @ d), g["axis_p"] @ d + g["t_max"] * (g["axis_d"] @ d)]
        depth = top[tuple(d)] - min(ts)
        tool = 2 * r / ratio_r
        corners.append({"r": r, "depth": depth, "tool": tool, "ratio": depth / tool, "loc": g["center"]})
    small = [c for c in corners if c["tool"] < min_tool]
    if small:
        c = min(small, key=lambda c: c["r"])
        F.append(finding("inside_corner_radius", c["r"], min_tool / 2, c["loc"],
                         f"Inside corner radius R{c['r']:g} mm at {fmt_pt(c['loc'])} needs a "
                         f"Ø{c['tool']:.2g} mm end mill, below the smallest practical tool (Ø{min_tool:g} mm).",
                         "fail", count=len(small)))
    deep = [c for c in corners if c["ratio"] > lim_pocket and c["tool"] >= min_tool]
    if deep:
        c = max(deep, key=lambda c: c["ratio"])
        F.append(finding("pocket_depth_vs_tool", c["ratio"], lim_pocket, c["loc"],
                         f"Inside corner R{c['r']:g} at {fmt_pt(c['loc'])} is {c['depth']:.0f} mm deep: the "
                         f"largest tool that fits is Ø{c['tool']:g} mm, so the cut is {c['ratio']:.1f}× tool "
                         f"diameter; limit {lim_pocket:g}×.", "fail", count=len(deep)))
    if corners and not small and not deep:
        c = min(corners, key=lambda c: c["r"])
        w = max(corners, key=lambda c: c["ratio"])
        F.append(finding("pocket_depth_vs_tool", w["ratio"], lim_pocket, c["loc"],
                         f"Smallest inside corner R{c['r']:g} allows a Ø{c['tool']:g} mm end mill; deepest "
                         f"corner cut is {w['ratio']:.1f}× tool diameter (limit {lim_pocket:g}×).", "info"))

    # ---- holes: depth / diameter
    holes = [g for g in cylinder_groups(part, concave=True) if g["is_hole"]]
    worst = None
    for g in holes:
        d = 2 * g["radius"]
        ratio = g["length"] / d
        if ratio > lim_hole:
            F.append(finding("hole_depth", ratio, lim_hole, g["top"],
                             f"Ø{d:g} mm hole at {fmt_pt(g['top'])} is {g['length']:.0f} mm deep "
                             f"({ratio:.1f}× diameter); drilled holes past {lim_hole:g}× diameter wander and "
                             f"pack chips.", "fail"))
        elif worst is None or ratio > worst[0]:
            worst = (ratio, g, d)
    if worst and not any(f["rule"] == "hole_depth" for f in F):
        ratio, g, d = worst
        F.append(finding("hole_depth", ratio, lim_hole, g["top"],
                         f"{len(holes)} hole{'s' if len(holes) > 1 else ''}; deepest relative to size is "
                         f"Ø{d:g} mm × {g['length']:.0f} mm ({ratio:.1f}× diameter, limit {lim_hole:g}×).", "info"))

    # ---- undercuts and number of setups
    stock = _stock_faces(part)
    reach = _Reach(part, rules)
    machined = [f for f in part.faces if f.idx not in stock]
    hidden = [f for f in machined if not any(reach.reachable(f, d) for d in setups)]
    if hidden:
        big = max(hidden, key=lambda f: f.area)
        area = sum(f.area for f in hidden)
        loc = reach.centre(big)
        F.append(finding("undercut", area, 0.0, loc,
                         f"{len(hidden)} face{'s' if len(hidden) > 1 else ''} ({area:.0f} mm², largest at "
                         f"{fmt_pt(loc)}) can't be seen by the tool from the listed setup{'s' if len(setups) > 1 else ''} "
                         f"({setup_names}): an undercut for 3-axis milling.", "fail", count=len(hidden)))

    cands = list(setups) + [a for a in AXES if not any(parallel(a, s, 0.01) and a @ s > 0 for s in setups)]
    R = {f.idx: {i for i, d in enumerate(cands) if reach.reachable(f, d)} for f in machined}
    never = [f for f in machined if not R[f.idx]]
    todo = {i for i, s in R.items() if s}
    chosen = []
    while todo:
        best = max(range(len(cands)), key=lambda i: (sum(1 for f in todo if i in R[f]), -i))
        chosen.append(best)
        todo -= {f for f in todo if best in R[f]}
    names = ", ".join(dir_name(cands[i]) for i in chosen) or "none"
    if never:
        big = max(never, key=lambda f: f.area)
        loc = reach.centre(big)
        F.append(finding("setups", len(chosen), len(setups), loc,
                         f"{len(never)} face{'s' if len(never) > 1 else ''} (largest at {fmt_pt(loc)}) can't be "
                         f"reached from any of the six axis directions; it needs a 4/5-axis machine or a special "
                         f"cutter (T-slot, dovetail).", "fail", directions=names))
    F.append(finding("setups", len(chosen), len(setups), (part.bbox_min + part.bbox_max) / 2,
                     f"Reaching every machined face takes {len(chosen)} setup{'s' if len(chosen) != 1 else ''} "
                     f"({names}); {len(setups)} listed ({setup_names}).", "info", directions=names))

    # ---- thin walls
    lim_wall = _wall_limit(rules, material)
    t, tloc, nrays, _ = min_wall(part)
    if t is not None:
        if t < lim_wall:
            F.append(finding("thin_wall", t, lim_wall, tloc,
                             f"Wall only {t:.2f} mm thick at {fmt_pt(tloc)}; {material} walls under "
                             f"{lim_wall:g} mm chatter and deflect under the cutter.", "fail"))
        else:
            F.append(finding("thin_wall", t, lim_wall, tloc,
                             f"Thinnest wall is {t:.2f} mm at {fmt_pt(tloc)}, above the {lim_wall:g} mm minimum "
                             f"for {material}.", "info"))

    return result("cnc", "machinable", "not_machinable", F,
                  file=str(step_path), setups=[[float(x) for x in d] for d in setups], material=material,
                  summary={"setups_needed": len(chosen), "setup_directions": names,
                           "min_wall_mm": None if t is None else round(t, 3),
                           "min_inside_radius_mm": round(min(c["r"] for c in corners), 3) if corners else None,
                           "sharp_inside_corners": len(sharp), "holes": len(holes),
                           "undercut_faces": len(hidden)})
