"""Design mode: run a build123d script, measure the part, check its strength."""
from pathlib import Path

import pytest

pytest.importorskip("build123d")

from goodman.design import runner
from goodman.design.strength import analyze

FIX = Path(__file__).resolve().parent / "fixtures_design"
PLA_SHELF = {"material": "PLA", "load_n": 19.62, "required_safety_factor": 2, "layer_normal": "z",
             "load_rule": "fixed_x", "load_x_mm": 150}


def _part(name):
    step, log = runner.run((FIX / f"{name}.py").read_text())
    assert step, log
    return step


def test_slices_match_closed_form_cantilever():
    # 100 x 20 x 6 block, 10 N at the tip: sigma at the wall = F L c / I = 10*100*3/360 = 8.33 MPa
    r = analyze(_part("block"), {"material": "Al6061-T6", "load_n": 10, "required_safety_factor": 2})
    assert r.critical.sigma == pytest.approx(10 * 100 * 3 / 360, rel=0.03)
    assert r.verdict == "safe"


def test_sharp_upright_pla_bracket_fails_across_layers():
    r = analyze(_part("l_sharp"), PLA_SHELF)
    assert r.verdict == "not_safe"
    assert r.critical.strength == 30          # across-layer PLA
    assert r.critical.kt > 2                   # sharp inside corner


def test_thick_filleted_bracket_passes():
    r = analyze(_part("l_fillet"), PLA_SHELF)
    assert r.verdict == "safe"
    assert "fillet" in r.critical.kt_note


@pytest.mark.parametrize("code", ["import os\nos.system('ls')", "open('/etc/passwd')", "import subprocess"])
def test_runner_refuses_unsafe_scripts(code):
    step, why = runner.run(code)
    assert step is None and why.startswith("not run")


def test_runner_reports_crash():
    step, why = runner.run("from build123d import *\nexport_step(undefined_part, 'part.step')")
    assert step is None and "NameError" in why
