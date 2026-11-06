"""FCL mesh-mesh collision and distance between posed parts (mm, assembly frame)."""
from __future__ import annotations

from dataclasses import dataclass

import fcl
import numpy as np
import trimesh


@dataclass
class Contact:
    point_mm: np.ndarray
    depth_mm: float


class CollisionWorld:
    def __init__(self, parts: dict[str, trimesh.Trimesh]):
        self.parts = parts
        self._bvh: dict[str, fcl.BVHModel] = {}
        self._pts: dict[str, np.ndarray] = {}

    def _model(self, name: str) -> fcl.BVHModel:
        if name not in self._bvh:
            m = self.parts[name]
            bvh = fcl.BVHModel()
            bvh.beginModel(len(m.vertices), len(m.faces))
            bvh.addSubModel(np.asarray(m.vertices, float), np.asarray(m.faces, np.int32))
            bvh.endModel()
            self._bvh[name] = bvh
        return self._bvh[name]

    def _points(self, name: str) -> np.ndarray:
        """Vertices plus an even surface sample (so coarse meshes like boxes still have local points)."""
        if name not in self._pts:
            m = self.parts[name]
            surf, _ = trimesh.sample.sample_surface_even(m, 3000, seed=0)
            self._pts[name] = np.vstack([m.vertices, surf])
        return self._pts[name]

    def _obj(self, name: str, T: np.ndarray) -> fcl.CollisionObject:
        return fcl.CollisionObject(self._model(name), fcl.Transform(T[:3, :3], T[:3, 3]))

    def collide(self, a: str, Ta: np.ndarray, b: str, Tb: np.ndarray) -> Contact | None:
        req = fcl.CollisionRequest(num_max_contacts=64, enable_contact=True)
        res = fcl.CollisionResult()
        if fcl.collide(self._obj(a, Ta), self._obj(b, Tb), req, res) == 0 or not res.contacts:
            return None
        pts = np.array([c.pos for c in res.contacts], float)
        point = pts.mean(axis=0)
        normals = [np.asarray(c.normal, float) for c in res.contacts]
        return Contact(point_mm=point, depth_mm=self._depth(a, Ta, b, Tb, point, normals))

    def _depth(self, a, Ta, b, Tb, point, normals, radius: float = 30.0) -> float:
        # FCL's mesh-mesh penetration depth is unreliable; estimate the overlap of nearby vertices projected
        # on candidate directions (contact normals + world axes) and keep the smallest.
        va = trimesh.transform_points(self._points(a), Ta)
        vb = trimesh.transform_points(self._points(b), Tb)
        na = va[np.linalg.norm(va - point, axis=1) <= radius]
        nb = vb[np.linalg.norm(vb - point, axis=1) <= radius]
        if len(na) == 0 or len(nb) == 0:
            return 0.0
        dirs = [n / np.linalg.norm(n) for n in normals if np.linalg.norm(n) > 1e-9] + list(np.eye(3))
        best = np.inf
        for n in dirs:
            pa, pb = na @ n, nb @ n
            best = min(best, pa.max() - pb.min(), pb.max() - pa.min())
        return float(max(best, 0.0))

    def distance(self, a: str, Ta: np.ndarray, b: str, Tb: np.ndarray) -> float:
        req, res = fcl.DistanceRequest(), fcl.DistanceResult()
        d = fcl.distance(self._obj(a, Ta), self._obj(b, Tb), req, res)
        return max(0.0, float(d))
