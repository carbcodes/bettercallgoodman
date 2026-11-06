import numpy as np
import trimesh

from goodman.motion.collide import CollisionWorld


def _cube(c, s=10.0):
    m = trimesh.creation.box(extents=[s, s, s])
    m.apply_translation(c)
    return m


def test_overlap_depth_and_point():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([8, 0, 0])})
    c = w.collide("a", np.eye(4), "b", np.eye(4))
    assert c is not None and abs(c.depth_mm - 2.0) < 0.5
    assert 3.0 - 0.5 <= c.point_mm[0] <= 5.0 + 0.5


def test_apart_and_transform():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([30, 0, 0])})
    assert w.collide("a", np.eye(4), "b", np.eye(4)) is None
    assert abs(w.distance("a", np.eye(4), "b", np.eye(4)) - 20.0) < 1e-6
    T = np.eye(4)
    T[0, 3] = -22.0
    assert w.collide("a", np.eye(4), "b", T) is not None


def test_touching_distance_zero():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([10, 0, 0])})
    assert w.distance("a", np.eye(4), "b", np.eye(4)) <= 0.01
