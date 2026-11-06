"""Mechy arm firmware reach rule (clearOk), from geometry.py constants.

W (wrist point) >= W_Z_MIN above the table everywhere, >= W_Z_NEAR within NEAR_R of the yaw axis,
and the fingertip (TOOL mm from W along the gripper axis) >= TIP_Z_MIN above the table.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from goodman.motion.inputs import ReachConstants
from goodman.motion.kinematics import Kinematics


class ReachRule:
    def __init__(self, kin: Kinematics, c: ReachConstants, wrist_joint: str = "wrist", yaw_joint: str = "yaw",
                 table_z: float = 0.0, tip_dir_home=(0.0, 0.0, -1.0), eps: float = 0.1):
        for j in (wrist_joint, yaw_joint):
            if j not in kin.joints:
                raise ValueError(f"reach rule needs a joint named {j!r} in joints.yaml")
        self.kin, self.c = kin, c
        self.wrist_joint, self.yaw_joint = wrist_joint, yaw_joint
        self.table_z, self.eps = table_z, eps
        self.tip_dir_home = np.asarray(tip_dir_home, float)
        chain = kin.path_to_ancestor(wrist_joint, "ground")
        self._w_drivers = set().union(*(kin.drivers(j) for j in chain[1:])) if len(chain) > 1 else set()
        self._tip_drivers = self._w_drivers | kin.drivers(wrist_joint)
        self._only = {wrist_joint, yaw_joint}

    def points(self, indep: Mapping[str, float]) -> tuple[np.ndarray, np.ndarray]:
        T = self.kin.body_transforms(indep, only=self._only)
        W = self.kin.joint_origin(self.wrist_joint, T)
        tip = W + T[self.wrist_joint][:3, :3] @ self.tip_dir_home * self.c.TOOL
        return W, tip

    def _yaw_distance(self, p: np.ndarray, T: Mapping[str, np.ndarray]) -> float:
        j = self.kin.joints[self.yaw_joint]
        o = self.kin.joint_origin(self.yaw_joint, T)
        parent = T[j.parent] if j.parent is not None else T["ground"]
        a = parent[:3, :3] @ j.axis
        d = p - o
        return float(np.linalg.norm(d - (d @ a) * a))

    def _w_ok(self, W: np.ndarray, T) -> bool:
        c, e, z0 = self.c, self.eps, self.table_z
        if W[2] - z0 < c.W_Z_MIN - e:
            return False
        return not (self._yaw_distance(W, T) < c.NEAR_R - e and W[2] - z0 < c.W_Z_NEAR - e)

    def allows(self, indep: Mapping[str, float]) -> bool:
        T = self.kin.body_transforms(indep, only=self._only)
        W = self.kin.joint_origin(self.wrist_joint, T)
        if not self._w_ok(W, T):
            return False
        tip = W + T[self.wrist_joint][:3, :3] @ self.tip_dir_home * self.c.TOOL
        return tip[2] - self.table_z >= self.c.TIP_Z_MIN - self.eps

    def complete(self, partial: Mapping[str, float], rng: np.random.Generator,
                 tries: int = 200) -> dict[str, float] | None:
        free = [j for j in self.kin.independent if j not in partial and j in self._tip_drivers]
        full = {**self.kin.home, **partial}
        if self.allows(full):
            return full
        if not free:
            return None
        if not (self._w_drivers & set(free)):
            # W is fixed by the given joints: if W fails, no setting of the free joints can help
            T = self.kin.body_transforms(full, only=self._only)
            if not self._w_ok(self.kin.joint_origin(self.wrist_joint, T), T):
                return None
        for _ in range(tries):
            for j in free:
                lo, hi = self.kin.limits[j]
                full[j] = float(rng.uniform(lo, hi))
            if self.allows(full):
                return dict(full)
        return None
