"""DFM checkers on STEP parts with known answers (tests/fixtures/dfm/*.py).

Each fixture script builds a part with build123d and declares EXPECTED: the verdict and
the key finding. The test writes the part to STEP, runs the checker on the STEP file and
compares.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("build123d")

from build123d import Align, Box, Cylinder, Pos, RectangleRounded, export_step, extrude  # noqa: E402

from goodman.dfm import check_cnc, check_printing  # noqa: E402
from goodman.dfm.__main__ import main as cli  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "dfm"
CASES = sorted(p.stem for p in FIX.glob("[pm][0-9]*.py"))
A = (Align.CENTER, Align.CENTER, Align.MIN)
FINDING_KEYS = {"rule", "value", "limit", "location", "why", "severity"}


def _load(name):
    sys.path.insert(0, str(FIX))
    try:
        spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(FIX))


def _step(part, tmp_path, name="part"):
    path = tmp_path / f"{name}.step"
    export_step(part, str(path))
    return path


def _check(checker, path, **kw):
    return check_printing(path, **kw) if checker == "printing" else check_cnc(path, **kw)


def _rules(res, rule):
    return [f for f in res["findings"] if f["rule"] == rule]


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = {}
    d = tmp_path_factory.mktemp("dfm")
    for name in CASES:
        mod = _load(name)
        path = _step(mod.build(), d, name)
        out[name] = (mod.EXPECTED, _check(mod.EXPECTED["checker"], path), path)
    return out


def test_thirteen_fixtures():
    assert len([c for c in CASES if c.startswith("p")]) == 7
    assert len([c for c in CASES if c.startswith("m")]) == 6


@pytest.mark.parametrize("name", CASES)
def test_fixture_verdict_and_key_finding(results, name):
    exp, res, _ = results[name]
    assert res["verdict"] == exp["verdict"], res["findings"]
    for f in res["findings"]:
        assert FINDING_KEYS <= set(f)
        assert len(f["location"]) == 3
        assert f["why"].endswith(".") and "\n" not in f["why"]
    key = _rules(res, exp["key_rule"])
    if exp["key_severity"] is None:
        assert not key, key
        return
    assert key, f"no {exp['key_rule']} finding in {res['findings']}"
    assert key[0]["severity"] == exp["key_severity"], key
    if "key_value" in exp:
        assert key[0]["value"] == pytest.approx(exp["key_value"], rel=0.02, abs=0.02)


def test_overhang_location_is_under_the_lip(results):
    res = results["p01_overhang_60"][1]
    f = _rules(res, "needs_support")[0]
    x, _, z = f["location"]
    assert 20 < x < 28 and 18 < z < 23
    assert "60°" in f["why"] and "45°" in f["why"] and "support" in f["why"]
    assert f["area_mm2"] == pytest.approx(185, abs=5) and f["support_height_mm"] == pytest.approx(21, abs=1.5)
    assert res["support_needed"] is True and "185 mm²" in res["support_summary"]


def test_no_supports_keeps_the_old_behaviour(results):
    exp, _, path = results["p01_overhang_60"]
    res = check_printing(path, supports=False)
    assert res["verdict"] == exp["no_supports"]["verdict"]
    f = _rules(res, exp["no_supports"]["key_rule"])
    assert f and f[0]["severity"] == exp["no_supports"]["key_severity"] and f[0]["value"] == pytest.approx(60)
    assert res["support_needed"] is False and not _rules(res, "needs_support")


def test_control_needs_no_support(results):
    res = results["p06_bracket_control"][1]
    assert res["verdict"] == "printable" and res["support_needed"] is False
    assert res["support_summary"] == "No support needed."


def test_thin_wall_fails_even_with_supports(results):
    res = results["p03_wall_0p5"][1]
    assert res["verdict"] == "not_printable" and _rules(res, "min_wall")[0]["severity"] == "fail"


def test_enclosed_cavity_is_also_trapped_from_the_outside(results):
    res = results["p07_enclosed_cavity"][1]
    assert res["verdict"] == "not_printable"
    assert not _rules(res, "needs_support"), "the cavity's ceiling must not be counted as ordinary support"


def test_support_in_small_bore_fails(tmp_path):
    # a shelf whose support column would land inside the Ø3.4 mm (M3) blind hole in the base below it
    part = (Box(10, 10, 30, align=A) + Pos(10, 0, 27) * Box(10, 10, 3, align=A)
            + Pos(10, 0, 0) * Box(10, 10, 6, align=A)) - Pos(10, 0, 1) * Cylinder(1.7, 5, align=A)
    res = check_printing(_step(part, tmp_path))
    f = _rules(res, "support_in_bore")
    assert res["verdict"] == "not_printable" and f and f[0]["value"] == pytest.approx(3.4) and f[0]["limit"] == 5


def test_tunnel_support_can_come_out(tmp_path):
    # a 20 mm square tunnel through a block: its ceiling needs support, removable through the open ends
    part = Box(40, 40, 40, align=A) - Pos(0, 0, 10) * Box(20, 50, 20, align=A)
    res = check_printing(_step(part, tmp_path))
    assert res["verdict"] == "printable_with_supports", res["findings"]
    assert not _rules(res, "trapped_support")


def test_m3_hole_warning_names_the_fastener(results):
    f = _rules(results["p05_m3_hole_3p0"][1], "hole_undersize")[0]
    assert f["fastener"] == "M3" and f["limit"] == 3.4


def test_m3_clearance_hole_no_warning(tmp_path):
    path = _step(Box(30, 30, 5, align=A) - Cylinder(1.7, 5, align=A), tmp_path)
    assert not _rules(check_printing(path), "hole_undersize")


def _bridge_part(span):
    return (Box(span + 10, 10, 3, align=A) + Pos(-(span + 5) / 2, 0, 3) * Box(5, 10, 10, align=A)
            + Pos((span + 5) / 2, 0, 3) * Box(5, 10, 10, align=A) + Pos(0, 0, 13) * Box(span + 10, 10, 3, align=A))


def test_short_bridge_passes(tmp_path):
    res = check_printing(_step(_bridge_part(8), tmp_path))
    assert res["verdict"] == "printable", res["findings"]
    assert res["summary"]["bridges_mm"] == [pytest.approx(8, abs=0.3)]


def test_long_bridge_needs_support(tmp_path):
    path = _step(_bridge_part(20), tmp_path)
    res = check_printing(path)
    f = _rules(res, "needs_support")
    assert res["verdict"] == "printable_with_supports" and f and f[0]["value"] == pytest.approx(20, abs=0.5)
    assert f[0]["support_height_mm"] == pytest.approx(10, abs=0.5) and f[0]["support_on"] == "part"
    res = check_printing(path, supports=False)
    f = _rules(res, "bridge")
    assert res["verdict"] == "not_printable" and f and f[0]["value"] == pytest.approx(20, abs=0.5)


def test_cantilever_shelf_is_overhang(tmp_path):
    part = Box(10, 10, 20, align=A) + Pos(10, 0, 17) * Box(10, 10, 3, align=A)
    path = _step(part, tmp_path)
    res = check_printing(path)
    f = _rules(res, "needs_support")
    assert res["verdict"] == "printable_with_supports" and f[0]["value"] == 90
    assert f[0]["support_height_mm"] == pytest.approx(17, abs=0.5) and f[0]["support_on"] == "bed"
    res = check_printing(path, supports=False)
    assert res["verdict"] == "not_printable" and _rules(res, "overhang")[0]["value"] == 90


def test_build_volume(tmp_path):
    path = _step(Box(240, 20, 5, align=A), tmp_path)
    assert check_printing(path, printer="prusa_mk4")["verdict"] == "printable"
    res = check_printing(path, printer="prusa_mini")
    assert res["verdict"] == "not_printable" and _rules(res, "build_volume")[0]["severity"] == "fail"


def test_build_dir_changes_the_answer(results):
    _, _, path = results["p01_overhang_60"]
    # Lying on its back face (-X down): the lip underside now faces sideways/up, no overhang.
    res = check_printing(path, build_dir=(1, 0, 0))
    assert not [f for f in _rules(res, "needs_support") + _rules(res, "overhang") if f["value"] > 50], res["findings"]


def test_flip_setup_fixes_tslot_listing(results):
    _, _, path = results["m04_tslot"]
    res = check_cnc(path, setups=[(0, 0, 1), (0, 1, 0)])
    assert not _rules(res, "undercut")


def test_two_sided_part_needs_two_setups(tmp_path):
    part = Box(40, 40, 20, align=A) - Pos(0, 0, 10) * extrude(RectangleRounded(20, 20, 3), amount=10) \
        - extrude(RectangleRounded(20, 20, 3), amount=5)
    path = _step(part, tmp_path)
    one = check_cnc(path)
    assert one["verdict"] == "not_machinable" and one["summary"]["setups_needed"] == 2
    two = check_cnc(path, setups=[(0, 0, 1), (0, 0, -1)])
    assert two["verdict"] == "machinable", two["findings"]


def test_tiny_corner_radius_below_practical_tool(tmp_path):
    part = Box(40, 40, 10, align=A) - Pos(0, 0, 8) * extrude(RectangleRounded(20, 20, 0.3), amount=2)
    res = check_cnc(_step(part, tmp_path))
    f = _rules(res, "inside_corner_radius")
    assert res["verdict"] == "not_machinable" and f[0]["value"] == pytest.approx(0.3)


def test_thin_wall_cnc(tmp_path):
    part = Box(20.6, 20, 10, align=A) - Pos(0, 0, 2) * extrude(RectangleRounded(20, 30, 3), amount=8)
    res = check_cnc(_step(part, tmp_path))
    f = _rules(res, "thin_wall")
    assert f[0]["severity"] == "fail" and f[0]["value"] == pytest.approx(0.3, abs=0.02)


def test_cli(results, capsys):
    _, _, p = results["p01_overhang_60"]
    assert cli(["printing", str(p), "--up", "0", "0", "1"]) == 0
    out = capsys.readouterr().out
    assert "PRINTABLE_WITH_SUPPORTS" in out and "needs_support" in out and "needs support" in out
    assert cli(["printing", str(p), "--no-supports"]) == 1
    assert "overhang" in capsys.readouterr().out
    _, _, m = results["m06_plate_control"]
    assert cli(["cnc", str(m), "--setups", "0,0,1", "--json"]) == 0
    assert '"verdict": "machinable"' in capsys.readouterr().out
