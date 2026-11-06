"""Sample each body pair's relevant joints, find collisions, refine first contact and worst pose."""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import product

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import qmc

from goodman.motion.collide import CollisionWorld, Contact
from goodman.motion.kinematics import Kinematics
from goodman.motion.pairs import PairPlan

GRID_STEP = {1: 0.5, 2: 2.0}
LOCAL_SPAN, LOCAL_STEP = 2.0, 0.5
MAX_DRAWN = 100_000


@dataclass
class Finding:
    parts: tuple[str, str]
    joints: list[str]
    first_contact: dict[str, float]
    worst_pose: dict[str, float]
    penetration_mm: float
    contact_point_mm: list[float]
    colliding_range: dict[str, tuple[float, float]]


@dataclass
class SweepResult:
    findings: list[Finding] = field(default_factory=list)
    ignored: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _axis(lo: float, hi: float, step: float) -> np.ndarray:
    a = np.arange(lo, hi + 1e-9, step)
    return a if hi - a[-1] < 1e-9 else np.append(a, hi)


def samples_for(joints: list[str], kin: Kinematics, named_poses: Mapping[str, Mapping[str, float]],
                n_halton: int = 20000, seed: int = 0, start: int = 0) -> np.ndarray:
    k = len(joints)
    lo = np.array([kin.limits[j][0] for j in joints])
    hi = np.array([kin.limits[j][1] for j in joints])
    if k in GRID_STEP:
        axes = [_axis(l, h, GRID_STEP[k]) for l, h in zip(lo, hi)]
        return np.array(list(product(*axes)), float).reshape(-1, k)
    h = qmc.Halton(d=k, scramble=False, seed=seed)
    if start:
        h.fast_forward(start)
    pts = lo + h.random(n_halton) * (hi - lo)
    if start:
        return pts
    corners = np.array(list(product(*zip(lo, hi))), float)
    named = np.array([[p.get(j, kin.home[j]) for j in joints] for p in named_poses.values()], float).reshape(-1, k)
    named = np.clip(named, lo, hi)
    return np.vstack([pts, corners, named])


class _PairSweeper:
    """Sweeps one body pair; holds its rule, rng and part spheres."""

    def __init__(self, kin, world, rule, body_pair, part_pairs, joints, spheres, rng):
        self.kin, self.world, self.rule = kin, world, rule
        self.ba, self.bb = body_pair
        self.part_pairs, self.joints, self.spheres, self.rng = part_pairs, joints, spheres, rng
        self.lo = np.array([kin.limits[j][0] for j in joints])
        self.hi = np.array([kin.limits[j][1] for j in joints])

    def full(self, s) -> dict[str, float] | None:
        partial = {j: float(v) for j, v in zip(self.joints, s)}
        if self.rule is None:
            return {**self.kin.home, **partial}
        return self.rule.complete(partial, self.rng)

    def check(self, full: Mapping[str, float], pairs) -> dict[tuple[str, str], Contact]:
        T = self.kin.body_transforms(full)
        Ta, Tb = T[self.ba], T[self.bb]
        hits = {}
        for a, b in pairs:
            ca, ra = self.spheres[a]
            cb, rb = self.spheres[b]
            if np.linalg.norm((Ta[:3, :3] @ ca + Ta[:3, 3]) - (Tb[:3, :3] @ cb + Tb[:3, 3])) > ra + rb:
                continue
            c = self.world.collide(a, Ta, b, Tb)
            if c is not None:
                hits[(a, b)] = c
        return hits

    def contact(self, s, pair):
        f = self.full(s)
        if f is None:
            return None, None
        return f, self.check(f, [pair]).get(pair)

    def first_contact(self, s_hit, f_hit, clear: np.ndarray, pair) -> dict[str, float]:
        if len(clear) == 0:
            return f_hit
        _, i = cKDTree(clear).query(s_hit, p=np.inf)
        lo, hi = clear[i].astype(float), np.asarray(s_hit, float)
        tol = 0.01 if len(self.joints) == 1 else 0.1
        best = f_hit
        while np.abs(hi - lo).max() > tol:
            mid = (lo + hi) / 2
            f, c = self.contact(mid, pair)
            if f is None:
                hi = mid
            elif c is not None:
                hi, best = mid, f
            else:
                lo = mid
        return best

    def worst(self, s0, f0, c0, pair) -> tuple[dict[str, float], Contact]:
        best_s, best_f, best_c = np.asarray(s0, float), f0, c0
        offsets = np.arange(-LOCAL_SPAN, LOCAL_SPAN + 1e-9, LOCAL_STEP)

        def try_point(s):
            nonlocal best_s, best_f, best_c
            s = np.clip(s, self.lo, self.hi)
            f, c = self.contact(s, pair)
            if c is not None and c.depth_mm > best_c.depth_mm:
                best_s, best_f, best_c = s, f, c
                return True
            return False

        if len(self.joints) <= 2:
            center = best_s.copy()
            for d in product(offsets, repeat=len(self.joints)):
                try_point(center + np.array(d))
        else:
            for _ in range(3):
                improved = False
                for k in range(len(self.joints)):
                    center = best_s.copy()
                    for o in offsets:
                        s = center.copy()
                        s[k] += o
                        improved |= try_point(s)
                if not improved:
                    break
        return best_f, best_c


def sweep(kin: Kinematics, world: CollisionWorld, plan: PairPlan, rule, named_poses, *,
          n_halton: int = 20000, seed: int = 0,
          progress: Callable[[str], None] | None = None) -> SweepResult:
    t0 = time.time()
    stats = dict(plan.stats, poses_checked=0, poses_unreachable=0, pairs_unreachable=0)
    spheres = {}
    for pairs in plan.candidates.values():
        for name in {p for pair in pairs for p in pair}:
            if name not in spheres:
                v = world.parts[name].vertices
                c = (v.min(axis=0) + v.max(axis=0)) / 2
                spheres[name] = (c, float(np.linalg.norm(v - c, axis=1).max()))
    findings = []
    for idx, (body_pair, part_pairs) in enumerate(plan.candidates.items()):
        joints = kin.relevant_joints(*body_pair)
        if not joints:
            continue
        sw = _PairSweeper(kin, world, rule, body_pair, part_pairs, joints, spheres,
                          np.random.default_rng(seed + idx))
        k = len(joints)
        samples = samples_for(joints, kin, named_poses, n_halton=n_halton, seed=seed)
        drawn, reach_s, reach_f = len(samples), [], []
        hit_rows: dict[tuple[str, str], list[tuple[int, Contact]]] = {}

        def run(batch):
            for s in batch:
                f = sw.full(s)
                if f is None:
                    stats["poses_unreachable"] += 1
                    continue
                row = len(reach_s)
                reach_s.append(s)
                reach_f.append(f)
                for pair, c in sw.check(f, part_pairs).items():
                    hit_rows.setdefault(pair, []).append((row, c))

        run(samples)
        if k >= 3:
            while len(reach_s) < n_halton and drawn < MAX_DRAWN and len(reach_s) < drawn / 2:
                more = samples_for(joints, kin, named_poses, n_halton=n_halton, seed=seed, start=drawn)
                drawn += len(more)
                run(more)
        stats["poses_checked"] += len(reach_s)
        if not reach_s:
            stats["pairs_unreachable"] += 1
            continue
        S = np.array(reach_s, float)
        for pair in part_pairs:
            rows = hit_rows.get(pair)
            if not rows:
                continue
            hit_idx = np.array([r for r, _ in rows])
            clear_mask = np.ones(len(S), bool)
            clear_mask[hit_idx] = False
            clear = S[clear_mask]
            H = S[hit_idx]
            if len(clear):
                d, _ = cKDTree(clear).query(H, p=np.inf)
                i = int(np.argmin(d))
            else:
                i = 0
            first = sw.first_contact(H[i], reach_f[hit_idx[i]], clear, pair)
            r_deep, c_deep = max(rows, key=lambda rc: rc[1].depth_mm)
            worst_f, worst_c = sw.worst(S[r_deep], reach_f[r_deep], c_deep, pair)
            findings.append(Finding(
                parts=pair, joints=list(joints), first_contact=first, worst_pose=worst_f,
                penetration_mm=float(worst_c.depth_mm),
                contact_point_mm=[float(x) for x in worst_c.point_mm],
                colliding_range={j: (float(H[:, n].min()), float(H[:, n].max())) for n, j in enumerate(joints)},
            ))
        if progress:
            progress(f"{body_pair[0]}–{body_pair[1]}: {k} joints, {len(reach_s)} poses, "
                     f"{sum(len(v) for v in hit_rows.values())} hits")
    stats["seconds"] = round(time.time() - t0, 1)
    return SweepResult(findings=findings, ignored=list(plan.ignored), stats=stats)
