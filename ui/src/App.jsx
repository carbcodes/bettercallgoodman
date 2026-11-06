import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Viewer from "./Viewer.jsx";
import { locateQuotes, parseAnswer } from "./answer.js";

const OUTCOMES = ["accepted", "caught", "false_alarm", "missed", "pending"];
const OUTCOME_LABEL = { accepted: "Accepted", caught: "Caught", false_alarm: "False alarm", missed: "Missed", pending: "Pending" };
const OUTCOME_NOTE = {
  accepted: "AI right, Goodman accepted",
  caught: "AI wrong, Goodman rejected",
  false_alarm: "AI right, Goodman rejected",
  missed: "AI wrong, Goodman accepted",
};
const AREA_LABEL = { strength: "Strength", collision: "Collision" };

const words = (v) => (v == null ? "–" : String(v).replace(/_/g, " "));
const num = (x) => {
  if (x == null) return "–";
  if (Array.isArray(x)) return x.map(num).join("–");
  if (typeof x !== "number") return String(x);
  const a = Math.abs(x);
  const s = a >= 100 ? x.toFixed(0) : a >= 10 ? x.toFixed(1) : x.toFixed(2);
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
};

function stage(t) {
  if (t.outcome !== "pending") return OUTCOME_NOTE[t.outcome];
  if (!t.attempt) return "waiting for the AI attempt";
  if (!t.claims) return "attempt saved, claims not extracted yet";
  return "claims saved, not checked yet";
}

function Outcome({ value, large }) {
  return <span className={`outcome o-${value} ${large ? "large" : ""}`}>{OUTCOME_LABEL[value] || value}</span>;
}

function useData() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    window.addEventListener("focus", load);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", load);
    };
  }, [load]);
  return { data, error };
}

function useHashId(ids) {
  const read = () => decodeURIComponent(window.location.hash.replace(/^#\/?/, ""));
  const [id, setId] = useState(read);
  useEffect(() => {
    const on = () => setId(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const current = ids.includes(id) ? id : ids[0];
  const go = (next, scroll = true) => {
    window.history.replaceState(null, "", `#/${next}`);
    setId(next);
    if (scroll) document.getElementById("case")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return [current, go];
}

// ------------------------------------------------------------------ pieces

function Header({ data }) {
  return (
    <header className="titleblock">
      <div className="tb-cell tb-brand">
        <span className="wordmark">Better Call Goodman</span>
      </div>
      <div className="tb-cell">
        <span className="label">Event</span>
        <span>Mercor Hack Day · Georgia Tech</span>
      </div>
      <div className="tb-cell">
        <span className="label">Date</span>
        <span className="mono">2026-11-06</span>
      </div>
      <div className="tb-cell">
        <span className="label">Data</span>
        <span className="mono">{data ? new Date(data.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "–"}</span>
      </div>
      <nav className="tb-cell tb-nav">
        <a href="#cases">Cases</a>
        <a href="#case">Detail</a>
        <a href="#results">Results</a>
      </nav>
    </header>
  );
}

function Counts({ tasks }) {
  const c = Object.fromEntries(OUTCOMES.map((o) => [o, 0]));
  tasks.forEach((t) => (c[t.outcome] = (c[t.outcome] || 0) + 1));
  return (
    <dl className="counts">
      {OUTCOMES.map((o) => (
        <div key={o} className={c[o] ? "" : "zero"}>
          <dt>{OUTCOME_LABEL[o]}</dt>
          <dd className={`mono o-text-${o}`}>{c[o]}</dd>
        </div>
      ))}
    </dl>
  );
}

function Hero({ tasks }) {
  return (
    <section className="hero">
      <h1>
        AI says your part is safe. <span className="nowrap">Goodman checks.</span>
      </h1>
      <p className="lede">
        We gave ChatGPT ten real design jobs. Goodman pulls the numbers out of each answer and recomputes them with
        physics and geometry, independently of the AI.
      </p>
      <ol className="pipeline mono">
        <li>prompt</li>
        <li>AI answer</li>
        <li>claims, with quotes</li>
        <li>physics recompute</li>
        <li>verdict + why</li>
      </ol>
      <Counts tasks={tasks} />
    </section>
  );
}

function CaseList({ tasks, current, go }) {
  const groups = ["strength", "collision"].map((a) => [a, tasks.filter((t) => t.area === a)]);
  return (
    <section id="cases" className="cases">
      <h2 className="section-title">
        <span className="num">01</span> Cases
      </h2>
      <div className="case-groups">
        {groups.map(([area, list]) => (
          <div key={area} className="case-group">
            <h3 className="label">{AREA_LABEL[area]}</h3>
            <ul>
              {list.map((t) => (
                <li key={t.id}>
                  <button className={`case-row ${t.id === current ? "active" : ""}`} onClick={() => go(t.id)}>
                    <span className="mono case-id">{t.id.split("-")[0]}</span>
                    <span className="case-title">
                      {t.title}
                      {t.control && !/control/i.test(t.title) && <span className="tag">control</span>}
                    </span>
                    <span className="case-stage small muted">{stage(t)}</span>
                    <Outcome value={t.outcome} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function Answer({ task }) {
  const [raw, setRaw] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    const el = box.current;
    const first = el?.querySelector("mark.claim");
    if (el && first) el.scrollTop = Math.max(0, first.offsetTop - el.offsetTop - 40);
    else if (el) el.scrollTop = 0;
  }, [task.id, task.claims, raw]);
  const a = task.attempt;
  const claimList = task.claims?.claims || [];
  const ranges = useMemo(() => (a ? locateQuotes(a.answer, claimList) : []), [a, claimList]);
  const status = Object.fromEntries((task.result?.claims || []).map((c) => [c.id, c.status]));
  if (!a) return <p className="empty">No AI attempt yet. The answer appears here once attempt.json is saved.</p>;
  const blocks = parseAnswer(a.answer);
  const hits = (b) => ranges.filter((r) => r.start < b.end && r.end > b.start);

  const renderText = (b) => {
    const hs = hits(b);
    if (!hs.length) return b.text;
    // highlight exact substrings that fall inside this line; mark the whole line otherwise
    const parts = [];
    let cur = b.start;
    for (const h of hs.sort((x, y) => x.start - y.start)) {
      const s = Math.max(h.start, b.start), e = Math.min(h.end, b.end);
      if (s > cur) parts.push(a.answer.slice(cur, s));
      parts.push(
        <mark key={h.id + s} className={`claim s-${status[h.id] || "pending"}`}>
          {a.answer.slice(Math.max(s, cur), e)}
          {e === h.end && <sup className="mono">{h.id}</sup>}
        </mark>,
      );
      cur = Math.max(cur, e);
    }
    if (cur < b.end) parts.push(a.answer.slice(cur, b.end));
    return parts;
  };

  return (
    <div className="answer-wrap">
      <div className="answer-meta small muted">
        <span>{a.model?.split(" (")[0]}</span>
        <span>·</span>
        <span>{a.interface}</span>
        <span>·</span>
        <span className="mono">{a.date?.slice(0, 16).replace("T", " ")}</span>
        <button className="link" onClick={() => setRaw(!raw)}>
          {raw ? "readable" : "raw text"}
        </button>
      </div>
      <div className="answer" ref={box}>
        {raw ? (
          <pre className="raw">{a.answer}</pre>
        ) : (
          blocks.map((b, i) =>
            b.type === "gap" ? (
              <div key={i} className="gap" />
            ) : b.type === "math" ? (
              <div key={i} className={`math mono ${hits(b).length ? "hit" : ""}`}>
                {hits(b).length ? (
                  <mark className={`claim s-${status[hits(b)[0].id] || "pending"}`}>
                    {b.text}
                    <sup className="mono">{hits(b).map((h) => h.id).join(",")}</sup>
                  </mark>
                ) : (
                  b.text
                )}
              </div>
            ) : (
              <p key={i}>{renderText(b)}</p>
            ),
          )
        )}
      </div>
      {!raw && <p className="small muted fine">Equations are shown as copied from the chat page, de-duplicated for reading. The exact text is under “raw text”.</p>}
    </div>
  );
}

function Claims({ task }) {
  const claims = task.claims?.claims;
  if (!claims) {
    return (
      <p className="empty">
        {task.attempt ? "Claims not extracted yet (claims.json)." : "Claims appear after the AI attempt is saved and its claims are extracted."}
      </p>
    );
  }
  const res = Object.fromEntries((task.result?.claims || []).map((c) => [c.id, c]));
  return (
    <table className="grid claims">
      <thead>
        <tr>
          <th>Claim</th>
          <th>Quantity</th>
          <th>The AI wrote</th>
          <th className="r">Claimed</th>
          <th className="r">Goodman</th>
          <th>Status</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        {claims.map((c) => {
          const r = res[c.id];
          return (
            <tr key={c.id} className={r ? `row-${r.status}` : ""}>
              <td className="mono">{c.id}</td>
              <td className="mono small">{c.quantity}</td>
              <td className="quote">“{c.quote}”</td>
              <td className="mono r">{num(c.value ?? [c.low, c.high])}</td>
              <td className="mono r">{r ? num(r.actual) : "–"}</td>
              <td>
                <span className={`status s-${r?.status || "pending"}`}>{r ? words(r.status) : "pending"}</span>
              </td>
              <td className="why">{r?.why || ""}</td>
            </tr>
          );
        })}
        {(task.result?.missing || []).map((m) => (
          <tr key={m.topic} className="row-refuted">
            <td className="mono">–</td>
            <td className="mono small">{m.topic}</td>
            <td className="quote muted">never mentioned</td>
            <td />
            <td />
            <td>
              <span className="status s-refuted">missing</span>
            </td>
            <td className="why">{m.why}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Check({ task }) {
  const ch = task.check;
  const tv = task.truth.values || {};
  return (
    <div className="check">
      <p className="small muted">
        {ch.source}
        {ch.model ? (
          <>
            {" "}
            · model <span className="mono">{ch.model}</span>
          </>
        ) : null}
      </p>
      {ch.error ? (
        <p className="empty">Checker error: {ch.error}</p>
      ) : (
        <ol className="calc mono">
          {ch.steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
          {(ch.notes || []).map((n, i) => (
            <li key={`n${i}`} className="muted">
              note: {n}
            </li>
          ))}
        </ol>
      )}
      {Object.keys(tv).length > 0 && (
        <table className="grid compact">
          <thead>
            <tr>
              <th>Quantity</th>
              <th className="r">Goodman</th>
              <th className="r">Hand calc</th>
              <th className="r">Tolerance</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(tv).map(([q, v]) => (
              <tr key={q}>
                <td className="mono small">{q}</td>
                <td className="mono r">{num(ch.values?.[q])}</td>
                <td className="mono r">{num(v.value)}</td>
                <td className="mono r">{v.tol ? `±${Math.round(v.tol * 100)}%` : "exact"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Verdict({ task }) {
  const r = task.result;
  const refuted = (r?.claims || []).filter((c) => c.status === "refuted");
  const conservative = (r?.claims || []).filter((c) => c.status === "conservative");
  return (
    <div className="verdict">
      <div className="verdict-head">
        <Outcome value={task.outcome} large />
        <span className="small muted">{stage(task)}</span>
      </div>
      <dl className="verdict-rows">
        <div>
          <dt>AI said</dt>
          <dd className="mono">{words(r?.ai_verdict ?? task.claims?.verdict)}</dd>
        </div>
        <div>
          <dt>Goodman</dt>
          <dd className="mono">{words(task.check.verdict)}</dd>
        </div>
        <div>
          <dt>Hand calc</dt>
          <dd className="mono">{words(task.truth.verdict)}</dd>
        </div>
      </dl>
      {refuted.length > 0 && (
        <ul className="whys">
          {refuted.map((c) => (
            <li key={c.id}>
              <span className="mono">{c.id}</span> {c.why}
            </li>
          ))}
          {(r.missing || []).map((m) => (
            <li key={m.topic}>
              <span className="mono">missing</span> {m.why}
            </li>
          ))}
        </ul>
      )}
      {r && refuted.length === 0 && (r.missing || []).length === 0 && (
        <p className="small">
          {conservative.length
            ? "No number is wrong on the unsafe side. Some are conservative:"
            : "Every checked number is within tolerance of Goodman’s recompute."}
        </p>
      )}
      {conservative.length > 0 && (
        <ul className="whys soft">
          {conservative.map((c) => (
            <li key={c.id}>
              <span className="mono">{c.id}</span> {c.why}
            </li>
          ))}
        </ul>
      )}
      {task.result_source && task.result_source !== "result.json" && <p className="small muted">Result {task.result_source}.</p>}
      <div className="trap">
        <span className="label">{task.control ? "Control case" : "What this case tests"}</span>
        <p>{task.control ? "A design that is genuinely fine. A fair checker must accept a correct answer." : task.trap}</p>
      </div>
      <details>
        <summary className="small">Hand calc and source (truth.yaml)</summary>
        <pre className="mono why-text">{task.truth.why}</pre>
        {task.truth.source && <p className="small muted">{task.truth.source}</p>}
      </details>
    </div>
  );
}

function Detail({ task, prev, next, go }) {
  return (
    <section id="case" className="detail">
      <h2 className="section-title">
        <span className="num">02</span> Case
        <span className="pager">
          <button className="link" disabled={!prev} onClick={() => prev && go(prev, false)}>
            ← prev
          </button>
          <button className="link" disabled={!next} onClick={() => next && go(next, false)}>
            next →
          </button>
        </span>
      </h2>

      <div className="case-block">
        <div className="cb-cell cb-id">
          <span className="label">Case</span>
          <span className="mono">{task.id}</span>
        </div>
        <div className="cb-cell cb-title">
          <span className="label">{AREA_LABEL[task.area]}</span>
          <span>
            {task.title}
            {task.control && !/control/i.test(task.title) && <span className="tag">control</span>}
          </span>
        </div>
        <div className="cb-cell">
          <span className="label">Outcome</span>
          <Outcome value={task.outcome} />
        </div>
      </div>

      <div className="detail-grid">
        <div className="col">
          <h3 className="sub">
            <span className="num">a</span> The job, as sent to the AI
          </h3>
          <blockquote className="prompt">{task.prompt}</blockquote>
          <h3 className="sub">
            <span className="num">b</span> The AI’s first answer
          </h3>
          <Answer task={task} />
        </div>
        <div className="col">
          <Viewer task={task} />
        </div>
      </div>

      <h3 className="sub">
        <span className="num">c</span> Claims Goodman extracted
      </h3>
      <Claims task={task} />

      <div className="detail-grid lower">
        <div className="col">
          <h3 className="sub">
            <span className="num">d</span> Goodman’s check
          </h3>
          <Check task={task} />
        </div>
        <div className="col">
          <h3 className="sub">
            <span className="num">e</span> Verdict
          </h3>
          <Verdict task={task} />
        </div>
      </div>
    </section>
  );
}

function acceptedNote(r) {
  const n = (st) => r.claims.filter((c) => c.status === st).length;
  return `${n("confirmed")} confirmed${n("conservative") ? `, ${n("conservative")} conservative` : ""}, none wrong`;
}

function Results({ tasks, go }) {
  const areas = ["strength", "collision"];
  const count = (list, o) => list.filter((t) => t.outcome === o).length;
  const finding = (t) => {
    const r = t.result;
    if (!r) return "";
    return r.claims.find((c) => c.status === "refuted")?.why || r.missing?.[0]?.why || (t.outcome === "accepted" ? acceptedNote(r) : "");
  };
  return (
    <section id="results" className="results">
      <h2 className="section-title">
        <span className="num">03</span> Results
      </h2>
      <div className="results-grid">
        <table className="grid summary">
          <thead>
            <tr>
              <th>Area</th>
              {OUTCOMES.map((o) => (
                <th key={o} className="r">
                  {OUTCOME_LABEL[o]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {areas.map((a) => {
              const list = tasks.filter((t) => t.area === a);
              return (
                <tr key={a}>
                  <td>{AREA_LABEL[a]}</td>
                  {OUTCOMES.map((o) => (
                    <td key={o} className={`mono r ${count(list, o) ? `o-text-${o}` : "muted"}`}>
                      {count(list, o)}
                    </td>
                  ))}
                </tr>
              );
            })}
            <tr className="total">
              <td>Total</td>
              {OUTCOMES.map((o) => (
                <td key={o} className="mono r">
                  {count(tasks, o)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
        <p className="small muted">
          Accepted and caught are Goodman doing its job. False alarm (rejecting a right answer) and missed (accepting a
          wrong one) are Goodman’s errors. Ten cases is a small sample.
        </p>
      </div>
      <table className="grid per-task">
        <thead>
          <tr>
            <th>Case</th>
            <th>Title</th>
            <th>AI said</th>
            <th>Goodman</th>
            <th>Hand calc</th>
            <th>Outcome</th>
            <th>Key finding</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} onClick={() => go(t.id)} className="clickable">
              <td className="mono">{t.id.split("-")[0]}</td>
              <td>
                {t.title}
                {t.control && !/control/i.test(t.title) && <span className="tag">control</span>}
              </td>
              <td className="mono small">{words(t.result?.ai_verdict ?? t.claims?.verdict ?? null)}</td>
              <td className="mono small">{words(t.check.verdict)}</td>
              <td className="mono small">{words(t.truth.verdict)}</td>
              <td>
                <Outcome value={t.outcome} />
              </td>
              <td className="why small">{finding(t) || <span className="muted">{stage(t)}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function App() {
  const { data, error } = useData();
  const tasks = useMemo(() => {
    const order = { strength: 0, collision: 1 };
    return [...(data?.tasks || [])].sort((a, b) => order[a.area] - order[b.area] || a.id.localeCompare(b.id));
  }, [data]);
  const ids = tasks.map((t) => t.id);
  const [current, go] = useHashId(ids);
  const idx = ids.indexOf(current);
  const task = tasks[idx];

  useEffect(() => {
    const on = (e) => {
      if (e.target.closest?.("input, textarea") || e.metaKey || e.ctrlKey) return;
      if (e.key === "ArrowRight" || e.key === "j") idx < ids.length - 1 && go(ids[idx + 1], false);
      if (e.key === "ArrowLeft" || e.key === "k") idx > 0 && go(ids[idx - 1], false);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  return (
    <>
      <Header data={data} />
      <main>
        {error && !data && (
          <p className="empty">
            Could not load data.json ({error}). Run <code>python -m goodman export</code> from the repo root.
          </p>
        )}
        {data && (
          <>
            <Hero tasks={tasks} />
            <CaseList tasks={tasks} current={current} go={go} />
            {task && <Detail task={task} prev={ids[idx - 1]} next={ids[idx + 1]} go={go} />}
            <Results tasks={tasks} go={go} />
          </>
        )}
      </main>
      <footer className="foot small muted">
        <span>Closed-form beam theory and exact geometry; no FEA, friction, dynamics or tolerances.</span>
        <span>The AI only extracts what an answer said. Physics code decides whether it is right.</span>
      </footer>
    </>
  );
}
