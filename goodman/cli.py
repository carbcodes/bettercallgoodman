"""python -m goodman <command> ..."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


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
        f"geometry.py={'yes (reach rule on)' if consts else 'no (full joint-limit box)'}")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="goodman")
    sub = ap.add_subparsers(dest="command", required=True)
    m = sub.add_parser("motion", help="range-of-motion collision check for a Mechy assembly")
    m.add_argument("glb")
    m.add_argument("joints")
    m.add_argument("--assembly", help="Mechy assembly.yaml (allow_contact); default: next to the GLB")
    m.add_argument("--geometry", help="Mechy geometry.py (reach rule); default: next to the GLB")
    m.add_argument("--out", default="motion-out")
    m.add_argument("--halton", type=int, default=20000, help="reachable samples for 3+ joint pairs")
    args = ap.parse_args(argv)
    if args.command == "motion":
        return run_motion(args)
    return 2
