import dataclasses

import numpy as np
import pytest
import trimesh

from goodman.motion.inputs import (check_consistency, load_allow_contact, load_joints, load_parts,
                                   load_placements, load_reach_constants)
from tests.motion.synth import write_c01, write_glb


def test_arm_glb_loads_all_parts_in_mm(arm):
    parts = load_parts(arm / "assembly.glb")
    assert len(parts) == 118
    lo, hi = parts["lower-shank"].bounds
    assert lo[0] < 10 < hi[0] and lo[2] < 116 < hi[2]
    assert parts["base"].bounds[0][2] > -1.0


def test_placements_match_glb_home(arm):
    placed = load_placements(arm / "assembly.yaml")
    scene = trimesh.load(arm / "assembly.glb", force="scene")
    root = scene.graph["assembly"][0]
    checked = 0
    for name in placed:
        T = np.linalg.inv(root) @ scene.graph[name][0]
        if np.allclose(T, np.eye(4)):
            continue  # placement baked into the vertices (axk2035, yaw-switch, uno-usb-keepout)
        T[:3, 3] *= 1000.0
        assert np.allclose(T, placed[name], atol=1e-4), name
        checked += 1
    assert checked >= 110


def test_joints_file(arm):
    m = load_joints(arm / "joints.yaml")
    assert len(m.joints) == 23
    assert [j.id for j in m.joints if not j.coupled] == ["yaw", "shoulder", "elbow", "wrist", "crank-a"]
    sh = next(j for j in m.joints if j.id == "shoulder")
    assert sh.limits == (20, 140) and sh.home == 90 and sh.parent == "yaw"
    assert m.poses["reach-low"] == {"yaw": 0, "shoulder": 20, "elbow": -74.6, "wrist": 29.6, "crank-a": 20}


def test_allow_contact(arm):
    allow = load_allow_contact(arm / "assembly.yaml")
    assert len(allow) == 138 and frozenset({"yaw-switch", "yaw-pulley"}) in allow


def test_reach_constants_parsed_not_executed(tmp_path, arm):
    c = load_reach_constants(arm / "geometry.py")
    assert (c.W_Z_MIN, c.W_Z_NEAR, c.NEAR_R, c.TIP_Z_MIN, c.TOOL) == (45.0, 95.0, 200.0, 3.0, 89.0)
    evil = tmp_path / "geometry.py"
    evil.write_text("raise SystemExit('executed!')\nTOOL = 89.0\nW_Z_MIN, W_Z_NEAR, NEAR_R, TIP_Z_MIN = 1.0, 2.0, 3.0, 4.0\n")
    assert load_reach_constants(evil).NEAR_R == 3.0
    (tmp_path / "g2.py").write_text("TOOL = 1.0\n")
    with pytest.raises(ValueError, match="W_Z_MIN"):
        load_reach_constants(tmp_path / "g2.py")


def test_consistency_errors(tmp_path):
    glb, jy = write_c01(tmp_path)
    m = load_joints(jy)
    parts = load_parts(glb)
    del parts["link"]
    with pytest.raises(ValueError, match="link"):
        check_consistency(glb, m, parts)


def test_hash_mismatch_warns(arm):
    m = load_joints(arm / "joints.yaml")
    m2 = dataclasses.replace(m, glb_sha256="0" * 64)
    with pytest.warns(UserWarning, match="sha256"):
        check_consistency(arm / "assembly.glb", m2, load_parts(arm / "assembly.glb"))


def test_synth_c01_roundtrip(tmp_path):
    glb, _ = write_c01(tmp_path)
    p = load_parts(glb)
    assert set(p) == {"base", "link"}
    assert np.allclose(p["link"].bounds, [[0, -7.5, 45], [120, 7.5, 65]], atol=1e-6)


def test_zero_triangle_part_dropped(tmp_path):
    empty = trimesh.Trimesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), int))
    write_glb(tmp_path / "a.glb", {"box": trimesh.creation.box(extents=[10, 10, 10]), "ghost": empty})
    with pytest.warns(UserWarning, match="ghost"):
        assert set(load_parts(tmp_path / "a.glb")) == {"box"}
