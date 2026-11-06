"""Deterministic visual documentation, mass budget, and fabrication notes."""
from pathlib import Path
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh
from validate import transforms
import geometry as G

def render(root,parts,joints,poses,report):
    from generate import COLORS
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.hashsalt':'aster320'})
    fig=plt.figure(figsize=(16,10),facecolor='#f3f2ec')
    fig.text(.05,.94,'ASTER / 320',fontsize=29,weight='bold',color='#22352f')
    fig.text(.05,.905,'Five-axis desktop manipulator  ·  160 + 160 mm links  ·  150 g design payload',fontsize=12,color='#52625a')
    ax=fig.add_axes([.03,.06,.60,.80],projection='3d',computed_zorder=False,facecolor='#f3f2ec')
    draw(ax,parts,joints,{},COLORS)
    ax.view_init(22,-63);ax.set(xlim=(-125,215),ylim=(-125,125),zlim=(0,345));ax.set_box_aspect((340,250,345));ax.set_axis_off()
    ax.text(0,0,341,'HOME',color='#52625a',fontsize=9)
    for n,name in enumerate(['reach-310mm','stowed','table-pick']):
        pose=next(p for p in poses if p['name']==name)
        a=fig.add_axes([.67,.60-.27*n,.29,.25],projection='3d',computed_zorder=False,facecolor='#f3f2ec')
        draw(a,parts,joints,pose['values'],COLORS)
        a.view_init(6,-89);a.set(xlim=(-110,360),ylim=(-100,100),zlim=(0,340));a.set_box_aspect((470,200,340));a.set_axis_off()
        a.text2D(0,.91,{'reach-310mm':'310.35 mm REACH','stowed':'COMPACT STOW','table-pick':'TABLE PICK'}[name],transform=a.transAxes,fontsize=10,weight='bold',color='#22352f')
    fig.text(.05,.035,f'{report["part_count"]} parts  /  {report["triangle_count"]:,} triangles  /  metal pivots + printed structure',fontsize=10,color='#52625a')
    fig.savefig(root/'preview.png',dpi=145,facecolor=fig.get_facecolor(),metadata={'Software':'Aster 320'});plt.close(fig)
    # Engineering schematic, home dimensions and envelopes, deliberately separate from the shaded model.
    fig,ax=plt.subplots(figsize=(11,8),facecolor='white')
    ax.set_aspect('equal');ax.set_xlim(-145,360);ax.set_ylim(-35,370);ax.axis('off')
    for pid,p in parts.items():
        if p['category'] not in ['printed','motor','pad']:continue
        v=p['mesh'].vertices+p['origin'];faces=p['mesh'].faces
        # silhouette of component projection is enough for dimensioned GA.
        from scipy.spatial import ConvexHull
        vv=v[:,[0,2]]
        try:h=ConvexHull(vv);pts=vv[h.vertices];ax.fill(*pts.T,fc='#eff1ee',ec='#7b8981',lw=.4)
        except Exception:pass
    ax.plot([-125,335],[0,0],color='#22352f',lw=1)
    def dim(a,b,label):
        ax.annotate('',b,a,arrowprops={'arrowstyle':'|-|','color':'#b94d24','lw':1})
        mid=(np.array(a)+b)/2;ax.text(mid[0]+3,mid[1]+4,label,fontsize=10,color='#b94d24')
    dim((-65,135),(-65,295),'160');dim((0,333),(160,333),'160');dim((220,160),(220,295),'135 TOOL')
    dim((-110,-15),(110,-15),'220 BASE');dim((-125,0),(-125,135),'135')
    for x,z,label in [(0,135,'SHOULDER'),(0,295,'ELBOW'),(160,295,'WRIST'),(160,227,'ROLL')]:
        ax.plot(x,z,'o',ms=4,color='#b94d24');ax.text(x+7,z+7,label,fontsize=8)
    ax.text(-135,355,'ASTER 320 / GENERAL ARRANGEMENT',fontsize=15,weight='bold')
    ax.text(240,140,'mm · Z-up\nHome pose\n\n5 positioning axes\n1 gripper actuator\n1 coupled jaw\n\nBase depth: 180\nRail spacings:\nupper 76 / forearm 54',fontsize=9,linespacing=1.6)
    fig.savefig(root/'drawing.svg',metadata={'Date':None,'Creator':'Aster 320'});plt.close(fig)

def draw(ax,parts,joints,values,colors):
    M,_=transforms(joints,values)
    triangles=[];cols=[]
    light=np.array([-.25,-.6,.75]);light/=np.linalg.norm(light)
    for pid,p in parts.items():
        v=trimesh.transform_points(p['mesh'].vertices+p['origin'],M[p['owner']]);f=p['mesh'].faces
        n=p['mesh'].face_normals@M[p['owner']][:3,:3].T
        shade=.65+.35*np.maximum(0,n@light)
        col=np.array(colors[p['material']][:3]);fc=shade[:,None]*col
        triangles.extend(v[f]);cols.extend(fc)
    poly=Poly3DCollection(triangles,facecolors=cols,edgecolors='none',linewidth=0,zsort='average')
    ax.add_collection3d(poly)
    ground=Poly3DCollection([[[-115,-95,-.3],[115,-95,-.3],[115,95,-.3],[-115,95,-.3]]],facecolors='#d8ddd5',alpha=.5)
    ax.add_collection3d(ground)

def write_design(root,parts,report):
    rows=[]
    for p in report['poses']:
        t=p['static_torque_nm_with_150g']
        rows.append(f'| {p["name"]} | {p["wrist_radius_mm"]:.2f} | {p["wrist_mm"][2]:.2f} | {p["tip_mm"][2]:.2f} | {t["shoulder"]:.3f} | {t["elbow"]:.3f} | {t["wrist"]:.3f} |')
    table='\n'.join(rows)
    doc=f'''# Aster 320 — five-axis desktop robot arm

Design target: carry **150 g**, with **310.35 mm horizontal reach from the yaw axis** while the gripper points down. The structure uses 160 mm upper and forearm links, a 135 mm shoulder height, and a 135 mm wrist-to-fingertip envelope. The four-hole 220 x 180 mm base must be bolted to a rigid desk. This is a dimensional engineering prototype, not a bench-tested load rating.

## Deliverables and rebuild

`assembly.glb` is the home assembly. `joints.yaml` has five positioning revolutes plus a gripper drive and one coupled follower (seven joints, six independent actuators). `assembly.yaml` lists intended contact pairs. `geometry.py` contains literal mm/degree constants. Individual print-ready, mm-unit solids are in `stl/`; `print-manifest.yaml` records their orientations and dimensions. `bom.csv` contains every modeled component. `validation.json` is generated from the exported GLB, not the in-memory design. `preview.png` and `drawing.svg` show the arrangement.

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py
.venv/bin/python validate.py
```

Use the pinned versions and Python 3.11. The generator needs no network, fixes polygon resolution, and does not use randomness, timestamps, or external assets. Generated files are hashed in `manifest.sha256.json`. The source files are the rebuild inputs. Do not edit generated meshes manually.

## Actuation and purchased hardware

| Axis | Motor | 12 V vendor stall torque | Planning torque budget |
|---|---|---:|---:|
| Yaw | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Shoulder | XM540-W270-T | 10.60 Nm | 3.180 Nm |
| Elbow | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Wrist pitch | XM430-W350-T | 4.10 Nm | 1.230 Nm |
| Tool roll | XC330-T288-T | 1.00 Nm | 0.300 Nm |
| Gripper | XC330-T288-T | 1.00 Nm | 0.200 Nm holding target |

The 30% stall-torque planning allowance is an explicit design assumption, **not a manufacturer continuous rating**. Commission with current-based position control, current/temperature telemetry, 20 degrees/s joint speed and 40 degrees/s² acceleration caps. Apply a 1.25 factor to static loads for slow-motion sizing. Verify the thermal duty cycle with 150 g before unattended use. Shoulder and elbow are backdrivable on power loss; support the arm before releasing torque.

Yaw uses two 6808-2RS bearings (40 x 52 x 7 mm) separated by 13 mm; a hollow printed spindle transfers torque while the bearings react overturning load. Each pitch joint has a separately supported steel 8 mm idler axle and a 608-2RS (8 x 22 x 7 mm) bearing opposite the metal servo horn. The follower jaw uses a 5 x 10 x 4 mm bearing and 5 mm axle. Aluminum OEM output horns transmit torque; printed splines are not used. Standard M2, M2.5, M3 and M4 socket screws, hex nuts, collars and brass board standoffs are separate meshes.

Purchased servo housings, connectors, bearings and boards are **envelope models**, not vendor CAD. Motor internals, actual thread helices and bearing balls are omitted. Servo body clamps use envelope dimensions and do not depend on case screw patterns. Shaft offsets and horn integration dimensions are integration assumptions; confirm against the ordered hardware before printing all parts. HN13 uses a 22 mm pitch circle with M2.5 fasteners; HN12 uses 16 mm / M2; HNX330 is modeled with an 11 mm / M2 pattern. Confirm the HNX330 variant and drill a test coupon first. Holes and bearing seats include FDM clearance; ream journals/seats to fit.

## Load calculation

The generator computes gravitational moments from each exported part's center of mass and assigned mass. Purchased motor masses are 165/82/23 g (XM540/XM430/XC330). Printed parts use the full solid volume at 1.20 g/cm³, conservatively exceeding a hollow/infilled print. Fasteners use steel density. A 150 g payload is applied at the nominal fingertip point. Wiring mass is represented by retained runs; allow extra margin for the flexible service loops. Total modeled mass: **{report['estimated_total_mass_g']:.1f} g**.

| Pose | Wrist radius mm | Wrist z mm | Nominal tip z mm | Shoulder Nm | Elbow Nm | Wrist Nm |
|---|---:|---:|---:|---:|---:|---:|
{table}

The reach pose has `shoulder=20`, `elbow=-20`, `wrist=-90`: radius = 160 cos(20°) + 160 = 310.35 mm; wrist z = 135 + 160 sin(20°) = 189.72 mm. Tip z = 54.72 mm. Reach is measured from the yaw axis, not the front edge of the base.

For a first structural estimate, the two upper rails each have 6 mm thickness and 30 mm width before the central relief. Treat the relieved section conservatively as two 7 mm edge ribs per rail: total section I about the bending axis = 2 x 6 x (30³ - 16³) / 12 = 22,904 mm⁴. At 3.18 Nm, nominal bending stress = M c / I = 2.08 MPa; a 3x local concentration allowance gives 6.25 MPa. Use a minimum coupon-qualified 15 MPa printed allowable at operating temperature. This is a beam screening calculation; it does not validate clamp preload, bearing creep, layer adhesion, or long-term fatigue.

For 0.20 Nm gripper input and two 41 mm lever arms, ideal force is 2.44 N per jaw. With 0.5 pad friction and a 25% force loss allowance, vertical capacity is 1.83 N, exceeding the 1.47 N weight of 150 g. Grip only near the lower pad center; verify actual pad/object friction. The fingers rotate and therefore are **not parallel jaws**. At home the inner pad gap is 15 mm; opening/closing changes both gap and contact angle. The gear pair is module 1, 28/28 teeth, 20-degree involute, 0.20 mm tooth thinning. Its exact relation is `jaw-r = -grip`; the follower has no second motor.

## Motion convention and limits

All joints use degrees. Origins and axes are in the common home frame, and rotation is `(value - home)` by the right-hand rule. Yaw is +Z; shoulder, elbow and wrist pitch are -Y; roll is -Z at home. Shoulder is absolute elevation above +X, elbow is relative bend and wrist is relative pitch. The home angles are 0, 90, -90, -90, 0. The gripper points down at home. This is a five-DOF positioning arm, so arbitrary six-DOF tool poses are not achievable.

The joint limits are cable/clearance controller bounds, not a claim that every Cartesian combination is safe. Yaw ±150°, shoulder 20…115°, elbow -125…5°, wrist -110…60°, roll ±120°, gripper -10…25°, follower -25…10°. Use software limits before torque enable; no continuous rotation through cable loops. Swept links, exposed hardware, the payload and cable slack require collision checking during path planning.

The mandatory safe-pose constants are wrist z >=95 mm; if wrist radius <145 mm, wrist z >=230 mm; nominal tip z >=5 mm. The check uses the `wrist` pitch frame and a -Z tool vector. Rotating fingers have off-axis corners, so validation additionally reports the actual pad's lowest vertex. Never treat the three scalar reach constraints as a complete collision checker.

## Printing and assembly

Print structural parts in dry PA12-CF, 0.2 mm layers, 6 perimeters, 6 top/bottom layers, 50% gyroid and 100% local infill around bearings, clamp ears and horn patterns. Use a 0.6 mm hardened nozzle. PETG is suitable for fit prototypes; do not assign it the same stiffness/creep rating. STL files are in millimetres and are rotated onto a useful print face; support may still be required under clamp bridges. Print the two pads in TPU 95A. Fit coupons are required for bearing bores and axle clearance. Split parts fit a 220 x 220 mm bed; the base is exactly 220 mm wide and needs a larger bed or no brim at the edges.

1. Finish the bearing seats and clearance holes. Install base columns, the yaw motor clamp, two bearings, spindle and deck. Retain the yaw bearing races axially without preloading them through printed material.
2. Install the shoulder motor in its split cradle. Assemble the metal horn, drive spacer, rear axle bracket, bearing and two upper rails. Bolt in both cross ties.
3. Add the elbow motor and its cradle to the upper rails. Install the elbow horn/spacer, rear idler and forearm rails; fit the two forearm cross ties.
4. Install the wrist pitch motor, fork, rear idler and roll bridge. Fit roll motor, horn and palm. Align servo encoder centers mechanically before configuring software home offsets.
5. Fit the gripper motor, geared jaws, follower axle/bearing and guard. Phase the right gear by half a tooth. Bond TPU pads and set closed-current limit before holding an object.
6. Install the power hub and U2D2 on standoffs. Run 12 V / GND / half-duplex TTL data through the chain. Use a regulated 12 V 8 A external supply, 7.5 A fuse, and DC-rated normally closed emergency-stop contacts in the motor supply feed. Do not carry motor current over USB. Verify connector polarity; XC330-T is the 12 V variant, not the 5 V M variant.
7. Route loose 50–80 mm service loops at the joints, secure fixed runs, and keep 15 mm minimum bend radius. Flexing spans are intentionally absent from rigid-body GLB geometry. Wire yaw with a service loop, not unlimited rotation. Use a host PC with DYNAMIXEL Protocol 2.0 through U2D2; assign IDs 1…6 in joint order. No motor firmware is supplied.
8. Bolt the base through its four 5.5 mm holes (196 x 156 mm pattern) to a rigid table using suitable M5 fasteners and washers. Desk fasteners and the external PSU are procurement items outside the assembly model. Do not operate the arm freestanding.

## Validation scope

Generated with Python {report['python']}. **{report['part_count']} parts, {report['joint_count']} joints, {report['triangle_count']:,} triangles**, {report['printed_part_count']} structural print pieces and {report['tpu_part_count']} pads. GLB root rotation, metre conversion, direct-child structure, unique names, references, parent/coupling graphs, home identity, mesh closure/winding, SHA-256 and safe-pose rules are checked by `validate.py`. `validation.json` records FCL contact results for every named pose: no unlisted contacts, including fixed-body fits. `motion-checks.json` checks six single-axis sweeps and four home-to-pose paths at no more than 2 degrees per sample. Every sampled configuration admitted by the safe-pose rules and every sampled path is clear. Rejected low-shoulder configurations are recorded, not hidden. This is a sampled check, not a continuous or full combinatorial workspace certificate. `mating-features.json` records material removed for the real hardware interfaces, including cable openings and captive-nut pockets. Mesh detail is intentionally modest to stay below 50,000 triangles. This deliverable does not replace physical fit, thermal, cyclic load or fabrication testing.

## Manufacturer references

- [XM540-W270 documentation](https://emanual.robotis.com/docs/en/dxl/x/xm540-w270/): 33.5 x 58.5 x 44 mm, 165 g, 10.6 Nm stall at 12 V.
- [XM430-W350 documentation](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/): 28.5 x 46.5 x 34 mm, 82 g, 4.1 Nm stall at 12 V.
- [XC330-T288 documentation](https://emanual.robotis.com/docs/en/dxl/x/xc330-t288/): 20 x 34 x 26 mm, 23 g, 1.0 Nm stall at 12 V; current-based position mode.
- [OEM horn drawings](https://en.robotis.com/service/downloadpage.php?ca_id=7020): purchase original metal horns, confirm interfaces against the current drawing.
- [U2D2](https://emanual.robotis.com/docs/en/parts/interface/u2d2/): 48 x 18 x 14.9 mm, USB to TTL interface; external motor power required.
- [U2D2 Power Hub](https://robotis.us/u2d2-power-hub-board-set/): 48 x 57 mm, 10 A maximum.

Manufacturer specifications checked 2026-11-06. The reduced CAD models and all custom structure are authored by this generator.
'''
    (root/'DESIGN.md').write_text(doc)
