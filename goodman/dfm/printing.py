"""FDM printability of a STEP solid (spec 05). Thresholds: goodman/rules/fdm.yaml.

check_printing(step_path, build_dir=(0, 0, 1), printer=None) -> dict

build_dir is the up direction on the print bed, in the STEP file's coordinates. The
part is assumed to sit on its lowest point along build_dir.
"""

from __future__ import annotations

import math

import numpy as np

from .geom import (all_vertices, cylinder_groups, edge_concavity, edge_length, edge_points,
                   face_samples, fmt_pt, frame_from_up, load_part, load_rules, min_wall,
                   parallel, perpendicular, rule_value, unit)
from .report import finding, result

HORIZONTAL_COS = math.cos(math.radians(1.0))
BED_TOL = 0.01


def _overhang_deg(n, up):
    """Angle from vertical of a down-facing surface (0 = vertical wall, 90 = flat ceiling)."""
    return np.degrees(np.arcsin(np.clip(-(n @ up), -1, 1)))


def _bed(part, up, h0):
    faces = []
    for f in part.faces:
        if f.kind != "plane" or f.plane_n is None or f.plane_n @ up > -HORIZONTAL_COS:
            continue
        if len(f.verts) and np.all(np.abs(f.verts @ up - h0) < BED_TOL):
            faces.append(f)
    return faces


def _bridge(part, f, up, rules):
    """Classify a flat, down-facing face above the bed: bridge (span) or cantilever/floating."""
    sup = []
    for e, a, b in part.edge_faces:
        if f.idx not in (a, b):
            continue
        concave, dihedral = edge_concavity(part, e, a, b)
        if concave and dihedral > 1.0:
            sup.append(edge_points(e, max(2, int(edge_length(e) / 0.25) + 1)))
    pts, _ = face_samples(f.face, spacing=0.5, max_n=120)
    if len(f.tri_pts):
        pts = np.vstack([pts, f.tri_pts.mean(1)])
    if not len(pts):
        return None
    if not sup:
        return {"kind": "floating", "length": None, "loc": pts.mean(0)}
    S = np.vstack(sup)
    D = np.linalg.norm(pts[:, None, :] - S[None], axis=2)
    d1 = D.min(1)
    k = int(np.argmax(d1))
    x, s1 = pts[k], S[np.argmin(D[k])]
    if d1[k] < 1e-6:
        return {"kind": "bridge", "length": 0.0, "loc": x}
    u = (s1 - x) / d1[k]
    rel = S - x
    dist = np.linalg.norm(rel, axis=1)
    opposite = (rel @ u) < -0.5 * dist
    if not np.any(opposite):
        return {"kind": "cantilever", "length": float(d1[k]), "loc": x}
    return {"kind": "bridge", "length": float(d1[k] + dist[opposite].min()), "loc": x}


def _fits(verts, e1, e2, e3, vol):
    X, Y, Z = vol
    ez = np.ptp(verts @ e3)
    best = None
    for a in np.radians(np.arange(0, 180, 2.5)):
        ax = math.cos(a) * e1 + math.sin(a) * e2
        ay = -math.sin(a) * e1 + math.cos(a) * e2
        ex, ey = np.ptp(verts @ ax), np.ptp(verts @ ay)
        if best is None or ex * ey < best[0] * best[1]:
            best = (ex, ey)
        if ez <= Z and ex <= X and ey <= Y:
            return True, (ex, ey, ez)
    return False, (best[0], best[1], ez)


def check_printing(step_path, build_dir=(0, 0, 1), printer=None) -> dict:
    rules = load_rules("fdm.yaml")
    up = unit(build_dir)
    part = load_part(step_path)
    verts = all_vertices(part)
    h = verts @ up
    h0 = float(h.min())
    F = []

    lim_oh = rule_value(rules, "overhang_max_deg")
    min_area = rule_value(rules, "overhang_min_area_mm2")
    lim_bridge = rule_value(rules, "bridge_max_mm")
    near_bed = rule_value(rules, "overhang_near_bed_mm")
    lo_us, hi_us = rule_value(rules, "hole_undersize_mm")

    # ---- bed contact
    bed = _bed(part, up, h0)
    bed_ids = {f.idx for f in bed}
    bed_area = sum(f.area for f in bed)
    bed_min = rule_value(rules, "bed_min_contact_mm2")
    if bed:
        loc = sum(f.tri_pts.mean(1).T @ f.tri_a for f in bed) / sum(f.tri_a.sum() for f in bed)
    else:
        loc = verts[np.argmin(h)]
    if bed_area < bed_min:
        F.append(finding("bed_contact", bed_area, bed_min, loc,
                         f"Only {bed_area:.1f} mm² of flat face on the bed plane at {fmt_pt(loc)}; "
                         f"FDM needs a flat face on the bed in this orientation.", "fail"))
    else:
        F.append(finding("bed_contact", bed_area, bed_min, loc,
                         f"{bed_area:.0f} mm² of flat face sits on the bed plane around {fmt_pt(loc)}.", "info"))

    # ---- horizontal holes: their tops are short bridges if small enough
    hole_groups = cylinder_groups(part, concave=True)
    horiz_small_hole_faces = set()
    for g in hole_groups:
        if g["is_hole"] and perpendicular(g["axis_d"], up) and 2 * g["radius"] <= lim_bridge:
            horiz_small_hole_faces.update(g["faces"])

    # ---- overhangs and bridges
    bridges = []
    for f in part.faces:
        if f.idx in bed_ids or not len(f.tri_n):
            continue
        if f.kind == "plane" and f.plane_n is not None and f.plane_n @ up <= -HORIZONTAL_COS:
            b = _bridge(part, f, up, rules)
            if b is None:
                continue
            if b["kind"] == "bridge":
                bridges.append(b["length"])
                if b["length"] > lim_bridge:
                    F.append(finding("bridge", b["length"], lim_bridge, b["loc"],
                                     f"Flat down-facing span of {b['length']:.1f} mm at {fmt_pt(b['loc'])} "
                                     f"bridges between supports; FDM bridges sag past {lim_bridge:g} mm.", "fail"))
                continue
            if f.area < min_area:
                continue
            what = ("a ceiling with no support below any edge" if b["kind"] == "floating"
                    else f"a ledge sticking out {b['length']:.1f} mm from its only support")
            F.append(finding("overhang", 90.0, lim_oh, b["loc"],
                             f"Overhang of 90° ({what}, {f.area:.0f} mm²) at {fmt_pt(b['loc'])}; "
                             f"FDM limit {lim_oh:g}° without support.", "fail", area_mm2=round(f.area, 1)))
            continue
        ang = _overhang_deg(f.tri_n, up)
        on_bed = np.all(np.abs(f.tri_pts @ up - h0) < BED_TOL, axis=1)
        bad = (ang > lim_oh + 1e-6) & ~on_bed
        area = float(f.tri_a[bad].sum())
        if area < min_area:
            continue
        worst = float(ang[bad].max())
        loc = (f.tri_pts[bad].mean(1).T @ f.tri_a[bad]) / area
        if float((f.tri_pts[bad] @ up).max()) - h0 <= near_bed:
            F.append(finding("overhang_near_bed", worst, lim_oh, loc,
                             f"Small {worst:.0f}° overhang ({area:.0f} mm²) at {fmt_pt(loc)} stays within "
                             f"{near_bed:g} mm of the bed (a bottom fillet or chamfer); expect slight droop, "
                             f"a 45° chamfer prints cleaner.", "warn", area_mm2=round(area, 1)))
            continue
        if f.idx in horiz_small_hole_faces:
            F.append(finding("overhang_hole_top", worst, lim_oh, loc,
                             f"Top of a horizontal hole at {fmt_pt(loc)} overhangs up to {worst:.0f}°; "
                             f"it is narrow enough (≤ {lim_bridge:g} mm) to bridge, expect a slightly rough top.",
                             "warn", area_mm2=round(area, 1)))
            continue
        F.append(finding("overhang", worst, lim_oh, loc,
                         f"Overhang of {worst:.0f}° over {area:.0f} mm² at {fmt_pt(loc)}; "
                         f"FDM limit {lim_oh:g}° without support.", "fail", area_mm2=round(area, 1)))

    # ---- minimum wall
    lim_wall = rule_value(rules, "min_wall_mm")
    t, tloc, nrays, _ = min_wall(part)
    if t is not None:
        if t < lim_wall:
            F.append(finding("min_wall", t, lim_wall, tloc,
                             f"Wall only {t:.2f} mm thick at {fmt_pt(tloc)}; FDM needs at least {lim_wall:g} mm "
                             f"(two 0.4 mm nozzle widths).", "fail"))
        else:
            F.append(finding("min_wall", t, lim_wall, tloc,
                             f"Thinnest wall is {t:.2f} mm at {fmt_pt(tloc)} ({nrays} rays), above the "
                             f"{lim_wall:g} mm minimum.", "info"))

    # ---- small vertical holes vs fasteners
    fasteners = rules["fasteners"]["metric"]
    for g in hole_groups:
        if not g["is_hole"] or not parallel(g["axis_d"], up):
            continue
        d = 2 * g["radius"]
        if d > rule_value(rules, "small_hole_max_mm"):
            continue
        name, spec = min(fasteners.items(), key=lambda kv: abs(kv[1]["nominal"] - d))
        if abs(spec["nominal"] - d) <= hi_us and d - hi_us < spec["nominal"]:
            F.append(finding("hole_undersize", d, spec["clearance"], g["top"],
                             f"Vertical Ø{d:.2f} mm hole at {fmt_pt(g['top'])} prints about "
                             f"{d - hi_us:.1f}-{d - lo_us:.1f} mm, too tight for an {name} screw; "
                             f"draw it at {spec['clearance']:g} mm (ISO 273 clearance).", "warn", fastener=name))

    # ---- build volume
    pkey = printer or rules["printers"]["default"]
    if isinstance(pkey, dict):
        pinfo = pkey
    elif pkey in rules["printers"]:
        pinfo = rules["printers"][pkey]
    else:
        raise ValueError(f"unknown printer {pkey!r}; known: {[k for k in rules['printers'] if k != 'default']}")
    vol = pinfo["volume"]
    e1, e2, e3 = frame_from_up(up)
    ok, ext = _fits(verts, e1, e2, e3, vol)
    centre = (part.bbox_min + part.bbox_max) / 2
    size = " × ".join(f"{x:.0f}" for x in ext)
    vol_s = " × ".join(f"{x:g}" for x in vol)
    if ok:
        F.append(finding("build_volume", max(ext), max(vol), centre,
                         f"Part ({size} mm, footprint × height) fits the {pinfo['name']} ({vol_s} mm).", "info"))
    else:
        F.append(finding("build_volume", max(ext), max(vol), centre,
                         f"Part ({size} mm, footprint × height) does not fit the {pinfo['name']} build volume "
                         f"({vol_s} mm) in this orientation.", "fail"))

    return result("printing", "printable", "not_printable", F,
                  file=str(step_path), build_dir=[float(x) for x in up], printer=pinfo.get("name", str(pkey)),
                  summary={"bed_contact_mm2": round(bed_area, 1),
                           "min_wall_mm": None if t is None else round(t, 3),
                           "bridges_mm": [round(b, 1) for b in bridges],
                           "extent_mm": [round(x, 1) for x in ext]})
