// 3D scenes for each task, built with plain three.js. Z is up, units are mm.
//
// Strength scenes colour each vertex with the same beam-theory model the checker
// uses (sigma = M*c/I along the length and through the depth, Kt applied as a
// local peak at the fillet/step). This is a picture of the closed-form check,
// not an FEA result, and the captions say so.

import * as THREE from "three";

export const COLORS = {
  ink: 0x1d1d1b,
  part: 0xdfe5ea,
  partDark: 0xaab4bd,
  steel: 0xbfc3c7,
  pcb: 0x55705e,
  red: 0xe5484d,
  blue: 0x20a4f3,
  ghost: 0x8a96a3,
};

// ---------------------------------------------------------------- colour map
// t = sigma / allowable (allowable = strength / required SF). Pale -> blue up to
// the allowable, red beyond it.
const STOPS = [
  [0.0, [0.91, 0.94, 0.965]],
  [0.5, [0.60, 0.80, 0.93]],
  [0.92, [0.09, 0.47, 0.78]],
  [1.0, [0.898, 0.282, 0.302]],
];
export function stressColor(t, out = new THREE.Color()) {
  if (t >= 1) return out.setRGB(...STOPS[3][1], THREE.SRGBColorSpace);
  t = Math.max(0, t);
  for (let i = 1; i < STOPS.length; i++) {
    if (t <= STOPS[i][0]) {
      const [t0, c0] = STOPS[i - 1];
      const [t1, c1] = STOPS[i];
      const f = (t - t0) / (t1 - t0);
      return out.setRGB(c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f, THREE.SRGBColorSpace);
    }
  }
  return out.setRGB(...STOPS[3][1], THREE.SRGBColorSpace);
}
export const COLORMAP_CSS = `linear-gradient(90deg, rgb(232,240,246) 0%, rgb(153,204,237) 46%, rgb(23,120,199) 85%, rgb(229,72,77) 92%, rgb(229,72,77) 100%)`;

// ---------------------------------------------------------------- helpers
const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.0, ...extra });

function withEdges(mesh, opacity = 0.35, color = COLORS.ink) {
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 25),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
  );
  mesh.add(edges);
  return mesh;
}

function box(sx, sy, sz, color, at = [0, 0, 0], extra) {
  const m = withEdges(new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat(color, extra)));
  m.position.set(...at);
  return m;
}

function ghostBox(sx, sy, sz, at = [0, 0, 0], opacity = 0.12, color = COLORS.ghost) {
  const m = new THREE.Mesh(
    new THREE.BoxGeometry(sx, sy, sz),
    mat(color, { transparent: true, opacity, depthWrite: false }),
  );
  withEdges(m, 0.45);
  m.position.set(...at);
  return m;
}

function cylZ(r, h, color, at = [0, 0, 0], seg = 48, extra) {
  const g = new THREE.CylinderGeometry(r, r, h, seg);
  g.rotateX(Math.PI / 2);
  const m = withEdges(new THREE.Mesh(g, mat(color, extra)), 0.3);
  m.position.set(...at);
  return m;
}

function arrow(from, dir, len, color = COLORS.ink) {
  const d = new THREE.Vector3(...dir).normalize();
  const a = new THREE.ArrowHelper(d, new THREE.Vector3(...from), len, color, Math.min(len * 0.25, 14), Math.min(len * 0.12, 7));
  return a;
}

function marker(at, r = 1.6, color = COLORS.red) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 16), new THREE.MeshBasicMaterial({ color }));
  m.position.set(...at);
  return m;
}

function line(points, color = COLORS.red, opacity = 1, dashed = false) {
  const g = new THREE.BufferGeometry().setFromPoints(points.map((p) => new THREE.Vector3(...p)));
  const m = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 3, gapSize: 2, transparent: true, opacity })
    : new THREE.LineBasicMaterial({ color, transparent: true, opacity });
  const l = new THREE.Line(g, m);
  if (dashed) l.computeLineDistances();
  return l;
}

// A box mesh whose vertex colours come from fn(x, y, z) in world coordinates.
function stressBox(sx, sy, sz, center, segs, fn) {
  const g = new THREE.BoxGeometry(sx, sy, sz, ...segs);
  g.translate(...center);
  const pos = g.attributes.position;
  const col = new Float32Array(pos.count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    stressColor(fn(pos.getX(i), pos.getY(i), pos.getZ(i)), c);
    col.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8 }));
  return withEdges(m, 0.25);
}

const ktFactor = (kt, d, rho) => 1 + (kt - 1) * Math.exp(-d / rho);

// ---------------------------------------------------------------- strength
function cantileverL(s) {
  // L-bracket: arm along +x (depth h in z), wall leg going up from the arm's root.
  const g = new THREE.Group();
  const L = s.length_mm, b = s.width_mm, h = s.depth_mm, F = s.load_n;
  const I = (b * h ** 3) / 12;
  const allow = s.strength / (s.required_sf || 1);
  const H = Math.max(60, L * 0.6); // leg height: not given in the task, illustrative
  const kt = s.kt || 1;
  const rho = Math.max(s.fillet_mm || 0, h * 0.3);
  const corner = [0, h / 2]; // inside corner (x, z): top of arm meets inner face of leg
  const dCorner = (x, z) => Math.hypot(x - corner[0], z - corner[1]);
  const arm = (x, y, z) => {
    const M = F * Math.max(L - Math.max(x, 0), 0);
    const sig = (M * Math.abs(z)) / I;
    return (sig * ktFactor(kt, dCorner(x, z), rho)) / allow;
  };
  const leg = (x, y, z) => {
    // wall leg: moment F*L at the corner, assumed to fall linearly to the top screw
    const sUp = Math.max(z - h / 2, 0);
    const M = F * L * Math.max(1 - sUp / H, 0);
    const u = x + h / 2; // across the leg thickness, 0 at its mid-plane
    return ((M * Math.abs(u)) / I) * ktFactor(kt, dCorner(x, z), rho) / allow;
  };
  g.add(stressBox(L, b, h, [L / 2, 0, 0], [160, 2, 16], arm));
  g.add(stressBox(h, b, H + h / 2, [-h / 2, 0, (H - h / 2) / 2], [16, 2, 90], leg));
  // wall
  const wall = ghostBox(2, b * 2.4, H * 1.3, [-h - 1, 0, H / 2], 0.08);
  g.add(wall);
  // load
  const m = Math.max(10, b * 1.1);
  g.add(ghostBox(m * 1.6, b * 1.4, m, [L - m * 0.8, 0, h / 2 + m / 2], 0.1));
  g.add(arrow([L - m * 0.8, 0, h / 2 + m + 45], [0, 0, -1], 40));
  g.add(marker([0, 0, h / 2], Math.max(0.9, h * 0.13), s.sigma_max > allow ? COLORS.red : COLORS.ink));
  return {
    group: g,
    view: [0.55, -1.0, 0.45],
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: s.required_sf, peak: s.sigma_max, nominal: s.sigma_nom, kt },
    notes: [
      `Peak at the ${s.fillet_mm} mm inside fillet: Kt ${kt.toFixed(2)} x ${s.sigma_nom.toFixed(1)} = ${s.sigma_max.toFixed(1)} MPa`,
      `Wall-leg height and moment fall-off are illustrative; the check is at the corner`,
    ],
  };
}

function cantileverStep(s) {
  const g = new THREE.Group();
  const L = s.length_mm, t = s.width_mm, d = s.depth_mm, F = s.load_n;
  const D = s.step.D_mm, r = s.step.r_mm;
  const allow = s.strength / (s.required_sf || 1);
  const Id = (t * d ** 3) / 12, ID = (t * D ** 3) / 12;
  const kt = s.kt || 1;
  const rho = Math.max(r, d * 0.25);
  const hub = 30;
  const dStep = (x, z) => Math.min(Math.hypot(x, z - d / 2), Math.hypot(x, z + d / 2));
  const arm = (x, y, z) => ((F * Math.max(L - x, 0) * Math.abs(z)) / Id) * ktFactor(kt, dStep(x, z), rho) / allow;
  const hubF = (x, y, z) => {
    const near = Math.abs(z) <= d / 2 + 0.5 ? ktFactor(kt, dStep(x, z), rho) : 1;
    return ((F * (L - x) * Math.abs(z)) / ID) * near / allow;
  };
  g.add(stressBox(L, t, d, [L / 2, 0, 0], [300, 1, 24], arm));
  g.add(stressBox(hub, t, D, [-hub / 2, 0, 0], [30, 1, 50], hubF));
  g.add(ghostBox(4, 30, D * 2, [-hub - 2, 0, 0], 0.1));
  g.add(arrow([L, 0, 60], [0, 0, -1], 50));
  g.add(marker([0, 0, d / 2], 1.2));
  g.add(marker([0, 0, -d / 2], 1.2));
  return {
    group: g,
    view: [0.3, -1.0, 0.3],
    focus: [35, 0, 0],
    focusRadius: 70,
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: s.required_sf, peak: s.sigma_max, nominal: s.sigma_nom, kt },
    notes: [
      `Peak at the ${r} mm step radius (D/d = ${(D / d).toFixed(2)}): Kt ${kt.toFixed(2)} x ${s.sigma_nom.toFixed(1)} = ${s.sigma_max.toFixed(0)} MPa`,
      `Hub length is illustrative; the check is at the step`,
    ],
  };
}

function column(s) {
  const g = new THREE.Group();
  const L = s.length_mm, d = s.diameter_mm;
  const allow = s.strength / 2;
  const tAxial = s.sigma / allow;
  const rod = cylZ(d / 2, L, 0, [0, 0, L / 2], 32);
  rod.material = new THREE.MeshStandardMaterial({ color: stressColor(tAxial), roughness: 0.8 });
  g.add(rod);
  // pins and clevises
  for (const z of [0, L]) {
    g.add(box(16, 10, 6, COLORS.partDark, [0, 0, z === 0 ? -3 : L + 3]));
    const pin = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, 14, 20), mat(COLORS.ink));
    pin.position.set(0, 0, z);
    g.add(pin);
  }
  // first buckling mode, amplitude exaggerated
  const A = L * 0.07;
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const z = (L * i) / 64;
    pts.push(new THREE.Vector3(A * Math.sin((Math.PI * z) / L), 0, z));
  }
  const tube = new THREE.Mesh(
    new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 96, d / 2, 16, false),
    new THREE.MeshStandardMaterial({ color: COLORS.red, roughness: 0.7, transparent: true, opacity: 0.55 }),
  );
  g.add(tube);
  g.add(arrow([0, 0, L + 70], [0, 0, -1], 60));
  g.add(arrow([0, 0, -70], [0, 0, 1], 60));
  return {
    group: g,
    view: [1.0, -1.0, 0.2],
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: 2, peak: s.sigma, nominal: s.sigma, kt: 1 },
    notes: [
      `Rod coloured by direct stress P/A = ${s.sigma.toFixed(1)} MPa: it looks comfortable`,
      `Red: first buckling mode (amplitude exaggerated). P_cr = ${s.buckling_load_n.toFixed(0)} N < ${s.load_n} N load`,
    ],
  };
}

function armTorque(s) {
  const g = new THREE.Group();
  const L = s.arm_length_mm;
  // servo body (MG996R is about 40 x 20 x 43 mm) and horn; axis along y
  g.add(box(40, 20, 38, COLORS.red, [-10, -14, -8], { roughness: 0.7 }));
  g.add(cylZ(9, 2, COLORS.ink, [0, 0, 0]).rotateX(Math.PI / 2));
  g.add(box(L, 4, 14, COLORS.part, [L / 2, -2, 0]));
  g.add(box(30, 30, 30, COLORS.partDark, [L - 15, -2, 22]));
  g.add(arrow([L - 15, -2, 90], [0, 0, -1], 50));
  g.add(arrow([L / 2, -2, 55], [0, 0, -1], 40, COLORS.ghost));
  // torque arc around the servo axis (the direction gravity turns the arm)
  const arc = new THREE.Mesh(new THREE.TorusGeometry(34, 1.2, 8, 48, Math.PI * 1.2), mat(COLORS.red));
  arc.rotation.x = Math.PI / 2;
  arc.rotation.y = -Math.PI * 0.1;
  arc.position.y = -26;
  g.add(arc);
  // dimension line for the lever arm
  g.add(line([[0, -2, -30], [L - 15, -2, -30]], COLORS.ink, 0.6));
  g.add(line([[0, -2, -26], [0, -2, -34]], COLORS.ink, 0.6));
  g.add(line([[L - 15, -2, -26], [L - 15, -2, -34]], COLORS.ink, 0.6));
  return {
    group: g,
    view: [0.25, -1.0, 0.3],
    legend: { kind: "torque", need: s.required_kgcm, have: s.stall_kgcm, margin: s.margin, requiredMargin: s.required_margin },
    notes: [
      `Tip ${s.tip_mass_kg} kg at ${L} mm and arm ${s.arm_mass_kg} kg at ${L / 2} mm: ${s.required_kgcm.toFixed(1)} kg·cm needed`,
      `Stall rating ${s.stall_kgcm} kg·cm (red: servo overloaded even before any margin)`,
    ],
  };
}

// ---------------------------------------------------------------- collision
function armTiltBase(s) {
  const g = new THREE.Group();
  const [bx, by, bz] = s.inputs.base_box_mm;
  const [, , pz] = s.inputs.pivot_mm;
  const [lx, ly, lz] = s.inputs.link_box_mm;
  const theta = (s.collision_angle_deg ?? 9.2) * (Math.PI / 180);
  const target = Math.abs(s.inputs.target_tilt_deg) * (Math.PI / 180);
  g.add(box(bx, by, bz, COLORS.part, [0, 0, bz / 2]));
  // pivot pin
  const pin = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, ly + 10, 24), mat(COLORS.ink));
  pin.position.set(0, 0, pz);
  g.add(pin);
  const link = (angle, solid) => {
    const piv = new THREE.Group();
    piv.position.set(0, 0, pz);
    const m = solid ? box(lx, ly, lz, COLORS.steel, [lx / 2, 0, 0]) : ghostBox(lx, ly, lz, [lx / 2, 0, 0], 0.1, COLORS.red);
    piv.add(m);
    piv.rotation.y = angle; // +angle tilts the +x end down
    return piv;
  };
  g.add(link(theta, true));
  g.add(link(target, false));
  // the centerline reasoning: line from pivot at -30 degrees just reaching the base corner
  g.add(line([[0, 0, pz], [lx * Math.cos(target), 0, pz - lx * Math.sin(target)]], COLORS.ink, 0.5, true));
  // contact: the link's underside touches the base's top edge at x = +30
  g.add(line([[bx / 2, -by / 2, bz], [bx / 2, by / 2, bz]], COLORS.red));
  g.add(marker([bx / 2, -ly / 2, bz], 1.6));
  g.add(marker([bx / 2, ly / 2, bz], 1.6));
  return {
    group: g,
    view: [0.25, -1.0, 0.25],
    legend: { kind: "contact", text: `First contact at ${(s.collision_angle_deg ?? 9.2).toFixed(1)}° (target ${Math.abs(s.inputs.target_tilt_deg)}°)` },
    notes: [
      `Solid link: first-contact pose, underside on the base's top edge (red)`,
      `Red ghost: the requested ${Math.abs(s.inputs.target_tilt_deg)}° pose. Dashed: the centerline-only reasoning`,
    ],
  };
}

function pcbEnclosure(s) {
  const g = new THREE.Group();
  const [cx, cy, cz] = s.inputs.cavity_mm;
  const [px, py, pt] = s.inputs.pcb_mm;
  const so = s.inputs.standoff_mm;
  const hc = s.inputs.tallest_component_mm;
  const clear = cz - (so + pt + hc);
  const wall = 2;
  // floor + walls (cut away on the front), lid above
  g.add(box(cx + 2 * wall, cy + 2 * wall, wall, COLORS.part, [0, 0, -wall / 2]));
  g.add(box(wall, cy + 2 * wall, cz, COLORS.part, [-cx / 2 - wall / 2, 0, cz / 2]));
  g.add(box(wall, cy + 2 * wall, cz, COLORS.part, [cx / 2 + wall / 2, 0, cz / 2]));
  g.add(box(cx, wall, cz, COLORS.part, [0, cy / 2 + wall / 2, cz / 2]));
  g.add(ghostBox(cx + 2 * wall, cy + 2 * wall, wall, [0, 0, cz + wall / 2], 0.16));
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) g.add(cylZ(2.5, so, COLORS.partDark, [sx * (px / 2 - 4), sy * (py / 2 - 4), so / 2], 24));
  g.add(box(px, py, pt, COLORS.pcb, [0, 0, so + pt / 2]));
  // the tall capacitor, with its top slice coloured by the result
  const capR = 5;
  const top = so + pt + hc;
  const capAt = [px / 2 - 12, 0];
  g.add(cylZ(capR, hc - 0.6, COLORS.steel, [capAt[0], capAt[1], so + pt + (hc - 0.6) / 2]));
  g.add(cylZ(capR, 0.6, clear < 0 ? COLORS.red : COLORS.blue, [capAt[0], capAt[1], top - 0.3]));
  if (clear < 0) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(capR, capR + 1.8, 48), new THREE.MeshBasicMaterial({ color: COLORS.red, side: THREE.DoubleSide }));
    ring.position.set(capAt[0], capAt[1], cz + 0.01);
    g.add(ring);
  } else {
    g.add(line([[capAt[0] + capR + 3, 0, top], [capAt[0] + capR + 3, 0, cz]], COLORS.blue));
  }
  // a few smaller parts for scale
  g.add(box(12, 9, 3.5, COLORS.ink, [-px / 2 + 8, 8, so + pt + 1.75]));
  g.add(box(8, 8, 1.2, COLORS.ink, [-6, -6, so + pt + 0.6]));
  return {
    group: g,
    view: [0.3, -1.0, 0.55],
    legend: clear < 0
      ? { kind: "contact", text: `Capacitor top ${top.toFixed(1)} mm vs lid underside ${cz.toFixed(1)} mm: ${(-clear).toFixed(1)} mm into the lid` }
      : { kind: "clear", text: `Capacitor top ${top.toFixed(1)} mm, lid ${cz.toFixed(1)} mm: ${clear.toFixed(1)} mm clearance (needs ${s.inputs.min_clearance_mm} mm)` },
    notes: [
      `Stack: floor 0, standoff ${so}, board ${pt}, capacitor ${hc} = ${top.toFixed(1)} mm`,
      `Front wall removed for the view; lid drawn translucent`,
    ],
  };
}

function counterboreCover(s) {
  const g = new THREE.Group();
  const { head_d_mm: hd, head_k_mm: k, counterbore_d_mm: cd, counterbore_depth_mm: depth } = s.inputs;
  const plateT = 10, coverT = 4, W = 60, Dp = 30;
  const proud = k - depth;
  g.add(ghostBox(W, Dp, plateT, [0, 0, -plateT / 2], 0.22, COLORS.part));
  g.add(ghostBox(W, Dp, coverT, [0, 0, coverT / 2], 0.14));
  for (const x of [-15, 15]) {
    // counterbore wall (drawn as a thin open tube) and the screw
    const bore = new THREE.Mesh(new THREE.CylinderGeometry(cd / 2, cd / 2, depth, 48, 1, true), mat(COLORS.partDark, { side: THREE.DoubleSide, transparent: true, opacity: 0.5 }));
    bore.rotateX(Math.PI / 2);
    bore.position.set(x, 0, -depth / 2);
    g.add(bore);
    g.add(cylZ(hd / 2, depth, COLORS.steel, [x, 0, -depth + depth / 2]));
    g.add(cylZ(hd / 2, proud, COLORS.red, [x, 0, proud / 2]));
    g.add(cylZ(2, plateT - depth, COLORS.steel, [x, 0, -depth - (plateT - depth) / 2], 24));
    const hex = new THREE.Mesh(new THREE.CylinderGeometry(1.75, 1.75, 0.2, 6), new THREE.MeshBasicMaterial({ color: COLORS.ink }));
    hex.rotateX(Math.PI / 2);
    hex.position.set(x, 0, proud + 0.11);
    g.add(hex);
  }
  return {
    group: g,
    view: [0.2, -1.0, 0.5],
    legend: { kind: "contact", text: `Head height ${k} mm in a ${depth} mm counterbore: ${proud.toFixed(1)} mm into the cover` },
    notes: [`Red: the part of each M4 head above the plate face, overlapping the cover`, `Plate and cover drawn translucent`],
  };
}

function gearShape(z, m, rootFactor = 1.25) {
  const rp = (m * z) / 2, ra = rp + m, rf = rp - rootFactor * m;
  const shape = new THREE.Shape();
  const step = (Math.PI * 2) / z;
  for (let i = 0; i < z; i++) {
    const a = i * step;
    const pts = [
      [rf, a - step * 0.5], [rf, a - step * 0.28], [ra, a - step * 0.14], [ra, a + step * 0.14], [rf, a + step * 0.28],
    ];
    pts.forEach(([r, t], j) => {
      const p = [r * Math.cos(t), r * Math.sin(t)];
      if (i === 0 && j === 0) shape.moveTo(...p);
      else shape.lineTo(...p);
    });
  }
  shape.closePath();
  return shape;
}

function gearCollar(s) {
  const g = new THREE.Group();
  const { module_mm: m, z_gear: zg, z_pinion: zp, center_distance_mm: C, collar_d_mm: cdia } = s.inputs;
  const faceG = 12, faceP = 6;
  const ext = (shape, depth, color, z0) => {
    const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 8 });
    const mesh = withEdges(new THREE.Mesh(geo, mat(color)), 0.25);
    mesh.position.z = z0;
    return mesh;
  };
  const gear = ext(gearShape(zg, m), faceG, COLORS.part, 0);
  g.add(gear);
  const pinion = ext(gearShape(zp, m), faceP, COLORS.steel, 0);
  pinion.position.x = C;
  pinion.rotation.z = Math.PI / zp;
  g.add(pinion);
  // shafts
  g.add(cylZ(4, 24, COLORS.ink, [0, 0, 2]));
  g.add(cylZ(3, 24, COLORS.ink, [C, 0, 2]));
  // collar on the pinion shaft, in the gear's plane next to the pinion
  const rc = cdia / 2;
  g.add(cylZ(rc, faceG - faceP, COLORS.partDark, [C, 0, faceP + (faceG - faceP) / 2]));
  // overlap: the lens where the gear's tip circle and the collar overlap
  const ra = (m * zg) / 2 + m;
  const xi = (C * C + ra * ra - rc * rc) / (2 * C);
  if (xi < ra) {
    const yi = Math.sqrt(ra * ra - xi * xi);
    const lens = new THREE.Shape();
    const a1 = Math.atan2(yi, xi);
    lens.absarc(0, 0, ra, -a1, a1, false);
    const a2 = Math.atan2(yi, xi - C);
    lens.absarc(C, 0, rc, a2, 2 * Math.PI - a2, false);
    const lensMesh = new THREE.Mesh(
      new THREE.ExtrudeGeometry(lens, { depth: faceG - faceP + 0.2, bevelEnabled: false, curveSegments: 24 }),
      new THREE.MeshBasicMaterial({ color: COLORS.red }),
    );
    lensMesh.position.z = faceP - 0.1;
    g.add(lensMesh);
  }
  // tip circle and pitch circle on the gear's top face
  const circle = (r, color, opacity, dashed) => {
    const pts = [];
    for (let i = 0; i <= 128; i++) pts.push([r * Math.cos((i / 128) * Math.PI * 2), r * Math.sin((i / 128) * Math.PI * 2), faceG + 0.2]);
    return line(pts, color, opacity, dashed);
  };
  g.add(circle((m * zg) / 2, COLORS.ink, 0.6, true));
  g.add(circle(ra, COLORS.red, 0.9, false));
  return {
    group: g,
    view: [0.15, -0.35, 1.0],
    legend: { kind: "contact", text: `Tip radius ${ra} + collar radius ${rc} = ${ra + rc} mm > ${C} mm centers: ${(ra + rc - C).toFixed(1)} mm overlap` },
    notes: [`Red: where the 40T tips sweep through the collar. Dashed: pitch circle (r ${(m * zg) / 2}), solid red: tip circle (r ${ra})`],
  };
}

function cantileverFatigue(s) {
  // Round arm drawn as a square bar of side d; colour is the peak of each load cycle.
  const g = new THREE.Group();
  const L = s.length_mm, d = s.diameter_mm, F = s.load_n;
  const I = (Math.PI * d ** 4) / 64;
  const allow = s.strength / (s.required_sf || 1);
  const arm = (x, y, z) => (F * Math.max(L - x, 0) * Math.min(Math.abs(z), d / 2)) / I / allow;
  g.add(stressBox(L, d, d, [L / 2, 0, 0], [120, 1, 16], arm));
  g.add(box(14, 30, 30, COLORS.partDark, [-7, 0, 0]));
  // the drive pushes 0 -> F -> 0: ghost of the arm at its other extreme
  g.add(ghostBox(L, d, d, [L / 2, 0, 0], 0.08));
  g.add(arrow([L, 0, 45], [0, 0, -1], 35));
  g.add(arrow([L, 0, -45], [0, 0, 1], 35, COLORS.muted ?? COLORS.ink));
  return {
    group: g,
    view: [0.45, -1.0, 0.4],
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: s.required_sf, peak: s.sigma_max, nominal: s.sigma_max, kt: 1 },
    notes: [],
  };
}

function simpleBeam(s) {
  // Flat bar on two supports, centre load; drawn at its true computed sag.
  const g = new THREE.Group();
  const L = s.span_mm, b = s.width_mm, h = s.depth_mm, P = s.load_n, E = s.E_mpa;
  const I = (b * h ** 3) / 12;
  const allow = s.strength / (s.required_sf || 1);
  const M = (x) => (P * Math.min(x, L - x)) / 2;
  const sag = (x) => {
    const u = Math.min(x, L - x);
    return (P * u * (3 * L * L - 4 * u * u)) / (48 * E * I);
  };
  const bar = stressBox(L, b, h, [L / 2, 0, 0], [200, 2, 6], (x, y, z) => (M(x) * Math.abs(z)) / I / allow);
  const pos = bar.geometry.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, pos.getZ(i) - sag(pos.getX(i)));
  pos.needsUpdate = true;
  bar.geometry.computeVertexNormals();
  bar.clear();
  g.add(withEdges(bar, 0.2));
  for (const x of [0, L]) g.add(box(16, b * 1.6, 30, COLORS.partDark, [x, 0, -h / 2 - 15]));
  // where it should be (2 mm allowed): straight reference line
  g.add(line([[0, 0, h / 2], [L, 0, h / 2]], COLORS.ink, 0.35, true));
  g.add(arrow([L / 2, 0, 90], [0, 0, -1], 70));
  return {
    group: g,
    view: [0.2, -1.0, 0.25],
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: s.required_sf, peak: s.sigma_max, nominal: s.sigma_max, kt: 1 },
    notes: [],
  };
}

function thermalColumn(s) {
  // Rod clamped at both ends; heating pushes it against the clamps until it bows.
  const g = new THREE.Group();
  const L = s.length_mm, d = s.diameter_mm;
  const allow = s.strength;
  const rod = cylZ(d / 2, L, 0, [0, 0, L / 2], 32);
  rod.material = new THREE.MeshStandardMaterial({ color: stressColor(s.sigma / allow), roughness: 0.8 });
  g.add(rod);
  for (const z of [0, L]) g.add(box(40, 40, 24, COLORS.partDark, [0, 0, z === 0 ? -12 : L + 12]));
  // fixed-fixed first mode: (1 - cos 2*pi*z/L) / 2, amplitude exaggerated
  const A = L * 0.06;
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const z = (L * i) / 64;
    pts.push(new THREE.Vector3((A * (1 - Math.cos((2 * Math.PI * z) / L))) / 2, 0, z));
  }
  g.add(new THREE.Mesh(
    new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 96, d / 2, 16, false),
    new THREE.MeshStandardMaterial({ color: COLORS.red, roughness: 0.7, transparent: true, opacity: 0.55 }),
  ));
  return {
    group: g,
    view: [1.0, -1.0, 0.2],
    legend: { kind: "stress", allow, strength: s.strength, requiredSf: 1, peak: s.sigma, nominal: s.sigma, kt: 1 },
    notes: [],
  };
}

function designPart(s) {
  // The AI's own part (tessellated from its STEP), coloured by beam-theory stress on the
  // measured sections: arm cuts (x = const) and wall-leg cuts (z = const).
  const g = new THREE.Group();
  // split big CAD triangles so the per-vertex stress colours have somewhere to live
  const V = s.mesh.v, out = [];
  const maxLen = 2.5;
  const push = (a, b, c, depth) => {
    const d = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
    if (depth > 7 || Math.max(d(a, b), d(b, c), d(c, a)) <= maxLen || out.length > 2.4e6) {
      out.push(...a, ...b, ...c);
      return;
    }
    const m = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2];
    const ab = m(a, b), bc = m(b, c), ca = m(c, a);
    push(a, ab, ca, depth + 1); push(ab, b, bc, depth + 1); push(ca, bc, c, depth + 1); push(ab, bc, ca, depth + 1);
  };
  const P = (i) => [V[3 * i], V[3 * i + 1], V[3 * i + 2]];
  for (let k = 0; k < s.mesh.t.length; k += 3) push(P(s.mesh.t[k]), P(s.mesh.t[k + 1]), P(s.mesh.t[k + 2]), 0);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(out, 3));
  geo.computeVertexNormals();
  const arm = s.sections.filter((q) => q.kind === "arm").sort((a, b) => a.at - b.at);
  const leg = s.sections.filter((q) => q.kind === "leg").sort((a, b) => a.at - b.at);
  const ratio = (q) => q.sigma / (q.strength / (s.required_sf || 1));
  const near = (list, v) => {
    let best = null;
    for (const q of list) if (!best || Math.abs(q.at - v) < Math.abs(best.at - v)) best = q;
    return best && Math.abs(best.at - v) <= Math.max(2, best.depth) ? best : null;
  };
  const pos = geo.attributes.position;
  const col = new Float32Array(pos.count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    let t = 0;
    const a = arm.length && x >= arm[0].at - 1 ? near(arm, x) : null;
    if (a && Math.abs(z - a.zc) <= a.c * 1.05) t = Math.max(t, (ratio(a) * Math.abs(z - a.zc)) / a.c);
    const l = leg.length ? near(leg, z) : null;
    if (l && Math.abs(x - l.xc) <= l.c * 1.05) t = Math.max(t, (ratio(l) * Math.abs(x - l.xc)) / l.c);
    stressColor(t, c);
    col.set([c.r, c.g, c.b], i * 3);
  }
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const solid = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8 }));
  const edgeGeo = new THREE.BufferGeometry();
  edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(V, 3));
  edgeGeo.setIndex(s.mesh.t);
  solid.add(new THREE.LineSegments(new THREE.EdgesGeometry(edgeGeo, 25), new THREE.LineBasicMaterial({ color: COLORS.ink, transparent: true, opacity: 0.25 })));
  g.add(solid);
  const bb = new THREE.Box3().setFromObject(g);
  const size = bb.getSize(new THREE.Vector3());
  g.add(ghostBox(1.5, size.y * 2 + 40, size.z * 1.4 + 20, [-0.75, (bb.min.y + bb.max.y) / 2, (bb.min.z + bb.max.z) / 2], 0.07));
  if (s.load_point) {
    const [lx, ly, lz] = s.load_point;
    const len = Math.max(25, size.z * 0.5);
    g.add(arrow([lx, ly, lz + len + 6], [0, 0, -1], len));
  }
  const worst = [...arm, ...leg].sort((p, q) => p.sf - q.sf)[0];
  const allow = worst ? worst.strength / (s.required_sf || 1) : 0;
  return {
    group: g,
    view: [0.55, -1.0, 0.45],
    legend: worst ? { kind: "stress", allow, strength: worst.strength, requiredSf: s.required_sf, peak: worst.sigma, nominal: worst.sigma, kt: 1 } : null,
    notes: [],
  };
}

function dfmPart(s) {
  // The AI's part with a red marker at each place the printing / CNC checker flagged (amber = warning).
  const g = new THREE.Group();
  const V = s.mesh.v;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(V, 3));
  geo.setIndex(s.mesh.t);
  geo.computeVertexNormals();
  const solid = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: COLORS.part, roughness: 0.8 }));
  solid.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: COLORS.ink, transparent: true, opacity: 0.25 })));
  g.add(solid);
  const bb = new THREE.Box3().setFromObject(g);
  const r = Math.max(2.5, bb.getSize(new THREE.Vector3()).length() * 0.025);
  let fails = 0;
  for (const f of s.findings) {
    if (!f.location || f.severity === "info") continue;
    const fail = f.severity === "fail";
    if (fail) fails++;
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(fail ? r : r * 0.7, 20, 14),
      new THREE.MeshBasicMaterial({ color: fail ? COLORS.red : 0xf0a020, transparent: true, opacity: 0.85, depthTest: false }),
    );
    m.position.set(...f.location);
    m.renderOrder = 5;
    g.add(m);
  }
  return {
    group: g,
    view: [0.55, -1.0, 0.45],
    legend: { kind: fails ? "contact" : "clear", text: fails ? `${fails} problem spot${fails > 1 ? "s" : ""} marked in red` : "No problem spots" },
    notes: [],
  };
}

const BUILDERS = {
  dfm: dfmPart,
  cantilever_root_fillet: cantileverL,
  cantilever_step: cantileverStep,
  column,
  arm_torque: armTorque,
  cantilever_fatigue: cantileverFatigue,
  simple_beam: simpleBeam,
  thermal_column: thermalColumn,
  design: designPart,
  "arm-tilt-base": armTiltBase,
  "pcb-enclosure": pcbEnclosure,
  "pcb-enclosure-control": pcbEnclosure,
  "counterbore-cover": counterboreCover,
  "gear-collar": gearCollar,
};

export function buildScene(scene) {
  const fn = BUILDERS[scene?.kind];
  if (!fn) return null;
  return fn(scene);
}
