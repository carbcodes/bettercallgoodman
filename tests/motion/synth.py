"""Synthetic Mechy-shaped inputs (GLB + joints.yaml) for tests."""
from pathlib import Path

import numpy as np
import trimesh
import yaml

ROOT_QUAT_WXYZ = [0.7071067811865476, -0.7071067811865475, 0.0, 0.0]  # GLB xyzw [-0.7071, 0, 0, 0.7071]


def _box(lo, hi) -> trimesh.Trimesh:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    m = trimesh.creation.box(extents=hi - lo)
    m.apply_translation((lo + hi) / 2)
    return m


def write_glb(path: Path, meshes_mm: dict[str, trimesh.Trimesh]) -> Path:
    """Mechy-like GLB: root node 'assembly' rotating Z-up to Y-up, metres, one child node per part."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    root = trimesh.transformations.quaternion_matrix(ROOT_QUAT_WXYZ)
    scene.graph.update(frame_to="assembly", frame_from=scene.graph.base_frame, matrix=root)
    for name, mesh in meshes_mm.items():
        m = mesh.copy()
        m.apply_scale(0.001)
        scene.add_geometry(m, node_name=name, geom_name=name, parent_node_name="assembly")
    path.write_bytes(scene.export(file_type="glb"))
    return path


def write_c01(dir: Path, pivot_z: float = 55.0) -> tuple[Path, Path]:
    dir = Path(dir)
    glb = write_glb(dir / "assembly.glb", {
        "base": _box([-30, -30, 0], [30, 30, 40]),
        "link": _box([0, -7.5, pivot_z - 10], [120, 7.5, pivot_z + 10]),
    })
    joints = {"joints": [{"id": "tilt", "type": "revolute", "parent": None, "origin": [0, 0, pivot_z],
                          "axis": [0, 1, 0], "parts": ["link"], "home": 0, "limits": [0, 30]}],
              "poses": []}
    jy = dir / "joints.yaml"
    jy.write_text(yaml.safe_dump(joints, sort_keys=False))
    return glb, jy
