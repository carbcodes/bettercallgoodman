import os
import subprocess
from pathlib import Path

import pytest

# Mechy keeps editing design/v4 in place, so tests pin the arm to a committed, self-consistent revision.
ARM_REPO_DEFAULT = "~/Mechy Projects/24-hourrobotarm"
ARM_COMMIT = "f6953e4"
CACHE = Path(__file__).resolve().parents[2] / ".cache" / f"mechy-arm-v4-{ARM_COMMIT}"
FILES = ["assembly.glb", "assembly.yaml", "joints.yaml", "geometry.py"]


def _extract(repo: Path) -> Path | None:
    if (CACHE / "joints.yaml").exists():
        return CACHE
    try:
        names = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ARM_COMMIT, "design/v4/poses"],
                               capture_output=True, text=True, check=True).stdout.split()
        wanted = [f"design/v4/{f}" for f in FILES] + [n for n in names if n.endswith("/assembly.yaml")]
        for name in wanted:
            data = subprocess.run(["git", "-C", str(repo), "show", f"{ARM_COMMIT}:{name}"],
                                  capture_output=True, check=True).stdout
            out = CACHE / name.removeprefix("design/v4/")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return CACHE


@pytest.fixture
def arm() -> Path:
    if "MECHY_ARM_V4" in os.environ:
        p = Path(os.environ["MECHY_ARM_V4"]).expanduser()
    else:
        p = _extract(Path(os.environ.get("MECHY_ARM_REPO", ARM_REPO_DEFAULT)).expanduser())
    if p is None or not (p / "assembly.glb").exists():
        pytest.skip("Mechy arm v4 not available")
    return p
