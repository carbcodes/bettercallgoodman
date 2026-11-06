#!/usr/bin/env python3
"""Deterministic Python 3.11 CAD build. All construction uses mm, Z up.

Run: python3.11 generate.py
No network, random seeds, timestamps, external assets, or other project imports.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("MPLCONFIGDIR", "/tmp/candy-crank-matplotlib")
import numpy as np
import scipy
from scipy.spatial.transform import Rotation
import trimesh
import yaml
import manifold3d as md
import geometry as G

HERE = Path(__file__).resolve().parent
PARTS = {}
CONTACT = set()
TEAL = (0.035, 0.25, 0.27, 1.0)
CREAM = (0.90, 0.85, 0.72, 1.0)
AMBER = (0.96, 0.50, 0.12, 1.0)
BLACK = (0.055, 0.07, 0.07, 1.0)
METAL = (0.57, 0.63, 0.65, 1.0)
GLASS = (0.46, 0.76, 0.77, 0.24)


def box(size, at=(0, 0, 0)):
    return md.Manifold.cube(size, center=True).translate(at)


def cyl(r, h, at=(0, 0, 0), axis="z", n=48):
    s = md.Manifold.cylinder(h, r, circular_segments=n, center=True)
    if axis == "y":
        s = s.rotate((-90, 0, 0))
    elif axis == "x":
        s = s.rotate((0, 90, 0))
    return s.translate(at)


def ring(ro, ri, h, at=(0, 0, 0), axis="y", n=48):
    return cyl(ro, h, at, axis, n) - cyl(ri, h + 2, at, axis, n)


def sphere(r, at=(0, 0, 0), n=24):
    return md.Manifold.sphere(r, n).translate(at)


def union(items):
    return md.Manifold.batch_boolean(items, md.OpType.Add)


def poly_xy(points, height, z=0):
    return md.Manifold.extrude(md.CrossSection([np.asarray(points, float)]), height).translate((0, 0, z))


def poly_xz(points, width, y=0):
    # Positive polygon coordinates map to world x,z; extrusion points toward -y.
    return poly_xy(points, width).rotate((90, 0, 0)).translate((0, y + width / 2, 0))


def rounded_box(size, radius=3, at=(0, 0, 0)):
    x, y, z = size
    shapes = [cyl(radius, z, (a * (x / 2 - radius), b * (y / 2 - radius), 0), n=24)
              for a in (-1, 1) for b in (-1, 1)]
    return md.Manifold.batch_hull(shapes).translate(at)


def d_bore(h, axis="y", at=(0, 0, 0), radius=4.15, flat=3.25):
    s = cyl(radius, h, axis=axis)
    s -= box((20, h + 2, 20) if axis == "y" else (20, 20, h + 2), (flat + 10, 0, 0))
    return s.translate(at)


def add(pid, solid, origin=(0, 0, 0), color=CREAM, kind="print", spec="", print_axis="z"):
    assert re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", pid) and pid not in PARTS
    assert solid.status() == md.Error.NoError, (pid, solid.status())
    raw = solid.to_mesh()
    v = np.asarray(raw.vert_properties[:, :3], float) - np.asarray(origin)
    mesh = trimesh.Trimesh(v, np.asarray(raw.tri_verts), process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0, pid
    assert len(mesh.split(only_watertight=False)) == 1, (pid, "disconnected solid")
    PARTS[pid] = dict(mesh=mesh, origin=np.asarray(origin, float), color=color, kind=kind,
                      spec=spec, print_axis=print_axis)
    return pid


def touch(a, b):
    if a != b:
        CONTACT.add(tuple(sorted((a, b))))


def contact_group(ids):
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            touch(a, b)


def orient_z(s, direction):
    direction = np.asarray(direction, float)
    r, _ = Rotation.align_vectors([direction], [[0, 0, 1]])
    transform = np.column_stack([r.as_matrix(), np.zeros(3)])
    return s.transform(transform)


def bolt(pid, diameter, length, face, direction=(0, 0, 1)):
    # face = bearing surface under head; shank extends opposite direction.
    r, hh = diameter * 0.85, diameter
    solid = cyl(diameter / 2, length, (0, 0, -length / 2), n=24)
    solid += cyl(r, hh, (0, 0, hh / 2), n=24)
    solid -= cyl(diameter * 0.43, hh * 0.55, (0, 0, hh * 0.8), n=6)
    solid = orient_z(solid, direction).translate(face)
    return add(pid, solid, face, METAL, "buy", f"M{diameter:g} x {length:g} socket screw; ISO 4762 envelope")


def nut(pid, diameter, at, axis="y"):
    af, h = (5.5, 2.4) if diameter == 3 else (7.0, 3.2) if diameter == 4 else (8.0, 4.0)
    s = ring(af / math.sqrt(3), diameter / 2, h, at, axis, n=6)
    # A separate round hole avoids a hexagonal bore.
    s = cyl(af / math.sqrt(3), h, at, axis, 6) - cyl(diameter / 2, h + 1, at, axis, 24)
    return add(pid, s, at, METAL, "buy", f"M{diameter:g} hex nut; {af:g} AF x {h:g} thick")


def washer(pid, diameter, at, axis="y"):
    ro, h = (3.5, 0.5) if diameter == 3 else (4.5, 0.8) if diameter == 4 else (5, 1)
    return add(pid, ring(ro, (diameter + 0.3) / 2, h, at, axis, 32), at, METAL, "buy", f"M{diameter:g} flat washer")


def gear(teeth, phase_deg, y, z):
    # Involute spur gear, transverse plane x,z. Tip/root relief and 0.3 mm
    # total backlash shared equally by the two gears. 20-degree PA, module 2.
    rp = G.GEAR_MODULE * teeth / 2
    rb = rp * math.cos(math.radians(G.GEAR_PRESSURE_ANGLE))
    rr = rp - 1.25 * G.GEAR_MODULE
    ra = rp + G.GEAR_MODULE
    inv = lambda r: math.sqrt(max(0, (r / rb) ** 2 - 1)) - math.acos(min(1, rb / r))
    half = math.pi / (2 * teeth) - G.GEAR_BACKLASH / (4 * rp)
    flank = lambda r: half + inv(rp) - inv(max(r, rb))
    pts = []
    pitch = 2 * math.pi / teeth
    for i in range(teeth):
        c = i * pitch + math.radians(phase_deg)
        pts.append((rr * math.cos(c - pitch / 2), rr * math.sin(c - pitch / 2)))
        pts.append((rr * math.cos(c - flank(rb)), rr * math.sin(c - flank(rb))))
        for r in np.linspace(max(rr, rb), ra, 7):
            a = c - flank(r)
            pts.append((r * math.cos(a), r * math.sin(a)))
        for a in np.linspace(c - flank(ra), c + flank(ra), 4)[1:]:
            pts.append((ra * math.cos(a), ra * math.sin(a)))
        for r in np.linspace(ra, max(rr, rb), 7)[1:]:
            a = c + flank(r)
            pts.append((r * math.cos(a), r * math.sin(a)))
        pts.append((rr * math.cos(c + flank(rb)), rr * math.sin(c + flank(rb))))
    return poly_xz([(x, zz + z) for x, zz in pts], G.GEAR_FACE_WIDTH, y) - d_bore(12, at=(0, y, z))


def build_parts():
    base = rounded_box(G.BASE_SIZE, 9, G.BASE_CENTER)
    for x in (-34, 34):
        for y in (-34, 34):
            base -= cyl(2.25, 20, (x, y, 8), n=28)
            base -= cyl(7.25 / math.sqrt(3), 3.8, (x, y, 5.7), n=6)
    for x in (-12, 12):
        base -= cyl(1.3, 6.5, (x, 9, 9), n=24)
    add("base", base, G.BASE_CENTER, TEAL, spec="PETG; 5 perimeters, 30% infill")
    for i, (x, y) in enumerate([(-59, -98), (59, -98), (-59, 44), (59, 44)], 1):
        p = add(f"rubber-foot-{i}", cyl(9, 4, (x, y, 2)), (x, y, 2), BLACK, "buy", "Adhesive silicone foot, 18 x 4 mm")
        touch("base", p)

    # Left and right cheeks include support feet and large lower windows.
    profile = [(-44, 12), (44, 12), (44, 202), (32, 208), (-32, 208), (-44, 202)]
    for side, sign in (("left", -1), ("right", 1)):
        y = sign * 22.5
        plate = poly_xz(profile, 8, y)
        plate += box((88, 24, 6), (0, sign * 27.5, 15))
        plate -= poly_xz([(-29, 26), (29, 26), (29, 85), (22, 92), (-22, 92), (-29, 85)], 12, y)
        plate -= poly_xz([(-20.5, 184), (20.5, 184), (36.5, 210), (-36.5, 210)], 12, y)
        for zz in (112, 166):
            plate -= cyl(5.0, 12, (0, y, zz), "y")
            plate -= cyl(G.BEARING_SEAT_DIAMETER / 2, 7.2, (0, sign * 23.1, zz), "y")
            for x in (-15, 15):
                plate -= cyl(1.7, 12, (x, y, zz), "y", 24)
                plate -= cyl(5.7 / math.sqrt(3), 2.6, (x, sign * 19.8, zz), "y", 6)
        for x, zz in [(-36, 112), (36, 112), (-20, 176), (20, 176)]:
            plate -= cyl(1.7, 12, (x, y, zz), "y", 24)
        for x in (-34, 34):
            plate -= cyl(2.25, 20, (x, sign * 34, 15), n=28)
        for x in (-39, 39):
            for zz in (91, 194):
                plate -= cyl(1.7, 12, (x, y, zz), "y", 24)
                if sign == 1:
                    plate -= cyl(5.7 / math.sqrt(3), 2.6, (x, 19.8, zz), "y", 6)
        if sign == -1:
            # Click-leaf support is outside the candy path, on the dry side.
            plate += box((9, 20, 6.8), (-24, -32.5, 90))
            plate -= cyl(1.3, 14, (-24, -38.5, 92), n=24)
        add(f"{side}-cheek", plate, (0, y, 112), TEAL, spec="PETG structural cheek with bearing shoulders and captive-nut pockets", print_axis="y")
        touch("base", f"{side}-cheek")
        for x, tag in ((-34, "a"), (34, "b")):
            w = washer(f"{side}-foot-washer-{tag}", 4, (x, sign * 34, 18.4), "z")
            b = bolt(f"{side}-foot-bolt-{tag}", 4, 16, (x, sign * 34, 18.8))
            n = nut(f"{side}-foot-nut-{tag}", 4, (x, sign * 34, 5.8), "z")
            contact_group([w, b, n, "base", f"{side}-cheek"])

    # A continuous housing sleeve separates inlet and outlet. No direct feed-through.
    sleeve = ring(38, G.DRUM_RADIUS + G.RADIAL_CLEARANCE, 37, (0, 0, 112), "y", 96)
    sleeve -= box((36, 42, 70), (0, 0, 157))
    sleeve -= box((36, 42, 70), (0, 0, 67))
    lower = union([box((2, 37, 44), (s * 19, 0, 162)) for s in (-1, 1)] +
                  [box((40, 2, 39.3), (0, s * 17.5, 164.35)) for s in (-1, 1)])
    outer = md.Manifold.extrude(md.CrossSection.square((40, 37), center=True), 58, scale_top=(2.8, 86 / 37)).translate((0, 0, 184))
    inner = md.Manifold.extrude(md.CrossSection.square((36, 33), center=True), 58, scale_top=(3, 82 / 33)).translate((0, 0, 184))
    hopper = sleeve + lower + (outer - inner)
    rim = box((116, 90, 2), (0, 0, 243)) - box((108, 82, 5), (0, 0, 243))
    hopper += rim
    for x, zz in [(-36, 112), (36, 112), (-20, 176), (20, 176)]:
        hopper += cyl(4.5, 37, (x, 0, zz), "y", 24)
        hopper -= cyl(1.7, 42, (x, 0, zz), "y", 24)
    hopper -= cyl(G.DRUM_RADIUS + G.RADIAL_CLEARANCE, 40, G.DRUM_ORIGIN, "y", 96)
    hopper -= cyl(4.5, 44, (0, 0, 166), "y")
    # Clearance at the tips of the external bearing-retainer screws.
    for x in (-15, 15):
        hopper -= cyl(1.9, 40, (x, 0, 166), "y", 24)
    for x, h in [(-40, 12), (0, 16), (40, 12)]:
        hopper += cyl(4, h, (x, 47, 246), "x", 32)
        hopper += box((h, 7, 3), (x, 43.5, 242.5))
    hopper -= cyl(1.7, 110, G.HINGE_ORIGIN, "x", 32)
    for x in (-21, 21):
        hopper -= cyl(5.4, 22.8, (x, 47, 246), "x", 40)
    for x in (-20, 20):
        stop = box((10, 3.24, 5), (x, 42.62, 241.5)) - cyl(4.2, 12, (x, 47, 246), "x", 40)
        hopper += stop
    for y in (-8, 8):
        hopper += cyl(3.5, 5, (17.5, y, 150), "x", 24)
        hopper -= cyl(1.3, 6, (18, y, 150), "x", 24)
    add("hopper-body", hopper, (0, 0, 184), CREAM, spec="PETG; integrated metering sleeve, funnel, rim, hinge and 105-degree stops")
    touch("hopper-body", "left-cheek")
    touch("hopper-body", "right-cheek")
    wiper = poly_xz([(11, 143.5), (22, 147), (22, 149), (20, 149), (11, 144.7)], 24)
    wiper += box((4, 26, 6), (22, 0, 150))
    for y in (-8, 8):
        wiper -= cyl(1.7, 6, (22, y, 150), "x", 24)
    add("inlet-wiper", wiper, (20, 0, 150), AMBER, spec="TPU 95A compliant candy cutoff blade; 1.2 mm tip; two M3 fixings", print_axis="y")
    touch("inlet-wiper", "hopper-body")
    for i, y in enumerate((-8, 8), 1):
        b = bolt(f"wiper-bolt-{i}", 3, 8, (24, y, 150), (1, 0, 0))
        contact_group([b, "inlet-wiper", "hopper-body"])
    for i, (x, zz) in enumerate([(-36, 112), (36, 112), (-20, 176), (20, 176)], 1):
        w = washer(f"housing-washer-{i}", 3, (x, -26.75, zz))
        s = add(f"housing-spacer-{i}", ring(3, 1.6, 3, (x, -28.5, zz), "y", 24), (x, -28.5, zz), METAL, "buy", "M3 spacer, 3.2 ID x 6 OD x 3 mm")
        b = bolt(f"housing-bolt-{i}", 3, 60, (x, -30, zz), (0, -1, 0))
        n = nut(f"housing-nut-{i}", 3, (x, 28.2, zz))
        contact_group([w, s, b, n, "left-cheek", "right-cheek", "hopper-body"])

    # Six radial, blind candy pockets with a flat floor.
    drum = cyl(G.DRUM_RADIUS, G.DRUM_WIDTH, (0, 0, 112), "y", 96)
    for i in range(G.POCKET_COUNT):
        # Flat pocket floor at radius 21. Entry is 19 mm, 11 mm deep at center.
        cutter = cyl(G.POCKET_DIAMETER / 2, 20, (0, 0, 31), "z", 40)
        cutter = cutter.rotate((0, 60 * i, 0)).translate(G.DRUM_ORIGIN)
        drum -= cutter
    drum -= d_bore(42, at=G.DRUM_ORIGIN)
    add("metering-drum", drum, G.DRUM_ORIGIN, AMBER, spec="Six 19 mm radial pockets, 11 mm central depth; 8 mm D bore", print_axis="y")

    for tag, z, ymin, ymax, flats in [
        ("main", 112, -41, 58, [(-41, -28), (-18, 18), (30.5, 58)]),
        ("agitator", 166, -35, 43, [(-35, -28), (-14, 14), (30.5, 43)])]:
        shaft = cyl(4, ymax - ymin, (0, (ymax + ymin) / 2, z), "y", 48)
        for a, b in flats:
            shaft -= box((12, b - a, 12), (9.1, (a + b) / 2, z))
        if tag == "main":
            shaft -= cyl(1.3, 11, (0, -35.5, z), "y", 24)
        add(f"{tag}-shaft", shaft, (0, 0, z), METAL, "make-metal", f"8 mm stainless shaft, {ymax-ymin:g} mm long; local D flats x=3.1 mm, round bearing journals")
        touch(f"{tag}-shaft", "metering-drum" if tag == "main" else "agitator-paddle")
        for side, sign in (("left", -1), ("right", 1)):
            at = (0, sign * 23, z)
            bearing = add(f"{tag}-bearing-{side}", ring(11, 4, 7, at, "y", 48), at, METAL, "buy", "608-2RS sealed deep-groove ball bearing, 8 x 22 x 7 mm; envelope model")
            cap_at = (0, sign * 27.25, z)
            cap = ring(13, 5, 1.5, cap_at)
            for x in (-15, 15):
                cap += cyl(3.3, 1.5, (x, sign * 27.25, z), "y", 24)
                cap -= cyl(1.7, 3, (x, sign * 27.25, z), "y", 24)
            capid = add(f"{tag}-retainer-{side}", cap, cap_at, CREAM, spec="Bearing outer-race retaining plate; center clears inner race", print_axis="y")
            contact_group([bearing, f"{tag}-shaft", f"{side}-cheek", capid])
            for x, suffix in ((-15, "a"), (15, "b")):
                b = bolt(f"{tag}-retainer-bolt-{side}-{suffix}", 3, 10, (x, sign * 28, z), (0, sign, 0))
                n = nut(f"{tag}-retainer-nut-{side}-{suffix}", 3, (x, sign * 19.8, z))
                contact_group([b, n, capid, f"{side}-cheek"])
        # Plain spacers load inner races only; retainers clear them radially.
        for side, y, h in [("left", -27.5, 2.0), ("right", 29.25, 5.5)]:
            p = add(f"{tag}-spacer-{side}", ring(4.9, 4.05, h, (0, y, z), "y", 40), (0, y, z), METAL, "buy", f"8 mm ID shaft spacer, OD 9.8, length {h:g} mm")
            contact_group([p, f"{tag}-shaft", f"{tag}-bearing-{side}"])
        collar = ring(7, 4.05, 6, (0, -31.5, z), "y", 40)
        collar -= cyl(1.5, 8, (6, -31.5, z), "x", 24)
        c = add(f"{tag}-shaft-collar", collar, (0, -31.5, z), METAL, "buy", "8 mm bore set-screw shaft collar, 14 OD x 6 wide")
        gr = add(f"{tag}-collar-grub", cyl(1.5, 4, (5.1, -31.5, z), "x", 20), (5.1, -31.5, z), METAL, "buy", "M3 x 4 grub screw onto shaft flat")
        contact_group([c, gr, f"{tag}-shaft", f"{tag}-spacer-left"])

    add("drive-gear-18t", gear(18, 90, 36, 112), (0, 36, 112), AMBER, spec="Module 2, 18 teeth, 20 degree involute, 8 mm face, D bore", print_axis="y")
    add("agitator-gear-36t", gear(36, 95, 36, 166), (0, 36, 166), TEAL, spec="Module 2, 36 teeth, 20 degree involute, 8 mm face, D bore", print_axis="y")
    touch("drive-gear-18t", "agitator-gear-36t")
    for tag, gearid in [("main", "drive-gear-18t"), ("agitator", "agitator-gear-36t")]:
        contact_group([gearid, f"{tag}-shaft", f"{tag}-spacer-right"])
    paddle = cyl(6.5, 28, (0, 0, 166), "y", 40) + box((28, 24, 3), (0, 0, 166))
    paddle -= d_bore(32, at=G.AGITATOR_ORIGIN)
    add("agitator-paddle", paddle, G.AGITATOR_ORIGIN, AMBER, spec="TPU 95A two-wing paddle; 28 mm span, 24 mm working width", print_axis="y")

    # Positive D-drive crank with a freely turning bearing-supported grip.
    crank = md.Manifold.batch_hull([cyl(11, 8, (0, 49, 112), "y", 40), cyl(8, 8, (50, 49, 112), "y", 32)])
    crank -= d_bore(12, at=(0, 49, 112))
    crank -= cyl(2.25, 14, (50, 49, 112), "y", 32)
    # M4 captive hex nut at the back of the handle boss.
    crank -= cyl(7.3 / math.sqrt(3), 3.6, (50, 46.8, 112), "y", 6)
    add("crank-arm", crank, G.CRANK_ORIGIN, AMBER, spec="50 mm crank, 8 mm D bore; M4 captive grip nut", print_axis="y")
    touch("crank-arm", "main-shaft")
    grip = cyl(11, 30, (50, 70, 112), "y", 64)
    grip -= cyl(4.1, 34, (50, 70, 112), "y", 32)
    for y in (57.5, 82.5):
        grip -= cyl(8.05, 5.1, (50, y, 112), "y", 48)
    # Shallow grip grooves stay clear of bearing seats.
    for y in (63, 67, 71, 75, 79):
        grip -= ring(12, 10.2, 0.9, (50, y, 112), "y", 48)
    add("free-spinning-grip", grip, G.GRIP_ORIGIN, TEAL, spec="30 mm long, 22 OD; two 625 bearings; circumferential grip grooves", print_axis="y")
    for name, y in [("inboard", 57.5), ("outboard", 82.5)]:
        bid = add(f"grip-bearing-{name}", ring(8, 2.5, 5, (50, y, 112), "y", 48), (50, y, 112), METAL, "buy", "625-2RS bearing, 5 x 16 x 5 mm; envelope model")
        touch(bid, "free-spinning-grip")
    add("grip-inner-spacer", ring(3.8, 2.55, 20, (50, 70, 112), "y", 32), (50, 70, 112), METAL, "buy", "5 mm ID, 7.6 OD x 20 mm inner-race spacer")
    shoulder = cyl(2.5, 30, (50, 70, 112), "y", 40) + cyl(2, 10, (50, 50, 112), "y", 32)
    shoulder += cyl(4.5, 4, (50, 87, 112), "y", 32)
    shoulder -= cyl(1.8, 2.5, (50, 88, 112), "y", 6)
    gripbolt = add("grip-axle-bolt", shoulder, G.GRIP_ORIGIN, METAL, "make-metal", "Precision shoulder screw: 5 mm shoulder x 30, M4 threaded tip x 10, head 9 x 4; smooth bearing journals")
    gripnut = nut("grip-captive-nut", 4, (50, 46.8, 112))
    add("grip-inboard-washer", ring(5, 2.15, 2, (50, 54, 112), "y", 32), (50, 54, 112), METAL, "buy", "M4 washer/spacer, 4.3 ID x 10 OD x 2 mm")
    contact_group([gripbolt, gripnut, "crank-arm", "grip-inner-spacer", "grip-inboard-washer", "grip-bearing-inboard", "grip-bearing-outboard"])
    add("crank-axial-spacer", ring(4.9, 4.05, 5, (0, 42.5, 112), "y", 40), (0, 42.5, 112), METAL, "buy", "8 ID x 9.8 OD x 5 spacer")
    contact_group(["crank-axial-spacer", "main-shaft", "drive-gear-18t", "crank-arm"])
    for tag, y, z, width, grub in [("crank", 55.5, 112, 5, 3), ("agitator-gear", 41.5, 166, 3, 2)]:
        c = ring(7, 4.05, width, (0, y, z), "y", 40) - cyl(grub / 2, 8, (6, y, z), "x", 24)
        add(f"{tag}-end-collar", c, (0, y, z), METAL, "make-metal", f"8 mm set-screw collar; 14 OD x {width} mm wide; M{grub} tapped radial hole")
        add(f"{tag}-end-grub", cyl(grub / 2, 4, (5.1, y, z), "x", 20), (5.1, y, z), METAL, "buy", f"M{grub} x 4 grub screw")
        shaftid = "main-shaft" if tag == "crank" else "agitator-shaft"
        contact_group([f"{tag}-end-collar", f"{tag}-end-grub", shaftid, "crank-arm" if tag == "crank" else "agitator-gear-36t"])

    # Six smoothly relieved scallops on a separate dry-side click cam.
    cam = cyl(16, 5, (0, -38.5, 112), "y", 72) - d_bore(8, at=(0, -38.5, 112))
    for i in range(6):
        a = math.radians(60 * i)
        cam -= cyl(3, 8, (18 * math.sin(a), -38.5, 112 + 18 * math.cos(a)), "y", 24)
    add("six-click-cam", cam, (0, -38.5, 112), AMBER, spec="Six 1 mm scallops; dry-side PETG click cam", print_axis="y")
    add("cam-inner-spacer", ring(4.9, 4.05, 1.5, (0, -35.25, 112), "y", 32), (0, -35.25, 112), METAL, "buy", "8 mm ID shaft spacer, 9.8 OD x 1.5 mm")
    add("cam-end-washer", ring(6, 1.65, 1.5, (0, -41.75, 112), "y", 32), (0, -41.75, 112), METAL, "buy", "M3 large washer, 12 OD x 1.5 mm")
    bolt("cam-retention-bolt", 3, 10, (0, -42.5, 112), (0, -1, 0))
    contact_group(["six-click-cam", "main-shaft", "main-shaft-collar", "cam-inner-spacer", "cam-end-washer", "cam-retention-bolt"])
    leaf = box((26, 6, 1.2), (-11, -38.5, 94)) + box((8, 8, 2.4), (-24, -38.5, 94.6))
    leaf += sphere(2.3, (0, -38.5, 95.0), 20)
    leaf -= cyl(1.7, 6, (-24, -38.5, 94.5), n=24)
    add("click-flexure", leaf, (-24, -38.5, 94), TEAL, spec="Replaceable PETG cantilever, 26 x 6 x 1.2 mm, compliant bump; print flat")
    b = bolt("click-flexure-bolt", 3, 10, (-24, -38.5, 95.8))
    contact_group([b, "click-flexure", "left-cheek"])
    touch("click-flexure", "six-click-cam")

    # Guard shell: all rotating gears covered, with 2 mm radial/axial clearance.
    guard = box((92, 17.5, 124), (0, 35.25, 146)) - box((88, 17, 120), (0, 33.5, 146))
    guard -= box((75, 5, 8), (0, 28, 208))
    guard -= cyl(5.3, 24, (0, 37, 112), "y", 48)
    guard -= cyl(7.4, 5, (0, 42, 166), "y", 48)
    for x in (-39, 39):
        for zz in (91, 194):
            guard += cyl(3.5, 15.5, (x, 34.25, zz), "y", 24)
            guard -= cyl(1.7, 22, (x, 35, zz), "y", 24)
            guard -= cyl(2.8, 3.2, (x, 42.6, zz), "y", 24)
    add("gear-guard", guard, (0, 35.25, 146), GLASS, spec="Clear PETG enclosure; 2 mm shell; all gear teeth behind guard", print_axis="y")
    touch("gear-guard", "right-cheek")
    for i, (x, zz) in enumerate([(x, z) for x in (-39, 39) for z in (91, 194)], 1):
        b = bolt(f"guard-bolt-{i}", 3, 25, (x, 41, zz), (0, 1, 0))
        n = nut(f"guard-nut-{i}", 3, (x, 19.8, zz))
        contact_group([b, n, "gear-guard", "right-cheek"])

    lid = rounded_box((116, 90, 3), 4, (0, 0, 246))
    for x in (-21, 21):
        lid += cyl(4, 22, (x, 47, 246), "x", 32)
        lid += box((18, 9, 3), (x, 47.5, 246))
    for x, h in [(-40, 12.8), (0, 16.8), (40, 12.8)]:
        lid -= cyl(4.2, h, (x, 47, 246), "x", 40)
    lid -= cyl(1.7, 110, G.HINGE_ORIGIN, "x", 32)
    lid += rounded_box((26, 10, 5), 3, (0, -44, 248.5))
    add("hinged-lid", lid, G.HINGE_ORIGIN, TEAL, spec="0 to 105 degree rear hinge, integral finger tab and hard-stop tabs")
    add("lid-hinge-pin", cyl(1.5, 122, G.HINGE_ORIGIN, "x", 32), G.HINGE_ORIGIN, METAL, "make-metal", "3 mm stainless dowel, cut to 122 mm; retain with two 3 mm push-on caps")
    for side, x in [("left", -61.5), ("right", 61.5)]:
        add(f"hinge-cap-{side}", cyl(3, 1, (x, 47, 246), "x", 24), (x, 47, 246), BLACK, "buy", "3 mm push-on shaft cap")
        touch(f"hinge-cap-{side}", "lid-hinge-pin")
    contact_group(["hinged-lid", "hopper-body", "lid-hinge-pin"])

    # Chute is a continuous closed solid but an open-topped trough.
    section = [(-70, 34), (8, 67), (8, 70), (-70, 37)]
    # Build in local (y,z) then extrude across x.
    chute = poly_xz(section, 34.2).rotate((0, 0, 90))
    for x in (-18.5, 18.5):
        wall = poly_xz([(-70, 34), (8, 67), (8, 77.5), (-70, 49)], 3).rotate((0, 0, 90)).translate((x, 0, 0))
        chute += wall
    # Integral rear support strut attaches to the base, leaving the cup bay open.
    chute += box((32, 6, 58), (0, 5, 41))
    chute += box((38, 20, 4), (0, 5, 14))
    for x in (-12, 12):
        chute -= cyl(1.7, 12, (x, 9, 15), n=24)
    add("delivery-chute", chute, (0, 0, 60), CREAM, spec="Open trough, 34 mm clear width, 23-degree slope; integral support; print on side", print_axis="x")
    touch("delivery-chute", "base")
    for i, x in enumerate((-12, 12), 1):
        b = bolt(f"chute-bolt-{i}", 3, 10, (x, 9, 16))
        touch(b, "delivery-chute")
        touch(b, "base")
    tray = rounded_box((88, 64, 15), 10, (0, -80, 19.5)) - rounded_box((82, 58, 16), 7, (0, -80, 23.5))
    add("catch-tray", tray, (0, -80, 19.5), AMBER, spec="Removable shallow catch tray; 3.5 mm floor and 3 mm walls")
    touch("catch-tray", "base")


def joints():
    main = ["metering-drum", "main-shaft", "drive-gear-18t", "crank-arm", "six-click-cam",
            "main-shaft-collar", "main-collar-grub", "main-spacer-left", "main-spacer-right",
            "crank-axial-spacer", "crank-end-collar", "crank-end-grub", "grip-axle-bolt", "grip-captive-nut",
            "grip-inner-spacer", "grip-inboard-washer", "grip-bearing-inboard", "grip-bearing-outboard", "cam-inner-spacer", "cam-end-washer", "cam-retention-bolt"]
    upper = ["agitator-shaft", "agitator-paddle", "agitator-gear-36t", "agitator-shaft-collar", "agitator-collar-grub",
             "agitator-spacer-left", "agitator-spacer-right", "agitator-gear-end-collar", "agitator-gear-end-grub"]
    return [
        dict(id="crank", type="revolute", parent=None, origin=list(G.DRUM_ORIGIN), axis=[0, 1, 0], parts=main, home=0, limits=list(G.CRANK_LIMITS), label="Crank / metering drum (one periodic turn)"),
        dict(id="agitator", type="revolute", parent=None, origin=list(G.AGITATOR_ORIGIN), axis=[0, 1, 0], parts=upper, home=0, limits=list(G.AGITATOR_LIMITS), label="Agitator / 36-tooth gear", coupled=[dict(joint="crank", ratio=G.AGITATOR_RATIO)]),
        dict(id="grip", type="revolute", parent="crank", origin=list(G.GRIP_ORIGIN), axis=[0, 1, 0], parts=["free-spinning-grip"], home=0, limits=list(G.GRIP_LIMITS), label="Free-spinning hand grip (one periodic turn)"),
        dict(id="lid", type="revolute", parent=None, origin=list(G.HINGE_ORIGIN), axis=[-1, 0, 0], parts=["hinged-lid"], home=0, limits=list(G.LID_LIMITS), label="Refill lid / physical rear stops"),
    ]


POSES = [dict(name="ready", values=dict(crank=0, grip=0, lid=0)),
         dict(name="first-click", values=dict(crank=60, grip=300, lid=0)),
         dict(name="second-click", values=dict(crank=120, grip=240, lid=0)),
         dict(name="half-turn", values=dict(crank=180, grip=180, lid=0)),
         dict(name="refill", values=dict(crank=0, grip=0, lid=105))]


def write_glb(path):
    """Minimal glTF 2.0 writer: exact root quaternion, one mesh per direct child."""
    data = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    def accessor(array, kind, component, target):
        while len(data) % 4:
            data.append(0)
        off = len(data)
        data.extend(array.tobytes(order="C"))
        views.append(dict(buffer=0, byteOffset=off, byteLength=array.nbytes, target=target))
        a = dict(bufferView=len(views)-1, componentType=component, count=len(array), type=kind)
        if kind == "VEC3":
            a.update(min=array.min(axis=0).astype(float).tolist(), max=array.max(axis=0).astype(float).tolist())
        accessors.append(a)
        return len(accessors)-1
    nodes.append(dict(name="assembly", rotation=[-0.7071068, 0, 0, 0.7071068], children=list(range(1, len(PARTS)+1))))
    for i, (pid, p) in enumerate(PARTS.items()):
        m = p["mesh"]
        # Flat face normals preserve crisp functional surfaces in any viewer.
        vertices = (m.vertices[m.faces].reshape(-1, 3) / 1000).astype("<f4")
        normals = np.repeat(m.face_normals, 3, axis=0).astype("<f4")
        idx = np.arange(len(vertices), dtype="<u4")
        pa = accessor(vertices, "VEC3", 5126, 34962)
        na = accessor(normals, "VEC3", 5126, 34962)
        ia = accessor(idx, "SCALAR", 5125, 34963)
        materials.append(dict(name=pid + "-material", pbrMetallicRoughness=dict(baseColorFactor=list(p["color"]), metallicFactor=0.75 if p["kind"] in ("buy", "make-metal") and p["color"] == METAL else 0, roughnessFactor=0.34), doubleSided=False, alphaMode="BLEND" if p["color"][3] < 1 else "OPAQUE"))
        meshes.append(dict(name=pid, primitives=[dict(attributes=dict(POSITION=pa, NORMAL=na), indices=ia, material=i, mode=4)]))
        nodes.append(dict(name=pid, mesh=i, translation=(p["origin"]/1000).tolist(), rotation=[0, 0, 0, 1]))
    doc = dict(asset=dict(version="2.0", generator="Candy Crank deterministic CAD / Python 3.11"), scene=0, scenes=[dict(nodes=[0])], nodes=nodes, meshes=meshes, materials=materials, buffers=[dict(byteLength=len(data))], bufferViews=views, accessors=accessors)
    j = json.dumps(doc, separators=(",", ":"), allow_nan=False).encode()
    j += b" " * ((-len(j)) % 4)
    data.extend(b"\0" * ((-len(data)) % 4))
    total = 12 + 8 + len(j) + 8 + len(data)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(j), b"JSON") + j + struct.pack("<I4s", len(data), b"BIN\0") + data)


def write_stls():
    out = HERE / "stl"
    out.mkdir(exist_ok=True)
    for pid, p in PARTS.items():
        if p["kind"] != "print":
            continue
        mesh = p["mesh"].copy()
        if p["print_axis"] == "y":
            mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
        elif p["print_axis"] == "x":
            mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [0, 1, 0]))
        mesh.apply_translation([-mesh.bounds.mean(axis=0)[0], -mesh.bounds.mean(axis=0)[1], -mesh.bounds[0, 2]])
        (out / f"{pid}.stl").write_bytes(trimesh.exchange.stl.export_stl(mesh))


def write_bom():
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["part_id", "quantity", "source", "specification", "print_file", "solid_volume_cm3"])
    for pid, p in PARTS.items():
        writer.writerow([pid, 1, p["kind"], p["spec"], f"stl/{pid}.stl" if p["kind"] == "print" else "", f"{p['mesh'].volume / 1000:.3f}"])
    (HERE / "bom.csv").write_text(out.getvalue())


def joint_transforms(values):
    js = {j["id"]: j for j in joints()}
    vals, transforms = {}, {}
    def val(jid):
        if jid not in vals:
            j = js[jid]
            vals[jid] = j["home"] + sum(c["ratio"]*(val(c["joint"])-js[c["joint"]]["home"]) for c in j["coupled"]) if j.get("coupled") else values.get(jid, j["home"])
        return vals[jid]
    def transform(jid):
        if jid not in transforms:
            j = js[jid]
            r = Rotation.from_rotvec(np.asarray(j["axis"]) * math.radians(val(jid)-j["home"])).as_matrix()
            t = np.eye(4)
            t[:3, :3] = r
            o = np.asarray(j["origin"])
            t[:3, 3] = o - r @ o
            transforms[jid] = transform(j["parent"]) @ t if j["parent"] else t
        return transforms[jid]
    result = {p: np.eye(4) for p in PARTS}
    for jid, j in js.items():
        for p in j["parts"]:
            result[p] = transform(jid)
    return result, {j: val(j) for j in js}


def verify():
    path = HERE / "assembly.glb"
    raw = path.read_bytes()
    js_len = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20+js_len])
    motion = yaml.safe_load((HERE / "joints.yaml").read_text())
    scene = trimesh.load(path, force="scene", process=False)
    root = doc["nodes"][0]
    assert root["name"] == "assembly" and root["rotation"] == [-0.7071068, 0, 0, 0.7071068]
    assert doc["scenes"] == [dict(nodes=[0])] and len(root["children"]) == len(PARTS)
    assert "animations" not in doc
    assert all("mesh" in n and "children" not in n for n in doc["nodes"][1:])
    assert len({n["mesh"] for n in doc["nodes"][1:]}) == len(PARTS)
    names = {n["name"] for n in doc["nodes"][1:]}
    assert names == set(PARTS) == set(scene.geometry)
    assert motion["glb_sha256"] == hashlib.sha256(raw).hexdigest()
    ids = {j["id"] for j in motion["joints"]}
    assert len(ids) == len(motion["joints"])
    assigned = []
    for j in motion["joints"]:
        assert j["parent"] is None or j["parent"] in ids
        assert set(j["parts"]) <= names
        assert j["limits"][0] <= j["home"] <= j["limits"][1]
        assert np.isclose(np.linalg.norm(j["axis"]), 1)
        assert all(c["joint"] in ids for c in j.get("coupled", []))
        assigned.extend(j["parts"])
    assert len(assigned) == len(set(assigned))
    # Resolve every pose; checks coupling, parenting, limits and cycles.
    for pose in motion["poses"]:
        assert set(pose["values"]) <= ids
        _, values = joint_transforms(pose["values"])
        for j in motion["joints"]:
            assert j["limits"][0] <= values[j["id"]] <= j["limits"][1]
    for pair in CONTACT:
        assert set(pair) <= names
    for node in ast.parse((HERE / "geometry.py").read_text()).body:
        assert isinstance(node, ast.Assign)
        value = ast.literal_eval(node.value)
        assert isinstance(value, (int, float, tuple))
    triangles = 0
    for name, mesh in scene.geometry.items():
        m = mesh.copy()
        m.merge_vertices()
        assert m.is_watertight and m.is_winding_consistent and m.volume > 0, name
        triangles += len(m.faces)
    assert triangles < 50000
    # STL files are in mm, individually watertight, on the build plate.
    stl_count = 0
    for stl in sorted((HERE / "stl").glob("*.stl")):
        m = trimesh.load(stl)
        assert m.is_watertight and m.volume > 0 and abs(m.bounds[0, 2]) < 1e-4, stl.name
        assert max(m.extents) < 220, stl.name
        stl_count += 1
    bounds = np.array([p["mesh"].bounds + p["origin"] for p in PARTS.values()])
    report = dict(status="PASS", python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                  part_count=len(PARTS), joint_count=len(ids), driven_joint_count=1, triangle_count=triangles,
                  printable_part_count=stl_count, glb_sha256=motion["glb_sha256"], glb_bytes=len(raw),
                  home_bounds_mm=[bounds[:, 0].min(axis=0).tolist(), bounds[:, 1].max(axis=0).tolist()],
                  checks=["GLB loaded back with trimesh", "single assembly root and exact required quaternion", "unique direct-child part nodes and one mesh each", "all joint parts, parents and drivers exist", "unique moving-part assignment", "coupling resolves and all named poses satisfy limits", "GLB SHA-256 matches joints.yaml", "closed outward-wound positive-volume meshes", "triangle count below 50000", "geometry.py literal constants only", "all printable STLs manifold, mm, bed at z=0, under 220 mm longest dimension"],
                  limitations=["Rigid-body geometry; compliant click-flexure deformation and bearing internals are not simulated", "Candy dimensions, dose reliability, torque, durability and food-contact suitability require physical prototype testing", "0..360 crank/grip ranges are periodic coordinate windows, not physical end stops"])
    (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def motion_audit():
    """Deterministic solid-intersection audit; sampled, not a continuous proof."""
    solids, bounds, bodies = {}, {}, {p: "ground" for p in PARTS}
    for j in joints():
        for p in j["parts"]:
            bodies[p] = j["id"]
    for name, p in PARTS.items():
        mesh = p["mesh"].copy(); mesh.apply_translation(p["origin"])
        solids[name] = md.Manifold(md.Mesh(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.uint32)))
        bounds[name] = mesh.bounds
    from itertools import combinations
    pairs = list(combinations(PARTS, 2))
    active = [(a, b) for a, b in pairs if bodies[a] != bodies[b] and tuple(sorted((a,b))) not in CONTACT]
    # Also test the meshing teeth and lid/hinge interfaces despite their declared contact.
    active += [("drive-gear-18t", "agitator-gear-36t"), ("hinged-lid", "hopper-body")]
    samples = [dict(crank=float(a)) for a in range(0, 361, 10)] + [dict(lid=float(a)) for a in range(5, 106, 5)]
    failures = []
    def overlap(a, b, posed, bb, pose):
        ba, bc = bb[a], bb[b]
        if np.any(ba[1] <= bc[0]+1e-5) or np.any(bc[1] <= ba[0]+1e-5):
            return
        volume = (posed[a] ^ posed[b]).volume()
        if volume > 0.01:
            failures.append(dict(parts=[a,b], pose=pose, intersection_mm3=round(volume, 6)))
    for a, b in pairs:
        if tuple(sorted((a,b))) not in CONTACT:
            overlap(a, b, solids, bounds, "home")
    for values in samples:
        ts, _ = joint_transforms(values)
        posed, bb = {}, {}
        for name in PARTS:
            posed[name] = solids[name].transform(ts[name][:3, :])
            raw = posed[name].bounding_box()
            bb[name] = np.array([raw[:3], raw[3:]])
        for a, b in active:
            overlap(a, b, posed, bb, values)
    # The lid's stop must engage just beyond its specified travel.
    ts, _ = joint_transforms(dict(lid=106))
    stop_volume = (solids["hinged-lid"].transform(ts["hinged-lid"][:3, :]) ^ solids["hopper-body"]).volume()
    result = dict(status="PASS" if not failures and stop_volume > 0.01 else "FAIL", method="manifold3d solid intersections",
                  home_static_pairs_checked=True, crank_step_degrees=10, lid_step_degrees=5,
                  pose_samples=len(samples), forbidden_volume_tolerance_mm3=0.01,
                  lid_stop_engages_at_106_degrees=bool(stop_volume > 0.01), failures=failures,
                  scope="All undeclared contacts at home; moving bodies against different bodies at sampled poses. Involute gears and lid/hopper additionally tested even though contact is declared. Compliant flexure/cam interface excluded; grip rotation is axisymmetric. Sampling is not a continuous collision proof.")
    (HERE / "motion-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["status"] == "PASS", result


def write_readme(report):
    content = '''# Candy / Crank

A hand-powered, refillable dispenser for **plain chocolate M&M's**. The 50 mm crank
turns a six-pocket drum on sealed bearings. An 18:36 involute gear pair counter-rotates
a flexible agitator at half speed. A replaceable six-lobe click cam and PETG leaf
give six tactile index positions per revolution. A bearing-supported grip turns
freely in your hand. A clear gear guard covers the teeth.

This is an engineered printable **prototype**, with geometric validation. Actual
dose count, feeding reliability, crank force and service life have not been measured.

## Files

- `assembly.glb`: complete home assembly, metres, exact requested frame and hierarchy.
- `joints.yaml`: four revolute joints, coupled agitator, five named poses and GLB hash.
- `assembly.yaml`: explicit intended contact pairs.
- `geometry.py`: literal millimetre/degree constants only.
- `stl/`: 21 separate printable parts in **millimetres**, oriented on z = 0.
- `bom.csv`: one row per physical part; buy, print and metal fabrication distinguished.
- `validation.json`: reloaded-GLB topology, structure, naming, units, limits and hash checks.
- `motion-validation.json`: reproducible sampled solid-intersection checks.
- `preview.png`: home and exposed-mechanism views; the guard is hidden for clarity.
- `generate.py`, `requirements.txt`: reproducible source and pinned dependencies.

## Rebuild

Use Python **3.11**. From this folder:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate.py
```

The generator overwrites all generated outputs, including STLs, preview, BOM,
documentation and validation reports. It needs no network after dependency installation.
Source files (`generate.py`, `geometry.py`, `requirements.txt`) are the build inputs.
No randomness or timestamps are embedded. Use the pinned versions and the same
platform for byte-identical regeneration; CAD triangulation can vary across platforms.

## Dimensions and operation

| Feature | Nominal size |
| --- | --- |
| Base footprint | 144 x 172 mm |
| Complete home envelope | 144 x 203 x 251 mm |
| Metering drum | 64 diameter x 36 wide |
| Six blind radial pockets | 19 diameter, 11 central depth, 60 degrees apart |
| Assumed candy envelope | 14.5 diameter x 8.5 thick; measure your batch |
| Drum housing clearance | 0.65 radial; 0.50 at each end |
| Hopper inlet / top opening | 36 x 33 / 108 x 82 |
| Internal hopper volume | Approximately 300 mL before candy voids and hardware |
| Main / agitator axes | z = 112 / 166; both along +Y |
| Gears | module 2; 18/36 teeth; 20 degree pressure angle; 8 face |
| Gear centre spacing / backlash | 54 / 0.30 mm total tangential backlash |
| Main / agitator stainless shafts | 8 diameter x 99 / 78 long |
| Main shaft bearings | Four 608-2RS, 8 x 22 x 7 |
| Grip bearings | Two 625-2RS, 5 x 16 x 5 |
| Crank / grip | 50 centre distance; 22 diameter x 30 grip |
| Lid travel | 0 to 105 degrees; integral hard stops |

Front is -Y. The crank is on +Y. Positive crank angles follow the right-hand rule
about +Y: the top pocket moves toward +X, past the flexible cutoff wiper, around
the closed sleeve, then out through the bottom opening. The chute leads forward
into a removable catch tray. Prime through approximately 180 degrees before the
first filled pocket reaches the outlet. Subsequently each 60-degree click brings
another pocket to the outlet. The intended dose is a small portion, typically one
plain candy; it is not an exact-count mechanism. Thin pieces may double-load.
Peanut, pretzel and other large varieties require different pocket geometry.

The `crank` and `grip` limits 0..360 represent one periodic revolution, **not physical
stops**. Reset the coordinate at the end of a turn to continue. The driven agitator
has value `-0.5 * crank`; its two-fold-symmetric paddle repeats after 180 degrees.
The agitator is ground-mounted, so its parent is null; it is driven by the crank,
not carried spatially by it. The grip is a child of the crank and spins independently.
Named poses use counter-rotation of the grip to keep its orientation steady.
Only the lid has physical angular end stops. Its positive axis is -X.

## Printing and fits

Use PETG for structural parts, gears and the click flexure. Use TPU 95A for the
agitator paddle and inlet wiper. Transparent PETG is suggested for the guard; the
GLB tint is illustrative and does not promise optical clarity from FDM.
Start with a 0.4 mm nozzle, 0.20 mm layers, 4-5 perimeters, and 30-40% infill.
Print the gears solid around their hubs. Print the thin click leaf flat with its
length in the XY plane. All supplied STLs fit within a 220 mm build envelope.
Inspect slicer previews: cheek feet, hopper hinge barrels, drum pocket ceilings,
chute and guard bosses can require local supports. These are not support-free parts.

Nominal bearing seats are 22.10 and 16.10 mm; D bores are 8.30 with the flat at
x = 3.25. Shaft flats are x = 3.10. These are starting tolerances for a calibrated
printer, not universal press-fit guarantees. Print fit coupons before the large
parts. Sand or ream bearing seats; press bearings by the outer race. Deburr every
candy-facing edge. Adjust the shell clearance only after measuring printed parts.
The 0.65 radial gap is between the drum and sleeve, not a candy size tolerance.

Food-facing printed parts require an appropriate material, surface finish and
cleaning process. This model is not food-contact certified. Keep bearing lubricant
outside the hopper, and make the hopper, drum, paddle, wiper, chute and tray easy
to remove and clean. Treat suitability for actual food use as a separate material
and finishing decision, not something established by mesh validation.

## Hardware and fabrication

`bom.csv` is authoritative for every screw, nut, spacer, bearing and printed part.
Bearing boundary dimensions follow SKF's deep-groove bearing catalogue:
[SKF catalogue](https://cdn.skfmediahub.skf.com/api/public/0901d196802809de/pdf_preview_medium/0901d196802809de_pdf_preview_medium.pdf).

Shaft coordinates below are world Y coordinates, in mm, with z at the shaft axis.
Use ground stainless 8 mm rod, preserving round journals at the bearing locations.
File or mill the indicated D flats to x = 3.10 relative to the shaft centre:

- Main: ends -41 and +58; flats -41..-28, -18..+18, +30.5..+58.
  Drill and tap the -Y end M3, 10 mm minimum usable depth, for the cam retaining screw.
- Agitator: ends -35 and +43; flats -35..-28, -14..+14, +30.5..+43.
- Lid pin: 3 mm stainless rod cut to 122, with two push-on retaining caps.
- Grip axle: precision 5 mm shoulder x 30, M4 tip x 10, head 9 diameter x 4.
  Match this shoulder screw or machine the specified geometry; ordinary fully
  threaded M5 screws are not equivalent bearing journals.
- The two compact end collars are fabricated/matched items: 8 bore, 14 OD;
  crank collar 5 wide with M3 radial grub, agitator collar 3 wide with M2 grub.
- Inner-race spacers use the sizes in the BOM. Their small OD clears the fixed
  bearing retainers. Do not substitute broad washers that rub the retainers.

Threads are represented by nominal envelopes and pilot holes, not helical threads.
Tap the 2.6 mm printed pilot holes M3 for the chute, click leaf and wiper fixings;
use light hand torque. The structural joints use through-bolts and captive nuts.
Retainer nuts fit into the inner cheek pockets. Short custom spacers and collars
are explicitly listed as hardware/fabrication rather than claimed to be prints.

## Assembly order

1. Print, deburr and dry-fit the parts. Fit the captive M3 bearing and guard nuts
   into the cheeks, and the captive M4 base nuts from underneath the base.
2. Seat the four 608 bearings against their 1 mm shoulders. Fit the outer-race
   retainers with M3 x 10 screws. Leave the right cheek loose during shaft assembly.
3. Place the drum inside the sleeve and the TPU paddle inside the throat. Insert
   their D shafts through the left bearing, moving part and right bearing.
   Close the cheeks around the hopper. Four M3 x 60 tie bolts use the 3 mm left
   spacers and washers shown; this keeps their ends clear of the large gear.
4. Fit the left inner-race spacers and shaft collars, leaving the rotating collars
   clear of the stationary retainers. Add the right inner-race spacers and phased
   18/36-tooth gears. At home the small gear has a tooth pointing up, and the large
   gear has a gap pointing down. Keep the pocket at top dead centre.
5. Fit the click cam, its 1.5 mm inner spacer, large end washer and axial M3 screw.
   Attach the click leaf to its external bracket. Its tip has about 0.3 mm initial
   geometric preload and about 1.3 mm peak lobe deflection. Flexure deformation
   is intentionally absent from the rigid GLB; its cam contact is allow-listed.
6. Fit the TPU wiper at the +X cutoff edge. Fit the clear guard with four recessed
   M3 x 25 screws. Their heads must sit flush with the front of the guard.
7. Install the crank spacer, arm and end collar. Press the two 625 bearings into
   the grip with the 20 mm inner spacer between them. Install the 5 mm shoulder
   axle, 2 mm M4 inboard spacer and captive M4 nut. The grip must rotate freely
   without axial rattle after tightening.
8. Attach the chute to its tapped base holes. Set the catch tray in front. Fit
   the lid, hinge pin and retaining caps; check opening to its 105-degree stop.
   Add four adhesive silicone feet.

Turn the empty mechanism through several revolutions first. Check that the drum
does not scrape its housing, the gears remain clear of screws, and the grip turns
freely. Then test a small batch of measured candies, followed by a fuller hopper.
Record doubles, misses and jams over at least 100 clicks before changing pocket
depth or claiming a particular dose. If a candy wedges, reverse gently and clear
it; do not increase force. Adjust click feel by changing leaf thickness or preload.

## What the checks establish

The build reloads the actual GLB and validates all required part, parent, driver
and SHA-256 references; closed/outward meshes; direct-child node structure; joint
limits; and the triangle budget. It checks undeclared solid overlaps at home and
samples crank travel at 10-degree steps and lid travel at 5-degree steps. The
meshing gears and lid/hopper are tested despite their contact declarations; the
lid stop is also checked to engage at 106 degrees. Sampling is not continuous
collision certification. Compliant leaves, rolling elements, candy motion, loads,
print distortion, wear and food suitability are outside that geometric check.
'''
    content += f"\nBuild: {report['part_count']} parts, {report['joint_count']} joints, {report['triangle_count']:,} triangles, {report['printable_part_count']} printable parts.\n"
    (HERE / "README.md").write_text(content)


def preview():
    # Small deterministic software z-buffer; no GPU/browser or external assets.
    from PIL import Image, ImageDraw, ImageFont
    from matplotlib import font_manager
    width, height = 900, 960
    bg = np.array([242, 238, 229], float)
    panels = []
    for panel, elev, azim, hidden, values in [
        (0, 21, -57, {"gear-guard"}, {}),
        (1, 16, 63, {"gear-guard", "right-cheek", "hinged-lid", "hopper-body", "lid-hinge-pin", "hinge-cap-left", "hinge-cap-right"}, {"crank": 60})]:
        canvas = np.broadcast_to(bg, (height, width, 3)).copy()
        depth = np.full((height, width), -np.inf)
        ts, _ = joint_transforms(values)
        el, az = math.radians(elev), math.radians(azim)
        direction = np.array([math.cos(az)*math.cos(el), math.sin(az)*math.cos(el), math.sin(el)])
        right = np.array([-math.sin(az), math.cos(az), 0])
        up = np.cross(direction, right)
        light = np.array([-0.3, -0.5, 0.8]); light /= np.linalg.norm(light)
        for pid, p in PARTS.items():
            if pid in hidden or (panel == 1 and ("guard-" in pid or "housing-bolt" in pid)):
                continue
            m = p["mesh"].copy(); m.apply_translation(p["origin"]); m.apply_transform(ts[pid])
            centered = m.vertices - np.array([0, -15, 126])
            screen = np.column_stack([centered @ right * 3.2 + width/2, height/2 - centered @ up * 3.2, centered @ direction])
            for face, normal in zip(m.faces, m.face_normals):
                if normal @ direction <= 0:
                    continue
                tri = screen[face]
                xmin, ymin = np.maximum(np.floor(tri[:, :2].min(0)).astype(int), [0, 0])
                xmax, ymax = np.minimum(np.ceil(tri[:, :2].max(0)).astype(int), [width-1, height-1])
                if xmin > xmax or ymin > ymax:
                    continue
                x, y = np.meshgrid(np.arange(xmin, xmax+1)+0.5, np.arange(ymin, ymax+1)+0.5)
                (x0,y0,z0),(x1,y1,z1),(x2,y2,z2) = tri
                den = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
                if abs(den) < 1e-9:
                    continue
                a = ((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/den
                b = ((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/den
                c = 1-a-b
                z = a*z0+b*z1+c*z2
                sub = depth[ymin:ymax+1, xmin:xmax+1]
                mask = (a >= -1e-8) & (b >= -1e-8) & (c >= -1e-8) & (z > sub)
                sub[mask] = z[mask]
                shade = np.clip(0.65 + 0.35*(normal @ light), 0.35, 1)
                canvas[ymin:ymax+1, xmin:xmax+1][mask] = np.array(p["color"][:3])*255*shade
        panels.append(Image.fromarray(np.uint8(np.clip(canvas, 0, 255))))
    image = Image.new("RGB", (1800, 1200), tuple(bg.astype(int)))
    for i, panel in enumerate(panels):
        image.paste(panel, (900*i, 145))
    draw = ImageDraw.Draw(image)
    fontpath = font_manager.findfont("DejaVu Sans")
    boldpath = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
    font = lambda n: ImageFont.truetype(fontpath, n)
    bold = lambda n: ImageFont.truetype(boldpath, n)
    ink = "#143f42"
    draw.text((72, 40), "A SIX-CLICK, HAND-POWERED CANDY DISPENSER", fill="#667572", font=font(17))
    draw.text((72, 81), "CANDY / CRANK", fill=ink, font=bold(34))
    draw.text((970, 81), "THE MECHANISM", fill=ink, font=bold(34))
    draw.text((72, 1110), "50 mm crank / six pockets / sealed bearings", fill=ink, font=font(21))
    draw.text((970, 1110), "18:36 gears / half-speed agitator", fill=ink, font=font(21))
    draw.text((72, 1152), "PRINTABLE PROTOTYPE  |  Guard hidden in these views for clarity  |  mm / Z up", fill="#667572", font=font(16))
    image.save(HERE / "preview.png", optimize=False)


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use Python 3.11 for a reproducible build.")
    build_parts()
    write_glb(HERE / "assembly.glb")
    digest = hashlib.sha256((HERE / "assembly.glb").read_bytes()).hexdigest()
    motion = dict(glb_sha256=digest, joints=joints(), poses=POSES)
    (HERE / "joints.yaml").write_text(yaml.safe_dump(motion, sort_keys=False, allow_unicode=False))
    (HERE / "assembly.yaml").write_text(yaml.safe_dump(dict(allow_contact=[list(p) for p in sorted(CONTACT)]), sort_keys=False))
    write_stls()
    write_bom()
    report = verify()
    print("GLB verified; checking sampled solid intersections...", flush=True)
    motion_audit()
    write_readme(report)
    preview()
    print(json.dumps({k: report[k] for k in ("status", "part_count", "joint_count", "triangle_count", "printable_part_count", "glb_sha256")}, indent=2))


if __name__ == "__main__":
    main()
