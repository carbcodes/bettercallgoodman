"""motion_result.json, renders and posed GLBs for each finding."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

from goodman.motion.kinematics import Kinematics  # noqa: E402
from goodman.motion.sweep import Finding, SweepResult  # noqa: E402


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def _stem(f: Finding) -> str:
    return f"{f.parts[0]}__{f.parts[1]}"


def why_text(f: Finding) -> str:
    nd = 2 if len(f.joints) == 1 else 1
    at = ", ".join(f"{j} {f.first_contact[j]:.{nd}f}°" for j in f.joints)
    x, y, z = (round(v) for v in f.contact_point_mm)
    return f"{f.parts[0]} hits {f.parts[1]} at {at}; contact near ({x}, {y}, {z}) mm"


def posed_meshes(kin: Kinematics, parts: dict[str, trimesh.Trimesh], pose) -> dict[str, trimesh.Trimesh]:
    T = kin.body_transforms(pose)
    out = {}
    for name, m in parts.items():
        p = m.copy()
        p.apply_transform(T[kin.body_of(name)])
        out[name] = p
    return out


def view_box(contact, a: trimesh.Trimesh, b: trimesh.Trimesh) -> tuple[np.ndarray, float]:
    """Cube centred on the contact, sized to show the smaller colliding part (1.5x its radius, min 40 mm)."""
    small = min((a, b), key=lambda m: float(np.ptp(m.vertices, axis=0).max()))
    radius = float(np.ptp(small.vertices, axis=0).max()) / 2
    return np.asarray(contact, float), max(40.0, 1.5 * radius)


def render_finding(path: Path, f: Finding, kin: Kinematics, parts: dict[str, trimesh.Trimesh]) -> None:
    posed = posed_meshes(kin, parts, f.worst_pose)
    c, r = view_box(f.contact_point_mm, posed[f.parts[0]], posed[f.parts[1]])
    fig = plt.figure(figsize=(8, 7), dpi=120)
    ax = fig.add_subplot(projection="3d")

    def near(tris):
        return tris[(np.abs(tris.mean(axis=1) - c) <= 1.5 * r).all(axis=1)]

    for name, m in posed.items():
        if name in f.parts:
            continue
        tris = near(m.vertices[m.faces])
        if len(tris):
            ax.add_collection3d(Poly3DCollection(tris, facecolor="0.7", edgecolor="none", alpha=0.12))
    order = sorted(f.parts, key=lambda n: -float(np.ptp(posed[n].vertices, axis=0).max()))  # big first, small on top
    colors = {f.parts[0]: "#d62728", f.parts[1]: "#ff7f0e"}
    for z, name in enumerate(order):
        tris = near(posed[name].vertices[posed[name].faces])
        alpha = 0.35 if z == 0 else 0.95
        ax.add_collection3d(Poly3DCollection(tris, facecolor=colors[name], edgecolor="none", alpha=alpha,
                                             zorder=z + 2, label=name))
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.scatter(*f.contact_point_mm, color="k", s=40, zorder=10)
    ax.legend(loc="upper left", fontsize=8)
    ax.view_init(elev=20, azim=-60)
    ax.set_xlabel("x mm")
    ax.set_ylabel("y mm")
    ax.set_zlabel("z mm")
    pose = ", ".join(f"{j} {f.worst_pose[j]:.1f}°" for j in f.joints)
    ax.set_title(f"{f.parts[0]} × {f.parts[1]}\n{pose}  (penetration ≈ {f.penetration_mm:.1f} mm)", fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def export_pose_glb(path: Path, kin: Kinematics, parts: dict[str, trimesh.Trimesh], pose) -> None:
    scene = trimesh.Scene()
    for name, m in posed_meshes(kin, parts, pose).items():
        scene.add_geometry(m, node_name=name, geom_name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(scene.export(file_type="glb"))


def write_result(out: Path, result: SweepResult, meta: dict, kin: Kinematics | None = None,
                 parts: dict[str, trimesh.Trimesh] | None = None) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    collisions = []
    for f in result.findings:
        entry = {
            "parts": list(f.parts),
            "joints": f.joints,
            "first_contact": {j: _r(v) for j, v in f.first_contact.items()},
            "worst": {"pose": {j: _r(v) for j, v in f.worst_pose.items()}, "penetration_mm": _r(f.penetration_mm)},
            "contact_point_mm": [_r(v, 1) for v in f.contact_point_mm],
            "colliding_range": {j: [_r(a), _r(b)] for j, (a, b) in f.colliding_range.items()},
            "why": why_text(f),
        }
        if kin is not None and parts is not None:
            entry["render"] = f"renders/{_stem(f)}.png"
            entry["pose_glb"] = f"poses/{_stem(f)}.glb"
            render_finding(out / entry["render"], f, kin, parts)
            export_pose_glb(out / entry["pose_glb"], kin, parts, f.worst_pose)
        collisions.append(entry)
    res = {
        "verdict": "collisions" if collisions else "no_collisions",
        **meta,
        "collisions": collisions,
        "ignored_pairs": [{"parts": list(p), "reason": why} for p, why in result.ignored],
        "stats": result.stats,
    }
    (out / "motion_result.json").write_text(json.dumps(res, indent=2))
    return res


def summary_lines(res: dict) -> list[str]:
    lines = [f"verdict: {res['verdict']} ({len(res['collisions'])} collisions)"]
    unreachable = res.get("stats", {}).get("pairs_unreachable", 0)
    if unreachable:
        lines.append(f"  ! {unreachable} body pairs not checked: no reachable pose under the reach rule")
    lines += [f"  - {c['why']}" for c in res["collisions"]]
    return lines
