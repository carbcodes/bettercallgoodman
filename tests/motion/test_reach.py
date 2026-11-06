import numpy as np

from goodman.motion.inputs import load_joints, load_placements, load_reach_constants
from goodman.motion.kinematics import Kinematics
from goodman.motion.reach import ReachRule


def _arm_rule(arm):
    m = load_joints(arm / "joints.yaml")
    kin = Kinematics(m, load_placements(arm / "assembly.yaml").keys())
    return ReachRule(kin, load_reach_constants(arm / "geometry.py")), m


def test_reach_low_boundary(arm):
    rule, m = _arm_rule(arm)
    W, tip = rule.points(m.poses["reach-low"])
    assert abs(W[2] - 45.0) < 0.5 and 3.0 < tip[2] < 11.0
    assert rule.allows(m.poses["reach-low"])
    lower = dict(m.poses["reach-low"], elbow=-76.6)
    assert rule.points(lower)[0][2] < W[2] and not rule.allows(lower)


def test_fold_low_boundary(arm):
    rule, m = _arm_rule(arm)
    W, _ = rule.points(m.poses["fold-low"])
    assert abs(np.hypot(W[0], W[1]) - 200.0) < 0.5 and abs(W[2] - 53.0) < 1.0
    assert rule.allows(m.poses["fold-low"])


def test_home_and_named_poses_allowed(arm):
    rule, m = _arm_rule(arm)
    assert rule.allows({}) and all(rule.allows(v) for v in m.poses.values())


def test_complete_fills_free_joints(arm):
    rule, _ = _arm_rule(arm)
    full = rule.complete({"shoulder": 20, "elbow": -70}, np.random.default_rng(0))
    assert full is not None and full["shoulder"] == 20 and set(full) == {"yaw", "shoulder", "elbow", "wrist", "crank-a"}
    assert rule.allows(full)
