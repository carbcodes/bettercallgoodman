import numpy as np

from goodman.motion.collide import CollisionWorld
from goodman.motion.inputs import load_joints, load_parts, load_placements
from goodman.motion.kinematics import Kinematics
from goodman.motion.pairs import plan_pairs
from goodman.motion.sweep import samples_for, sweep
from tests.motion.synth import write_c01


def _arm_kin(arm):
    return Kinematics(load_joints(arm / "joints.yaml"), load_placements(arm / "assembly.yaml").keys())


def _sweep_c01(tmp_path, pivot_z, rule=None):
    glb, jy = write_c01(tmp_path / f"p{pivot_z}", pivot_z=pivot_z)
    parts = load_parts(glb)
    kin = Kinematics(load_joints(jy), parts.keys())
    world = CollisionWorld(parts)
    return sweep(kin, world, plan_pairs(kin, world, parts, set()), rule, {})


def test_samples_sizes(arm):
    kin = _arm_kin(arm)
    assert samples_for(["crank-a"], kin, {}).shape == (121, 1)
    assert samples_for(["shoulder", "elbow"], kin, {}).shape == (61 * 119, 2)
    s = samples_for(["yaw", "shoulder", "elbow"], kin, {"p": {"yaw": 1, "shoulder": 30, "elbow": 0}})
    assert s.shape == (20000 + 8 + 1, 3)
    assert (s.min(0) >= [-150, 20, -135]).all() and (s.max(0) <= [150, 140, 100]).all()


def test_c01_first_contact(tmp_path):
    r = _sweep_c01(tmp_path, pivot_z=55.0)
    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.parts == ("base", "link") and f.joints == ["tilt"]
    assert abs(f.first_contact["tilt"] - 9.22) <= 0.05
    assert f.colliding_range["tilt"][1] == 30.0 and f.worst_pose["tilt"] == 30.0
    p = np.array(f.contact_point_mm)
    assert (p >= [-31, -8.5, -1]).all() and (p <= [31, 8.5, 41]).all()


def test_c01_control_clean(tmp_path):
    assert _sweep_c01(tmp_path, pivot_z=70.0).findings == []


def test_unreachable_collision_not_reported(tmp_path):
    class OnlyShallow:
        def complete(self, partial, rng, tries=200):
            return dict(partial) if partial.get("tilt", 0) <= 5 else None
    r = _sweep_c01(tmp_path, pivot_z=55.0, rule=OnlyShallow())
    assert r.findings == [] and r.stats["poses_unreachable"] > 0


def test_all_unreachable_counted(tmp_path):
    class Never:
        def complete(self, partial, rng, tries=200):
            return None
    r = _sweep_c01(tmp_path, pivot_z=55.0, rule=Never())
    assert r.findings == [] and r.stats["pairs_unreachable"] == 1


def test_shared_joint_sets_sampled_once(tmp_path):
    # two links on the same joint against the base: one joint set, one sample pass, two findings
    from tests.motion.synth import _box, write_glb
    import yaml
    glb = write_glb(tmp_path / "assembly.glb", {
        "base": _box([-30, -30, 0], [30, 30, 40]),
        "link": _box([0, -7.5, 45], [120, 7.5, 65]),
        "link2": _box([0, 10, 45], [120, 20, 65]),
    })
    jy = tmp_path / "joints.yaml"
    jy.write_text(yaml.safe_dump({"joints": [{"id": "tilt", "parent": None, "origin": [0, 0, 55], "axis": [0, 1, 0],
                                              "parts": ["link"], "home": 0, "limits": [0, 30]},
                                             {"id": "tilt2", "parent": None, "origin": [0, 0, 55], "axis": [0, 1, 0],
                                              "parts": ["link2"], "home": 0, "limits": [0, 30],
                                              "coupled": [{"joint": "tilt", "ratio": 1}]}]}))
    parts = load_parts(glb)
    kin = Kinematics(load_joints(jy), parts.keys())
    world = CollisionWorld(parts)
    r = sweep(kin, world, plan_pairs(kin, world, parts, set()), None, {})
    assert sorted(f.parts for f in r.findings) == [("base", "link"), ("base", "link2")]
    assert r.stats["poses_checked"] == 61
