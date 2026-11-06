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
          <span className="tick" style={{ left: "92%" }} />
        </div>
        <div className="legend-scale mono">
          <span>0</span>
          <span style={{ left: "92%" }}>allowable {fmt(legend.allow)} MPa</span>
        </div>
        <div className="legend-read mono">
          peak {fmt(legend.peak, 1)} MPa
          {legend.kt > 1.001 ? ` (Kt ${legend.kt.toFixed(2)} × ${fmt(legend.nominal, 1)})` : ""}
          <span className="muted"> · allowable = {fmt(legend.strength)} MPa / SF {legend.requiredSf}</span>
        </div>
      </div>
    );
  }
  if (legend.kind === "torque") {
    const max = Math.max(legend.need * legend.requiredMargin, legend.have) * 1.05;
    return (
      <div className="legend">
        <div className="torque-bars mono">
          <div><span>stall rating</span><i style={{ width: `${(legend.have / max) * 100}%` }} /><b>{fmt(legend.have, 1)} kg·cm</b></div>
          <div><span>needed</span><i className="red" style={{ width: `${(legend.need / max) * 100}%` }} /><b>{fmt(legend.need, 1)}</b></div>
          <div><span>needed × {legend.requiredMargin}</span><i className="red faint" style={{ width: `${((legend.need * legend.requiredMargin) / max) * 100}%` }} /><b>{fmt(legend.need * legend.requiredMargin, 1)}</b></div>
        </div>
      </div>
    );
  }
  return (
    <div className="legend">
      <div className={`legend-read mono ${legend.kind === "contact" ? "red-text" : "blue-text"}`}>
        <span className={`swatch ${legend.kind === "contact" ? "red" : "blue"}`} /> {legend.text}
      </div>
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
    scene.background = new THREE.Color(0xf4f2ed);
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
    const grid = new THREE.GridHelper(radius * 4, 24, 0xd6d1c6, 0xe4e0d7);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, bbox.min.z - radius * 0.02);
    scene.add(grid);

    if (spec.focus) center.set(...spec.focus);
    const camR = spec.focusRadius || radius;
    const camera = new THREE.PerspectiveCamera(30, 1, camR / 100, radius * 40);
    camera.up.set(0, 0, 1);
    const dir = new THREE.Vector3(...spec.view).normalize();
    camera.position.copy(center).addScaledVector(dir, camR * 3.1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.update();

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
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

  const isStrength = task.area === "strength";
  return (
    <figure className="viewer">
      <div className="viewer-head">
        <span className="label">{isStrength ? (task.scene.kind === "arm_torque" ? "Torque at the shoulder" : "Beam-theory stress, not FEA") : "Geometry and contact"}</span>
        <span className="muted small">drag to orbit · scroll to zoom</span>
      </div>
      <div className="viewer-canvas" ref={host}>
        {failed && <div className="viewer-fallback">WebGL is not available in this browser.</div>}
        {!built && <div className="viewer-fallback">No 3D view for this case.</div>}
      </div>
      {built && (
        <figcaption>
          <Legend legend={built.legend} />
          <ul className="viewer-notes">
            {built.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </figcaption>
      )}
    </figure>
  );
}
