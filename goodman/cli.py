"""python -m goodman check|truth|report|export|motion

  check  <task_dir>...  compare the task's claims.json with Goodman's check -> result.json
  truth  <task_dir>...  print Goodman's own calculation and verdict (no AI involved)
  report                write results/summary.md from every tasks/*/*/result.json
  export [--out PATH]   write ui/public/data.json for the presentation UI (ui/)
  motion <glb> <joints> range-of-motion collision check for a Mechy assembly
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from . import verdict as V

OUTCOMES = ["accepted", "caught", "false_alarm", "missed"]


def cmd_check(args) -> int:
    rc = 0
    results_dir = Path(args.root) / "results"
    for d in map(Path, args.task_dirs):
        claims_path = d / "claims.json"
        if not claims_path.exists():
            print(f"{d}: no claims.json yet. Run the AI (attempt.json), extract and review its claims "
                  f"(specs/02-claims.md), then re-run `python -m goodman check {d}`.", file=sys.stderr)
            rc = 2
            continue
        claims = json.loads(claims_path.read_text())
        result = V.evaluate(d, claims)
        paths = V.write_result(d, result, results_dir)
        print(f"{result['task_id']}: {result['outcome']}  (AI said {result['ai_verdict']}, truth {result['true_verdict']})")
        for c in result["claims"]:
            print(f"  [{c['status']}] {c['id']}: {c['why']}")
        for m in result["missing"]:
            print(f"  [missing] {m['topic']}: {m['why']}")
        print(f"  wrote {', '.join(map(str, paths))}")
    return rc


def cmd_truth(args) -> int:
    rc = 0
    for d in map(Path, args.task_dirs):
        task, truth = V.load_task(d)
        _, res = V.run_checker(task)
        print(f"== {task['id']}  ({task['area']}, model {res.model})")
        for s in res.steps:
            print(f"   {s}")
        for n in res.notes:
            print(f"   note: {n}")
        agree = V.normalize_verdict(res.verdict) == V.normalize_verdict(truth.get("verdict"))
        print(f"   verdict: {res.verdict}   truth.yaml: {truth.get('verdict')}   {'AGREE' if agree else 'DISAGREE'}")
        for q, tv in (truth.get("values") or {}).items():
            mine = res.values.get(q)
            if mine is None:
                print(f"   {q}: truth {tv['value']}, not computed by checker")
                continue
            ok = V._rel(mine, tv["value"]) <= tv["tol"]
            print(f"   {q}: goodman {V._fmt(mine)}  truth {tv['value']} (tol {tv['tol']:.0%})  {'ok' if ok else 'OUT OF TOLERANCE'}")
            agree = agree and ok
        rc = rc or (0 if agree else 1)
    return rc


def cmd_report(args) -> int:
    root = Path(args.root)
    rows, counts = [], {}
    for task_yaml in sorted(root.glob("tasks/*/*/task.yaml")):
        d = task_yaml.parent
        area = d.parent.name
        counts.setdefault(area, Counter())
        rp = d / "result.json"
        if not rp.exists():
            rows.append(f"| {area} | {d.name} | not run | | | |")
            continue
        r = json.loads(rp.read_text())
        counts[area][r["outcome"]] += 1
        refuted = sum(c["status"] == "refuted" for c in r["claims"])
        first = next((c["why"] for c in r["claims"] if c["status"] == "refuted"), None) \
            or next((m["why"] for m in r["missing"]), "")
        rows.append(f"| {area} | {r['task_id']} | {r['outcome']} | {r['ai_verdict']} | {r['true_verdict']} | "
                    f"{refuted} refuted; {first.replace('|', '/')} |")
    lines = ["# Results", "", "## Outcomes by area", "",
             "| Area | " + " | ".join(OUTCOMES) + " |", "|---|" + "---|" * len(OUTCOMES)]
    total = Counter()
    for area, c in counts.items():
        total.update(c)
        lines.append(f"| {area} | " + " | ".join(str(c[o]) for o in OUTCOMES) + " |")
    lines.append("| **total** | " + " | ".join(str(total[o]) for o in OUTCOMES) + " |")
    lines += ["", "accepted and caught are good (right answer accepted, wrong answer caught); "
              "false_alarm and missed are Goodman's errors.", "",
              "## Per task", "", "| Area | Task | Outcome | AI verdict | True verdict | Key finding |",
              "|---|---|---|---|---|---|", *rows, ""]
    out = root / "results" / "summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"wrote {out}")
    return 0


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _neighbour(explicit: str | None, glb: Path, name: str) -> Path | None:
    if explicit:
        return Path(explicit)
    p = glb.parent / name
    return p if p.exists() else None


def run_motion(args: argparse.Namespace) -> int:
    from goodman.motion.collide import CollisionWorld
    from goodman.motion.inputs import (check_consistency, load_allow_contact, load_joints, load_parts,
                                       load_reach_constants)
    from goodman.motion.kinematics import Kinematics
    from goodman.motion.pairs import plan_pairs
    from goodman.motion.reach import ReachRule
    from goodman.motion.report import summary_lines, write_result
    from goodman.motion.sweep import sweep

    def log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    glb, jy = Path(args.glb), Path(args.joints)
    asm = _neighbour(args.assembly, glb, "assembly.yaml")
    geo = _neighbour(args.geometry, glb, "geometry.py")
    try:
        consts = load_reach_constants(geo) if geo else None
        allow = load_allow_contact(asm) if asm else set()
        motion = load_joints(jy)
        parts = load_parts(glb)
        check_consistency(glb, motion, parts)
        kin = Kinematics(motion, parts.keys())
        rule = ReachRule(kin, consts) if consts else None
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    log(f"inputs: {glb.name}, {jy.name}, assembly.yaml={'yes' if asm else 'no'}, "
        f"geometry.py={'yes (reach rule on)' if consts else 'yes, no reach constants (full joint-limit box)' if geo else 'no (full joint-limit box)'}")
    world = CollisionWorld(parts)
    plan = plan_pairs(kin, world, parts, allow)
    log(f"pairs: {plan.stats}")
    result = sweep(kin, world, plan, rule, motion.poses, n_halton=args.halton, progress=log)
    meta = {
        "inputs": {"glb": str(glb), "joints": str(jy), "assembly_yaml": str(asm) if asm else None,
                   "geometry_py": str(geo) if geo else None, "glb_sha256": _sha(glb), "joints_sha256": _sha(jy),
                   "reach_rule": vars(consts) if consts else None},
        "swept_joints": {j: list(kin.limits[j]) for j in kin.independent},
    }
    res = write_result(Path(args.out), result, meta, kin, parts)
    print("\n".join(summary_lines(res)))
    return 1 if res["collisions"] else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="goodman", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="repo root (default: current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("check", cmd_check), ("truth", cmd_truth)):
        sp = sub.add_parser(name)
        sp.add_argument("task_dirs", nargs="+")
        sp.set_defaults(fn=fn)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    from .export import cmd_export
    ep = sub.add_parser("export")
    ep.add_argument("--out", default=None, help="output path (default: ui/public/data.json)")
    ep.set_defaults(fn=cmd_export)
    m = sub.add_parser("motion", help="range-of-motion collision check for a Mechy assembly")
    m.add_argument("glb")
    m.add_argument("joints")
    m.add_argument("--assembly", help="Mechy assembly.yaml (allow_contact); default: next to the GLB")
    m.add_argument("--geometry", help="Mechy geometry.py (reach rule); default: next to the GLB")
    m.add_argument("--out", default="motion-out")
    m.add_argument("--halton", type=int, default=20000, help="reachable samples for 3+ joint pairs")
    m.set_defaults(fn=run_motion)
    args = p.parse_args(argv)
    return args.fn(args)
