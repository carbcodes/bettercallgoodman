"""Checker registry: area -> module with `check(task) -> result` and `MISSING_WHY`.

A new area (e.g. collision) plugs in by adding one entry here. The result object
must expose `.verdict`, `.values` (quantity -> float), `.steps` (list of str),
`.alternatives` (quantity -> [(value, why)]) and `.notes`.
"""

from . import strength

CHECKERS = {
    "strength": strength,
}
