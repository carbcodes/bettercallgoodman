"""Choose which part pairs need a motion sweep: different bodies, not designed contacts, not provably too far."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import trimesh

from goodman.motion.collide import CollisionWorld
from goodman.motion.kinematics import Kinematics

HOME_CONTACT_MM = 0.01


@dataclass
class PairPlan:
    candidates: dict[tuple[str, str], list[tuple[str, str]]] = field(default_factory=dict)
    ignored: list[tuple[tuple[str, str], str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def reach_ball(kin: Kinematics, body: str, ancestor: str, mesh: trimesh.Trimesh) -> tuple[np.ndarray, float]:
    """Ball (home coordinates of `ancestor`'s frame) containing the part at every joint value."""
    v = np.asarray(mesh.vertices)
    chain = kin.path_to_ancestor(body, ancestor)
    if not chain:
        c = (v.min(axis=0) + v.max(axis=0)) / 2
        return c, float(np.linalg.norm(v - c, axis=1).max())
    origins = [kin.joints[j].origin for j in chain]  # bottom -> top
    r = float(np.linalg.norm(v - origins[0], axis=1).max())
    r += sum(float(np.linalg.norm(origins[k] - origins[k + 1])) for k in range(len(origins) - 1))
    return origins[-1], r


def plan_pairs(kin: Kinematics, world: CollisionWorld, parts: dict[str, trimesh.Trimesh],
               allow: set[frozenset[str]]) -> PairPlan:
    order = {b: i for i, b in enumerate(kin.bodies())}
    plan = PairPlan()
    s = dict(pairs_total=0, pairs_same_body=0, pairs_ignored=0, pairs_rejected_far=0, pairs_sampled=0)
    I = np.eye(4)
    for p, q in combinations(sorted(parts), 2):
        s["pairs_total"] += 1
        bp, bq = kin.body_of(p), kin.body_of(q)
        if bp == bq:
            s["pairs_same_body"] += 1
            continue
        if (order[bp], p) > (order[bq], q):
            p, q, bp, bq = q, p, bq, bp
        pair = (p, q)
        if frozenset(pair) in allow:
            plan.ignored.append((pair, "allow_contact"))
            s["pairs_ignored"] += 1
            continue
        lca = kin.common_ancestor(bp, bq)
        cp, rp = reach_ball(kin, bp, lca, parts[p])
        cq, rq = reach_ball(kin, bq, lca, parts[q])
        if np.linalg.norm(cp - cq) > rp + rq:
            s["pairs_rejected_far"] += 1
            continue
        if world.distance(p, I, q, I) <= HOME_CONTACT_MM:
            plan.ignored.append((pair, "in contact at home"))
            s["pairs_ignored"] += 1
            continue
        plan.candidates.setdefault((bp, bq), []).append(pair)
        s["pairs_sampled"] += 1
    plan.stats = s
    return plan
