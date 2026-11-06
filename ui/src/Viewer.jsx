import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { buildScene, COLORMAP_CSS } from "./scenes.js";

const fmt = (x, d = 0) => (x == null ? "–" : Number(x).toFixed(d));

function Legend({ legend }) {
  if (!legend) return null;
  if (legend.kind === "stress") {
    // the bar maps sigma/allowable 0..1 onto 0..92 %, red beyond (same stops as scenes.js)
    return (
      <div className="legend">
        <div className="legend-bar" style={{ background: COLORMAP_CSS }}>
          <span className="tick" style={{ left: "80%" }} />
        </div>
        <div className="legend-read mono">
          <span>
            peak <b>{fmt(legend.peak, 1)} MPa</b>
          </span>
          <span>allowable {fmt(legend.allow)} MPa</span>
        </div>
      </div>
    );
  }
  if (legend.kind === "torque") {
    const max = Math.max(legend.need * legend.requiredMargin, legend.have) * 1.05;
    return (
      <div className="legend">
        <div className="torque-bars mono">
          <div><span>servo stall</span><i style={{ width: `${(legend.have / max) * 100}%` }} /><b>{fmt(legend.have, 1)} kg·cm</b></div>
          <div><span>needed</span><i className="red" style={{ width: `${(legend.need / max) * 100}%` }} /><b>{fmt(legend.need, 1)}</b></div>
          <div><span>× {legend.requiredMargin} margin</span><i className="red faint" style={{ width: `${((legend.need * legend.requiredMargin) / max) * 100}%` }} /><b>{fmt(legend.need * legend.requiredMargin, 1)}</b></div>
        </div>
      </div>
    );
  }
  const red = legend.kind === "contact";
  return (
    <div className="legend">
      <div className={`contact mono ${red ? "red" : "blue"}`}>
        <span className="swatch" /> {legend.text}
      </div>
    </div>
  );
}

// What Goodman did for this part, step by step, from its result.json.
function Explain({ r, inputs }) {
  const [dx, dy, dz] = [r.bbox[3] - r.bbox[0], r.bbox[4] - r.bbox[1], r.bbox[5] - r.bbox[2]];
  const cuts = r.sections || [];
  const arm = cuts.filter((q) => q.kind === "arm").length;
  const leg = cuts.length - arm;
  const crit = r.critical || "";
  const where = crit.split(":")[0].replace("(wall leg)", "on the wall plate");
  const sigma = (crit.match(/= ([\d.]+) MPa vs ([\d.]+) MPa/) || []).slice(1);
  const kt = (crit.match(/Kt ([\d.]+)/) || [])[1];
  const how = /across layers/.test(r.critical_note) ? "across print layers" : /yield/.test(r.critical_note) ? "yield" : "along print layers";
  const ok = r.goodman_verdict === "safe";
  return (
    <div className="explain">
      <div className="explain-head">What Goodman did</div>
      <ol>
        <li>Ran ChatGPT's CAD script in a sandbox and got the real part: {dx.toFixed(0)} × {dy.toFixed(0)} × {dz.toFixed(0)} mm.</li>
        <li>Put the {inputs.load_n.toFixed(1)} N load where it acts, {r.lever_mm.toFixed(0)} mm from the wall.</li>
        <li>Cut the part {cuts.length} times ({arm} along the arm, {leg} through the wall plate) and measured each cross-section.</li>
        <li>
          Worst cut, {where}: {sigma[0]} MPa{kt ? ` (corner factor ${kt})` : ""} against {sigma[1]} MPa {how}.
        </li>
        <li>
          Safety factor <b>{r.safety_factor.toFixed(2)}</b> vs {inputs.required_safety_factor} required: <b className={ok ? "ok" : "bad"}>{ok ? "holds" : "breaks"}</b>
          {r.claimed_sf != null ? `. ChatGPT said ${r.claimed_sf}.` : "."}
        </li>
      </ol>
    </div>
  );
}

export default function Viewer({ task }) {
  const host = useRef(null);
  const [built, setBuilt] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = host.current;
    const spec = buildScene(task.scene);
    setBuilt(spec);
    if (!el || !spec) return;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setFailed(true);
      return;
    }
    setFailed(false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d2c6, 2.1));
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(-1, -2, 3);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(2, 1, 1);
    scene.add(fill);
    scene.add(spec.group);

    // frame the part
    const bbox = new THREE.Box3().setFromObject(spec.group);
    const size = bbox.getSize(new THREE.Vector3());
    const center = bbox.getCenter(new THREE.Vector3());
    const radius = size.length() / 2;
    const grid = new THREE.GridHelper(radius * 4, 24, 0xd5e3ee, 0xe9f0f6);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, bbox.min.z - radius * 0.02);
    scene.add(grid);

    if (spec.focus) center.set(...spec.focus);
    const camR = spec.focusRadius || radius;
    const camera = new THREE.PerspectiveCamera(30, 1, camR / 100, radius * 40);
    camera.up.set(0, 0, 1);
    const dir = new THREE.Vector3(...spec.view).normalize();
    camera.position.copy(center).addScaledVector(dir, camR / Math.sin((15 * Math.PI) / 180));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.update();

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // design parts: push the part up and left so the explanation card has the bottom right
      if (task.area === "cad") camera.setViewOffset(w, h, w * 0.14, h * 0.1, w, h);
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf;
    const tick = () => {
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        o.geometry?.dispose?.();
        if (o.material) [].concat(o.material).forEach((m) => m.dispose());
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [task.id, task.scene]);

  const tag = task.area === "cad" ? "The AI's part · beam-theory stress" : task.area === "strength" ? (task.scene?.kind === "arm_torque" ? "Torque" : "Beam-theory stress") : "Geometry";
  return (
    <figure className="viewer" style={{ margin: 0 }}>
      <div className="viewer-canvas" ref={host}>
        {failed && <div className="viewer-fallback">WebGL is not available in this browser.</div>}
        {!built && <div className="viewer-fallback">No 3D view for this case yet.</div>}
      </div>
      {built && <Legend legend={built.legend} />}
      {task.area === "cad" && !String(task.id).includes(":") && task.result?.sections && (
        <Explain r={task.result} inputs={task.inputs} />
      )}
    </figure>
  );
}
