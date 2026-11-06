"""python -m goodman.dfm printing <part.step> [--up 0 0 1] [--printer prusa_mk4] [--json]
python -m goodman.dfm cnc <part.step> [--setups 0,0,1 0,0,-1] [--material Al6061-T6] [--json]

Exit code 0 = printable / machinable, 1 = not, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import sys


def _vec(s: str):
    parts = [float(x) for x in s.replace(",", " ").split()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"expected x,y,z, got {s!r}")
    return tuple(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m goodman.dfm", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("printing", help="FDM printability")
    p.add_argument("step")
    p.add_argument("--up", nargs=3, type=float, default=[0, 0, 1], metavar=("X", "Y", "Z"),
                   help="up direction on the print bed (default 0 0 1)")
    p.add_argument("--printer", default=None, help="printer key in goodman/rules/fdm.yaml")
    p.add_argument("--json", action="store_true", help="print the result dict as JSON")
    c = sub.add_parser("cnc", help="3-axis CNC millability")
    c.add_argument("step")
    c.add_argument("--setups", nargs="+", type=_vec, default=[(0, 0, 1)], metavar="X,Y,Z",
                   help="spindle directions, e.g. --setups 0,0,1 0,0,-1 (default 0,0,1)")
    c.add_argument("--material", default="Al6061-T6")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        from .report import format_text
        if a.cmd == "printing":
            from .printing import check_printing
            res = check_printing(a.step, build_dir=tuple(a.up), printer=a.printer)
        else:
            from .cnc import check_cnc
            res = check_cnc(a.step, setups=a.setups, material=a.material)
    except ImportError as e:
        print(f"goodman.dfm needs the optional geometry stack: pip install build123d ({e})", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if a.json else format_text(res))
    return 0 if res["verdict"] in ("printable", "machinable") else 1


if __name__ == "__main__":
    sys.exit(main())
