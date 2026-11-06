"""python -m goodman check|truth|report

  check  <task_dir>...  compare the task's claims.json with Goodman's check -> result.json
  truth  <task_dir>...  print Goodman's own calculation and verdict (no AI involved)
  report                write results/summary.md from every tasks/*/*/result.json
  export [--out PATH]   write ui/public/data.json for the presentation UI (ui/)
"""

from __future__ import annotations

import argparse
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
    args = p.parse_args(argv)
    return args.fn(args)
