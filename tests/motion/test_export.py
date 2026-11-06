import json

from goodman.cli import main
from goodman.export import _motion_record
from tests.motion.synth import write_c01


def test_motion_record_for_ui(tmp_path):
    glb, jy = write_c01(tmp_path)
    out = tmp_path / "results" / "motion" / "c01"
    assert main(["motion", str(glb), str(jy), "--out", str(out)]) == 1
    (out / "card.json").write_text(json.dumps({"title": "C01", "status": "collides", "order": 1}))
    rec = _motion_record(out, tmp_path, tmp_path / "public")
    assert rec["title"] == "C01" and rec["glb"] == "motion/c01.glb"
    assert (tmp_path / "public/motion/c01.glb").read_bytes() == glb.read_bytes()
    assert len(rec["collisions"]) == 1 and rec["collisions"][0]["contact_point_mm"]
    assert {j["id"] for j in rec["joints"]} and all("coupled" in j for j in rec["joints"])


def test_motion_record_skips_missing_glb(tmp_path):
    d = tmp_path / "results" / "motion" / "gone"
    d.mkdir(parents=True)
    (d / "motion_result.json").write_text(json.dumps({"inputs": {"glb": "nope.glb", "joints": "nope.yaml"}, "collisions": []}))
    assert _motion_record(d, tmp_path, tmp_path / "public") is None
