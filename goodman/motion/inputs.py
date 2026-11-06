"""Loaders for Mechy design outputs: assembly.glb, joints.yaml, assembly.yaml and geometry.py constants.

Units after loading: mm and degrees, Z-up assembly frame.
"""
from __future__ import annotations

import ast
import hashlib
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
import yaml
from scipy.spatial.transform import Rotation

ROOT_NODE = "assembly"
REACH_NAMES = ("W_Z_MIN", "W_Z_NEAR", "NEAR_R", "TIP_Z_MIN", "TOOL")


def load_parts(glb: Path) -> dict[str, trimesh.Trimesh]:
    """Every part mesh at its home pose, in mm, Z-up assembly frame, keyed by GLB node name."""
    scene = trimesh.load(Path(glb), force="scene")
    parents = scene.graph.transforms.parents
    has_root = ROOT_NODE in scene.graph.nodes
    top = ROOT_NODE if has_root else scene.graph.base_frame
    to_asm = np.linalg.inv(scene.graph[ROOT_NODE][0]) if has_root else np.eye(4)

    def part_of(node: str) -> str | None:
        # a part is a direct child of the root node; trimesh adds one child node per mesh primitive
        while node in parents:
            if parents[node] == top:
                return node
            node = parents[node]
        return None

    pieces: dict[str, list[trimesh.Trimesh]] = {n: [] for n, p in parents.items() if p == top}
    for node in scene.graph.nodes_geometry:
        part = part_of(node)
        T_world, geom = scene.graph[node]
        mesh = scene.geometry.get(geom)
        if part is None or not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
            continue
        m = mesh.copy()
        m.apply_transform(to_asm @ T_world)
        pieces[part].append(m)
    parts: dict[str, trimesh.Trimesh] = {}
    for name in sorted(pieces):
        meshes = pieces[name]
        m = trimesh.util.concatenate(meshes) if meshes else None
        if m is None or len(m.faces) == 0 or m.area <= 0:
            warnings.warn(f"part {name} has no triangles; skipped", UserWarning, stacklevel=2)
            continue
        m.apply_scale(1000.0)
        parts[name] = m
    return parts


@dataclass(frozen=True)
class Joint:
    id: str
    parent: str | None
    origin: np.ndarray
    axis: np.ndarray
    parts: tuple[str, ...]
    home: float
    limits: tuple[float, float]
    coupled: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class MotionFile:
    joints: tuple[Joint, ...]
    poses: dict[str, dict[str, float]]
    glb_sha256: str | None


def load_joints(path: Path) -> MotionFile:
    d = yaml.safe_load(Path(path).read_text())
    joints = []
    for j in d.get("joints") or []:
        axis = np.asarray(j["axis"], float)
        joints.append(Joint(
            id=str(j["id"]),
            parent=j.get("parent"),
            origin=np.asarray(j["origin"], float),
            axis=axis / np.linalg.norm(axis),
            parts=tuple(j.get("parts") or ()),
            home=float(j.get("home", 0.0)),
            limits=(float(j["limits"][0]), float(j["limits"][1])),
            coupled=tuple((str(c["joint"]), float(c["ratio"])) for c in j.get("coupled") or ()),
        ))
    poses = {p["name"]: {k: float(v) for k, v in p["values"].items()} for p in d.get("poses") or []}
    return MotionFile(tuple(joints), poses, d.get("glb_sha256"))


def check_consistency(glb: Path, motion: MotionFile, parts: dict[str, trimesh.Trimesh]) -> None:
    for j in motion.joints:
        for p in j.parts:
            if p not in parts:
                raise ValueError(f"joints.yaml part not in GLB: {p} (joint {j.id})")
    if motion.glb_sha256:
        actual = hashlib.sha256(Path(glb).read_bytes()).hexdigest()
        if actual != motion.glb_sha256:
            warnings.warn(f"GLB sha256 {actual[:12]}… differs from joints.yaml glb_sha256 "
                          f"{motion.glb_sha256[:12]}…; files may come from different builds",
                          UserWarning, stacklevel=2)


def load_allow_contact(assembly_yaml: Path) -> set[frozenset[str]]:
    d = yaml.safe_load(Path(assembly_yaml).read_text()) or {}
    return {frozenset(pair) for pair in d.get("allow_contact") or ()}


def load_placements(assembly_yaml: Path) -> dict[str, np.ndarray]:
    """Mechy part placements as 4x4 (mm; Euler degrees, scipy extrinsic 'xyz')."""
    d = yaml.safe_load(Path(assembly_yaml).read_text()) or {}
    out = {}
    for p in d.get("parts") or ():
        T = np.eye(4)
        T[:3, :3] = Rotation.from_euler("xyz", p.get("rotation", [0, 0, 0]), degrees=True).as_matrix()
        T[:3, 3] = p.get("position", [0, 0, 0])
        out[p["id"]] = T
    return out


@dataclass(frozen=True)
class ReachConstants:
    W_Z_MIN: float
    W_Z_NEAR: float
    NEAR_R: float
    TIP_Z_MIN: float
    TOOL: float


def load_reach_constants(geometry_py: Path) -> ReachConstants:
    """Read the reach-rule constants from geometry.py WITHOUT executing it (ast + literal_eval only)."""
    tree = ast.parse(Path(geometry_py).read_text())
    found: dict[str, float] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            pairs = []
            if isinstance(target, ast.Name):
                pairs = [(target, node.value)]
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                    and len(target.elts) == len(node.value.elts):
                pairs = list(zip(target.elts, node.value.elts))
            for t, v in pairs:
                if isinstance(t, ast.Name) and t.id in REACH_NAMES:
                    try:
                        found[t.id] = float(ast.literal_eval(v))
                    except (ValueError, TypeError, SyntaxError):
                        pass
    for name in REACH_NAMES:
        if name not in found:
            raise ValueError(f"geometry.py is missing {name}")
    return ReachConstants(**found)
