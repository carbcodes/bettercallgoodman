# Design a jointed mechanical assembly and export it

Design this mechanism: **<DESCRIBE THE DESIGN HERE, e.g. "a desktop robot arm with yaw, shoulder, elbow, wrist and a two-jaw gripper">**

Design it the way a real designer would. Use realistic dimensions and real parts: links, brackets, axles, bearings, bolts, nuts, motors, boards, cable plugs. Give it the joint limits the mechanism should really have. If parts are driven together, for example gripper jaws from one crank or wheels from a steering linkage, model that as a driven joint (see `coupled` below).

Put everything in one folder. Use Python 3.11 with `numpy`, `scipy`, `trimesh`, `pyyaml` and, if you like, `pygltflib`, `manifold3d` or `build123d`. Include `generate.py`, which rebuilds every file the same way every time.

All lengths are mm and all angles are degrees, in a Z-up frame, unless stated otherwise. Follow the formats below exactly, because other tools read these files.

## `assembly.glb`: 3D geometry at the home pose

- One root node named `assembly`, with rotation quaternion `[-0.7071068, 0, 0, 0.7071068]` (glTF order x, y, z, w). That's the Z-up frame turned into glTF's Y-up.
- Every part is a **direct child** of `assembly`, and the **node name is the part id**. Use lowercase with hyphens, and make each id unique. One mesh per node. No deeper hierarchy, no animations.
- Node translations are in **metres**, in the Z-up frame. Mesh vertices are in metres, in the part's local frame. Place parts with the node's translation and rotation.
- Meshes are closed, with outward-facing triangles. Keep the whole file under 50,000 triangles.
- Every joint is at its `home` value.

## `joints.yaml`: how it moves

```yaml
glb_sha256: <sha256 hex of assembly.glb>
joints:
  - id: shoulder
    type: revolute
    parent: yaw              # id of the joint this one rides on, or null if it's mounted to the ground
    origin: [0, 0, 116]      # mm, in the home frame
    axis: [0, 1, 0]
    parts: [upper-link, shoulder-axle]
    home: 90
    limits: [20, 140]
    label: Shoulder
  - id: jaw-l
    type: revolute
    parent: wrist
    origin: [...]
    axis: [...]
    parts: [jaw-l]
    home: 0
    limits: [-10, 50]
    coupled: [{joint: crank-a, ratio: 1.0}]
poses:
  - name: stowed
    values: {shoulder: 30, elbow: -120}
```

- A joint rotates by `(value − home)` degrees about `axis` through `origin`, by the right-hand rule. Both `axis` and `origin` are given in the home frame. A child joint moves with its parent.
- A joint with `coupled` is driven: `value = home + Σ ratio · (driver − driver.home)`. A driven joint can drive another one.
- `parts` lists the parts the joint moves. Each part is listed under at most one joint. Parts under no joint are fixed to the ground.
- `poses` gives at least three named poses the mechanism is meant to use.

## `assembly.yaml`: parts meant to touch

```yaml
allow_contact:
  - [shoulder-bolt, shoulder-nut]
  - [belt, pulley]
```

## `geometry.py`: key dimensions

Write only plain constants, with literal numbers or tuples. No imports, no function calls.

If the design is a robot arm, give the base joint the id `yaw` and the wrist joint the id `wrist`, and add the controller's safe-pose limits in exactly this form:

```python
TOOL = 89.0                                               # fingertip distance from the wrist joint along the gripper (−z at home)
W_Z_MIN, W_Z_NEAR, NEAR_R, TIP_Z_MIN = 45.0, 95.0, 200.0, 3.0
```

These limits mean three things:
- The wrist joint's origin stays at least `W_Z_MIN` above the table (z = 0).
- Within `NEAR_R` of the yaw axis, the wrist joint's origin stays at least `W_Z_NEAR` above the table.
- The fingertip stays at least `TIP_Z_MIN` above the table.

Pick values that suit your arm.

## When you're done

Run `generate.py`. Then load the GLB back and confirm:
- every part in `joints.yaml` exists in it;
- every `coupled` driver and every `parent` exists;
- the hash matches.

Report the part count, the joint count and the triangle count.
