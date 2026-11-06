"""Compare an AI's claims (claims.json) with Goodman's own computation and the
hand-written truth (truth.yaml); build result.json exactly as in specs/01.

Two independent judgements are made:
  * Goodman's decision (accept / reject) uses the CHECKER's computed values and
    verdict, with truth.yaml's tolerances and must_mention list.
  * Whether the AI was actually right uses truth.yaml's values and verdict
    (specs/01: verdict matches, every truth value it states is in tolerance,
    nothing in must_mention is missing).
Crossing the two gives the outcome: accepted / caught / false_alarm / missed.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .checkers import CHECKERS

# Tolerances for quantities that truth.yaml doesn't list (relative error).
DEFAULT_TOL = {
    "moment_nmm": 0.05, "load_n": 0.05, "material_strength_mpa": 0.15,
    "required_torque_nm": 0.05, "required_torque_kgcm": 0.05, "stall_torque_nm": 0.05,
}
FALLBACK_TOL = 0.10

# Verdict words that mean the same thing across tasks (specs/02 + servo wording).
_SYNONYMS = {
    "safe": "safe", "ok": "safe", "will_hold": "safe", "holds": "safe",
    "not_safe": "not_safe", "unsafe": "not_safe", "wont_hold": "not_safe", "will_not_hold": "not_safe",
    "fits": "fits", "does_not_fit": "does_not_fit", "doesnt_fit": "does_not_fit",
}


def normalize_verdict(v) -> str:
    if v is None:
        return "unclear"
    key = str(v).strip().lower().replace("'", "").replace("’", "").replace("-", "_").replace(" ", "_")
    return _SYNONYMS.get(key, key)


def load_task(task_dir: Path) -> tuple[dict, dict]:
    task = yaml.safe_load(open(task_dir / "task.yaml"))
    truth = yaml.safe_load(open(task_dir / "truth.yaml"))
    return task, truth


def run_checker(task: dict):
    mod = CHECKERS[task["area"]]
    return mod, mod.check(task)


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b) if b else abs(a - b)


def _within(claim: dict, actual: float, tol: float) -> bool:
    if "low" in claim or "high" in claim:
        lo = claim.get("low", claim.get("value"))
        hi = claim.get("high", claim.get("value"))
        return lo * (1 - tol) <= actual <= hi * (1 + tol) or _rel(lo, actual) <= tol or _rel(hi, actual) <= tol
    return _rel(float(claim["value"]), actual) <= tol


def _claimed(claim: dict):
    if "low" in claim or "high" in claim:
        return [claim.get("low"), claim.get("high")]
    return claim.get("value")


def _fmt(x: float) -> str:
    return f"{x:.3g}" if abs(x) < 1000 else f"{x:.0f}"


def _diagnose(claim: dict, actual: float, tol: float, alternatives: list) -> str:
    """Name the mistake: find the known-mistake value closest to the claim."""
    c = claim.get("value")
    if c is None:  # range: use its midpoint for diagnosis
        c = (claim.get("low", 0) + claim.get("high", 0)) / 2
    c = float(c)
    best = None
    for value, why in alternatives:
        if value and _rel(c, value) <= max(tol, 0.08):
            if best is None or _rel(c, value) < _rel(c, best[0]):
                best = (value, why)
    head = f"Claimed {_fmt(c)}, actual {_fmt(actual)}"
    if best:
        return f"{head}: {best[1]}"
    pct = (c - actual) / actual * 100 if actual else 0
    return f"{head} ({pct:+.0f}%)"


def evaluate(task_dir: Path, claims: dict) -> dict:
    task_dir = Path(task_dir)
    task, truth = load_task(task_dir)
    mod, res = run_checker(task)
    truth_values = truth.get("values") or {}

    out_claims = []
    goodman_reject = False
    ai_right = True

    for cl in claims.get("claims", []):
        q = cl.get("quantity")
        entry = {"id": cl.get("id"), "status": "cannot_check", "claimed": _claimed(cl), "actual": None, "why": ""}
        numeric = cl.get("value") is not None or "low" in cl or "high" in cl
        if not numeric or isinstance(cl.get("value"), bool):
            entry["why"] = f"Non-numeric claim for '{q}'; the {task['area']} checker only checks numbers"
        elif q in res.values or q in truth_values:
            actual = res.values.get(q, truth_values.get(q, {}).get("value"))
            tol = float(truth_values[q]["tol"]) if q in truth_values else DEFAULT_TOL.get(q, FALLBACK_TOL)
            entry["actual"] = round(float(actual), 4)
            if _within(cl, actual, tol):
                entry["status"] = "confirmed"
                entry["why"] = f"Within {tol:.0%} of Goodman's {_fmt(actual)}"
            else:
                entry["status"] = "refuted"
                entry["why"] = _diagnose(cl, actual, tol, res.alternatives.get(q, []))
                if q in truth_values:
                    goodman_reject = True
            # AI-right is judged against the hand-written truth, not the checker
            if q in truth_values and not _within(cl, float(truth_values[q]["value"]), float(truth_values[q]["tol"])):
                ai_right = False
        else:
            entry["why"] = f"Goodman does not model '{q}' for this task (model {res.model})"
        out_claims.append(entry)

    mentions = set(claims.get("mentions") or [])
    missing = [{"topic": t, "why": mod.MISSING_WHY.get(t, f"Answer never mentions {t}")}
               for t in (truth.get("must_mention") or []) if t not in mentions]

    ai_verdict = normalize_verdict(claims.get("verdict"))
    true_verdict = normalize_verdict(truth.get("verdict"))
    checker_verdict = normalize_verdict(res.verdict)

    if ai_verdict != checker_verdict or missing:
        goodman_reject = True
    if ai_verdict != true_verdict or missing:
        ai_right = False

    outcome = {(True, False): "accepted", (False, True): "caught",
               (True, True): "false_alarm", (False, False): "missed"}[(ai_right, goodman_reject)]

    return {
        "task_id": task["id"],
        "outcome": outcome,
        "ai_verdict": claims.get("verdict"),
        "true_verdict": truth.get("verdict"),
        "claims": out_claims,
        "missing": missing,
        "checker": task["area"],
        "checker_version": getattr(mod, "VERSION", "0.1"),
    }


def write_result(task_dir: Path, result: dict, results_dir: Path | None = None) -> list[Path]:
    paths = [Path(task_dir) / "result.json"]
    if results_dir is not None:
        results_dir.mkdir(parents=True, exist_ok=True)
        paths.append(results_dir / f"{result['task_id']}.json")
    for p in paths:
        p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return paths
