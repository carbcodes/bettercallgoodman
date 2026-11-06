import { useCallback, useEffect, useMemo, useState } from "react";
import Viewer from "./Viewer.jsx";

const fmt = (x) => (x == null ? "–" : x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2));
const cleanTitle = (t) => t.replace(/\s*\(AI-designed\)/i, "");

function useData() {
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
      if (r.ok) setData(await r.json());
    } catch {
      /* keep the last good data */
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
  return data;
}

const TABS = [
  { id: "break", label: "Will it break?" },
  { id: "make", label: "Can we manufacture it?" },
  { id: "collide", label: "Will it collide with itself?" },
];

// Which process to judge a part by: PLA is printed, anything else is milled.
const processOf = (t) => (t.inputs?.material === "PLA" ? "printing" : "cnc");
// Words for each manufacturing verdict (printing has a middle one: prints, but only with supports).
const VERDICT_WORD = { printable: "Printable", printable_with_supports: "Printable with supports", not_printable: "Not printable", machinable: "Machinable", not_machinable: "Not machinable" };
const SHORT_WORD = { printable: "Prints", printable_with_supports: "Needs supports", not_printable: "Can't print", machinable: "Machinable", not_machinable: "Can't mill" };
const RULE_NAME = { overhang: "Overhang", needs_support: "Needs support", overhang_hole_top: "Hole tops", overhang_near_bed: "Bottom edge", bridge: "Bridge", min_wall: "Thin wall", hole_undersize: "Hole size", bed_contact: "Bed contact", build_volume: "Build volume", undercut: "Undercut", setups: "Setups", thin_wall: "Thin wall", hole_depth: "Hole depth", inside_corner: "Inside corner", pocket_depth: "Pocket depth" };
const ruleName = (r) => RULE_NAME[r] || r.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const PROC = { printing: { name: "3D printing", ok: "Printable", bad: "Not printable" }, cnc: { name: "3-axis CNC", ok: "Machinable", bad: "Not machinable" } };

// Printable / Not printable / Waiting for the manufacturing tab.
function makeState(t, proc) {
  const r = t.dfm?.[proc];
  if (!r || r.error) return "waiting";
  if (r.verdict === "printable_with_supports") return "warn";
  return ["printable", "machinable"].includes(r.verdict) ? "holds" : "breaks";
}

// Holds / Breaks / Waiting, from Goodman's own measurement of the AI's part.
function state(t) {
  const r = t.result;
  if (!r || r.outcome === "pending") return "waiting";
  return r.goodman_verdict === "safe" ? "holds" : "breaks";
}
const LABEL = { holds: "Holds", breaks: "Breaks", waiting: "Waiting" };

// How far ChatGPT's own safety factor was from the one Goodman measured.
function accuracy(r) {
  if (!r || r.claimed_sf == null || r.safety_factor == null) return null;
  const ratio = r.claimed_sf / r.safety_factor;
  if (ratio > 1.15) return { tone: "bad", text: `ChatGPT overstated it ${ratio.toFixed(1)}×` };
  if (ratio < 0.87) return { tone: "ok", text: `ChatGPT was cautious (${Math.round((1 - ratio) * 100)}% low)` };
  return { tone: "ok", text: `ChatGPT was within ${Math.round(Math.abs(ratio - 1) * 100)}%` };
}

// "Holds at the wall-leg corner: 12 MPa vs 30 MPa across layers. SF 2.59, AI claimed 2.2." -> the middle part
const where = (why) => (why || "").replace(/^(Holds|Breaks)\s+/, "").replace(/\.\s*SF .*$/, "");

function Rail({ tasks, current, go, stateOf, labelOf }) {
  return (
    <nav className="rail">
      {tasks.map((t) => {
        const s = stateOf(t);
        return (
          <button key={t.id} className={`rail-row ${t.id === current ? "active" : ""}`} onClick={() => go(t.id)}>
            <span className="rail-title">{cleanTitle(t.title)}</span>
            <span className={`pill s-${s}`}>{labelOf(t, s)}</span>
          </button>
        );
      })}
    </nav>
  );
}

function Panel({ task }) {
  const r = task.result;
  const s = state(task);
  const acc = accuracy(r);
  const bad = (r?.requirements || []).filter((q) => !q.ok && q.rule !== "safety factor");
  return (
    <aside className="panel">
      <h1 className="panel-title">{cleanTitle(task.title)}</h1>
      <div className={`verdict s-${s}`}>{LABEL[s]}</div>

      {s !== "waiting" && (
        <>
          <div className="sf-row">
            <div>
              <span>Required</span>
              <b className="mono">{fmt(task.inputs.required_safety_factor)}</b>
            </div>
            <div>
              <span>ChatGPT said</span>
              <b className="mono">{fmt(r.claimed_sf)}</b>
            </div>
            <div className="measured">
              <span>Goodman measured</span>
              <b className="mono">{fmt(r.safety_factor)}</b>
            </div>
          </div>
          {acc && <p className={`acc ${acc.tone}`}>{acc.text}</p>}
          <p className="where">Weakest spot: {where(r.why)}</p>
          {task.printing && (
            <p className={`acc ${task.printing.verdict === "not_printable" ? "bad" : "ok"}`}>
              {task.printing.label}
              {task.printing.verdict === "not_printable"
                ? ` — ${task.printing.problems[0] || ""}`
                : task.printing.support_needed
                  ? ` — ${task.printing.support_summary}`
                  : ""}
            </p>
          )}
          {bad.map((q) => (
            <p key={q.rule} className="acc bad">
              Too big: {q.rule} {q.value} mm, limit {q.limit} mm
            </p>
          ))}
        </>
      )}
      {task.attempt?.chat_url && (
        <a className="chat-link" href={task.attempt.chat_url} target="_blank" rel="noreferrer">
          Open the ChatGPT chat
        </a>
      )}
    </aside>
  );
}

function MakePanel({ task, proc, setProc }) {
  const r = task.dfm?.[proc];
  const s = makeState(task, proc);
  const P = PROC[proc];
  const word = s === "waiting" ? "Waiting" : VERDICT_WORD[r.verdict] || (s === "breaks" ? P.bad : P.ok);
  // one card per rule: fails first, then warnings, repeats folded into a count
  const groups = [];
  const hasUndercut = (r?.findings || []).some((f) => f.rule === "undercut" && f.severity === "fail");
  for (const f of r?.findings || []) {
    if (f.severity === "info") continue;
    if (hasUndercut && f.rule === "setups") continue; // same face, said twice
    const g = groups.find((x) => x.rule === f.rule && x.severity === f.severity);
    if (g) g.n++;
    else groups.push({ rule: f.rule, severity: f.severity, why: f.why, n: 1 });
  }
  const passed = (r?.findings || []).filter((f) => f.severity === "info" && ["bed_contact", "min_wall", "build_volume", "thin_wall", "hole_depth", "setups"].includes(f.rule));
  const note = proc === "printing" ? r?.support_summary : null;
  return (
    <aside className="panel">
      <h1 className="panel-title">{cleanTitle(task.title)}</h1>
      <div className="seg">
        {Object.entries(PROC).map(([k, v]) => (
          <button key={k} className={k === proc ? "on" : ""} onClick={() => setProc(k)}>{v.name}</button>
        ))}
      </div>
      <div className={`verdict s-${s}`}>{word}</div>
      {note && s !== "waiting" && <p className="where">{note}</p>}
      {r?.error && <p className="acc bad">{r.error}</p>}
      {s !== "waiting" && groups.length === 0 && <p className="acc ok">No problems on the AI's real geometry.</p>}
      <div className="finds">
        {groups.map((g) => (
          <div key={g.rule + g.severity} className={`find ${g.severity === "fail" ? "bad" : "warn"}`}>
            <div className="find-head">
              <b>{ruleName(g.rule)}</b>
              {g.n > 1 && <span className="mono">×{g.n}</span>}
              <span className="find-tag">{g.severity === "fail" ? "Problem" : "Heads-up"}</span>
            </div>
            <p>{g.why}</p>
          </div>
        ))}
      </div>
      {passed.length > 0 && (
        <div className="passed">
          <span className="passed-head">Passed</span>
          {passed.map((f, i) => (
            <span key={i} className="chip" title={f.why}>✓ {ruleName(f.rule)}</span>
          ))}
        </div>
      )}
      {proc === "cnc" && task.inputs?.material === "PLA" && (
        <p className="where">This part is PLA, so milling is only a what-if (checked as Al 6061).</p>
      )}
      {proc === "cnc" && <p className="where">Judged with the part flipped to any of its six sides.</p>}
      {task.prompt && (
        <details className="prompt">
          <summary>Prompt we gave ChatGPT</summary>
          <p>{task.prompt}</p>
        </details>
      )}
      {task.attempt?.chat_url && (
        <a className="chat-link" href={task.attempt.chat_url} target="_blank" rel="noreferrer">
          Open the ChatGPT chat
        </a>
      )}
    </aside>
  );
}

function CollideTab() {
  return (
    <div className="soon">
      <h2>Will it collide with itself?</h2>
      <p>Range-of-motion and clearance checks for assemblies. Fabian's collision checker plugs in here.</p>
    </div>
  );
}

export default function App() {
  const data = useData();
  const [tab, setTab] = useState("break");
  const [proc, setProc] = useState(null);
  const tasks = useMemo(() => (data?.tasks || []).filter((t) => t.area === "cad" && t.result).sort((a, b) => a.id.localeCompare(b.id)), [data]);
  const ids = tasks.map((t) => t.id);
  const [picked, setPicked] = useState(() => decodeURIComponent(window.location.hash.replace(/^#\/?/, "")));
  const current = ids.includes(picked) ? picked : ids[0];
  const go = (id) => {
    window.history.replaceState(null, "", `#/${id}`);
    setPicked(id);
  };
  const idx = ids.indexOf(current);
  const task = tasks[idx];

  useEffect(() => {
    const on = (e) => {
      if (e.metaKey || e.ctrlKey) return;
      if (["ArrowDown", "ArrowRight"].includes(e.key) && idx < ids.length - 1) go(ids[idx + 1]);
      if (["ArrowUp", "ArrowLeft"].includes(e.key) && idx > 0) go(ids[idx - 1]);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  const pr = proc || (task ? processOf(task) : "printing");
  const stateOf = tab === "make" ? (t) => makeState(t, proc || processOf(t)) : state;
  const labelOf = tab === "make" ? (t, s) => (s === "waiting" ? "Waiting" : SHORT_WORD[t.dfm?.[proc || processOf(t)]?.verdict] || "") : (t, s) => LABEL[s];
  const holds = tasks.filter((t) => ["holds", "warn"].includes(stateOf(t))).length;
  const breaks = tasks.filter((t) => stateOf(t) === "breaks").length;
  const okWord = tab === "make" ? "pass" : "hold";
  const badWord = tab === "make" ? "fail" : "break";
  const dfmScene = useMemo(
    () => (task?.mesh && task.dfm?.[pr]?.findings ? { kind: "dfm", mesh: task.mesh, findings: task.dfm[pr].findings.filter((f) => !(f.rule === "setups" && f.severity === "fail")) } : null),
    [task, pr],
  );
  return (
    <div className="app">
      <header className="top">
        <span className="brand">Better Call Goodman</span>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={t.id === tab ? "on" : ""} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        {tab !== "collide" && (
          <div className="counts">
            <span className="o-accepted"><b className="mono">{holds}</b> {okWord}</span>
            <span className={breaks ? "o-caught" : "zero"}><b className="mono">{breaks}</b> {badWord}</span>
          </div>
        )}
      </header>
      {!data ? (
        <p className="loading">Loading…</p>
      ) : tab === "collide" ? (
        <CollideTab />
      ) : (
        <div className="body">
          <Rail tasks={tasks} current={current} go={go} stateOf={stateOf} labelOf={labelOf} />
          {task && <Viewer task={tab === "make" ? { ...task, id: `${task.id}:${pr}`, scene: dfmScene } : task} />}
          {task && (tab === "make" ? <MakePanel task={task} proc={pr} setProc={setProc} /> : <Panel task={task} />)}
        </div>
      )}
    </div>
  );
}
