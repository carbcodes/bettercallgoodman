"""Forward kinematics over Mechy joints.yaml: one rigid body per joint plus 'ground'.

A joint rotates by (value - home) degrees about `axis` through `origin` (both in the home assembly frame,
right-hand rule), composed down the parent chain. Coupled joints: value = home + sum(ratio * (driver - driver.home)).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
from scipy.spatial.transform import Rotation

from goodman.motion.inputs import Joint, MotionFile

GROUND = "ground"


def rotation_about(origin: np.ndarray, axis: np.ndarray, deg: float) -> np.ndarray:
    T = np.eye(4)
    R = Rotation.from_rotvec(axis * np.radians(deg)).as_matrix()
    T[:3, :3] = R
    T[:3, 3] = origin - R @ origin
    return T


class Kinematics:
    def __init__(self, motion: MotionFile, part_ids: Iterable[str]):
        self.joints: dict[str, Joint] = {j.id: j for j in motion.joints}
        self.independent: list[str] = [j.id for j in motion.joints if not j.coupled]
        self.limits = {j: self.joints[j].limits for j in self.independent}
        self.home = {j: self.joints[j].home for j in self.independent}
        self._body: dict[str, str] = {p: GROUND for p in part_ids}
        for j in motion.joints:
            for p in j.parts:
                self._body[p] = j.id
        self._order = self._topological()
        self._drivers: dict[str, set[str]] = {}

    def _topological(self) -> list[str]:
        order, seen = [], set()

        def visit(jid: str) -> None:
            if jid in seen:
                return
            parent = self.joints[jid].parent
            if parent is not None:
                visit(parent)
            seen.add(jid)
            order.append(jid)

        for jid in self.joints:
            visit(jid)
        return order

    def body_of(self, part: str) -> str:
        return self._body.get(part, GROUND)

    def bodies(self) -> list[str]:
        return [GROUND] + list(self.joints)

    def joint_values(self, indep: Mapping[str, float]) -> dict[str, float]:
        values: dict[str, float] = {}

        def value(jid: str) -> float:
            if jid in values:
                return values[jid]
            j = self.joints[jid]
            if j.coupled:
                v = j.home + sum(r * (value(d) - self.joints[d].home) for d, r in j.coupled)
            else:
                v = float(indep.get(jid, j.home))
            values[jid] = v
            return v

        for jid in self.joints:
            value(jid)
        return values

    def body_transforms(self, indep: Mapping[str, float]) -> dict[str, np.ndarray]:
        v = self.joint_values(indep)
        M = {GROUND: np.eye(4)}
        for jid in self._order:
            j = self.joints[jid]
            parent = M[j.parent] if j.parent is not None else M[GROUND]
            M[jid] = parent @ rotation_about(j.origin, j.axis, v[jid] - j.home)
        return M

    def joint_origin(self, joint: str, T: Mapping[str, np.ndarray]) -> np.ndarray:
        j = self.joints[joint]
        parent = T[j.parent] if j.parent is not None else T[GROUND]
        return (parent @ np.append(j.origin, 1.0))[:3]

    def _chain(self, body: str) -> list[str]:
        out = []
        while body != GROUND and body is not None:
            out.append(body)
            body = self.joints[body].parent or GROUND
        return out

    def common_ancestor(self, body_a: str, body_b: str) -> str:
        up_a = self._chain(body_a)
        for b in self._chain(body_b):
            if b in up_a:
                return b
        return GROUND

    def path_to_ancestor(self, body: str, ancestor: str) -> list[str]:
        out = []
        for b in self._chain(body):
            if b == ancestor:
                break
            out.append(b)
        return out

    def drivers(self, jid: str) -> set[str]:
        if jid not in self._drivers:
            j = self.joints[jid]
            self._drivers[jid] = {jid} if not j.coupled else set().union(*(self.drivers(d) for d, _ in j.coupled))
        return self._drivers[jid]

    def relevant_joints(self, body_a: str, body_b: str) -> list[str]:
        lca = self.common_ancestor(body_a, body_b)
        path = self.path_to_ancestor(body_a, lca) + self.path_to_ancestor(body_b, lca)
        found = set().union(*(self.drivers(j) for j in path)) if path else set()
        return [j for j in self.independent if j in found]
