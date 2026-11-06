import json

from goodman.cli import main
from tests.motion.synth import write_c01


def test_cli_c01(tmp_path, capsys):
    glb, jy = write_c01(tmp_path)
    code = main(["motion", str(glb), str(jy), "--out", str(tmp_path / "out")])
    assert code == 1
    res = json.loads((tmp_path / "out/motion_result.json").read_text())
    assert res["verdict"] == "collisions" and len(res["collisions"]) == 1
    c = res["collisions"][0]
    assert set(c) >= {"parts", "joints", "first_contact", "worst", "contact_point_mm", "colliding_range", "render", "why"}
    assert (tmp_path / "out" / c["render"]).stat().st_size > 10_000
    out = capsys.readouterr().out
    assert "collisions" in out and ("link hits base" in out or "base hits link" in out)
    assert set(res["stats"]) >= {"pairs_total", "pairs_same_body", "pairs_ignored", "pairs_rejected_far",
                                 "pairs_sampled", "poses_checked", "poses_unreachable", "pairs_unreachable", "seconds"}


def test_cli_control(tmp_path):
    glb, jy = write_c01(tmp_path, pivot_z=70.0)
    assert main(["motion", str(glb), str(jy), "--out", str(tmp_path / "o")]) == 0
    assert json.loads((tmp_path / "o/motion_result.json").read_text())["verdict"] == "no_collisions"


def test_cli_picks_up_neighbours_and_reports_bad_geometry(tmp_path, capsys):
    glb, jy = write_c01(tmp_path)
    (tmp_path / "geometry.py").write_text("TOOL = 1.0\n")
    assert main(["motion", str(glb), str(jy), "--out", str(tmp_path / "o")]) == 2
    assert "W_Z_MIN" in capsys.readouterr().err


def test_view_box_zooms_on_contact():
    import numpy as np
    import trimesh
    from goodman.motion.report import view_box
    big = trimesh.creation.box(extents=[400, 400, 400])
    small = trimesh.creation.box(extents=[10, 10, 10])
    small.apply_translation([150, 0, 0])
    c, r = view_box([150.0, 0.0, 0.0], big, small)
    assert np.allclose(c, [150, 0, 0]) and 40 <= r <= 60


def test_summary_flags_unreachable_pairs():
    from goodman.motion.report import summary_lines
    res = {"verdict": "no_collisions", "collisions": [], "stats": {"pairs_unreachable": 2}}
    text = "\n".join(summary_lines(res))
    assert "2 body pairs" in text and "not checked" in text
