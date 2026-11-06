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

    def points(self, indep: Mapping[str, float]) -> tuple[np.ndarray, np.ndarray]:
        T = self.kin.body_transforms(indep)
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

    def allows(self, indep: Mapping[str, float]) -> bool:
        T = self.kin.body_transforms(indep)
        W = self.kin.joint_origin(self.wrist_joint, T)
        tip = W + T[self.wrist_joint][:3, :3] @ self.tip_dir_home * self.c.TOOL
        c, e, z0 = self.c, self.eps, self.table_z
        if W[2] - z0 < c.W_Z_MIN - e:
            return False
        if self._yaw_distance(W, T) < c.NEAR_R - e and W[2] - z0 < c.W_Z_NEAR - e:
            return False
        return tip[2] - z0 >= c.TIP_Z_MIN - e

    def complete(self, partial: Mapping[str, float], rng: np.random.Generator,
                 tries: int = 200) -> dict[str, float] | None:
        free = [j for j in self.kin.independent if j not in partial]
        full = {**self.kin.home, **partial}
        if self.allows(full):
            return full
        if not free:
            return None
        for _ in range(tries):
            for j in free:
                lo, hi = self.kin.limits[j]
                full[j] = float(rng.uniform(lo, hi))
            if self.allows(full):
                return dict(full)
        return None
