"""Design mode: the AI writes CAD code for a part that must carry a load; Goodman runs
it, measures the real geometry and checks the strength itself.

  python -m goodman.design check tasks/cad/<id>     run the AI's script, measure, write result.json
  python -m goodman.design part  <script.py> <task>  same check on any script (used by the tests)
"""
