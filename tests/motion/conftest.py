import os
from pathlib import Path

import pytest

ARM_DEFAULT = "~/Mechy Projects/24-hourrobotarm/design/v4"


@pytest.fixture
def arm() -> Path:
    p = Path(os.environ.get("MECHY_ARM_V4", ARM_DEFAULT)).expanduser()
    if not (p / "assembly.glb").exists():
        pytest.skip(f"Mechy arm v4 not found at {p}")
    return p
