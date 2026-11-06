"""Run an AI-written build123d script safely enough for a hackathon: read it first,
refuse anything that reaches outside a temp folder, then run it in a separate
`python -I` process with a time limit and collect the part.step it exports."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 90
ALLOWED_IMPORTS = {"build123d", "math", "numpy", "typing", "dataclasses", "itertools", "functools",
                   "collections", "enum", "copy", "__future__", "operator", "statistics"}
BLOCKED_CALLS = {"open", "exec", "eval", "compile", "__import__", "input", "getattr", "setattr", "globals", "vars"}
BAD_PATH = re.compile(r"^(/|~)|(^|/)\.\.(/|$)")


def script_from_answer(answer: str, code_blocks: list[str] | None = None) -> str | None:
    """The block that exports the part: prefer one calling export_step, else the last build123d block."""
    blocks = list(code_blocks or []) or re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", answer or "", re.S)
    for b in blocks:
        if "export_step" in b:
            return b
    b123 = [b for b in blocks if "build123d" in b]
    return b123[-1] if b123 else None


def reasons_not_to_run(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error, line {e.lineno}: {e.msg}"]
    why = []
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or "<relative>"]
        why += [f"line {node.lineno}: imports {m}" for m in mods if m.split(".")[0] not in ALLOWED_IMPORTS]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            why.append(f"line {node.lineno}: calls {node.func.id}()")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and BAD_PATH.search(node.value):
            why.append(f"line {node.lineno}: path outside its folder: {node.value[:40]!r}")
    return why


def run(code: str, keep_dir: Path | None = None) -> tuple[Path | None, str]:
    """Run the script in a fresh temp dir. Returns (STEP path, log). A refused or failed run gives (None, why)."""
    if not code:
        return None, "the answer contains no build123d script"
    refuse = reasons_not_to_run(code)
    if refuse:
        return None, "not run: " + "; ".join(refuse)
    work = Path(tempfile.mkdtemp(prefix="goodman-cad-"))
    (work / "script.py").write_text(code)
    try:
        p = subprocess.run([sys.executable, "-I", "script.py"], cwd=work, capture_output=True, text=True,
                           timeout=TIMEOUT_S, env={"PATH": "/usr/bin:/bin", "HOME": str(work)})
    except subprocess.TimeoutExpired:
        return None, f"script ran longer than {TIMEOUT_S} s"
    log = (p.stdout + p.stderr).strip()
    steps = sorted(work.glob("*.step")) + sorted(work.glob("*.stp"))
    if p.returncode != 0:
        last = log.splitlines()[-1] if log else f"exit code {p.returncode}"
        return None, f"script crashed: {last}"
    if not steps:
        return None, "script ran but wrote no .step file"
    step = steps[0]
    if keep_dir:
        keep_dir.mkdir(parents=True, exist_ok=True)
        step = Path(shutil.copy(step, keep_dir / "part.step"))
    return step, log
