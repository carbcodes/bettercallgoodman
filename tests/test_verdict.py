"""verdict.py on hand-written claim sets (tests/fixtures, never tasks/)."""
import json
from pathlib import Path

import pytest

from goodman.verdict import evaluate

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
CASES = sorted(p.name for p in FIX.iterdir() if p.is_dir())

SPEC_KEYS = {"task_id", "outcome", "ai_verdict", "true_verdict", "claims", "missing", "checker", "checker_version"}


def _run(case, kind):
    claims = json.loads((FIX / case / f"{kind}.json").read_text())
    return evaluate(ROOT / "tasks" / "strength" / case, claims)


@pytest.mark.parametrize("case", CASES)
def test_correct_claims_accepted(case):
    r = _run(case, "correct")
    assert set(r) == SPEC_KEYS
    assert r["outcome"] == "accepted", r
    assert all(c["status"] == "confirmed" for c in r["claims"]), r["claims"]
    assert r["missing"] == []


@pytest.mark.parametrize("case", CASES)
def test_wrong_claims_caught(case):
    r = _run(case, "wrong")
    assert r["outcome"] == "caught", r
    assert any(c["status"] == "refuted" for c in r["claims"])


def _why(r, cid):
    return next(c["why"] for c in r["claims"] if c["id"] == cid)


def test_whys_name_the_mistake():
    r = _run("s01-pla-speaker-bracket", "wrong")
    assert "missed the stress concentration" in _why(r, "k2")
    assert "across layers" in _why(r, "k3") and "across layers" in _why(r, "k4")
    assert [m["topic"] for m in r["missing"]] == ["layer_direction_strength"]

    r = _run("s02-aluminum-arm-step", "wrong")
    assert "Kt ~ 2.6" in _why(r, "k2") and "missed the stress concentration" in _why(r, "k3")

    r = _run("s03-steel-rod-brace", "wrong")
    assert _why(r, "k1").startswith("Within")  # the stress itself is right
    assert "checked compressive stress only" in _why(r, "k2") and "785 N" in _why(r, "k2")

    r = _run("s04-servo-shoulder", "wrong")
    assert "unit mix-up" in _why(r, "k1") and "unit mix-up" in _why(r, "k2")


def test_range_and_unknown_claims():
    claims = {"task_id": "s03-steel-rod-brace", "verdict": "not_safe", "mentions": ["buckling"], "claims": [
        {"id": "k1", "quantity": "buckling_load_n", "low": 700, "high": 800, "quote": "700-800 N"},
        {"id": "k2", "quantity": "fatigue_sf", "value": 3.0, "quote": "fatigue SF 3"},
    ]}
    r = evaluate(ROOT / "tasks" / "strength" / "s03-steel-rod-brace", claims)
    assert [c["status"] for c in r["claims"]] == ["confirmed", "cannot_check"]
    assert r["outcome"] == "accepted"


def test_unclear_verdict_is_wrong():
    claims = json.loads((FIX / "s05-steel-shelf-control" / "correct.json").read_text())
    claims["verdict"] = "unclear"
    r = evaluate(ROOT / "tasks" / "strength" / "s05-steel-shelf-control", claims)
    assert r["outcome"] == "caught"


def _shelf(verdict, sf):
    return {"task_id": "s05-steel-shelf-control", "verdict": verdict, "mentions": [],
            "claims": [{"id": "k1", "quantity": "safety_factor", "value": sf, "quote": "q"}]}


def test_cautious_number_with_right_verdict_passes():
    r = evaluate(ROOT / "tasks" / "strength" / "s05-steel-shelf-control", _shelf("safe", 3.0))
    assert r["claims"][0]["status"] == "conservative"
    assert r["outcome"] == "accepted"


def test_cautious_number_with_wrong_verdict_is_caught():
    r = evaluate(ROOT / "tasks" / "strength" / "s05-steel-shelf-control", _shelf("not_safe", 1.5))
    assert r["claims"][0]["status"] == "refuted"
    assert r["outcome"] == "caught"


def test_unsafe_side_error_still_refuted():
    r = evaluate(ROOT / "tasks" / "strength" / "s05-steel-shelf-control", _shelf("safe", 8.0))
    assert r["claims"][0]["status"] == "refuted"
    assert r["outcome"] == "caught"


def test_new_case_whys_name_the_mistake():
    r = _run("s06-feeder-spring-arm", "wrong")
    assert "checked static stress only" in _why(r, "k2") and "Goodman" in _why(r, "k2")
    assert [m["topic"] for m in r["missing"]] == ["fatigue"]

    r = _run("s07-flat-bar-shelf", "wrong")
    for cid in ("k2", "k3", "k4"):
        assert "strong axis" in _why(r, cid), _why(r, cid)

    r = _run("s08-heated-guide-rail", "wrong")
    assert "checked thermal stress only" in _why(r, "k2")
    assert [m["topic"] for m in r["missing"]] == ["buckling"]


def test_s08_pinned_ends_buckling_named():
    claims = {"task_id": "s08-heated-guide-rail", "verdict": "not_safe", "mentions": ["buckling"], "claims": [
        {"id": "k1", "quantity": "buckling_load_n", "value": 397, "quote": "P_cr = 397 N"}]}
    r = evaluate(ROOT / "tasks" / "strength" / "s08-heated-guide-rail", claims)
    assert r["claims"][0]["status"] == "conservative"  # low buckling load, right verdict
    assert "pinned_pinned" in r["claims"][0]["why"]
