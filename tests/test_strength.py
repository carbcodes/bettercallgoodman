"""The checker's own answer must agree with the hand-written truth.yaml."""
import math
from pathlib import Path

import pytest
import yaml

from goodman.checkers import strength
from goodman.verdict import normalize_verdict

ROOT = Path(__file__).resolve().parent.parent
CASES = sorted(p.name for p in (ROOT / "tasks" / "strength").iterdir() if (p / "task.yaml").exists())


def _load(case):
    d = ROOT / "tasks" / "strength" / case
    return yaml.safe_load(open(d / "task.yaml")), yaml.safe_load(open(d / "truth.yaml"))


def test_five_cases_present():
    assert len(CASES) == 5


@pytest.mark.parametrize("case", CASES)
def test_verdict_matches_truth(case):
    task, truth = _load(case)
    res = strength.check(task)
    assert normalize_verdict(res.verdict) == normalize_verdict(truth["verdict"])


@pytest.mark.parametrize("case", CASES)
def test_values_within_truth_tolerance(case):
    task, truth = _load(case)
    res = strength.check(task)
    for q, tv in truth["values"].items():
        assert q in res.values, f"checker does not compute {q}"
        rel = abs(res.values[q] - tv["value"]) / abs(tv["value"])
        assert rel <= tv["tol"], f"{q}: checker {res.values[q]:.4g} vs truth {tv['value']} (rel {rel:.2%})"


def test_model_inferred_without_model_key():
    for case in CASES:
        task, _ = _load(case)
        assert strength.infer_model(task["inputs"]) == task["model"]


def test_sections():
    r = strength.rect_section(20, 6)
    assert r["Z"] == pytest.approx(120.0) and r["I"] == pytest.approx(360.0)
    c = strength.round_section(6)
    assert c["I"] == pytest.approx(math.pi * 6**4 / 64)


def test_kt_fit_known_point():
    # Peterson chart 3.10: D/d = 2, r/d = 0.1 in bending reads Kt ~1.9-2.0
    assert 1.85 <= strength.kt_shoulder_bending(2.0, 1.0, 0.1) <= 2.05
    assert strength.kt_shoulder_bending(1.0, 1.0, 0.1) == 1.0  # no step, no Kt


def test_johnson_for_stubby_column():
    A, I = strength.round_section(20)["A"], strength.round_section(20)["I"]
    p, mode, *_ = strength.column_critical_load(200000, 250, A, I, 100, 1.0)
    assert mode == "johnson" and p < 250 * A


def test_kgcm_conversion():
    assert 14.4 * strength.NM_PER_KGCM == pytest.approx(1.4126, rel=1e-3)
