"""python -m goodman export: one JSON file for the presentation UI (ui/).

Reads every tasks/<area>/<id>/ folder (task.yaml, prompt.md, truth.yaml and,
when present, attempt*.json, claims.json, result.json), runs the area's checker
for its line-by-line calculation, and writes ui/public/data.json.

Read-only with respect to tasks/: nothing in a task folder is created or edited.
Missing files are fine: the UI shows the task as "pending".
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import verdict as V
from .checkers import CHECKERS


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _latest_attempt(d: Path) -> tuple[dict | None, str | None]:
    """attempt.json, or the highest attempt-N.json if a run was redone (specs/01)."""
    numbered = []
    for p in d.glob("attempt-*.json"):
        m = re.fullmatch(r"attempt-(\d+)\.json", p.name)
        if m:
            numbered.append((int(m.group(1)), p))
    if numbered:
        p = max(numbered)[1]
    elif (d / "attempt.json").exists():
        p = d / "attempt.json"
    else:
        return None, None
    return _read_json(p), p.name


def _checker(task: dict):
    """Run the area's checker if one is registered. Returns a plain dict or None."""
    if task["area"] not in CHECKERS:
        return None
    try:
        _, res = V.run_checker(task)
    except Exception as e:  # a broken checker must not break the whole export
        return {"error": f"{type(e).__name__}: {e}"}
    return {
        "model": res.model,
        "verdict": res.verdict,
        "values": {k: float(v) for k, v in res.values.items()},
        "steps": list(res.steps),
        "notes": list(res.notes),
    }


def _scene(task: dict, checker: dict | None, truth: dict) -> dict:
    """Numbers the 3D view needs, taken from task inputs and the checker's values."""
    inp = task.get("inputs") or {}
    vals = (checker or {}).get("values") or {}
    tv = {k: v.get("value") for k, v in (truth.get("values") or {}).items()}
    area = task["area"]
    if area == "strength":
        model = (checker or {}).get("model") or task.get("model")
        s = {"kind": model}
        if model in ("cantilever_root_fillet", "cantilever_step"):
            sec = inp["section"]
            if "depth_mm" in sec:
                b, h = sec["thickness_mm"], sec["depth_mm"]
            else:
                b, h = sec["width_mm"], sec["thickness_mm"]
            s.update(length_mm=inp["lever_mm"], width_mm=b, depth_mm=h, load_n=inp["load_n"],
                     fillet_mm=inp.get("fillet_mm") or (inp.get("step") or {}).get("r_mm"),
                     step=inp.get("step"), material=inp.get("material"),
                     kt=vals.get("stress_concentration_kt"), sigma_nom=vals.get("nominal_stress_mpa"),
                     sigma_max=vals.get("max_stress_mpa"), strength=vals.get("material_strength_mpa"),
                     safety_factor=vals.get("safety_factor"),
                     required_sf=inp.get("required_safety_factor"))
        elif model == "column":
            s.update(length_mm=inp["length_mm"], diameter_mm=inp["diameter_mm"], load_n=inp["load_n"],
                     sigma=vals.get("max_stress_mpa"), buckling_load_n=vals.get("buckling_load_n"),
                     strength=vals.get("material_strength_mpa"), safety_factor=vals.get("safety_factor"),
                     end_condition=inp.get("end_condition"))
        elif model == "cantilever_fatigue":
            s.update(length_mm=inp["lever_mm"], diameter_mm=inp["diameter_mm"], load_n=inp["load_max_n"],
                     sigma_max=vals.get("max_stress_mpa"), strength=vals.get("material_strength_mpa"),
                     required_sf=inp.get("required_safety_factor"))
        elif model == "simple_beam":
            sec = inp["section"]
            s.update(span_mm=inp["span_mm"], width_mm=sec["width_mm"], depth_mm=sec["depth_mm"], load_n=inp["load_n"],
                     E_mpa=inp["E_mpa"], sigma_max=vals.get("max_stress_mpa"), strength=vals.get("material_strength_mpa"),
                     required_sf=inp.get("required_safety_factor"))
        elif model == "thermal_column":
            s.update(length_mm=inp["length_mm"], diameter_mm=inp["diameter_mm"], sigma=vals.get("thermal_stress_mpa"),
                     strength=vals.get("material_strength_mpa"))
        elif model == "arm_torque":
            s.update(arm_length_mm=inp["arm_length_mm"], arm_mass_kg=inp.get("arm_mass_kg", 0),
                     tip_mass_kg=inp.get("tip_mass_kg", 0), stall_kgcm=inp["stall_torque_kgcm"],
                     required_kgcm=vals.get("required_torque_kgcm"), margin=vals.get("torque_margin"),
                     required_margin=inp.get("required_margin"))
        return s
    # collision: geometry straight from the task, contact numbers from the truth
    # (or a collision checker's values, once one is registered)
    merged = {**tv, **vals}
    return {"kind": task["id"].split("-", 1)[1], "inputs": inp,
            "collision_angle_deg": merged.get("collision_angle_deg"),
            "min_clearance_mm": merged.get("min_clearance_mm")}


def _task_record(d: Path) -> dict:
    task, truth = V.load_task(d)
    prompt = (d / "prompt.md").read_text().strip() if (d / "prompt.md").exists() else ""
    attempt, attempt_file = _latest_attempt(d)
    claims = _read_json(d / "claims.json")
    result = _read_json(d / "result.json")
    checker = _checker(task)

    result_source = "result.json" if result else None
    if result is None and claims is not None and task["area"] in CHECKERS:
        try:  # computed in memory only; result.json is written by `goodman check`
            result = V.evaluate(d, claims)
            result_source = "computed at export (not yet saved by goodman check)"
        except Exception:
            result = None

    if checker is None:  # no checker for this area yet: show the hand calc from truth.yaml
        steps = [ln.strip() for ln in (truth.get("why") or "").splitlines() if ln.strip()]
        check = {"source": "truth.yaml hand calc (collision checker not registered yet)",
                 "model": None, "verdict": truth.get("verdict"), "steps": steps, "notes": [],
                 "values": {k: v.get("value") for k, v in (truth.get("values") or {}).items()}}
    else:
        check = {"source": f"goodman truth ({task['area']} checker)", **checker}

    return {
        "id": task["id"],
        "area": task["area"],
        "title": task.get("title", task["id"]),
        "trap": task.get("trap"),
        "control": bool(task.get("control")),
        "inputs": task.get("inputs") or {},
        "prompt": prompt,
        "truth": {
            "verdict": truth.get("verdict"),
            "values": truth.get("values") or {},
            "must_mention": truth.get("must_mention") or [],
            "why": truth.get("why"),
            "source": truth.get("source"),
        },
        "check": check,
        "attempt": None if attempt is None else {
            "file": attempt_file,
            "model": attempt.get("model"),
            "interface": attempt.get("interface"),
            "date": attempt.get("date"),
            "answer": attempt.get("answer", ""),
            "notes": attempt.get("notes"),
        },
        "claims": claims,
        "result": result,
        "result_source": result_source,
        "outcome": (result or {}).get("outcome", "pending"),
        "scene": _scene(task, checker if checker and "error" not in checker else None, truth),
    }


def build(root: Path) -> dict:
    tasks = [_task_record(p.parent) for p in sorted(Path(root).glob("tasks/*/*/task.yaml"))]
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tasks": tasks}


def cmd_export(args) -> int:
    root = Path(args.root)
    data = build(root)
    out = Path(args.out) if args.out else root / "ui" / "public" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for t in data["tasks"]:
        counts[t["outcome"]] = counts.get(t["outcome"], 0) + 1
    print(f"wrote {out}: {len(data['tasks'])} tasks ({', '.join(f'{v} {k}' for k, v in sorted(counts.items()))})")
    return 0
