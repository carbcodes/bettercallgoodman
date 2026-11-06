"""Every checked result traces back to one ChatGPT chat and its exact prompt."""
from goodman import trace


def test_every_result_traces_to_one_chat():
    rows = [trace.trace(p.parent) for p in sorted(trace.ROOT.glob("tasks/*/*/prompt.md"))]
    problems = [(r["task"], p) for r in rows for p in r["problems"]]
    assert problems == []
    for r in rows:
        if r["task"].startswith("cad/") and r["outcome"] in ("accepted", "caught"):
            assert r["chat_url"], r["task"]
            assert r["script_sha"], r["task"]
