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

function Rail({ tasks, current, go }) {
  return (
    <nav className="rail">
      {tasks.map((t) => {
        const s = state(t);
        return (
          <button key={t.id} className={`rail-row ${t.id === current ? "active" : ""}`} onClick={() => go(t.id)}>
            <span className="rail-title">{cleanTitle(t.title)}</span>
            <span className={`pill s-${s}`}>{LABEL[s]}</span>
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

export default function App() {
  const data = useData();
  const tasks = useMemo(() => (data?.tasks || []).filter((t) => t.area === "cad").sort((a, b) => a.id.localeCompare(b.id)), [data]);
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

  const holds = tasks.filter((t) => state(t) === "holds").length;
  const breaks = tasks.filter((t) => state(t) === "breaks").length;
  return (
    <div className="app">
      <header className="top">
        <span className="brand">Better Call Goodman</span>
        <span className="pitch">ChatGPT designs the part. Goodman measures it.</span>
        <div className="counts">
          <span className="o-accepted"><b className="mono">{holds}</b> hold</span>
          <span className={breaks ? "o-caught" : "zero"}><b className="mono">{breaks}</b> break</span>
        </div>
      </header>
      {!data ? (
        <p className="loading">Loading…</p>
      ) : (
        <div className="body">
          <Rail tasks={tasks} current={current} go={go} />
          {task && <Viewer task={task} />}
          {task && <Panel task={task} />}
        </div>
      )}
    </div>
  );
}
