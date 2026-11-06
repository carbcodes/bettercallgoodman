"""Sanity checks for the generated strength cases (tasks/strength/g*).

Fails (exit 1) if any case:
  * is missing prompt.md / task.yaml / truth.yaml, or a YAML file doesn't parse
  * disagrees with `python -m goodman truth` (verdict or any value out of tolerance)
  * has a prompt.md that names the trap (buckling, fatigue, stress concentration, Kt, layer, ...)
  * is borderline: the governing safety factor (or torque margin, or deflection ratio) sits
    within 15% of the requirement, or the verdict flips when any one numeric input (or the
    material property the checker reads from goodman/materials.yaml) moves by +/-15%, or under
    a reasonable alternative method (Kt +/-10%, Gerber instead of Goodman, design-recommended
    column K factors)
and fails if controls are under 25% or over 35% of the cases, or a model has fewer than 12.

Usage: python scripts/check_cases.py [--quiet]
"""

from __future__ import annotations

import contextlib
import copy
import io
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from goodman import cli  # noqa: E402
from goodman.checkers import strength  # noqa: E402
from goodman.verdict import normalize_verdict  # noqa: E402

FILES = ("prompt.md", "task.yaml", "truth.yaml")
TASK_KEYS = {"id", "area", "model", "title", "trap", "control", "inputs"}
TRUTH_KEYS = {"verdict", "values", "why"}
BANNED = [r"buckl\w*", r"fatigue", r"stress concentrations?", r"layers?", r"interlayer",
          r"endurance", r"goodman", r"gerber", r"euler", r"johnson", r"weak[- ]axis", r"strong[- ]axis",
          r"thermal stress", r"infinite life", r"s-n curve", r"stress raiser", r"notch\w*", r"anisotrop\w*",
          r"slender\w*", r"usable torque", r"unit conversion"]
BANNED_RE = re.compile("|".join(f"(?:\\b{b})" for b in BANNED), re.IGNORECASE)
BANNED_CASE = re.compile(r"\bKt\b")  # case-sensitive (don't flag 'kt' inside other words)
PERTURB = 0.15
MARGIN = 0.15
MIN_PER_MODEL = 12
CONTROL_RANGE = (0.25, 0.35)
MAT_KEYS = ("E_mpa", "yield_mpa", "ultimate_mpa", "in_layer_strength_mpa", "across_layer_strength_mpa")
DESIGN_K = {"pinned_pinned": 1.0, "fixed_fixed": 0.65, "fixed_pinned": 0.8, "fixed_free": 2.1}  # AISC recommended


def numeric_paths(d, prefix=()):
    for k, v in d.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            yield prefix + (k,)
        elif isinstance(v, dict):
            yield from numeric_paths(v, prefix + (k,))


def set_path(d, path, value):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value


def get_path(d, path):
    for k in path:
        d = d[k]
    return d


def run(model, inp, mats):
    return strength.MODELS[model](inp, mats)


def criteria(model, inp, res):
    """(name, capacity/demand ratio relative to the requirement) for each pass/fail criterion."""
    v = res.values
    if model == "arm_torque":
        return [("torque margin", v["torque_margin"] / float(inp.get("required_margin", 1.0)))]
    out = [("safety factor", v["safety_factor"] / float(inp.get("required_safety_factor", 1.0)))]
    if model == "simple_beam" and inp.get("max_deflection_mm") is not None:
        out.append(("deflection", float(inp["max_deflection_mm"]) / v["deflection_mm"]))
    return out


def alternative_verdicts(model, inp, mats, res):
    """Verdicts under reasonable alternative methods."""
    out = []
    v = res.values
    if model in ("cantilever_root_fillet", "cantilever_step"):
        req = float(inp.get("required_safety_factor", 1.0))
        for f in (1.1, 1 / 1.1):
            kt = max(1.0, v["stress_concentration_kt"] * f)
            sf = v["material_strength_mpa"] / (kt * v["nominal_stress_mpa"])
            out.append((f"Kt x{f:.2f}", "safe" if sf >= req else "not_safe"))
    if model == "cantilever_fatigue":
        req = float(inp.get("required_safety_factor", 1.0))
        gerber = next(val for val, why in res.alternatives["fatigue_safety_factor"] if "Gerber" in why)
        sf = min(v["static_safety_factor"], gerber)
        out.append(("Gerber", "safe" if sf >= req else "not_safe"))
    if model in ("column", "thermal_column"):
        saved = dict(strength.K_FACTORS)
        try:
            strength.K_FACTORS.clear()
            strength.K_FACTORS.update(DESIGN_K)
            out.append(("design K (AISC)", run(model, inp, mats).verdict))
        finally:
            strength.K_FACTORS.clear()
            strength.K_FACTORS.update(saved)
    return out


def check_case(d: Path, mats: dict) -> tuple[list[str], dict]:
    errs, info = [], {}
    for f in FILES:
        if not (d / f).exists():
            errs.append(f"missing {f}")
    if errs:
        return errs, info
    try:
        task = yaml.safe_load((d / "task.yaml").read_text())
        truth = yaml.safe_load((d / "truth.yaml").read_text())
    except yaml.YAMLError as e:
        return [f"YAML does not parse: {e}"], info
    if missing := TASK_KEYS - set(task):
        errs.append(f"task.yaml missing {sorted(missing)}")
    if missing := TRUTH_KEYS - set(truth):
        errs.append(f"truth.yaml missing {sorted(missing)}")
    if errs:
        return errs, info
    if task["id"] != d.name:
        errs.append(f"id {task['id']} != folder name")
    if task["area"] != "strength" or task["model"] not in strength.MODELS:
        errs.append(f"bad area/model {task['area']}/{task['model']}")
        return errs, info
    model, inp = task["model"], task["inputs"]
    tag = re.match(r"\[([a-z_]+)\]", str(task["trap"]))
    info.update(model=model, control=bool(task["control"]), trap=tag.group(1) if tag else "?", verdict=truth["verdict"])

    # 1. goodman truth must agree
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["truth", str(d)])
    if rc != 0:
        errs.append("goodman truth disagrees:\n      " + buf.getvalue().strip().replace("\n", "\n      "))

    # 2. prompt must not name the trap
    prompt = (d / "prompt.md").read_text()
    hits = sorted({m.group(0).lower() for m in BANNED_RE.finditer(prompt)} | set(BANNED_CASE.findall(prompt)))
    if hits:
        errs.append(f"prompt mentions trap words: {hits}")

    # 3. not borderline
    base = run(model, inp, mats)
    bv = normalize_verdict(base.verdict)
    if task["control"] and bv != "safe":
        errs.append("control case is not safe")
    if not task["control"] and bv == "safe":
        errs.append("trap case is safe (should be a control)")
    crit = criteria(model, inp, base)
    for name, ratio in crit:
        if abs(ratio - 1) < MARGIN:
            errs.append(f"borderline: {name} is {ratio:.2f}x the requirement (within {MARGIN:.0%})")
    worst = (min(abs(r - 1) for _, r in crit), "baseline")
    for path in numeric_paths(inp):
        x = get_path(inp, path)
        for s in (1 - PERTURB, 1 + PERTURB):
            p = copy.deepcopy(inp)
            set_path(p, path, x * s)
            r = run(model, p, mats)
            if normalize_verdict(r.verdict) != bv:
                errs.append(f"borderline: {'.'.join(path)} x{s:.2f} flips the verdict to {r.verdict}")
            worst = min(worst, (min(abs(q - 1) for _, q in criteria(model, p, r)), f"{'.'.join(path)} x{s:.2f}"))
    mat_name = inp.get("material")
    if mat_name in mats:
        for k in MAT_KEYS:
            if k in mats[mat_name] and k not in inp:
                for s in (1 - PERTURB, 1 + PERTURB):
                    m2 = copy.deepcopy(mats)
                    m2[mat_name][k] *= s
                    r = run(model, inp, m2)
                    if normalize_verdict(r.verdict) != bv:
                        errs.append(f"borderline: materials.yaml {mat_name}.{k} x{s:.2f} flips the verdict to {r.verdict}")
    for name, v in alternative_verdicts(model, inp, mats, base):
        if normalize_verdict(v) != bv:
            errs.append(f"borderline: alternative method ({name}) gives {v}")
    info["ratio"] = crit[0][1]
    info["worst"] = worst
    return errs, info


def main(argv=None) -> int:
    quiet = "--quiet" in (argv or sys.argv[1:])
    mats = strength.load_materials()
    dirs = sorted(p for p in (ROOT / "tasks" / "strength").glob("g*") if p.is_dir())
    failed, infos = 0, []
    for d in dirs:
        errs, info = check_case(d, mats)
        infos.append(info)
        if errs:
            failed += 1
            print(f"FAIL {d.name}")
            for e in errs:
                print(f"    {e}")
        elif not quiet:
            print(f"ok   {d.name:<40} {info['model']:<23} {info['verdict']:<9} "
                  f"{'control' if info['control'] else info['trap']:<21} SF/req {info['ratio']:.2f}  "
                  f"closest to the line: {info['worst'][1]} ({info['worst'][0]:.0%} away)")
    n = len(dirs)
    problems = []
    if n == 0:
        problems.append("no tasks/strength/g* cases found")
    models = Counter(i.get("model") for i in infos)
    traps = Counter(i.get("trap") for i in infos if not i.get("control"))
    controls = sum(bool(i.get("control")) for i in infos)
    frac = controls / n if n else 0
    if n and not CONTROL_RANGE[0] <= frac <= CONTROL_RANGE[1]:
        problems.append(f"controls are {frac:.0%} of cases (need {CONTROL_RANGE[0]:.0%}-{CONTROL_RANGE[1]:.0%})")
    for m in strength.MODELS:
        if models[m] < MIN_PER_MODEL:
            problems.append(f"model {m} has {models[m]} cases (need >= {MIN_PER_MODEL})")
    print()
    print(f"cases: {n}   controls: {controls} ({frac:.0%})   failed: {failed}")
    print("per model: " + ", ".join(f"{m} {models[m]}" for m in strength.MODELS))
    print("per trap (non-control): " + ", ".join(f"{t} {c}" for t, c in sorted(traps.items(), key=lambda x: -x[1])))
    for p in problems:
        print(f"FAIL {p}")
    ok = failed == 0 and not problems
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
