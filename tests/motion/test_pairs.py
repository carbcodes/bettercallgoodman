from goodman.motion.collide import CollisionWorld
from goodman.motion.inputs import load_allow_contact, load_joints, load_parts
from goodman.motion.kinematics import Kinematics
from goodman.motion.pairs import plan_pairs
from tests.motion.synth import write_c01, write_c01_with_far


def _plan(glb, jy, allow):
    parts = load_parts(glb)
    kin = Kinematics(load_joints(jy), parts.keys())
    return plan_pairs(kin, CollisionWorld(parts), parts, allow)


def test_c01_single_candidate(tmp_path):
    glb, jy = write_c01(tmp_path)
    plan = _plan(glb, jy, allow=set())
    assert plan.candidates == {("ground", "tilt"): [("base", "link")]}


def test_far_part_rejected(tmp_path):
    plan = _plan(*write_c01_with_far(tmp_path), allow=set())
    assert ("far", "link") not in sum(plan.candidates.values(), []) and plan.stats["pairs_rejected_far"] == 1


def test_allow_and_home_contact_ignored(tmp_path):
    glb, jy = write_c01(tmp_path, pivot_z=50.0)
    plan = _plan(glb, jy, allow=set())
    assert plan.candidates == {} and plan.ignored == [(("base", "link"), "in contact at home")]
    glb, jy = write_c01(tmp_path / "b")
    assert _plan(glb, jy, allow={frozenset({"base", "link"})}).ignored[0][1] == "allow_contact"


def test_arm_plan_sane(arm):
    allow = load_allow_contact(arm / "assembly.yaml")
    plan = _plan(arm / "assembly.glb", arm / "joints.yaml", allow=allow)
    s = plan.stats
    assert s["pairs_total"] == 118 * 117 // 2
    assert s["pairs_same_body"] + s["pairs_ignored"] + s["pairs_rejected_far"] + s["pairs_sampled"] == s["pairs_total"]
    flat = {frozenset(p) for v in plan.candidates.values() for p in v}
    assert not flat & allow
    assert ("base", "lower-shank") in plan.candidates[("ground", "shoulder")]
