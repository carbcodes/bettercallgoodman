"""python -m goodman.design check tasks/cad/<id>...   (see goodman/design/__init__.py)"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from . import runner
from .strength import analyze, describe

SF_RE = re.compile(r"safety factor[^0-9\n]{0,60}?(\d+(?:\.\d+)?)", re.I)


def latest_attempt(d: Path) -> dict | None:
    files = sorted(d.glob("attempt*.json"), key=lambda p: (len(p.stem), p.stem))
    for f in reversed(files):
        a = json.loads(f.read_text())
        if a.get("answer"):
            a["_file"] = f.name
            return a
    return None


def claimed_sf(answer: str) -> tuple[float | None, str]:
    """The safety factor the AI says to expect: the first one in its closing summary."""
    tail = answer[-1500:]
    m = SF_RE.search(tail) or SF_RE.search(answer)
    return (float(m.group(1)), m.group(0)) if m else (None, "")


def _write_mesh(step: Path, out: Path) -> None:
    """Triangles of the part for the 3D view (positions in mm, rounded)."""
    from build123d import import_step
    verts, tris = import_step(str(step)).tessellate(0.2, 0.3)
    out.write_text(json.dumps({"v": [round(c, 2) for v in verts for c in (v.X, v.Y, v.Z)],
                               "t": [i for t in tris for i in t]}))


def check(d: Path) -> dict:
    task = yaml.safe_load((d / "task.yaml").read_text())
    inp = task["inputs"]
    a = latest_attempt(d)
    if a is None:
        return {"task_id": task["id"], "outcome": "pending", "why": "no AI answer yet"}
    script = (d / "attempt_script.py").read_text() if (d / "attempt_script.py").exists() else \
        runner.script_from_answer(a["answer"], a.get("code"))
    step, log = runner.run(script, keep_dir=d)
    sf_claim, quote = claimed_sf(a["answer"])
    base = {"task_id": task["id"], "attempt": a["_file"], "ai_verdict": "safe", "claimed_sf": sf_claim,
            "claimed_quote": quote, "checker": "design", "checker_version": "0.1"}
    if step is None:
        return {**base, "outcome": "caught", "goodman_verdict": "no_part", "why": log, "requirements": [], "claims": []}
    r = analyze(step, inp)
    _write_mesh(step, d / "part.mesh.json")
    reqs = []
    bb = r.bbox
    if "max_reach_mm" in inp:
        reach = bb[3] - bb[0]
        reqs.append({"rule": "reach", "value": round(reach, 1), "limit": inp["max_reach_mm"], "ok": reach <= inp["max_reach_mm"] + 0.5})
    if "max_width_mm" in inp:
        width = bb[4] - bb[1]
        reqs.append({"rule": "width", "value": round(width, 1), "limit": inp["max_width_mm"], "ok": width <= inp["max_width_mm"] + 0.5})
    reqs.append({"rule": "one solid", "value": r.solids, "limit": 1, "ok": r.solids == 1})
    reqs.append({"rule": "safety factor", "value": round(r.sf, 2), "limit": inp["required_safety_factor"], "ok": r.verdict == "safe"})
    ok = all(q["ok"] for q in reqs)
    claims = []
    if sf_claim is not None:
        if abs(sf_claim - r.sf) <= 0.15 * r.sf:
            st = "confirmed"
        elif sf_claim < r.sf:
            st = "conservative"
        else:
            st = "refuted"
        claims.append({"id": "k1", "quantity": "safety_factor", "claimed": sf_claim, "actual": round(r.sf, 3),
                       "status": st, "quote": quote})
    crit = r.critical
    if crit:
        where = "at the wall-leg corner" if crit.kind == "leg" else f"{crit.at - r.bbox[0]:.0f} mm from the wall"
        how = "across layers" if "across layers" in crit.kt_note else ("yield" if "yield" in crit.kt_note else "along layers")
        short = (f"{'Holds' if ok else 'Breaks'} {where}: {crit.sigma:.0f} MPa vs {crit.strength:.0f} MPa {how}"
                 f"{' with a sharp corner' if 'sharp' in crit.kt_note and crit.kt > 1 else ''}. SF {r.sf:.2f}"
                 f"{f', AI claimed {sf_claim:g}' if sf_claim is not None else ''}.")
    else:
        short = "No load path found."
    if ok:
        why = f"Holds: worst section {describe(crit)}"
    else:
        bad = [q for q in reqs if not q["ok"]]
        why = "; ".join(f"{q['rule']} {q['value']} vs limit {q['limit']}" for q in bad if q["rule"] != "safety factor")
        if r.verdict != "safe" and crit:
            why = (why + "; " if why else "") + f"breaks at {describe(crit)} ({crit.kt_note})"
        if sf_claim is not None:
            why += f". The AI claimed SF {sf_claim:g}."
    return {**base, "outcome": "accepted" if ok else "caught", "goodman_verdict": "safe" if ok else "not_safe",
            "safety_factor": round(r.sf, 3), "lever_mm": round(r.lever_mm, 1), "load_point": [round(v, 2) for v in r.load_point],
            "bbox": bb, "volume_mm3": round(r.volume, 1), "notes": r.notes, "requirements": reqs, "claims": claims,
            "critical": describe(crit) if crit else None, "critical_note": crit.kt_note if crit else None,
            "why": short, "why_long": why,
            "sections": [{"kind": s.kind, "at": round(s.at, 2), "depth": round(s.depth, 2), "zc": round(s.centroid[2], 2),
                          "xc": round(s.centroid[0], 2), "c": round(s.c, 2), "sigma": round(s.sigma, 2),
                          "strength": s.strength, "sf": round(s.sf, 3)} for s in r.sections]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="goodman.design")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("task_dirs", nargs="+")
    args = p.parse_args(argv)
    for d in map(Path, args.task_dirs):
        res = check(d)
        (d / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
        print(f"{res['task_id']}: {res['outcome']}  {res.get('why', '')}")
        for q in res.get("requirements", []):
            print(f"   [{'ok' if q['ok'] else 'FAIL'}] {q['rule']}: {q['value']} (limit {q['limit']})")
        for k in res.get("claims", []):
            print(f"   [{k['status']}] AI claimed SF {k['claimed']} vs Goodman {k['actual']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
