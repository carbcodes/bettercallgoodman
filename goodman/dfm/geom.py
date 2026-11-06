"""Shared B-rep helpers for the DFM checkers (OCP / OpenCascade via build123d).

Everything works on a single solid read from STEP: per-face triangles with outward
normals, UV-grid sample points, ray casts, edge concavity and cylinder grouping.
Lengths are mm, angles degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
try:
    from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
except ImportError:  # some OCP builds don't wrap it; BRepClass_FaceClassifier does the same job
    from OCP.BRepClass import BRepClass_FaceClassifier

    class BRepTopAdaptor_FClass2d:
        def __init__(self, face, tol):
            self._face, self._tol, self._c = face, tol, BRepClass_FaceClassifier()

        def Perform(self, p2d):
            self._c.Perform(self._face, p2d, self._tol)
            return self._c.State()
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GProp import GProp_GProps
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopAbs import TopAbs_FORWARD
from OCP.TopExp import TopExp_Explorer
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.IFSelect import IFSelect_RetDone

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
MESH_TOL = 0.05          # linear deflection of the triangulation, mm
ANG_TOL_DEG = 1.0        # "parallel" / "horizontal" tolerance


def load_rules(name: str) -> dict:
    return yaml.safe_load((RULES_DIR / name).read_text())


def rule_value(rules: dict, key: str):
    r = rules["rules"][key]
    return r["value"] if isinstance(r, dict) else r


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n == 0:
        raise ValueError("zero-length direction")
    return v / n


def rnd(p, nd=1) -> list[float]:
    return [round(float(x), nd) + 0.0 for x in p]


def fmt_pt(p) -> str:
    return "(" + ", ".join(f"{x:g}" for x in rnd(p)) + ")"


# ---------------------------------------------------------------- loading

def read_step(step_path) -> "TopoDS_Shape":
    reader = STEPControl_Reader()
    if reader.ReadFile(str(step_path)) != IFSelect_RetDone:
        raise ValueError(f"could not read STEP file {step_path}")
    reader.TransferRoots()
    return reader.OneShape()


def solids_of(shape) -> list:
    out, exp = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        out.append(_downcast('Solid')(exp.Current()))
        exp.Next()
    return out


@dataclass
class FaceInfo:
    idx: int
    face: object
    kind: str                       # plane | cylinder | other
    area: float
    tri_pts: np.ndarray             # (n, 3, 3) triangle vertices
    tri_n: np.ndarray               # (n, 3) outward unit normals
    tri_a: np.ndarray               # (n,) areas
    verts: np.ndarray               # (m, 3) mesh vertices
    plane_n: np.ndarray | None = None
    cyl: dict | None = None         # radius, axis_p, axis_d, concave, span_deg


@dataclass
class Part:
    shape: object
    faces: list[FaceInfo]
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    edge_faces: list = field(default_factory=list)   # [(edge, face_idx_a, face_idx_b)]
    _isect: object = None
    _face_map: object = None

    # -------- ray casting
    def ray_hits(self, origin, direction, tmin=1e-3, tmax=1e6):
        """Hits along a ray as (distance, face_index) sorted by distance, ignoring t < tmin."""
        if self._isect is None:
            self._isect = IntCurvesFace_ShapeIntersector()
            self._isect.Load(self.shape, 1e-6)
        o = [float(x) for x in origin]
        d = [float(x) for x in direction]
        self._isect.Perform(gp_Lin(gp_Pnt(*o), gp_Dir(*d)), tmin, tmax)
        hits = []
        for i in range(1, self._isect.NbPnt() + 1):
            hits.append((self._isect.WParameter(i), self.face_index(self._isect.Face(i))))
        return sorted(hits)

    def face_index(self, f) -> int:
        return self._face_map[_key(f)]

    def inside(self, p, tol=1e-6) -> bool:
        c = BRepClass3d_SolidClassifier(self.shape, gp_Pnt(*map(float, p)), tol)
        return c.State() == TopAbs_IN

    def neighbours(self, i) -> set[int]:
        return {b if a == i else a for _, a, b in self.edge_faces if i in (a, b)}


def _face_triangles(face):
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    trsf = loc.Transformation()
    pts = np.array([[*(lambda p: (p.X(), p.Y(), p.Z()))(tri.Node(i).Transformed(trsf))]
                    for i in range(1, tri.NbNodes() + 1)])
    idx = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=int) - 1
    if face.Orientation() == TopAbs_REVERSED:
        idx = idx[:, [0, 2, 1]]
    return pts, idx


def surface_point_normal(face, u, v):
    s = BRepAdaptor_Surface(face)
    p, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    s.D1(u, v, p, du, dv)
    n = np.cross([du.X(), du.Y(), du.Z()], [dv.X(), dv.Y(), dv.Z()])
    nn = np.linalg.norm(n)
    if nn < 1e-12:
        return np.array([p.X(), p.Y(), p.Z()]), None
    n = n / nn
    if face.Orientation() == TopAbs_REVERSED:
        n = -n
    return np.array([p.X(), p.Y(), p.Z()]), n


def normal_near(face, p):
    """Outward normal of `face` at the point of the face closest to p."""
    surf = BRep_Tool.Surface_s(face)
    proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, p)), surf)
    if proj.NbPoints() == 0:
        return None
    u, v = proj.LowerDistanceParameters()
    return surface_point_normal(face, u, v)[1]


def face_samples(face, spacing=1.0, max_n=40):
    """Interior sample points (and outward normals) on a UV grid of roughly `spacing` mm."""
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    s = BRepAdaptor_Surface(face)

    def P(u, v):
        q = s.Value(u, v)
        return np.array([q.X(), q.Y(), q.Z()])

    um, vm = (umin + umax) / 2, (vmin + vmax) / 2
    lu = np.linalg.norm(P(umin, vm) - P(um, vm)) + np.linalg.norm(P(um, vm) - P(umax, vm))
    lv = np.linalg.norm(P(um, vmin) - P(um, vm)) + np.linalg.norm(P(um, vm) - P(um, vmax))
    nu = int(np.clip(math.ceil(lu / spacing), 2, max_n))
    nv = int(np.clip(math.ceil(lv / spacing), 2, max_n))
    cls = BRepTopAdaptor_FClass2d(face, 1e-7)
    pts, nrm = [], []
    for i in range(nu):
        u = umin + (i + 0.5) * (umax - umin) / nu
        for j in range(nv):
            v = vmin + (j + 0.5) * (vmax - vmin) / nv
            if cls.Perform(gp_Pnt2d(u, v)) != TopAbs_IN:
                continue
            p, n = surface_point_normal(face, u, v)
            if n is not None:
                pts.append(p)
                nrm.append(n)
    return np.array(pts).reshape(-1, 3), np.array(nrm).reshape(-1, 3)


def _cyl_info(face, s, verts):
    c = s.Cylinder()
    ax = c.Axis()
    ap = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
    ad = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    p, n = surface_point_normal(face, (umin + umax) / 2, (vmin + vmax) / 2)
    radial = p - ap - np.dot(p - ap, ad) * ad
    t = (verts - ap) @ ad
    return {"radius": c.Radius(), "axis_p": ap, "axis_d": ad,
            "concave": bool(n is not None and np.dot(n, radial) < 0),
            "span_deg": math.degrees(umax - umin),
            "t_min": float(t.min()) if len(t) else 0.0, "t_max": float(t.max()) if len(t) else 0.0}


def load_part(step_path) -> Part:
    shape = read_step(step_path)
    solids = solids_of(shape)
    if not solids:
        raise ValueError(f"{step_path}: no solid in the STEP file")
    if len(solids) > 1:
        # keep the largest solid; the checkers report on one part at a time
        def vol(s):
            g = GProp_GProps()
            BRepGProp.VolumeProperties_s(s, g)
            return g.Mass()
        solids.sort(key=vol, reverse=True)
    shape = solids[0]
    BRepMesh_IncrementalMesh(shape, MESH_TOL, False, 0.3, True)

    # unique faces in explorer order (an indexed shape map, without needing TopTools wrappers)
    fmap, flist = {}, []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        k = _key(ex.Current())
        if k not in fmap:
            fmap[k] = len(flist)
            flist.append(ex.Current())
        ex.Next()
    faces = []
    for i in range(1, len(flist) + 1):
        f = _downcast('Face')(flist[i - 1])
        pts, idx = _face_triangles(f)
        tp = pts[idx] if len(idx) else np.zeros((0, 3, 3))
        cr = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0]) if len(tp) else np.zeros((0, 3))
        a2 = np.linalg.norm(cr, axis=1)
        keep = a2 > 1e-12
        tp, cr, a2 = tp[keep], cr[keep], a2[keep]
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        s = BRepAdaptor_Surface(f)
        st = s.GetType()
        fi = FaceInfo(idx=i - 1, face=f, kind="other", area=g.Mass(), tri_pts=tp,
                      tri_n=cr / a2[:, None] if len(a2) else cr, tri_a=a2 / 2, verts=pts)
        if st == GeomAbs_Plane:
            fi.kind = "plane"
            umin, umax, vmin, vmax = BRepTools.UVBounds_s(f)
            fi.plane_n = surface_point_normal(f, (umin + umax) / 2, (vmin + vmax) / 2)[1]
        elif st == GeomAbs_Cylinder:
            fi.kind = "cylinder"
            fi.cyl = _cyl_info(f, s, pts)
        faces.append(fi)

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()  # box.Get() isn't wrapped in every OCP build
    x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
    part = Part(shape=shape, faces=faces, bbox_min=np.array([x0, y0, z0]), bbox_max=np.array([x1, y1, z1]))
    part._face_map = fmap

    # edge -> the faces it borders
    edges = {}
    for fi_idx, f in enumerate(flist):
        ex = TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            k = _key(ex.Current())
            edges.setdefault(k, [ex.Current(), set()])[1].add(fi_idx)
            ex.Next()
    for e_shape, anc in edges.values():
        e = _downcast('Edge')(e_shape)
        if BRep_Tool.Degenerated_s(e):
            continue
        uniq = sorted(anc)
        if len(uniq) == 2:
            part.edge_faces.append((e, uniq[0], uniq[1]))
    return part


def _downcast(kind: str):
    """TopoDS.Face_s(...) in older OCP builds, TopoDS.Face(...) in newer ones."""
    return getattr(TopoDS, kind + "_s", None) or getattr(TopoDS, kind)


def _key(shape) -> int:
    """Orientation-independent identity of a sub-shape (same TShape and location)."""
    return hash(shape.Oriented(TopAbs_FORWARD))


# ---------------------------------------------------------------- edges

def edge_points(edge, n=12) -> np.ndarray:
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    out = []
    for t in np.linspace(t0, t1, n):
        p = c.Value(t)
        out.append([p.X(), p.Y(), p.Z()])
    return np.array(out)


def edge_length(edge) -> float:
    return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(edge))


def edge_is_line(edge) -> bool:
    return BRepAdaptor_Curve(edge).GetType() == GeomAbs_Line


def edge_direction(edge) -> np.ndarray:
    pts = edge_points(edge, 2)
    return unit(pts[1] - pts[0])


def _dist_to_polyline(q: np.ndarray, poly: np.ndarray) -> np.ndarray:
    a, b = poly[:-1], poly[1:]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-18)
    t = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(2) / L2[None], 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(q[:, None, :] - proj, axis=2).min(1)


def edge_concavity(part: Part, edge, fa: int, fb: int):
    """Return (concave: bool, dihedral_deg) for the edge shared by faces fa and fb.

    dihedral_deg is the angle between the two outward normals at the edge midpoint
    (0 = tangent / smooth). Concave means the material angle is over 180° (an inside
    corner): the neighbour face bends toward the air side of the other face.
    """
    poly = edge_points(edge, 16)
    p = poly[len(poly) // 2]
    na, nb = normal_near(part.faces[fa].face, p), normal_near(part.faces[fb].face, p)
    if na is None or nb is None:
        return False, 0.0
    dihedral = math.degrees(math.acos(float(np.clip(np.dot(na, nb), -1, 1))))
    votes = 0.0
    for f_from, f_to, n_from in ((fa, fb, na), (fb, fa, nb)):
        v = part.faces[f_to].verts
        if not len(v):
            continue
        d = _dist_to_polyline(v, poly)
        off = v[d > 1e-4]
        if not len(off):
            continue
        g = off[np.argmin(np.linalg.norm(off - p, axis=1))]
        votes += np.sign(np.dot(g - p, n_from))
    return votes > 0, dihedral


# ---------------------------------------------------------------- holes / cylinders

def cylinder_groups(part: Part, concave=True):
    """Coaxial, equal-radius cylindrical faces merged into features.

    Returns dicts: radius, axis_p, axis_d, span_deg (total angle), t_min/t_max
    (extent along the axis), faces (indices), is_hole (span >= 300°).
    """
    groups = []
    for f in part.faces:
        if f.kind != "cylinder" or f.cyl["concave"] != concave:
            continue
        c = f.cyl
        for g in groups:
            if abs(g["radius"] - c["radius"]) > 1e-3 or abs(abs(np.dot(g["axis_d"], c["axis_d"])) - 1) > 1e-6:
                continue
            dp = c["axis_p"] - g["axis_p"]
            if np.linalg.norm(dp - np.dot(dp, g["axis_d"]) * g["axis_d"]) > 1e-3:
                continue
            s = np.sign(np.dot(g["axis_d"], c["axis_d"]))
            t = (f.verts - g["axis_p"]) @ g["axis_d"]
            g["span_deg"] += c["span_deg"]
            g["t_min"] = min(g["t_min"], float(t.min()))
            g["t_max"] = max(g["t_max"], float(t.max()))
            g["faces"].append(f.idx)
            break
        else:
            t = (f.verts - c["axis_p"]) @ c["axis_d"]
            groups.append({"radius": c["radius"], "axis_p": c["axis_p"], "axis_d": c["axis_d"],
                           "span_deg": c["span_deg"], "t_min": float(t.min()), "t_max": float(t.max()),
                           "faces": [f.idx]})
    for g in groups:
        g["is_hole"] = g["span_deg"] >= 300
        g["length"] = g["t_max"] - g["t_min"]
        g["center"] = g["axis_p"] + g["axis_d"] * (g["t_min"] + g["t_max"]) / 2
        g["top"] = g["axis_p"] + g["axis_d"] * g["t_max"]
    return groups


def parallel(a, b, tol_deg=ANG_TOL_DEG) -> bool:
    return abs(float(np.dot(unit(a), unit(b)))) >= math.cos(math.radians(tol_deg))


def perpendicular(a, b, tol_deg=ANG_TOL_DEG) -> bool:
    return abs(float(np.dot(unit(a), unit(b)))) <= math.sin(math.radians(tol_deg))


# ---------------------------------------------------------------- wall thickness

def min_wall(part: Part, spacing=1.0, max_rays=6000):
    """Ray-cast thickness: from sample points on every face, shoot inward along -normal
    and take the distance to the first surface hit. Hits on a face that shares an edge
    with the source face are skipped, so sharp wedges at chamfers don't read as walls.

    Returns (thickness, location, n_rays, samples) where samples is a list of
    (thickness, midpoint) for every ray, or (None, None, 0, []) for an empty part.
    """
    budget = max(1, max_rays // max(1, len(part.faces)))
    best, best_loc, n, samples = None, None, 0, []
    for f in part.faces:
        pts, nrm = face_samples(f.face, spacing=spacing, max_n=max(2, int(math.sqrt(budget))))
        if len(f.tri_pts):
            cen = f.tri_pts.mean(1)
            pts = np.vstack([pts, cen])
            nrm = np.vstack([nrm, f.tri_n])
        nb = part.neighbours(f.idx)
        for p, nv in zip(pts, nrm):
            n += 1
            for t, hit in part.ray_hits(p, -nv, tmin=1e-3):
                if hit == f.idx and t < 1e-2:
                    continue
                if hit in nb:
                    break
                mid = p - nv * t / 2
                samples.append((t, mid))
                if best is None or t < best:
                    best, best_loc = t, mid
                break
    return best, best_loc, n, samples


def frame_from_up(up):
    """Orthonormal (e1, e2, e3=up) frame."""
    e3 = unit(up)
    ref = np.array([1.0, 0, 0]) if abs(e3[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = unit(ref - np.dot(ref, e3) * e3)
    e2 = np.cross(e3, e1)
    return e1, e2, e3


def all_vertices(part: Part) -> np.ndarray:
    vs = [f.verts for f in part.faces if len(f.verts)]
    return np.vstack(vs) if vs else np.zeros((0, 3))
