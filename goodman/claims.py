"""Claim extraction (specs/02): turn an AI's answer into claims.json.

  python -m goodman.claims prompt   <task_dir>               print the extraction prompt (answer only, no truth)
  python -m goodman.claims validate <task_dir> [--reviewed-by NAME]
                                    claims.draft.json -> claims.json (quotes verified, units converted)

The extractor is a different AI from the one being tested. It only reads the
answer in attempt.json; it never sees task.yaml or truth.yaml, and it never
judges whether a claim is right. Deciding that is the checkers' job.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

G = 9.81

# Quantities the checkers understand, per area: name -> (canonical unit, meaning).
QUANTITIES = {
    "strength": {
        "load_n": ("N", "the force the AI used for the load"),
        "moment_nmm": ("N·mm", "maximum bending moment"),
        "section_modulus_mm3": ("mm³", "section modulus Z"),
        "nominal_stress_mpa": ("MPa", "stress BEFORE any stress concentration factor, only if the answer gives both"),
        "stress_concentration_kt": ("", "stress concentration factor Kt"),
        "max_stress_mpa": ("MPa", "the highest stress the answer relies on for its verdict"),
        "material_strength_mpa": ("MPa", "the material strength (yield or tensile) the answer compares against"),
        "safety_factor": ("", "the overall safety factor / margin the verdict rests on"),
        "buckling_load_n": ("N", "critical buckling load"),
        "stress_safety_factor": ("", "safety factor against yield/strength only, if separate from buckling"),
        "buckling_safety_factor": ("", "safety factor against buckling, if given separately"),
        "required_torque_nm": ("N·m", "torque the load needs at the joint, WITHOUT any safety factor or margin"),
        "required_torque_with_margin_nm": ("N·m", "torque needed once the safety factor or margin is applied"),
        "stall_torque_nm": ("N·m", "the motor's rated/stall torque as the answer used it"),
        "torque_margin": ("", "available torque divided by required torque"),
        "deflection_mm": ("mm", "tip or maximum deflection"),
    },
    "collision": {
        "min_clearance_mm": ("mm", "smallest gap between parts; negative means overlap/interference"),
        "collision_angle_deg": ("deg", "angle at which parts first touch"),
        "reach_deg": ("deg", "how far the joint can move before contact"),
        "stack_height_mm": ("mm", "total height of a stack of parts"),
    },
}

VERDICTS = {
    "strength": ["safe", "not_safe", "will_hold", "wont_hold", "unclear"],
    "collision": ["fits", "does_not_fit", "unclear"],
}

# Topics we look for in every answer of an area. The same list for every task, so it leaks nothing.
MENTIONS = {
    "strength": {
        "stress_concentration": "a stress concentration factor (Kt) or stress raiser at a corner, fillet, step or hole",
        "layer_direction_strength": "3D-print layer orientation / weaker strength across layers",
        "buckling": "buckling of a compression member",
        "fatigue": "fatigue or cyclic loading",
        "unit_conversion": "converting between kg·cm and N·m (or similar torque units)",
    },
    "collision": {
        "part_thickness": "the thickness/height of a moving or stacked part, not just its centerline",
        "pcb_thickness": "the circuit board's own thickness in a height stack",
        "tip_diameter": "a gear's outside (tip) diameter rather than its pitch diameter",
        "head_height": "a screw head's height compared with the counterbore depth",
    },
}

# Unit -> (canonical unit, factor) for the conversions answers actually use.
UNITS = {
    "mpa": ("MPa", 1.0), "n/mm2": ("MPa", 1.0), "n/mm^2": ("MPa", 1.0), "n/mm²": ("MPa", 1.0),
    "gpa": ("MPa", 1000.0), "pa": ("MPa", 1e-6), "kpa": ("MPa", 1e-3), "psi": ("MPa", 0.00689476), "ksi": ("MPa", 6.89476),
    "n": ("N", 1.0), "kn": ("N", 1000.0), "lbf": ("N", 4.44822), "kgf": ("N", G), "kg": ("N", G),
    "n·mm": ("N·mm", 1.0), "nmm": ("N·mm", 1.0), "n·m": ("N·mm", 1000.0), "nm": ("N·mm", 1000.0),
    "kg·cm": ("N·mm", G * 10), "kgcm": ("N·mm", G * 10), "kgf·cm": ("N·mm", G * 10), "lbf·in": ("N·mm", 112.985),
    "mm": ("mm", 1.0), "cm": ("mm", 10.0), "m": ("mm", 1000.0), "in": ("mm", 25.4),
    "mm3": ("mm³", 1.0), "mm³": ("mm³", 1.0), "cm3": ("mm³", 1000.0), "cm³": ("mm³", 1000.0),
    "deg": ("deg", 1.0), "°": ("deg", 1.0), "degrees": ("deg", 1.0),
    "": ("", 1.0),
}
# Torque quantities are stored in N·m, so N·mm values get scaled once more.
TORQUE_NM = {"required_torque_nm", "required_torque_with_margin_nm", "stall_torque_nm"}

PROMPT = """You extract claims from an engineering answer. You do NOT judge whether anything is right.

Read the ANSWER below and return JSON only, no prose, in exactly this shape:
{{
  "verdict": one of {verdicts},
  "claims": [
    {{"id": "k1", "quantity": "<name from the table>", "value": <number>, "unit": "<unit as written>",
      "quote": "<exact sentence or phrase from the answer, copied character for character>"}}
  ],
  "mentions": [<topic names from the topic list that the answer discusses at all>],
  "notes": "<anything ambiguous, e.g. hedged verdicts or several values for one quantity>"
}}

Rules:
- verdict: the answer's final conclusion. If it never commits, use "unclear".
- One claim per quantity the answer actually states as a number. Use the value from its final summary when it gives several, and mention the others in notes.
- A range ("20-30 MPa") becomes "low" and "high" instead of "value".
- quote must appear verbatim in the answer (same characters, same symbols). Keep it short: the phrase that states the number.
- Never compute or infer a number the answer doesn't state. Never add quantities that aren't in the table.
- "unit" is the unit exactly as the answer wrote it (MPa, psi, N, kg·cm, N·m, mm, in, deg; "" for a plain ratio).

Quantities (name: meaning):
{quantities}

Topics (name: meaning):
{mentions}

ANSWER:
<<<
{answer}
>>>
"""


def _area(task_dir: Path) -> str:
    return task_dir.parent.name


def build_prompt(task_dir: Path) -> str:
    area = _area(task_dir)
    attempt = json.loads((task_dir / "attempt.json").read_text())
    q = "\n".join(f"- {k}: {m}" for k, (_, m) in QUANTITIES[area].items())
    t = "\n".join(f"- {k}: {m}" for k, m in MENTIONS[area].items())
    return PROMPT.format(verdicts=json.dumps(VERDICTS[area]), quantities=q, mentions=t, answer=attempt["answer"])


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("×", "x").replace("*", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _unit_key(u: str) -> str:
    u = unicodedata.normalize("NFKC", u or "").strip().lower()
    return u.replace(" ", "").replace("-", "·").replace("⋅", "·").replace(".", "·").replace("*", "·")


def convert(quantity: str, value: float, unit: str, area: str) -> tuple[float, str | None]:
    """Value in the quantity's canonical unit, or an error message."""
    want = QUANTITIES[area][quantity][0]
    key = _unit_key(unit)
    if key not in UNITS:
        return value, f"unknown unit '{unit}'"
    have, factor = UNITS[key]
    if quantity in TORQUE_NM:
        if have != "N·mm":
            return value, f"unit '{unit}' is not a torque"
        return value * factor / 1000.0, None
    if want in ("", "deg") and have == "":
        return value, None
    if have != want:
        return value, f"unit '{unit}' doesn't match {quantity} ({want or 'ratio'})"
    return value * factor, None


def validate(task_dir: Path, draft: dict, reviewed_by: str | None = None) -> tuple[dict, list[str]]:
    area = _area(task_dir)
    answer = _norm(json.loads((task_dir / "attempt.json").read_text())["answer"])
    problems, claims = [], []
    for i, cl in enumerate(draft.get("claims", []), 1):
        cid = cl.get("id") or f"k{i}"
        quote = cl.get("quote", "")
        if not quote or _norm(quote) not in answer:
            problems.append(f"{cid}: dropped, quote not found verbatim in the answer: {quote!r}")
            continue
        q = cl.get("quantity")
        out = {"id": cid, "quantity": q, "quote": quote, "unit_as_written": cl.get("unit", "")}
        if q not in QUANTITIES[area]:
            problems.append(f"{cid}: quantity '{q}' isn't one the {area} checker knows; kept as cannot_check")
            out.update({k: cl[k] for k in ("value", "low", "high") if k in cl})
            claims.append(out)
            continue
        for k in ("value", "low", "high"):
            if k in cl and cl[k] is not None:
                v, err = convert(q, float(cl[k]), cl.get("unit", ""), area)
                if err:
                    problems.append(f"{cid}: {err}; kept the number as written")
                out[k] = round(v, 6)
        claims.append(out)
    verdict = draft.get("verdict", "unclear")
    if verdict not in VERDICTS[area]:
        problems.append(f"verdict '{verdict}' isn't one of {VERDICTS[area]}")
    mentions = [m for m in draft.get("mentions", []) if m in MENTIONS[area]]
    result = {
        "task_id": task_dir.name,
        "verdict": verdict,
        "claims": claims,
        "mentions": mentions,
        "notes": draft.get("notes", ""),
        "extracted_by": draft.get("extracted_by", ""),
        "reviewed_by": reviewed_by,
    }
    return result, problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="goodman.claims", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("prompt")
    sp.add_argument("task_dir")
    sv = sub.add_parser("validate")
    sv.add_argument("task_dirs", nargs="+")
    sv.add_argument("--reviewed-by", default=None)
    args = p.parse_args(argv)
    if args.cmd == "prompt":
        print(build_prompt(Path(args.task_dir)))
        return 0
    rc = 0
    for d in map(Path, args.task_dirs):
        draft_path = d / "claims.draft.json"
        if not draft_path.exists():
            print(f"{d}: no claims.draft.json", file=sys.stderr)
            rc = 2
            continue
        result, problems = validate(d, json.loads(draft_path.read_text()), args.reviewed_by)
        (d / "claims.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(f"{d.name}: verdict {result['verdict']}, {len(result['claims'])} claims, mentions {result['mentions']}"
              f"{'' if args.reviewed_by else '  (NOT REVIEWED)'}")
        for pr in problems:
            print(f"  ! {pr}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
