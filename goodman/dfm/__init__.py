"""Design-for-manufacturing checkers on STEP solids: FDM printing and 3-axis CNC.

    from goodman.dfm import check_printing, check_cnc
    check_printing("part.step", build_dir=(0, 0, 1))
    check_cnc("part.step", setups=[(0, 0, 1)], material="Al6061-T6")

Needs the optional geometry stack: `pip install build123d` (pulls in OCP).
"""

from .printing import check_printing
from .cnc import check_cnc

__all__ = ["check_printing", "check_cnc"]
