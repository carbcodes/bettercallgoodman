"""FDM printability of a STEP solid (spec 05). Thresholds: goodman/rules/fdm.yaml.

check_printing(step_path, build_dir=(0, 0, 1), printer=None, supports=True) -> dict

build_dir is the up direction on the print bed, in the STEP file's coordinates. The
part is assumed to sit on its lowest point along build_dir.

With supports allowed (the default) overhangs, ledges, ceilings and long bridges are
"needs_support" warnings and the verdict is printable_with_supports; they are failures
only when the support could not be removed (a sealed cavity, a face with no open path to
it) or would stand inside a small bore that must stay clean. supports=False keeps every
overhang past the limit a failure.
"""

from __future__ import annotations

import math

import numpy as np

from .geom import (all_vertices, cylinder_groups, edge_concavity, edge_length, edge_points,
                   face_samples, fmt_pt, frame_from_up, inner_shells, load_part, load_rules,
                   min_wall, parallel, perpendicular, rule_value, unit)
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


def _escape_dirs(up, n_h):
    e1, e2, e3 = frame_from_up(up)
    dirs = [-e3]
    for k in range(n_h):
        a = 2 * math.pi * k / n_h
        h = math.cos(a) * e1 + math.sin(a) * e2
        dirs += [h, unit(h - e3)]
    return dirs


def _pick(pts, w, n):
    """Up to n indices, the largest-weight samples first."""
    order = np.argsort(-w)
    return order[:n]


SELF_HIT_MM = 0.5   # a ray from a triangle centroid may re-hit its own curved face right away; ignore that


def _in_hole(q, holes, tol=0.1):
    """The hole (cylinder group) whose bore or floor contains point q, else None."""
    for g in holes:
        rel = q - g["axis_p"]
        t = float(rel @ g["axis_d"])
        r = float(np.linalg.norm(rel - t * g["axis_d"]))
        if r <= g["radius"] + tol and g["t_min"] - tol <= t <= g["t_max"] + tol:
            return g
    return None


def _support(part, src, pts, nrm, w, up, h0, rules, clean_holes, max_pts=24):
    """Where support under these down-facing sample points would stand and whether it can be removed.

    Returns dict(height, on, clean_hits, trapped): height = tallest support column (mm), on = "bed" or
    "part", clean_hits = small holes (bore or floor) that a column lands in, trapped = no ray from any
    sample leaves the part (support could not be pulled out).
    """
    lift = rule_value(rules, "support_lift_mm")
    lim_oh = rule_value(rules, "overhang_max_deg")
    dirs = _escape_dirs(up, int(rule_value(rules, "support_escape_directions")))
    sel = list(_pick(pts, w, max_pts))
    # add a UV grid over the face so narrow features below (a small hole) are not missed by the
    # few triangle centroids a flat face has
    gp, gn = face_samples(part.faces[src].face, spacing=1.0, max_n=12)
    if len(gp):
        keep = _overhang_deg(gn, up) > lim_oh - 1e-6
        pts = np.vstack([pts, gp[keep]])
        nrm = np.vstack([nrm, gn[keep]])
        sel += list(range(len(pts) - int(keep.sum()), len(pts)))
    height, on, clean_hits, escaped = 0.0, "bed", [], False
    def cast(o, d):
        return [(t, f) for t, f in part.ray_hits(o, d, tmin=1e-3) if not (f == src and t < SELF_HIT_MM)]

    for i in sel:
        p, n = pts[i], nrm[i]
        hits = cast(p, -up)
        if hits:
            t, face = hits[0]
            on = "part"
            g = _in_hole(p - up * t, clean_holes)
            if g is not None and g not in clean_hits:
                clean_hits.append(g)
        else:
            t = float(p @ up - h0)
        height = max(height, t)
        if not escaped:
            q = p + n * lift
            for d in dirs:
                if d @ n < -1e-6:
                    continue
                if not cast(q, d):
                    escaped = True
                    break
    return {"height": height, "on": on, "clean_hits": clean_hits, "trapped": not escaped and len(sel) > 0}


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


def check_printing(step_path, build_dir=(0, 0, 1), printer=None, supports=None) -> dict:
    rules = load_rules("fdm.yaml")
    if supports is None:
        supports = bool(rule_value(rules, "supports_allowed"))
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
    clean_bore = rule_value(rules, "clean_bore_max_mm")
    supported = []          # (area, height) of every region that needs support

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

    clean_holes = [g for g in hole_groups if g["is_hole"] and 2 * g["radius"] < clean_bore]

    # ---- sealed internal voids: nothing inside them can ever come out
    cavity_faces = set()
    lim_cav = rule_value(rules, "enclosed_cavity_max_mm3")
    for vol_mm3, cen, fids in inner_shells(part):
        cavity_faces.update(fids)
        if vol_mm3 > lim_cav:
            F.append(finding("enclosed_cavity", vol_mm3, lim_cav, cen,
                             f"Sealed cavity of {vol_mm3:.0f} mm³ around {fmt_pt(cen)}; support or loose material "
                             f"inside it can never be removed, so it needs an opening or must be split.", "fail"))

    def support_finding(src, rule, worst, loc, area, pts, nrm, w, what):
        """An overhang past the limit: a needs_support warning, or a failure if supports are off,
        trapped, or would stand in a bore that must stay clean."""
        if not supports:
            F.append(finding(rule, worst, lim_oh, loc,
                             f"Overhang of {worst:.0f}° ({what}, {area:.0f} mm²) at {fmt_pt(loc)}; "
                             f"FDM limit {lim_oh:g}° without support.", "fail", area_mm2=round(area, 1)))
            return
        sup = _support(part, src, pts, nrm, w, up, h0, rules, clean_holes)
        hgt = sup["height"]
        if sup["trapped"]:
            F.append(finding("trapped_support", worst, lim_oh, loc,
                             f"Overhang of {worst:.0f}° ({what}, {area:.0f} mm²) at {fmt_pt(loc)} needs support, "
                             f"but no straight path leads out from under it, so the support could not be removed.",
                             "fail", area_mm2=round(area, 1), support_height_mm=round(hgt, 1)))
            return
        if sup["clean_hits"]:
            d = min(2 * g["radius"] for g in sup["clean_hits"])
            F.append(finding("support_in_bore", d, clean_bore, loc,
                             f"Support for the {worst:.0f}° overhang ({area:.0f} mm²) at {fmt_pt(loc)} would stand "
                             f"inside a Ø{d:.1f} mm hole, which must stay clean for a screw and is too narrow "
                             f"(< {clean_bore:g} mm) to scrape out.", "fail", area_mm2=round(area, 1),
                             support_height_mm=round(hgt, 1)))
            return
        supported.append((area, hgt))
        F.append(finding("needs_support", worst, lim_oh, loc,
                         f"Overhang of {worst:.0f}° ({what}, {area:.0f} mm²) at {fmt_pt(loc)} needs support about "
                         f"{hgt:.0f} mm tall standing on the {sup['on']}; FDM limit {lim_oh:g}° without support.",
                         "warn", area_mm2=round(area, 1), support_height_mm=round(hgt, 1), support_on=sup["on"]))

    # ---- overhangs and bridges
    bridges = []
    for f in part.faces:
        if f.idx in bed_ids or f.idx in cavity_faces or not len(f.tri_n):
            continue
        if f.kind == "plane" and f.plane_n is not None and f.plane_n @ up <= -HORIZONTAL_COS:
            b = _bridge(part, f, up, rules)
            if b is None:
                continue
            if b["kind"] == "bridge":
                bridges.append(b["length"])
                if b["length"] > lim_bridge:
                    cen, w = f.tri_pts.mean(1), f.tri_a
                    if not supports:
                        F.append(finding("bridge", b["length"], lim_bridge, b["loc"],
                                         f"Flat down-facing span of {b['length']:.1f} mm at {fmt_pt(b['loc'])} "
                                         f"bridges between supports; FDM bridges sag past {lim_bridge:g} mm.", "fail"))
                        continue
                    sup = _support(part, f.idx, cen, f.tri_n, w, up, h0, rules, clean_holes)
                    if sup["trapped"]:
                        F.append(finding("trapped_support", b["length"], lim_bridge, b["loc"],
                                         f"Bridge of {b['length']:.1f} mm at {fmt_pt(b['loc'])} needs support, but no "
                                         f"straight path leads out from under it, so the support could not be removed.",
                                         "fail", area_mm2=round(f.area, 1)))
                        continue
                    supported.append((f.area, sup["height"]))
                    F.append(finding("needs_support", b["length"], lim_bridge, b["loc"],
                                     f"Flat span of {b['length']:.1f} mm at {fmt_pt(b['loc'])} bridges between supports "
                                     f"and needs support about {sup['height']:.0f} mm tall under {f.area:.0f} mm²; "
                                     f"FDM bridges sag past {lim_bridge:g} mm.", "warn", area_mm2=round(f.area, 1),
                                     support_height_mm=round(sup["height"], 1), support_on=sup["on"]))
                continue
            if f.area < min_area:
                continue
            what = ("a ceiling with no support below any edge" if b["kind"] == "floating"
                    else f"a ledge sticking out {b['length']:.1f} mm from its only support")
            support_finding(f.idx, "overhang", 90.0, b["loc"], f.area, f.tri_pts.mean(1), f.tri_n, f.tri_a, what)
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
        support_finding(f.idx, "overhang", worst, loc, area, f.tri_pts[bad].mean(1), f.tri_n[bad], f.tri_a[bad],
                        "a sloped underside")

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

    need = bool(supported)
    if supported:
        tot = sum(a for a, _ in supported)
        tall = max(h for _, h in supported)
        line = (f"{len(supported)} region{'s need' if len(supported) > 1 else ' needs'} support: {tot:.0f} mm² of "
                f"down-facing area, tallest support {tall:.0f} mm.")
    elif supports:
        line = "No support needed."
    else:
        line = "Supports not allowed (--no-supports): every overhang past the limit is a failure."
    return result("printing", "printable", "not_printable", F, mid_word="printable_with_supports", mid=need,
                  support_needed=need, support_summary=line, supports=supports,
                  file=str(step_path), build_dir=[float(x) for x in up], printer=pinfo.get("name", str(pkey)),
                  summary={"bed_contact_mm2": round(bed_area, 1),
                           "min_wall_mm": None if t is None else round(t, 3),
                           "bridges_mm": [round(b, 1) for b in bridges],
                           "extent_mm": [round(x, 1) for x in ext]})
