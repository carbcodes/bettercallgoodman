"""Finding records and the result dict shared by both checkers."""

from __future__ import annotations

from .geom import rnd

SEVERITIES = ("fail", "warn", "info")


def finding(rule, value, limit, location, why, severity="fail", **extra) -> dict:
    assert severity in SEVERITIES
    f = {"rule": rule,
         "value": round(float(value), 3) if isinstance(value, (int, float)) else value,
         "limit": round(float(limit), 3) if isinstance(limit, (int, float)) else limit,
         "location": rnd(location) if location is not None else None,
         "why": why,
         "severity": severity}
    f.update(extra)
    return f


def result(checker, ok_word, bad_word, findings, **meta) -> dict:
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings = sorted(findings, key=lambda f: order[f["severity"]])
    fails = any(f["severity"] == "fail" for f in findings)
    return {"checker": checker, "verdict": bad_word if fails else ok_word, "findings": findings, **meta}


def format_text(res: dict) -> str:
    lines = [f"{res['checker']}: {res['verdict'].upper()}  ({res.get('file', '')})"]
    for f in res["findings"]:
        lines.append(f"  [{f['severity']}] {f['rule']}: {f['why']}")
    return "\n".join(lines)
