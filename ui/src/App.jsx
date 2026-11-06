import { useCallback, useEffect, useMemo, useState } from "react";
import Viewer from "./Viewer.jsx";

const OUTCOMES = ["accepted", "caught", "false_alarm", "missed"];
const OUTCOME_LABEL = { accepted: "Accepted", caught: "Caught", false_alarm: "False alarm", missed: "Missed", pending: "Pending" };

// Short names for the claim rows; anything unlisted falls back to its key.
const QTY = {
  load_n: ["Load", "N"],
  moment_nmm: ["Moment", "N·mm"],
  section_modulus_mm3: ["Section modulus", "mm³"],
  nominal_stress_mpa: ["Nominal stress", "MPa"],
  stress_concentration_kt: ["Kt", ""],
  max_stress_mpa: ["Max stress", "MPa"],
  material_strength_mpa: ["Strength used", "MPa"],
  safety_factor: ["Safety factor", ""],
  stress_safety_factor: ["Stress SF", ""],
  buckling_safety_factor: ["Buckling SF", ""],
  buckling_load_n: ["Buckling load", "N"],
  required_torque_nm: ["Torque needed", "N·m"],
  required_torque_with_margin_nm: ["Torque × margin", "N·m"],
  stall_torque_nm: ["Stall torque", "N·m"],
  torque_margin: ["Torque margin", ""],
  deflection_mm: ["Deflection", "mm"],
  fatigue_safety_factor: ["Fatigue SF", ""],
  static_safety_factor: ["Static SF", ""],
  thermal_stress_mpa: ["Thermal stress", "MPa"],
  thermal_force_n: ["Thermal force", "N"],
  critical_temperature_rise_c: ["Buckles at +", "°C"],
  min_clearance_mm: ["Clearance", "mm"],
  collision_angle_deg: ["First contact", "°"],
  reach_deg: ["Reach", "°"],
};

const AREA = { cad: "AI designs the part", strength: "AI analyzes a part", collision: "Collision" };
const words = (v) => (v == null ? "–" : String(v).replace(/_/g, " "));
const num = (x) => {
  if (x == null) return "–";
  if (Array.isArray(x)) return x.map(num).join("–");
  if (typeof x !== "number") return String(x);
  const a = Math.abs(x);
  const s = a >= 100 ? x.toFixed(0) : a >= 10 ? x.toFixed(1) : x.toFixed(2);
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
};
const shortId = (id) => id.split("-")[0];

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

function Mark({ outcome }) {
  return <span className={`mark o-${outcome}`} aria-hidden />;
}

// "Caught" splits into the two stories we tell: wrong verdict, or right verdict for wrong reasons.
function outcomeNote(t) {
  const r = t.result;
  if (!r) return t.attempt ? "Not checked yet" : "Waiting for the AI";
  const sameVerdict = words(r.ai_verdict) === words(r.true_verdict);
  if (t.outcome === "caught") return sameVerdict ? "Right verdict, wrong numbers" : "Wrong verdict";
  if (t.outcome === "accepted") return "AI was right";
  if (t.outcome === "false_alarm") return "Goodman rejected a right answer";
  return "Goodman missed a wrong answer";
}

function Rail({ tasks, current, go }) {
  return (
    <nav className="rail">
      {["cad", "strength", "collision"].map((area) => (
        <div key={area} className="rail-group">
          <div className="rail-head">{AREA[area] || area}</div>
          {tasks
            .filter((t) => t.area === area)
            .map((t) => (
              <button key={t.id} className={`rail-row ${t.id === current ? "active" : ""}`} onClick={() => go(t.id)}>
                <span className="mono rail-id">{shortId(t.id)}</span>
                <span className="rail-title">{t.title.replace(/\s*\(control\)/i, "")}</span>
                {t.control && <span className="rail-tag">ctrl</span>}
                <Mark outcome={t.outcome} />
              </button>
            ))}
        </div>
      ))}
    </nav>
  );
}

function Claims({ task }) {
  const r = task.result;
  const claims = task.claims?.claims || [];
  const res = Object.fromEntries((r?.claims || []).map((c) => [c.id, c]));
  const rows = claims.filter((c) => res[c.id]?.status !== "cannot_check");
  if (!rows.length) return null;
  return (
    <table className="claims">
      <thead>
        <tr>
          <th />
          <th className="r">AI</th>
          <th className="r">Goodman</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const st = res[c.id]?.status || "pending";
          const [name, unit] = QTY[c.quantity] || [c.quantity, ""];
          return (
            <tr key={c.id} className={`s-${st}`}>
              <td>
                {name}
                {unit && <span className="unit"> {unit}</span>}
              </td>
              <td className="mono r ai">{num(c.value ?? [c.low, c.high])}</td>
              <td className="mono r">{num(res[c.id]?.actual)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Panel({ task }) {
  const r = task.result;
  const why = task.area === "cad"
    ? r?.why
    : r?.claims.find((c) => c.status === "refuted")?.why?.split(": ").pop() || r?.missing?.[0]?.why;
  return (
    <aside className="panel">
      <div className="panel-id mono">
        {shortId(task.id)} · {AREA[task.area] || task.area}
        {task.control ? " · control" : ""}
      </div>
      <h1 className="panel-title">{task.title.replace(/\s*\(control\)/i, "")}</h1>

      <div className={`outcome o-${task.outcome}`}>
        <span className="outcome-word">{OUTCOME_LABEL[task.outcome]}</span>
        <span className="outcome-note">{outcomeNote(task)}</span>
      </div>

      <dl className="verdicts">
        <div>
          <dt>AI said</dt>
          <dd>{words(r?.ai_verdict ?? task.claims?.verdict)}</dd>
        </div>
        <div>
          <dt>Goodman</dt>
          <dd>{words(task.check.verdict)}</dd>
        </div>
      </dl>

      <Claims task={task} />
      {why && <p className={`why ${task.outcome === "accepted" ? "ok" : ""}`}>{why}</p>}
    </aside>
  );
}

function Counts({ tasks }) {
  return (
    <div className="counts">
      {OUTCOMES.map((o) => {
        const n = tasks.filter((t) => t.outcome === o).length;
        return (
          <span key={o} className={n ? `o-${o}` : "zero"}>
            <b className="mono">{n}</b> {OUTCOME_LABEL[o].toLowerCase()}
          </span>
        );
      })}
    </div>
  );
}

export default function App() {
  const data = useData();
  const tasks = useMemo(() => {
    const order = { cad: 0, strength: 1, collision: 2 };
    return [...(data?.tasks || [])].sort((a, b) => order[a.area] - order[b.area] || a.id.localeCompare(b.id));
  }, [data]);
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

  return (
    <div className="app">
      <header className="top">
        <span className="brand">Better Call Goodman</span>
        <span className="pitch">AI says your part is safe. Goodman checks.</span>
        {data && <Counts tasks={tasks} />}
      </header>
      {!data ? (
        <p className="loading">Loading… run <code>python -m goodman export</code> if this stays.</p>
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
