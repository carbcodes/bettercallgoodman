import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const STATUS = {
  collides: { word: "Collides", short: "Collides", tone: "breaks" },
  conditional: { word: "Collides if misused", short: "If misused", tone: "warn" },
  clear: { word: "No collisions", short: "Clear", tone: "holds" },
};
const BLUE = 0x20a4f3;
const RED = 0xe5484d;
const DEG = Math.PI / 180;
const num = (x) => Number(x).toLocaleString("en-US");
const ang = (x) => `${x < 0 ? "−" : ""}${Math.abs(x).toFixed(0)}°`;

// Forward kinematics, same as goodman/motion/kinematics.py: a joint turns (value - home) degrees about
// `axis` through `origin` (home assembly frame, mm), composed down the parent chain; coupled joints follow
// home + sum(ratio * (driver - driver.home)).
function makeKinematics(joints) {
  const byId = Object.fromEntries(joints.map((j) => [j.id, j]));
  const bodyOf = {};
  for (const j of joints) for (const p of j.parts || []) bodyOf[p] = j.id;
  const independent = joints.filter((j) => !j.coupled?.length).map((j) => j.id);
  const home = Object.fromEntries(independent.map((id) => [id, byId[id].home]));
  const values = (indep) => {
    const v = {};
    const val = (id) => {
      if (id in v) return v[id];
      const j = byId[id];
      v[id] = j.coupled?.length
        ? j.home + j.coupled.reduce((s, [d, r]) => s + r * (val(d) - byId[d].home), 0)
        : indep[id] ?? j.home;
      return v[id];
    };
    joints.forEach((j) => val(j.id));
    return v;
  };
  const transforms = (indep) => {
    const v = values(indep);
    const M = {};
    const get = (id) => {
      if (M[id]) return M[id];
      const j = byId[id];
      const P = j.parent ? get(j.parent) : new THREE.Matrix4();
      const [ox, oy, oz] = j.origin;
      const R = new THREE.Matrix4().makeRotationAxis(new THREE.Vector3(...j.axis).normalize(), (v[id] - j.home) * DEG);
      const T = new THREE.Matrix4().makeTranslation(ox, oy, oz).multiply(R).multiply(new THREE.Matrix4().makeTranslation(-ox, -oy, -oz));
      M[id] = P.clone().multiply(T);
      return M[id];
    };
    joints.forEach((j) => get(j.id));
    return M;
  };
  return { bodyOf, independent, home, transforms };
}

const lerpPose = (a, b, t) => Object.fromEntries(Object.keys({ ...a, ...b }).map((k) => [k, (a[k] ?? 0) + ((b[k] ?? a[k] ?? 0) - (a[k] ?? 0)) * t]));
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

// What the viewer should show: a collision pose, or a named pose of the design.
function target(design, sel, which) {
  if (sel?.kind === "collision") {
    const c = sel.c;
    const pose = which === "first" ? c.first_contact : c.worst?.pose || c.first_contact;
    return { pose, parts: c.parts, contact: which === "first" ? null : c.contact_point_mm, firstContact: which === "first" ? c.contact_point_mm : null };
  }
  if (sel?.kind === "pose") {
    const p = design.poses.find((q) => q.name === sel.name);
    return { pose: p?.values || {}, parts: sel.parts || null, contact: null };
  }
  return { pose: {}, parts: null, contact: null };
}

function CollideViewer({ design, sel, which, ghost, onT, apiRef }) {
  const host = useRef(null);
  const [status, setStatus] = useState("loading");
  const want = useRef(null); // the latest thing to show, applied as soon as the model has loaded
  want.current = { tg: target(design, sel, which), ghost };

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setStatus("nowebgl");
      return;
    }
    setStatus("loading");
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d2c6, 2.0));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(-1, -2, 3);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.6);
    fill.position.set(2, 1, 1);
    scene.add(fill);
    const camera = new THREE.PerspectiveCamera(32, 1, 1, 100000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const kin = makeKinematics(design.joints);
    const parts = {}; // name -> { obj, home: Matrix4, meshes: [{ mesh, mat }] }
    const asm = new THREE.Group();
    scene.add(asm);
    const ghostMat = new THREE.MeshStandardMaterial({ color: 0xb8c4cf, transparent: true, opacity: 0.1, depthWrite: false, roughness: 0.9 });
    // blue (the part that gets hit) is see-through so the red part is visible even deep inside it
    const hiMat = [BLUE, RED].map((c, i) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.5, metalness: 0.05, emissive: c, emissiveIntensity: 0.12, ...(i === 0 ? { transparent: true, opacity: 0.45, depthWrite: false } : {}) }));
    const marker = new THREE.Group();
    const dot = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), new THREE.MeshBasicMaterial({ color: 0x1c1c1c, depthTest: false, transparent: true }));
    const halo = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.MeshBasicMaterial({ color: RED, transparent: true, opacity: 0.22, depthTest: false }));
    dot.renderOrder = halo.renderOrder = 10;
    marker.add(halo, dot);
    marker.visible = false;
    scene.add(marker);

    const st = { from: { ...kin.home }, to: { ...kin.home }, cur: { ...kin.home }, t: 1, playing: false, start: 0, dur: 1400, ready: false, radius: 100, center: new THREE.Vector3(), contact: null, camFrom: null, camTo: null };

    const applyPose = (pose) => {
      st.cur = pose;
      const M = kin.transforms(pose);
      for (const [name, p] of Object.entries(parts)) {
        const b = kin.bodyOf[name];
        p.obj.matrix.copy(b ? M[b] : new THREE.Matrix4()).multiply(p.home);
        p.obj.matrixWorldNeedsUpdate = true;
      }
    };

    const paint = (hl, ghosted) => {
      for (const [name, p] of Object.entries(parts)) {
        const i = hl ? hl.indexOf(name) : -1;
        for (const m of p.meshes) m.mesh.material = i >= 0 ? hiMat[i] : ghosted && hl ? ghostMat : m.mat;
        p.obj.renderOrder = i >= 0 ? 2 : 0;
      }
    };

    // move the orbit target (and keep the viewing direction) over the same tween as the pose
    const aim = (point, dist) => {
      const dir = camera.position.clone().sub(controls.target).normalize();
      st.camFrom = { target: controls.target.clone(), pos: camera.position.clone() };
      st.camTo = { target: point.clone(), pos: point.clone().addScaledVector(dir, dist) };
    };

    const api = {
      show(tg, ghosted) {
        if (!st.ready) return;
        st.from = { ...kin.home };
        st.to = { ...kin.home, ...tg.pose };
        st.t = 0;
        st.playing = true;
        st.start = performance.now();
        st.contact = tg.contact || tg.firstContact;
        st.hl = tg.parts;
        st.ghosted = ghosted;
        paint(tg.parts, ghosted);
        const r = st.radius;
        if (st.contact) {
          const s = r * 0.012;
          dot.scale.setScalar(s);
          halo.scale.setScalar(s * 3.2);
          marker.position.set(...st.contact);
          aim(new THREE.Vector3(...st.contact), r * 1.7);
        } else aim(st.center, r * 2.6);
        marker.visible = false;
      },
      ghost(on) {
        st.ghosted = on;
        paint(st.hl, on);
      },
      scrub(t) {
        st.playing = false;
        st.t = t;
        st.camFrom = null;
        applyPose(lerpPose(st.from, st.to, ease(t)));
        marker.visible = !!st.contact && t > 0.97;
      },
      replay() {
        st.t = 0;
        st.playing = true;
        st.start = performance.now();
      },
    };
    apiRef.current = api;

    new GLTFLoader().load(
      design.glb,
      (gltf) => {
        if (disposed) return;
        const root = gltf.scene.getObjectByName("assembly") || gltf.scene;
        root.updateMatrix();
        const S = new THREE.Matrix4().makeScale(1000, 1000, 1000); // GLB metres -> mm, assembly frame (Z up)
        const names = new Map();
        for (const j of design.joints) for (const p of j.parts || []) names.set(THREE.PropertyBinding.sanitizeNodeName(p), p);
        for (const child of [...root.children]) {
          child.updateMatrix();
          const name = names.get(child.name) || child.name;
          const home = S.clone().multiply(child.matrix);
          child.matrixAutoUpdate = false;
          const meshes = [];
          child.traverse((o) => {
            if (o.isMesh) {
              o.material = o.material.clone();
              meshes.push({ mesh: o, mat: o.material });
            }
          });
          asm.add(child);
          parts[name] = { obj: child, home, meshes };
        }
        applyPose(kin.home);
        asm.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(asm);
        st.center = box.getCenter(new THREE.Vector3());
        st.radius = box.getSize(new THREE.Vector3()).length() / 2;
        const grid = new THREE.GridHelper(st.radius * 5, 30, 0xd5e3ee, 0xe9f0f6);
        grid.rotation.x = Math.PI / 2;
        grid.position.set(st.center.x, st.center.y, box.min.z - 0.5);
        scene.add(grid);
        camera.near = st.radius / 200;
        camera.far = st.radius * 60;
        controls.target.copy(st.center);
        camera.position.copy(st.center).add(new THREE.Vector3(1.1, -1.6, 0.9).normalize().multiplyScalar(st.radius * 2.6));
        camera.updateProjectionMatrix();
        st.ready = true;
        if (import.meta.env.DEV) window.__collide = { st, parts, kin };
        setStatus("ready");
        api.show(want.current.tg, want.current.ghost);
      },
      undefined,
      () => !disposed && setStatus("error"),
    );

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf, lastT = -1, disposed = false;
    const tick = () => {
      const now = performance.now();
      if (st.ready && st.playing) {
        const t = Math.min(1, (now - st.start) / st.dur);
        st.t = t;
        const e = ease(t);
        applyPose(lerpPose(st.from, st.to, e));
        if (st.camFrom) {
          controls.target.lerpVectors(st.camFrom.target, st.camTo.target, e);
          camera.position.lerpVectors(st.camFrom.pos, st.camTo.pos, e);
        }
        marker.visible = !!st.contact && t > 0.97;
        if (t >= 1) {
          st.playing = false;
          st.camFrom = null;
        }
      }
      if (st.t !== lastT) {
        lastT = st.t;
        onT.current?.(st.t);
      }
      if (marker.visible) halo.material.opacity = 0.16 + 0.12 * Math.sin(now / 260);
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        o.geometry?.dispose?.();
        if (o.material) [].concat(o.material).forEach((m) => m.dispose());
      });
      for (const p of Object.values(parts)) for (const m of p.meshes) m.mat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      if (apiRef.current === api) apiRef.current = null;
    };
  }, [design.id]);

  useEffect(() => {
    apiRef.current?.show(target(design, sel, which), ghost);
  }, [design.id, sel, which]);
  useEffect(() => {
    apiRef.current?.ghost(ghost);
  }, [ghost]);

  return (
    <div className="viewer-canvas" ref={host}>
      {status === "loading" && <div className="viewer-fallback">Loading the 3D model…</div>}
      {status === "error" && <div className="viewer-fallback">Couldn't load {design.glb}. Run `python -m goodman export`.</div>}
      {status === "nowebgl" && <div className="viewer-fallback">WebGL is not available in this browser.</div>}
    </div>
  );
}

function PoseBar({ design, sel, which, setWhich, ghost, setGhost, apiRef, onT }) {
  const [t, setT] = useState(1);
  useEffect(() => {
    onT.current = setT;
    return () => (onT.current = null);
  }, [onT]);
  const tg = target(design, sel, which);
  const isCol = sel?.kind === "collision";
  const moved = Object.entries(tg.pose || {}).filter(([k, v]) => Math.abs(v - (design.joints.find((j) => j.id === k)?.home ?? 0)) > 0.05);
  return (
    <div className="posebar">
      {tg.parts && (
        <div className="pair mono">
          <span className="sw blue" />
          {tg.parts[0]}
          <span className="vs">{isCol ? "hits" : "and"}</span>
          <span className="sw red" />
          {tg.parts[1]}
          {isCol && which !== "first" && <b className="depth">{sel.c.worst.penetration_mm.toFixed(1)} mm overlap</b>}
          {sel?.kind === "pose" && <b className="depth ok">{sel.note}</b>}
        </div>
      )}
      <div className="posebar-row">
        <button className="play" onClick={() => apiRef.current?.replay()} title="Replay from home">
          ▶
        </button>
        <input type="range" min="0" max="1" step="0.001" value={t} onChange={(e) => apiRef.current?.scrub(Number(e.target.value))} aria-label="Home to collision" />
        <span className="posebar-end mono">{isCol ? (which === "first" ? "first touch" : "deepest") : sel?.kind === "pose" ? sel.name : "home"}</span>
      </div>
      <div className="posebar-row">
        <div className="joints mono">
          {moved.length ? moved.map(([k, v]) => <span key={k}>{k} <b>{ang(v)}</b></span>) : <span>home pose</span>}
        </div>
        {isCol && (
          <div className="seg small">
            <button className={which === "worst" ? "on" : ""} onClick={() => setWhich("worst")}>Deepest</button>
            <button className={which === "first" ? "on" : ""} onClick={() => setWhich("first")}>First touch</button>
          </div>
        )}
        {tg.parts && (
          <label className="ghost-toggle">
            <input type="checkbox" checked={ghost} onChange={(e) => setGhost(e.target.checked)} /> See-through
          </label>
        )}
      </div>
    </div>
  );
}

function DesignPanel({ design, sel, select }) {
  const S = STATUS[design.status] || STATUS.collides;
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const k = q.trim().toLowerCase();
    return k ? design.collisions.filter((c) => c.parts.join(" ").toLowerCase().includes(k)) : design.collisions;
  }, [design, q]);
  const st = design.stats || {};
  const n = design.collisions.length;
  const safe = design.compare_pose && design.collisions[0];
  return (
    <aside className="panel">
      <h1 className="panel-title">{design.title}</h1>
      <div className={`verdict s-${S.tone}`}>
        {S.word}
        {n > 0 && <span className="verdict-n mono">{n} part pairs</span>}
      </div>
      {design.headline && <p className="headline">{design.headline}</p>}
      <div className="claim-row">
        <div>
          <span>The design said</span>
          <b>{design.claim?.text || "–"}</b>
          {design.claim?.file && <i className="mono">{design.claim.file}</i>}
        </div>
        <div className="measured">
          <span>Goodman found</span>
          <b>{n ? `${n} collisions` : "No collisions"}</b>
          <i className="mono">{num(st.poses_checked || 0)} poses</i>
        </div>
      </div>
      {design.notes.map((t, i) => (
        <p key={i} className="where">{t}</p>
      ))}
      {safe && (
        <button
          className={`safe-btn ${sel?.kind === "pose" ? "on" : ""}`}
          onClick={() => select({ kind: "pose", name: design.compare_pose, parts: safe.parts, note: "clear when parked" })}
        >
          Show the intended way ({design.compare_pose})
        </button>
      )}
      {n > 0 && (
        <div className="cols">
          <div className="cols-head">
            <span>Collisions, deepest first</span>
            {n > 8 && <input className="cols-q" placeholder="Filter parts" value={q} onChange={(e) => setQ(e.target.value)} />}
          </div>
          <div className="cols-list">
            {list.map((c) => {
              const on = sel?.kind === "collision" && sel.c === c;
              return (
                <button key={c.parts.join("|")} className={`col-row ${on ? "on" : ""}`} onClick={() => select({ kind: "collision", c })}>
                  <span className="col-parts mono">
                    <span className="sw blue" />
                    {c.parts[0]}
                    <br />
                    <span className="sw red" />
                    {c.parts[1]}
                  </span>
                  <span className="col-depth mono">{c.worst.penetration_mm.toFixed(1)} mm</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {n === 0 && design.poses.length > 0 && (
        <div className="cols">
          <div className="cols-head">
            <span>Named poses</span>
          </div>
          <div className="pose-chips">
            {design.poses.map((p) => (
              <button key={p.name} className={`chip-btn ${sel?.kind === "pose" && sel.name === p.name ? "on" : ""}`} onClick={() => select({ kind: "pose", name: p.name })}>
                {p.name}
              </button>
            ))}
          </div>
        </div>
      )}
      <p className="fineprint">
        {num(st.pairs_sampled || 0)} of {num(st.pairs_total || 0)} part pairs swept through every joint's range
        {design.reach_rule ? ", limited to poses the firmware's reach rule allows" : ""}. Designed contacts and parts on the same body are skipped.
        Source: <span className="mono">{design.source}</span>
      </p>
    </aside>
  );
}

export default function CollideTab({ motion }) {
  const ids = motion.map((m) => m.id);
  const [picked, setPicked] = useState(ids[0]);
  const design = motion.find((m) => m.id === picked) || motion[0];
  const [sel, setSel] = useState(null);
  const [which, setWhich] = useState("worst");
  const [ghost, setGhost] = useState(true);
  const apiRef = useRef(null);
  const onT = useRef(null);

  // default selection per design: its deepest collision, or its first named pose
  useEffect(() => {
    if (!design) return;
    setSel(design.collisions[0] ? { kind: "collision", c: design.collisions[0] } : design.poses[0] ? { kind: "pose", name: design.poses[0].name } : null);
    setWhich("worst");
  }, [design?.id]);

  useEffect(() => {
    const on = (e) => {
      if (e.metaKey || e.ctrlKey || e.target.tagName === "INPUT") return;
      const list = design?.collisions || [];
      const i = sel?.kind === "collision" ? list.indexOf(sel.c) : -1;
      if (e.key === "ArrowDown" && i < list.length - 1) setSel({ kind: "collision", c: list[i + 1] });
      if (e.key === "ArrowUp" && i > 0) setSel({ kind: "collision", c: list[i - 1] });
      const d = ids.indexOf(design?.id);
      if (e.key === "ArrowRight" && d < ids.length - 1) setPicked(ids[d + 1]);
      if (e.key === "ArrowLeft" && d > 0) setPicked(ids[d - 1]);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  if (!design) {
    return (
      <div className="soon">
        <h2>Will it collide with itself?</h2>
        <p>No collision sweeps yet. Run `python -m goodman motion` and then `python -m goodman export`.</p>
      </div>
    );
  }
  return (
    <div className="body">
      <nav className="rail">
        {motion.map((m) => {
          const S = STATUS[m.status] || STATUS.collides;
          return (
            <button key={m.id} className={`rail-row ${m.id === design.id ? "active" : ""}`} onClick={() => setPicked(m.id)}>
              <span className="rail-title">
                {m.title}
                <span className="rail-sub mono">{m.collisions.length ? `${m.collisions.length} pairs` : "0 pairs"}</span>
              </span>
              <span className={`pill s-${S.tone}`}>{S.short}</span>
            </button>
          );
        })}
      </nav>
      <figure className="viewer" style={{ margin: 0 }}>
        <CollideViewer key={design.id} design={design} sel={sel} which={which} ghost={ghost} onT={onT} apiRef={apiRef} />
        <PoseBar design={design} sel={sel} which={which} setWhich={setWhich} ghost={ghost} setGhost={setGhost} apiRef={apiRef} onT={onT} />
      </figure>
      <DesignPanel design={design} sel={sel} select={setSel} />
    </div>
  );
}
