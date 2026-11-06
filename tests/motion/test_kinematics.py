import numpy as np
import pytest

from goodman.motion.inputs import Joint, MotionFile, load_joints, load_parts, load_placements
from goodman.motion.kinematics import Kinematics
from tests.motion.synth import write_c01

POSES = ["gripper-closed", "gripper-open", "reach-table", "elbow-up", "elbow-folded", "stretched", "yaw-limit",
         "wrist-limit-pos", "wrist-limit-neg", "reach-wrist-pos", "reach-wrist-neg", "elbow-back-q2max",
         "elbow-up-q2max", "fold-low", "reach-low"]


def _arm_kin(arm):
    return Kinematics(load_joints(arm / "joints.yaml"), load_placements(arm / "assembly.yaml").keys())


def test_home_is_identity(arm):
    T = _arm_kin(arm).body_transforms({})
    assert all(np.allclose(t, np.eye(4)) for t in T.values())


@pytest.mark.parametrize("pose", POSES)
def test_matches_mechy_pose(arm, pose):
    m = load_joints(arm / "joints.yaml")
    home = load_placements(arm / "assembly.yaml")
    want = load_placements(arm / "poses" / pose / "assembly.yaml")
    kin = Kinematics(m, home.keys())
    T = kin.body_transforms(m.poses[pose])
    for part, P in want.items():
        got = T[kin.body_of(part)] @ home[part]
        assert np.allclose(got[:3, 3], P[:3, 3], atol=0.01), part
        ang = np.degrees(np.arccos(np.clip((np.trace(got[:3, :3].T @ P[:3, :3]) - 1) / 2, -1, 1)))
        assert ang < 0.01, part


def test_relevant_joints(arm):
    kin = _arm_kin(arm)
    assert kin.relevant_joints("ground", "shoulder") == ["yaw", "shoulder"]
    assert kin.relevant_joints(kin.body_of("jaw-a"), kin.body_of("gripper-base")) == ["crank-a"]
    assert kin.relevant_joints(kin.body_of("e-bolt"), kin.body_of("lower-shank")) == ["shoulder"]
    assert kin.relevant_joints(kin.body_of("turret"), kin.body_of("shoulder-motor")) == []


def test_coupled_chain_resolves_recursively():
    J = lambda id, coupled=(): Joint(id, None, np.zeros(3), np.array([0, 0, 1.0]), (), 0.0, (-90, 90), coupled)
    m = MotionFile((J("j1"), J("j2", (("j1", 2.0),)), J("j3", (("j2", -1.0),))), {}, None)
    v = Kinematics(m, []).joint_values({"j1": 10})
    assert v == {"j1": 10, "j2": 20, "j3": -20}


def test_c01_tilt(tmp_path):
    glb, jy = write_c01(tmp_path)
    kin = Kinematics(load_joints(jy), ["base", "link"])
    T = kin.body_transforms({"tilt": 30})["tilt"]
    far_end = T @ np.array([120, 0, 55, 1.0])
    assert np.allclose(far_end[:3], [120 * np.cos(np.radians(30)), 0, 55 - 120 * np.sin(np.radians(30))], atol=1e-6)
