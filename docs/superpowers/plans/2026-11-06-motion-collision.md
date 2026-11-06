# Range-of-Motion Collision Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m goodman motion <assembly.glb> <joints.yaml>` sweeps every reachable combination of an assembly's independent joints and reports which part pairs collide, at which joint values, and where.

**Architecture:**
- Load the Mechy GLB (one mesh per part, home pose) and `joints.yaml`, and build forward kinematics per rigid body.
- Only part pairs on different bodies that aren't designed contacts or provably too far apart get checked.
- Each surviving body pair is sampled over just the independent joints that move it (a grid for 1–2 joints, Halton for 3–5), filtered by the reach rule read from `geometry.py`.
- Collision queries go through FCL. Hits are bisected to first contact, and a local search finds the worst pose.

**Tech Stack:** Python 3.12, numpy, trimesh 5.2, python-fcl 0.7.0.11 (macOS arm64 wheel confirmed), scipy (Halton, Euler), matplotlib (renders), pyyaml, pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-motion-collision-design.md`

## Global Constraints

- Units in the code are **mm and degrees** in the **Z-up assembly frame**. The GLB is metres under a root node `assembly` that rotates Z-up to Y-up. Undo that once, at load time.
- Mechy placements (`assembly.yaml` / `poses/*/assembly.yaml`): `position` is mm, and `rotation` is Euler degrees in scipy's **extrinsic `'xyz'`**. Checked: `[90, -90, 0]` gives `[0.5, -0.5, 0.5, 0.5]`, the GLB quaternion of `lower-shank`.
- Joint motion: rotate by `(value − home)` degrees about `axis` through `origin`, right-hand rule, composed down the `parent` chain.
- A coupled joint's value is `home + Σ ratio·(driver − driver.home)`, resolved recursively.
- **Never execute `geometry.py`.** Parse it with `ast` and read only `W_Z_MIN`, `W_Z_NEAR`, `NEAR_R`, `TIP_Z_MIN` and `TOOL` through `ast.literal_eval`.
- Don't copy Mechy source code; this repo is public. Reading Mechy data files as test fixtures is fine.
- Sampling: 1 joint, a 0.5° grid. 2 joints, a 2° grid. 3–5 joints, 20,000 reachable Halton points (seed 0) plus box corners plus named poses. Refine first contact to 0.01° for 1-joint pairs and 0.1° otherwise.
- Allowed contact: the pair is in `allow_contact`, **or** its distance at home is ≤ 0.01 mm.
- Reach-rule comparisons use a 0.1 mm tolerance in favour of reachable.
- Real-arm tests read `MECHY_ARM_V4` (default `~/Mechy Projects/24-hourrobotarm/design/v4`) and `pytest.skip` if it's missing.
- `goodman/cli.py` may also be created by the strength checker's owner. If it already exists when you get there, add the `motion` subcommand to it rather than overwriting.
- Commit after every task on branch `collision/motion-sweep`.

## Review Focus

1. **The GLB and `joints.yaml` come from different builds** (`glb_sha256` mismatch). Warn on stderr and keep going (Task 1).
2. **A part named in `joints.yaml` is missing from the GLB.** Stop with an error naming the part. A GLB part listed in no joint is ground; that's normal (Task 1).
3. **A body pair whose every sample is unreachable** must show in `stats.pairs_unreachable`, never silently look clean (Task 6).
4. **A coupled joint driven by another coupled joint** must resolve recursively, not read a raw value (Task 2).
5. **A part with zero triangles** (an empty keepout export): skip it with a warning, and don't crash FCL (Task 1).

---

### Task 1: Package scaffold and input loaders

**Files:**
- Create: `requirements.txt`, `goodman/__init__.py`, `goodman/motion/__init__.py`, `goodman/motion/inputs.py`
- Create: `tests/__init__.py`, `tests/motion/__init__.py`, `tests/motion/conftest.py`, `tests/motion/synth.py`, `tests/motion/test_inputs.py`

**Interfaces:**
- Produces, in `goodman/motion/inputs.py`:
  - `load_parts(glb: Path) -> dict[str, trimesh.Trimesh]`: home pose, mm, Z-up assembly frame, keyed by node name. Zero-triangle parts are dropped with a `warnings.warn`.
  - `@dataclass(frozen=True) Joint`: `id: str`, `parent: str | None`, `origin: np.ndarray` (3,), `axis: np.ndarray` (3, unit), `parts: tuple[str, ...]`, `home: float`, `limits: tuple[float, float]`, `coupled: tuple[tuple[str, float], ...]`.
  - `@dataclass(frozen=True) MotionFile`: `joints: tuple[Joint, ...]`, `poses: dict[str, dict[str, float]]`, `glb_sha256: str | None`.
  - `load_joints(path: Path) -> MotionFile`.
  - `check_consistency(glb: Path, motion: MotionFile, parts: dict[str, trimesh.Trimesh]) -> None`: raises `ValueError("joints.yaml part not in GLB: <id>")`, and warns if the sha256 differs.
  - `load_allow_contact(assembly_yaml: Path) -> set[frozenset[str]]`.
  - `@dataclass(frozen=True) ReachConstants`: `W_Z_MIN`, `W_Z_NEAR`, `NEAR_R`, `TIP_Z_MIN`, `TOOL`, all floats.
  - `load_reach_constants(geometry_py: Path) -> ReachConstants`: raises `ValueError("geometry.py is missing <NAME>")`.
  - `load_placements(assembly_yaml: Path) -> dict[str, np.ndarray]`: 4×4 per part (mm, extrinsic `'xyz'` degrees).
- Produces, in `tests/motion/synth.py`: `write_c01(dir: Path, pivot_z: float = 55.0) -> tuple[Path, Path]`. It writes a Mechy-shaped `assembly.glb` (root node `assembly` with quaternion `[-0.7071068, 0, 0, 0.7071068]`, metres, child nodes `base` and `link`) and `joints.yaml`:
  - `base`: box 60×60×40 mm spanning x, y ±30 and z 0..40.
  - `link`: box spanning x 0..120, y ±7.5, z `pivot_z ± 10`.
  - One joint: `tilt`, parent null, origin `[0, 0, pivot_z]`, axis `[0, 1, 0]`, parts `[link]`, home 0, limits `[0, 30]`, no poses. A positive angle tilts the link down.
- Produces, in `tests/motion/conftest.py`: an `arm` fixture returning the `MECHY_ARM_V4` path, or skipping.

- [ ] **Step 1: Create the venv, add `requirements.txt`, install**

`requirements.txt` holds `numpy`, `scipy`, `trimesh==5.2.0`, `python-fcl==0.7.0.11`, `matplotlib`, `pyyaml` and `pytest`.
Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -c "import fcl, trimesh, scipy; print('ok')"`
Expected: `ok`. Add `.venv/` to `.gitignore`.

- [ ] **Step 2: Write the failing tests** in `tests/motion/test_inputs.py`

```python
def test_arm_glb_loads_all_parts_in_mm(arm):
    parts = load_parts(arm / "assembly.glb")
    assert len(parts) == 118
    # lower-shank node sits at (10, -8, 116) mm; its home bbox must contain the shoulder pivot (10, ~, 116)
    lo, hi = parts["lower-shank"].bounds
    assert lo[0] < 10 < hi[0] and lo[2] < 116 < hi[2]
    assert parts["base"].bounds[0][2] > -1.0          # base sits on z = 0 (table), Z-up, mm

def test_placements_match_glb_home(arm):
    # pins the Euler convention: Mechy home placements == GLB node transforms
    placed = load_placements(arm / "assembly.yaml")
    import trimesh, numpy as np
    scene = trimesh.load(arm / "assembly.glb", force="scene")
    root = scene.graph["assembly"][0]
    for name in placed:
        T = np.linalg.inv(root) @ scene.graph[name][0]
        T[:3, 3] *= 1000.0
        assert np.allclose(T, placed[name], atol=1e-4), name

def test_joints_file(arm):
    m = load_joints(arm / "joints.yaml")
    assert len(m.joints) == 23
    assert [j.id for j in m.joints if not j.coupled] == ["yaw", "shoulder", "elbow", "wrist", "crank-a"]
    sh = next(j for j in m.joints if j.id == "shoulder")
    assert sh.limits == (20, 140) and sh.home == 90 and sh.parent == "yaw"
    assert m.poses["reach-low"] == {"yaw": 0, "shoulder": 20, "elbow": -74.6, "wrist": 29.6, "crank-a": 20}

def test_allow_contact(arm):
    allow = load_allow_contact(arm / "assembly.yaml")
    assert len(allow) == 138 and frozenset({"yaw-switch", "yaw-pulley"}) in allow

def test_reach_constants_parsed_not_executed(tmp_path, arm):
    c = load_reach_constants(arm / "geometry.py")
    assert (c.W_Z_MIN, c.W_Z_NEAR, c.NEAR_R, c.TIP_Z_MIN, c.TOOL) == (45.0, 95.0, 200.0, 3.0, 89.0)
    evil = tmp_path / "geometry.py"
    evil.write_text("raise SystemExit('executed!')\nTOOL = 89.0\nW_Z_MIN, W_Z_NEAR, NEAR_R, TIP_Z_MIN = 1.0, 2.0, 3.0, 4.0\n")
    assert load_reach_constants(evil).NEAR_R == 3.0
    (tmp_path / "g2.py").write_text("TOOL = 1.0\n")
    with pytest.raises(ValueError, match="W_Z_MIN"):
        load_reach_constants(tmp_path / "g2.py")

def test_consistency_errors(tmp_path):
    glb, jy = write_c01(tmp_path)
    m = load_joints(jy)
    parts = load_parts(glb)
    del parts["link"]
    with pytest.raises(ValueError, match="link"):
        check_consistency(glb, m, parts)

def test_hash_mismatch_warns(arm):
    m = load_joints(arm / "joints.yaml")
    m2 = dataclasses.replace(m, glb_sha256="0" * 64)
    with pytest.warns(UserWarning, match="sha256"):
        check_consistency(arm / "assembly.glb", m2, load_parts(arm / "assembly.glb"))

def test_synth_c01_roundtrip(tmp_path):
    glb, _ = write_c01(tmp_path)
    p = load_parts(glb)
    assert set(p) == {"base", "link"}
    assert np.allclose(p["link"].bounds, [[0, -7.5, 45], [120, 7.5, 65]], atol=1e-6)

def test_zero_triangle_part_dropped(tmp_path):
    empty = trimesh.Trimesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), int))
    write_glb(tmp_path / "a.glb", {"box": trimesh.creation.box(extents=[10, 10, 10]), "ghost": empty})
    with pytest.warns(UserWarning, match="ghost"):
        assert set(load_parts(tmp_path / "a.glb")) == {"box"}
```

`write_glb(path, meshes_mm: dict[str, Trimesh])` is the scene writer in `synth.py` that `write_c01` also uses. If trimesh refuses to export an empty mesh, make the ghost a single degenerate triangle with zero area and treat zero-area meshes the same way.

- [ ] **Step 3: Run them and see them fail**

Run: `.venv/bin/pytest tests/motion/test_inputs.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 4: Implement `inputs.py` and `synth.py`**

- `load_parts`: `trimesh.load(path, force="scene")`. For each node in `scene.graph.nodes_geometry`, use `T = inv(T_root) @ T_world`, transform a copy of the geometry, then scale by 1000.
- `load_reach_constants`: walk `ast.parse(text).body` for `Assign` nodes, handling both a `Name` target and a `Tuple` target matched against a `Tuple` value, and `literal_eval` each value node.
- `write_glb`: build a `trimesh.Scene` with node `assembly` (that root rotation) as the parent of each mesh node (vertices in metres), then `scene.export(path)`.

- [ ] **Step 5: Run them and see them pass**

Run: `.venv/bin/pytest tests/motion/test_inputs.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

`git add requirements.txt .gitignore goodman tests && git commit -m "motion: input loaders for Mechy GLB, joints, allow_contact, geometry constants"`

---

### Task 2: Kinematics

**Files:**
- Create: `goodman/motion/kinematics.py`, `tests/motion/test_kinematics.py`

**Interfaces:**
- Consumes: `MotionFile`, `Joint` and `load_placements` from Task 1.
- Produces `class Kinematics(motion: MotionFile, part_ids: Iterable[str])`:
  - `independent: list[str]`: joints without `coupled`, in file order.
  - `limits: dict[str, tuple[float, float]]` and `home: dict[str, float]`, for independent joints.
  - `body_of(part: str) -> str`: a joint id, or `"ground"`.
  - `bodies() -> list[str]`: `"ground"` first.
  - `joint_values(indep: Mapping[str, float]) -> dict[str, float]`: every joint. Missing independents take their home value; coupled joints resolve recursively.
  - `body_transforms(indep: Mapping[str, float]) -> dict[str, np.ndarray]`: 4×4 per body, with `"ground"` as the identity.
  - `joint_origin(joint: str, T: dict[str, np.ndarray]) -> np.ndarray`: the posed origin, i.e. the parent body's transform applied to the home origin.
  - `relevant_joints(body_a: str, body_b: str) -> list[str]`: the independent joints that change the pair's relative pose, in `independent` order.
  - `path_to_ancestor(body: str, ancestor: str) -> list[str]`: joint ids from `body` up to (not including) `ancestor`.
  - `common_ancestor(body_a: str, body_b: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_home_is_identity(arm):
    kin = _arm_kin(arm)
    T = kin.body_transforms({})
    assert all(np.allclose(t, np.eye(4)) for t in T.values())

@pytest.mark.parametrize("pose", ["gripper-closed", "gripper-open", "reach-table", "elbow-up", "elbow-folded",
    "stretched", "yaw-limit", "wrist-limit-pos", "wrist-limit-neg", "reach-wrist-pos", "reach-wrist-neg",
    "elbow-back-q2max", "elbow-up-q2max", "fold-low", "reach-low"])
def test_matches_mechy_pose(arm, pose):
    m = load_joints(arm / "joints.yaml"); home = load_placements(arm / "assembly.yaml")
    want = load_placements(arm / "poses" / pose / "assembly.yaml")
    kin = Kinematics(m, home.keys())
    T = kin.body_transforms(m.poses[pose])
    for part, P in want.items():
        got = T[kin.body_of(part)] @ home[part]
        assert np.allclose(got[:3, 3], P[:3, 3], atol=0.01), part                                 # 0.01 mm
        ang = np.degrees(np.arccos(np.clip((np.trace(got[:3, :3].T @ P[:3, :3]) - 1) / 2, -1, 1)))
        assert ang < 0.01, part                                                                    # 0.01°

def test_relevant_joints(arm):
    kin = _arm_kin(arm)
    assert kin.relevant_joints("ground", "shoulder") == ["yaw", "shoulder"]
    assert kin.relevant_joints(kin.body_of("jaw-a"), kin.body_of("gripper-base")) == ["crank-a"]
    assert kin.relevant_joints(kin.body_of("e-bolt"), kin.body_of("lower-shank")) == ["shoulder"]
    assert kin.relevant_joints(kin.body_of("turret"), kin.body_of("shoulder-motor")) == []

def test_coupled_chain_resolves_recursively():
    J = lambda id, coupled=(): Joint(id, None, np.zeros(3), np.array([0, 0, 1.0]), (), 0.0, (-90, 90), coupled)
    m = MotionFile((J("j1"), J("j2", (("j1", 2.0),)), J("j3", (("j2", -1.0),))), {}, None)
    v = Kinematics(m, []).joint_values({"j1": 10})
    assert v == {"j1": 10, "j2": 20, "j3": -20}

def test_c01_tilt(tmp_path):
    glb, jy = write_c01(tmp_path)
    kin = Kinematics(load_joints(jy), ["base", "link"])
    T = kin.body_transforms({"tilt": 30})["tilt"]
    far_end = T @ np.array([120, 0, 55, 1.0])
    assert np.allclose(far_end[:3], [120 * np.cos(np.radians(30)), 0, 55 - 120 * np.sin(np.radians(30))], atol=1e-6)
```

`_arm_kin(arm)` is a test helper: load the joints and the GLB part ids, and build `Kinematics`.

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/motion/test_kinematics.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `kinematics.py`**

- Rotation about an axis through a point: `T = Tr(o) @ R(axis, θ) @ Tr(−o)`, with `R` from `scipy.spatial.transform.Rotation.from_rotvec`.
- `body_transforms`: compute `M[j] = M[parent] @ T_j`, walking the joints in topological order.
- `relevant_joints`: collect the joints on `path_to_ancestor(a, lca) + path_to_ancestor(b, lca)`, then map each joint to its independent drivers (itself if it isn't coupled, otherwise recurse through `coupled`).

If a pose test fails, recheck the sign or coupling convention rather than loosening the tolerance.

- [ ] **Step 4: Run them and see them pass**

Run: `.venv/bin/pytest tests/motion/test_kinematics.py -v`
Expected: 19 PASS.

- [ ] **Step 5: Commit**

`git commit -am "motion: forward kinematics validated against Mechy's 15 poses"` (stage the new files first).

---

### Task 3: Reach rule

**Files:**
- Create: `goodman/motion/reach.py`, `tests/motion/test_reach.py`

**Interfaces:**
- Consumes: `Kinematics` (Task 2), `ReachConstants` (Task 1).
- Produces `class ReachRule(kin, c: ReachConstants, wrist_joint="wrist", yaw_joint="yaw", table_z=0.0, tip_dir_home=(0, 0, -1), eps=0.1)`:
  - `points(indep) -> tuple[np.ndarray, np.ndarray]`: W, the posed origin of `wrist_joint`; and the tip, `W + R_body(wrist_joint) @ tip_dir_home * TOOL`.
  - `allows(indep) -> bool`, where `r` is W's distance to the posed `yaw_joint` axis line:
    - `W.z − table_z ≥ W_Z_MIN − eps`
    - if `r < NEAR_R − eps`, then also `W.z − table_z ≥ W_Z_NEAR − eps`
    - `tip.z − table_z ≥ TIP_Z_MIN − eps`
  - `complete(partial: Mapping[str, float], rng: np.random.Generator, tries: int = 200) -> dict[str, float] | None`: fills every independent joint missing from `partial`. Try home first, then `tries` uniform draws within limits. Return the first full assignment that `allows`, or `None`.
- Sweeps take `rule: ReachRule | None`; `None` means everything is reachable. Tests may pass any object with these `allows` and `complete` methods.

- [ ] **Step 1: Write the failing tests**

```python
def test_reach_low_boundary(arm):
    rule, m = _arm_rule(arm)
    W, tip = rule.points(m.poses["reach-low"])
    assert abs(W[2] - 45.0) < 0.5 and 3.0 < tip[2] < 11.0          # pose note: "W 45 above the table", "tip ~7 up"
    assert rule.allows(m.poses["reach-low"])
    lower = dict(m.poses["reach-low"], elbow=-76.6)
    assert rule.points(lower)[0][2] < W[2] and not rule.allows(lower)

def test_fold_low_boundary(arm):
    rule, m = _arm_rule(arm)
    W, _ = rule.points(m.poses["fold-low"])
    assert abs(np.hypot(W[0], W[1]) - 200.0) < 0.5 and abs(W[2] - 53.0) < 0.5   # "W 200 out, 53 high"
    assert rule.allows(m.poses["fold-low"])

def test_home_and_named_poses_allowed(arm):
    rule, m = _arm_rule(arm)
    assert rule.allows({}) and all(rule.allows(v) for v in m.poses.values())

def test_complete_fills_free_joints(arm):
    rule, _ = _arm_rule(arm)
    full = rule.complete({"shoulder": 20, "elbow": -70}, np.random.default_rng(0))
    assert full is not None and full["shoulder"] == 20 and set(full) == {"yaw", "shoulder", "elbow", "wrist", "crank-a"}
    assert rule.allows(full)
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/pytest tests/motion/test_reach.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `reach.py`**

- [ ] **Step 4: Run them and see them pass**

Run: `.venv/bin/pytest tests/motion/test_reach.py -v`
Expected: PASS. If `test_home_and_named_poses_allowed` fails on a named pose by more than `eps`, report it rather than widening `eps`. It means the rule's interpretation is wrong.

- [ ] **Step 5: Commit**

---

### Task 4: Collision primitives

**Files:**
- Create: `goodman/motion/collide.py`, `tests/motion/test_collide.py`

**Interfaces:**
- Produces:
  - `@dataclass Contact`: `point_mm: np.ndarray` (3,), `depth_mm: float`.
  - `class CollisionWorld(parts: dict[str, trimesh.Trimesh])`: builds and caches one `fcl.BVHModel` per part on first use.
    - `collide(a: str, Ta: np.ndarray, b: str, Tb: np.ndarray) -> Contact | None`. `point_mm` is the mean of the FCL contact positions, in the assembly frame.
    - `distance(a, Ta, b, Tb) -> float`: mm, and 0 when overlapping.

- [ ] **Step 1: Write the failing tests**

```python
def _cube(c, s=10.0):
    m = trimesh.creation.box(extents=[s, s, s]); m.apply_translation(c); return m

def test_overlap_depth_and_point():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([8, 0, 0])})          # 2 mm overlap along x
    c = w.collide("a", np.eye(4), "b", np.eye(4))
    assert c is not None and abs(c.depth_mm - 2.0) < 0.5
    assert 3.0 - 0.5 <= c.point_mm[0] <= 5.0 + 0.5

def test_apart_and_transform():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([30, 0, 0])})
    assert w.collide("a", np.eye(4), "b", np.eye(4)) is None
    assert abs(w.distance("a", np.eye(4), "b", np.eye(4)) - 20.0) < 1e-6
    T = np.eye(4); T[0, 3] = -22.0                                               # move b into a
    assert w.collide("a", np.eye(4), "b", T) is not None

def test_touching_distance_zero():
    w = CollisionWorld({"a": _cube([0, 0, 0]), "b": _cube([10, 0, 0])})
    assert w.distance("a", np.eye(4), "b", np.eye(4)) <= 0.01
```

- [ ] **Step 2: Run them and see them fail.** `.venv/bin/pytest tests/motion/test_collide.py -v`

- [ ] **Step 3: Implement `collide.py`**

Use `fcl.CollisionRequest(num_max_contacts=64, enable_contact=True)` and take the max `penetration_depth` across contacts as `depth_mm`.

If that fails `test_overlap_depth_and_point` (FCL mesh-mesh depth is often 0), compute depth instead along `n` = the mean contact normal. Project both parts' vertices that lie within 30 mm of `point_mm` onto `n`, and take `depth = min(max_a − min_b, max_b − min_a)`.

- [ ] **Step 4: Run them and see them pass.** Same command. Expected: PASS.

- [ ] **Step 5: Commit**

---

### Task 5: Pair planning (skip, ignore, quick reject)

**Files:**
- Create: `goodman/motion/pairs.py`, `tests/motion/test_pairs.py`

**Interfaces:**
- Consumes: `Kinematics`, `CollisionWorld`, and the `load_allow_contact` result.
- Produces:
  - `@dataclass PairPlan`:
    - `candidates: dict[tuple[str, str], list[tuple[str, str]]]`: body pair → part pairs to sample.
    - `ignored: list[tuple[tuple[str, str], str]]`: part pair plus reason, `"allow_contact"` or `"in contact at home"`.
    - `stats: dict[str, int]` with keys `pairs_total`, `pairs_same_body`, `pairs_ignored`, `pairs_rejected_far`, `pairs_sampled`.
  - `plan_pairs(kin, world, parts: dict[str, trimesh.Trimesh], allow: set[frozenset[str]]) -> PairPlan`
  - `reach_ball(kin, body, ancestor, mesh) -> tuple[np.ndarray, float]`: the centre and radius of a ball, in the ancestor's frame (home coordinates), that contains the part over every joint value.

`reach_ball` algorithm (conservative, triangle inequality):
- With `chain = path_to_ancestor(body, ancestor)` (bottom to top):
  - If the chain is empty, return the mesh's bounding sphere.
  - Otherwise the centre is the top joint's origin, and the radius is `Σ |origin_k − origin_{k+1}|` along the chain plus the max distance from the bottom joint's origin to any mesh vertex.
- A part pair is rejected as far when `|c_a − c_b| > r_a + r_b`, using `ancestor = common_ancestor`.

- [ ] **Step 1: Write the failing tests**

```python
def test_c01_single_candidate(tmp_path):
    glb, jy = write_c01(tmp_path)
    plan = _plan(glb, jy, allow=set())
    assert plan.candidates == {("ground", "tilt"): [("base", "link")]}

def test_far_part_rejected(tmp_path):
    # c01 plus a 5 mm cube "far" on ground at (1000, 0, 0): link can't reach it
    plan = _plan(*write_c01_with_far(tmp_path), allow=set())
    assert ("far", "link") not in sum(plan.candidates.values(), []) and plan.stats["pairs_rejected_far"] == 1

def test_allow_and_home_contact_ignored(tmp_path):
    glb, jy = write_c01(tmp_path, pivot_z=50.0)                       # link underside at z=40 touches base at home
    plan = _plan(glb, jy, allow=set())
    assert plan.candidates == {} and plan.ignored == [(("base", "link"), "in contact at home")]
    glb, jy = write_c01(tmp_path / "b")
    assert _plan(glb, jy, allow={frozenset({"base", "link"})}).ignored[0][1] == "allow_contact"

def test_arm_plan_sane(arm):
    plan = _plan(arm / "assembly.glb", arm / "joints.yaml", allow=load_allow_contact(arm / "assembly.yaml"))
    s = plan.stats
    assert s["pairs_total"] == 118 * 117 // 2
    assert s["pairs_same_body"] + s["pairs_ignored"] + s["pairs_rejected_far"] + s["pairs_sampled"] == s["pairs_total"]
    flat = {frozenset(p) for v in plan.candidates.values() for p in v}
    assert not flat & load_allow_contact(arm / "assembly.yaml")
    assert ("base", "lower-shank") in plan.candidates[("ground", "shoulder")]   # the shank can swing down into the base
```

`_plan` and `write_c01_with_far` are test helpers.

- [ ] **Step 2: Run them and see them fail.** `.venv/bin/pytest tests/motion/test_pairs.py -v`
- [ ] **Step 3: Implement `pairs.py`.** "In contact at home" means `world.distance(a, I, b, I) <= 0.01`. The allow check comes first, so its reason wins.
- [ ] **Step 4: Run them and see them pass.**
- [ ] **Step 5: Commit**

---

### Task 6: Sampling, sweep and refinement

**Files:**
- Create: `goodman/motion/sweep.py`, `tests/motion/test_sweep.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces:
  - `samples_for(joints: list[str], kin, named_poses: dict[str, dict[str, float]], n_halton: int = 20000, seed: int = 0, start: int = 0) -> np.ndarray`: shape (n, k).
    - k=1: `np.arange(lo, hi + 1e-9, 0.5)`, plus `hi`.
    - k=2: a 2° meshgrid, including the upper limits.
    - k≥3: `scipy.stats.qmc.Halton(d=k, scramble=False)` points `start..start+n_halton` scaled to the limits, plus all 2^k corners, plus each named pose projected on `joints`.
  - `@dataclass Finding`: `parts: tuple[str, str]`, `joints: list[str]`, `first_contact: dict[str, float]` (all independents), `worst_pose: dict[str, float]` (all independents), `penetration_mm: float`, `contact_point_mm: list[float]`, `colliding_range: dict[str, tuple[float, float]]`.
  - `@dataclass SweepResult`: `findings: list[Finding]`, `ignored` (from `PairPlan`), and `stats: dict`, which is the `PairPlan` stats plus `poses_checked`, `poses_unreachable`, `pairs_unreachable` and `seconds`.
  - `sweep(kin, world, plan: PairPlan, rule, named_poses, *, n_halton=20000, seed=0, progress: Callable[[str], None] | None = None) -> SweepResult`

For each body pair with joints `J`:
1. Draw samples. For each sample:
   - `full = rule.complete(dict(zip(J, s)), rng)`, or home-filled when `rule is None`.
   - If `None`, count it unreachable and move on.
   - Otherwise compute the transforms once and run `collide` on every candidate part pair.
2. If k≥3 and fewer than half the drawn samples were reachable, draw more Halton points (`start` continues) until 20,000 are reachable or 100,000 have been drawn.
3. If no samples were reachable, increment `pairs_unreachable` and report nothing for this body pair.
4. For each part pair with at least one hit:
   - `colliding_range`: the min and max of each joint over the hit samples.
   - `first_contact`: take the hit sample nearest (max-norm on J) to its nearest clear reachable sample, then bisect along that segment. Midpoints that aren't reachable count as hits, since bisection must stay inside the reachable region. Stop when the segment's max joint change is ≤ 0.01° (k=1) or 0.1° (k≥2), and report the end that collides.
   - `worst_pose`: start from the hit sample with the largest `depth_mm` and search a local grid ±2° at 0.5° steps on J, reachable points only, maximising `depth_mm`.
   - `contact_point_mm` and `penetration_mm` come from the worst pose.
5. Call `progress(f"{body_a}–{body_b}: {k} joints, {n} poses, {hits} hits")` once per body pair.

- [ ] **Step 1: Write the failing tests**

```python
def test_samples_sizes(arm):
    kin = _arm_kin(arm)
    assert samples_for(["crank-a"], kin, {}).shape == (121, 1)                       # -10..50 at 0.5°
    assert samples_for(["shoulder", "elbow"], kin, {}).shape == (61 * 118, 2)        # 20..140, -135..100 at 2° incl. ends
    s = samples_for(["yaw", "shoulder", "elbow"], kin, {"p": {"yaw": 1, "shoulder": 30, "elbow": 0}})
    assert s.shape == (20000 + 8 + 1, 3) and (s.min(0) >= [-150, 20, -135]).all() and (s.max(0) <= [150, 140, 100]).all()

def test_c01_first_contact(tmp_path):
    r = _sweep_c01(tmp_path, pivot_z=55.0)
    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.parts == ("base", "link") and f.joints == ["tilt"]
    assert abs(f.first_contact["tilt"] - 9.22) <= 0.05                     # truth.yaml tolerance
    assert f.colliding_range["tilt"][1] == 30.0 and f.worst_pose["tilt"] == 30.0
    p = np.array(f.contact_point_mm)                                         # inside both parts' posed boxes (+1 mm)
    assert (p >= [-31, -8.5, -1]).all() and (p <= [31, 8.5, 41]).all()      # base box, and link's y-span

def test_c01_control_clean(tmp_path):
    assert _sweep_c01(tmp_path, pivot_z=70.0).findings == []

def test_unreachable_collision_not_reported(tmp_path):
    class OnlyShallow:  # duck-typed rule: tilt above 5° is unreachable
        def complete(self, partial, rng, tries=200):
            return dict(partial) if partial.get("tilt", 0) <= 5 else None
    r = _sweep_c01(tmp_path, pivot_z=55.0, rule=OnlyShallow())
    assert r.findings == [] and r.stats["poses_unreachable"] > 0

def test_all_unreachable_counted(tmp_path):
    class Never:
        def complete(self, partial, rng, tries=200): return None
    r = _sweep_c01(tmp_path, pivot_z=55.0, rule=Never())
    assert r.findings == [] and r.stats["pairs_unreachable"] == 1
```

`_sweep_c01` is a helper that writes the synthetic case, plans the pairs and calls `sweep`.

- [ ] **Step 2: Run them and see them fail.** `.venv/bin/pytest tests/motion/test_sweep.py -v`
- [ ] **Step 3: Implement `sweep.py`**
- [ ] **Step 4: Run them and see them pass.**
- [ ] **Step 5: Commit**

---

### Task 7: Report, renders and CLI

**Files:**
- Create: `goodman/motion/report.py`, `goodman/cli.py` (or modify it if it exists), `goodman/__main__.py`, `tests/motion/test_cli.py`

**Interfaces:**
- Consumes: `SweepResult`, `Finding`, `Kinematics` and the loaders.
- Produces:
  - `why_text(f: Finding) -> str`: `"<a> hits <b> at <j1> <v1>°, <j2> <v2>°; contact near (x, y, z) mm"`, with first-contact values of `f.joints` only, rounded to 0.1° (0.01° for k=1) and 1 mm.
  - `render_finding(path: Path, f: Finding, kin, parts) -> None`: a matplotlib `Poly3DCollection` PNG of the worst pose. The two colliding parts are drawn in red and orange at full resolution; every other part is light grey, alpha 0.15, with every 10th face drawn. Keep it under 10 s per render.
  - `export_pose_glb(path: Path, kin, parts, pose: dict[str, float]) -> None`: the posed assembly in mm, Z-up, for spot checks.
  - `write_result(out: Path, result: SweepResult, meta: dict) -> dict`: writes `out/motion_result.json` in the spec's shape, plus `out/renders/<a>__<b>.png` and `out/poses/<a>__<b>.glb` per finding. `meta` holds `inputs`, `swept_joints` and `reach_rule`. `verdict` is `"collisions"` if there are any findings, otherwise `"no_collisions"`.
  - `goodman.cli.main(argv: list[str] | None = None) -> int`:
    - Usage: `motion <glb> <joints.yaml> [--assembly P] [--geometry P] [--out DIR] [--halton N]`.
    - `--out` defaults to `./motion-out`.
    - `--assembly` and `--geometry` default to `assembly.yaml` and `geometry.py` next to the GLB when present.
    - Prints progress lines on stderr. On stdout it prints the verdict, the finding count and one `why` line per finding.
    - Returns 0 for no collisions, 1 for collisions, and 2 for input errors (one-line message on stderr).

- [ ] **Step 1: Write the failing tests**

```python
def test_cli_c01(tmp_path, capsys):
    glb, jy = write_c01(tmp_path)
    code = main(["motion", str(glb), str(jy), "--out", str(tmp_path / "out")])
    assert code == 1
    res = json.loads((tmp_path / "out/motion_result.json").read_text())
    assert res["verdict"] == "collisions" and len(res["collisions"]) == 1
    c = res["collisions"][0]
    assert set(c) >= {"parts", "joints", "first_contact", "worst", "contact_point_mm", "colliding_range", "render", "why"}
    assert (tmp_path / "out" / c["render"]).stat().st_size > 10_000
    out = capsys.readouterr().out
    assert "collisions" in out and ("link hits base" in out or "base hits link" in out)
    assert set(res["stats"]) >= {"pairs_total", "pairs_same_body", "pairs_ignored", "pairs_rejected_far",
                                 "pairs_sampled", "poses_checked", "poses_unreachable", "pairs_unreachable", "seconds"}

def test_cli_control(tmp_path):
    glb, jy = write_c01(tmp_path, pivot_z=70.0)
    assert main(["motion", str(glb), str(jy), "--out", str(tmp_path / "o")]) == 0
    assert json.loads((tmp_path / "o/motion_result.json").read_text())["verdict"] == "no_collisions"

def test_cli_picks_up_neighbours_and_reports_bad_geometry(tmp_path, capsys):
    glb, jy = write_c01(tmp_path)
    (tmp_path / "geometry.py").write_text("TOOL = 1.0\n")                    # missing W_Z_MIN etc.
    assert main(["motion", str(glb), str(jy), "--out", str(tmp_path / "o")]) == 2
    assert "W_Z_MIN" in capsys.readouterr().err
```

- [ ] **Step 2: Run them and see them fail.** `.venv/bin/pytest tests/motion/test_cli.py -v`
- [ ] **Step 3: Implement `report.py`, `cli.py` and `__main__.py`.** The whole flow:
  1. Load the inputs and run `check_consistency`.
  2. Build `Kinematics`, then `ReachRule` if constants were found.
  3. `CollisionWorld`, then `plan_pairs`, then `sweep`, then `write_result`.
- [ ] **Step 4: Run all motion tests.** `.venv/bin/pytest tests/motion -v`. Expected: all PASS.
- [ ] **Step 5: Commit**

---

### Task 8: Run on the v4 robot arm and record the result

**Files:**
- Create: `results/motion/robotarm-v4/` (generated output, committed), `results/motion/robotarm-v4/NOTES.md`
- Modify: `goodman/motion/sweep.py`, only if the run is too slow

- [ ] **Step 1: Time a run**

Run: `time .venv/bin/python -m goodman motion "$HOME/Mechy Projects/24-hourrobotarm/design/v4/assembly.glb" "$HOME/Mechy Projects/24-hourrobotarm/design/v4/joints.yaml" --out results/motion/robotarm-v4`
Expected: it finishes in under 30 min and writes `motion_result.json`. The stderr log should show `geometry.py` and `assembly.yaml` being picked up.

- [ ] **Step 2: If it's over 30 min, parallelise across body pairs**

Use `concurrent.futures.ProcessPoolExecutor`, with each worker building its own `CollisionWorld`, and merge results in body-pair order so output stays deterministic. Re-run Step 1 and `.venv/bin/pytest tests/motion`.

- [ ] **Step 3: Spot-check every finding**

Open `results/motion/robotarm-v4/poses/*.glb` in a viewer, or look at the renders. Confirm each reported pair visibly overlaps at the worst pose and that the pose satisfies the reach rule.

In `NOTES.md`, write one line per finding: real, false alarm (and why), or design-intent contact missing from `allow_contact`. Don't edit Mechy's files.

- [ ] **Step 4: Commit**

`git add results/motion/robotarm-v4 && git commit -m "motion: v4 robot arm sweep results"`
