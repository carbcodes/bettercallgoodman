#!/usr/bin/env python3
"""Deterministic Aster 320 assembly. Run with Python 3.11; no network access.

All construction is in mm. GLB is written explicitly so its graph/units/root
quaternion meet the interchange contract exactly. Purchased parts are envelope
models; printed parts are boolean solids with real clearance holes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True

os.environ.setdefault('MPLCONFIGDIR', '/tmp/aster320-matplotlib')
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
import yaml
import geometry as G

ROOT = Path(__file__).resolve().parent
PARTS = {}
CONTACT = set()
COLORS = {
    'print': (0.79, 0.84, 0.80, 1), 'accent': (0.91, 0.37, 0.16, 1),
    'motor': (0.14, 0.17, 0.19, 1), 'steel': (0.64, 0.69, 0.73, 1),
    'aluminum': (0.79, 0.81, 0.83, 1), 'rubber': (0.075, 0.085, 0.09, 1),
    'pcb': (0.025, 0.34, 0.24, 1), 'plug': (0.88, 0.86, 0.76, 1),
    'brass': (0.70, 0.51, 0.22, 1), 'cable': (0.16, 0.18, 0.21, 1),
}

def box(size, center=(0, 0, 0)):
    m = trimesh.creation.box(size)
    m.apply_translation(center)
    return m

def cyl(r, h, center=(0, 0, 0), axis=(0, 0, 1), n=20):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=n)
    m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], axis))
    m.apply_translation(center)
    return m

def union(*meshes):
    if len(meshes) == 1:
        return meshes[0].copy()
    return trimesh.boolean.union(list(meshes), engine='manifold')

def cut(body, *holes):
    return trimesh.boolean.difference([body, *holes], engine='manifold') if holes else body

def ring(ro, ri, h, center=(0, 0, 0), axis=(0, 0, 1), n=24):
    return cut(cyl(ro, h, center, axis, n), cyl(ri, h+2, center, axis, n))

def rod(a, b, r, n=12):
    a, b = np.array(a, float), np.array(b, float)
    return cyl(r, np.linalg.norm(b-a), (a+b)/2, b-a, n)

def add(pid, mesh, owner=None, category='printed', material='print', spec='', mass=None,
        origin=None, print_rotation=(0, 0, 0)):
    assert pid not in PARTS, pid
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals(multibody=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0, pid
    # Translation-only local frames keep holes and node origins inspectable.
    origin = np.array(mesh.bounds.mean(axis=0) if origin is None else origin, dtype=float)
    local = mesh.copy()
    local.apply_translation(-origin)
    if mass is None:
        density = {'printed':1.2, 'hardware':7.85, 'bearing':7.85,
                   'pad':1.15, 'electronics':1.8, 'cable':1.5}.get(category, 2.7)
        mass = mesh.volume / 1000 * density
    PARTS[pid] = dict(mesh=local, origin=origin, owner=owner, category=category,
                      material=material, spec=spec, mass_g=float(mass),
                      print_rotation=print_rotation)
    return pid

def touch(*ids):
    for a, b in zip(ids, ids[1:]):
        assert a != b
        CONTACT.add(tuple(sorted((a, b))))

def bolt(pid, d, length, start, axis=(0, 0, 1), owner=None, mates=(), nut=False):
    """ISO 4762 envelope: start is underside of head; shaft points along axis."""
    a = np.array(axis, float); a /= np.linalg.norm(a)
    p = np.array(start, float)
    hr = {2:1.9, 2.5:2.25, 3:2.75, 4:3.5, 5:4.25}.get(d, d*.9)
    head = cyl(hr, d, p-a*d/2, a, 12)
    shaft = cyl(d/2, length+.02, p+a*(length/2-.01), a, 12)
    socket = cyl(d*.46, d*.6, p-a*d*.80, a, 6)
    mesh = cut(union(head, shaft), socket)
    add(pid, mesh, owner, 'hardware', 'steel', f'ISO 4762 M{d:g}x{length:g}; simplified thread')
    for q in mates: touch(pid, q)
    if nut:
        npid = pid.removesuffix('-bolt')+'-nut'
        af = {2:4, 2.5:5, 3:5.5, 4:7, 5:8}[d]
        h = .8*d
        nc = p+a*(length-h/2-1)
        mesh = cut(cyl(af/math.sqrt(3), h, nc, a, 6), cyl(d*.43, h+2, nc, a, 16))
        add(npid, mesh, owner, 'hardware', 'steel', f'ISO 4032 M{d:g} hex nut')
        touch(pid, npid)
        for q in mates: touch(npid, q)
    return pid

def bearing(pid, inner, outer, width, center, axis, stationary, rotating, owner_outer, owner_inner):
    """Two races plus sealed rolling-element envelope; actual rings have clearance."""
    t = (outer-inner)/2
    specs = f'{inner:g} x {outer:g} x {width:g} mm sealed radial ball bearing'
    add(pid+'-outer', ring(outer/2, outer/2-t*.35, width, center, axis), owner_outer,
        'bearing','steel',specs+' outer race')
    add(pid+'-inner', ring(inner/2+t*.35, inner/2, width, center, axis), owner_inner,
        'bearing','steel',specs+' inner race')
    add(pid+'-seal', ring(outer/2-t*.35-.02, inner/2+t*.35+.02, width-.4, center, axis),
        owner_outer, 'bearing','rubber',specs+' sealed ball/cage envelope',mass=1.0)
    touch(pid+'-outer', stationary)
    touch(pid+'-inner', rotating)
    touch(pid+'-outer',pid+'-seal',pid+'-inner')

def plate_holes(mesh, points, radius, h, axis=(0,1,0)):
    return cut(mesh, *(cyl(radius, h, p, axis, 16) for p in points))

def servo(pid, family, shaft, direction=(0,1,0), down=(0,0,-1), owner=None):
    """Housing uses manufacturer envelope. Local x=width, y=depth, z=height.
    Output center offsets are envelope integration assumptions, documented in BOM.
    Clamp mounts avoid relying on undocumented body screw locations.
    """
    sizes = {'540':(33.5,44,58.5,16.5,165),
             '430':(28.5,34,46.5,10.75,82), '330':(20,26,34,7,23)}
    w, dep, ht, off, mass = sizes[family]
    a = np.array(direction,float); down=np.array(down,float)
    up=-down; right=np.cross(a,up)
    R=np.column_stack([right,a,up])
    c=np.array(shaft,float)+down*off
    m=box([w,dep,ht]); T=np.eye(4); T[:3,:3]=R; T[:3,3]=c; m.apply_transform(T)
    spec={'540':'ROBOTIS XM540-W270-T', '430':'ROBOTIS XM430-W350-T', '330':'ROBOTIS XC330-T288-T'}[family]
    add(pid,m,owner,'motor','motor',spec,mass=mass)
    # Two connector faces with through-housing cable reliefs omitted from housing envelope.
    for n,dx in enumerate([-w*.23,w*.23]):
        pc=c+down*(ht/2+2)+right*dx
        pm=box([w*.36,7,4]); TT=T.copy(); TT[:3,3]=pc; pm.apply_transform(TT)
        add(pid+f'-socket-{n+1}',pm,owner,'electronics','plug',
            'JST 3-pin TTL servo socket envelope',mass=.3)
        touch(pid,pid+f'-socket-{n+1}')
    return dict(w=w,dep=dep,ht=ht,off=off,c=c,R=R)

def horn(pid, family, center, axis, owner, motor):
    r,pcd,d = {'540':(13,22,2.5),'430':(10,16,2),'330':(7.5,11,2)}[family]
    c=np.array(center,float); a=np.array(axis,float)
    basis=trimesh.geometry.align_vectors([0,0,1],a)[:3,:3]
    holes=[c+basis@np.array([pcd/2*math.cos(t),pcd/2*math.sin(t),0])
           for t in np.linspace(0,2*math.pi,4,endpoint=False)]
    m=plate_holes(ring(r,1.5,3,c,a),holes,d*.43,6,a)
    add(pid,m,owner,'purchased','aluminum',{'540':'HN13-N101','430':'HN12-N101','330':'HNX330-N101'}[family]+' output horn envelope',mass=5 if family!='540' else 9)
    touch(pid,motor)
    return holes,d

def frame_rail(pid,a,b,y,width,thick,r1,r2,owner,end_bores,holes=()):
    a=np.array([a[0],y,a[1]],float); b=np.array([b[0],y,b[1]],float)
    delta=b-a; L=np.linalg.norm(delta)
    m=box([width,thick,L],(0,0,0))
    T=trimesh.geometry.align_vectors([0,0,1],delta); T[:3,3]=(a+b)/2
    m.apply_transform(T)
    m=union(m,cyl(r1,thick,a,(0,1,0),32),cyl(r2,thick,b,(0,1,0),32))
    # Rounded lightening slot retains two continuous load-bearing ribs.
    if L>90:
        u=delta/L; p=a+u*43; q=b-u*43
        slot=box([width-14,thick+4,np.linalg.norm(q-p)],(0,0,0))
        TT=T.copy(); TT[:3,3]=(p+q)/2; slot.apply_transform(TT)
        slot=union(slot,cyl((width-14)/2,thick+4,p,(0,1,0),16),cyl((width-14)/2,thick+4,q,(0,1,0),16))
        m=cut(m,slot)
    m=plate_holes(m,[a,b],end_bores,thick+4)
    if holes: m=plate_holes(m,holes,1.7,thick+4)
    add(pid,m,owner,print_rotation=(90,0,0),spec='PA12-CF; continuous ribs, flat printed on broad side')

def pitch_motor_mount(pid,family,shaft,owner,attach_to,width_y,down=(0,0,-1)):
    """Open split cradle: bottom, two cheeks and bolt-on keeper; OEM body untouched."""
    info=servo(pid+'-motor',family,shaft,down=down,owner=owner)
    w,dep,ht=info['w'],info['dep'],info['ht']; c=info['c']; R=info['R']
    # Local cradle base and cheeks with clamp ears, then map into assembly frame.
    bottom=box([w+20,width_y,5],[0,0,-ht/2-2.25])
    if pid=='elbow':bottom=union(bottom,box([28,70,8],[0,0,-ht/2-5]))
    sides=[box([8,width_y,ht*.65],[s*(w/2+4.25),0,-ht*.175]) for s in [-1,1]]
    ears=[box([10,12,8],[s*(w/2+6),0,ht*.15]) for s in [-1,1]]
    m=union(bottom,*sides,*ears)
    # Four vertical clamp fastener clearances, one at each side/end.
    pts=[[s*(w/2+5), yy,0] for s in [-1,1] for yy in [-width_y/2+6,width_y/2-6]]
    # Side walls are long; bolts run through upper keeper into bottom nuts.
    m=plate_holes(m,pts,1.65,ht+25,(0,0,1))
    if pid=='wrist':
        # Pocket the cheeks between the four clamp rods; retain 5 mm edge ribs.
        m=cut(m,box([w+25,width_y-22,ht*.38],[0,0,-ht*.20]))
    T=np.eye(4);T[:3,:3]=R;T[:3,3]=c;m.apply_transform(T)
    add(pid+'-cradle',m,owner,spec='PA12-CF open motor cradle; 0.5 mm diametral clearance')
    keeper=union(box([w+20,width_y,4],[0,0,ht/2+2.25]))
    # central ventilation opening avoids insulating the motor housing.
    keeper=cut(keeper,box([w-8,dep-10,8],[0,0,ht/2+2.25]))
    keeper=plate_holes(keeper,pts,1.65,ht+25,(0,0,1));keeper.apply_transform(T)
    add(pid+'-keeper',keeper,owner,spec='PA12-CF ventilated clamp cap')
    touch(pid+'-cradle',pid+'-motor',pid+'-keeper')
    for q in attach_to: touch(pid+'-cradle',q)
    # Separate steel tie rods use M3 lengths appropriate to the full cradle depth.
    length=math.ceil((ht+9)/5)*5
    for n,p in enumerate(pts):
        pp=R@np.array([p[0],p[1],ht/2+4.25])+c
        bolt(pid+f'-clamp-{n+1}-bolt',3,length,pp,-R[:,2],owner,[pid+'-cradle',pid+'-keeper'],nut=True)
    return info

def build_base():
    holes=[(x,y,4) for x in [-98,98] for y in [-78,78]]
    m=plate_holes(box(G.BASE_SIZE,[0,0,4]),holes,2.75,14,(0,0,1))
    colpts=[(x,y,4) for x in [-34,34] for y in [-34,34]]
    m=plate_holes(m,colpts,2.2,14,(0,0,1))
    add('base-plate',m,spec='PA12-CF 220x180x8; four 5.5 mm desk mounting holes; solid locally')
    for n,(x,y,_) in enumerate(colpts):
        c=(x,y,39.5)
        m=ring(7,2.2,63,c,n=20)
        add(f'base-column-{n+1}',m,spec='Printed compression standoff, M4 through bolt')
        touch('base-plate',f'base-column-{n+1}')
        bolt(f'base-column-{n+1}-bolt',4,70,[x,y,72],(0,0,-1),None,[f'base-column-{n+1}','base-plate'],nut=True)
    # Bearing carrier is a stepped annulus tied to four columns.
    carrier=union(ring(32,20.6,28,(0,0,61)),box([82,82,6],[0,0,72]))
    carrier=cut(carrier,cyl(20.6,40,(0,0,60)),cyl(26.1,7.2,(0,0,55)),cyl(26.1,7.2,(0,0,68)))
    carrier=plate_holes(carrier,[(x,y,72) for x,y,_ in colpts],2.2,14,(0,0,1))
    add('yaw-bearing-carrier',carrier,spec='PA12-CF; two 6808-2RS seats 52.2 mm x 7.2, 13 mm spacing')
    for n in range(4): touch('yaw-bearing-carrier',f'base-column-{n+1}',f'base-column-{n+1}-bolt')
    # Horizontal body, vertical output; x is motor's long dimension.
    info=servo('yaw-motor','430',(0,0,29),direction=(0,0,1),down=(1,0,0))
    saddle=union(box([54,42,5],[11,0,10.5]),box([54,5,27],[11,-20,24]),box([54,5,27],[11,20,24]))
    add('yaw-motor-saddle',saddle,spec='PA12-CF body cradle, zip-clamp ears and base screws')
    touch('yaw-motor-saddle','base-plate','yaw-motor')
    for i,yy in enumerate([-20,20]):
        add(f'yaw-motor-strap-{i+1}',box([54,4,4],[11,yy,40]),spec='PA12-CF motor retention bar')
        for j,xx in enumerate([-11,33]):
            bolt(f'yaw-saddle-{i+1}-{j+1}-bolt',3,35,[xx,yy,42],(0,0,-1),None,['yaw-motor-saddle',f'yaw-motor-strap-{i+1}','base-plate'],nut=True)
    hp,hd=horn('yaw-horn','430',(0,0,47.5),(0,0,1),'yaw','yaw-motor')
    shaft=union(ring(19.95,13,28,(0,0,63)),cyl(19.95,4,(0,0,51)))
    shaft=plate_holes(shaft,[p+[0,0,3.5] for p in hp],1.15,9,(0,0,1))
    add('yaw-spindle',shaft,'yaw',spec='PA12-CF hollow 39.9 mm journal; horn-driven, bearing-supported')
    touch('yaw-spindle','yaw-horn')
    for i,p in enumerate(hp): bolt(f'yaw-horn-{i+1}-bolt',2,6,p+[0,0,5.5],(0,0,-1),'yaw',['yaw-horn','yaw-spindle'])
    for n,z in enumerate([55,68]):
        bearing(f'yaw-bearing-{n+1}',40,52,7,(0,0,z),(0,0,1),'yaw-bearing-carrier','yaw-spindle',None,'yaw')
    disk=ring(54,5,8,(0,0,81),n=48)
    disk=plate_holes(disk,[(x,y,81) for x in [-24,24] for y in [-24,24]],1.7,12,(0,0,1))
    add('yaw-turntable',disk,'yaw',spec='PA12-CF deck; underside engages spindle flange')
    touch('yaw-turntable','yaw-spindle')
    for i,a in enumerate([45,135,225,315]):
        x,y=16*np.cos(np.radians(a)),16*np.sin(np.radians(a))
        bolt(f'yaw-deck-{i+1}-bolt',3,12,[x,y,85],(0,0,-1),'yaw',['yaw-turntable','yaw-spindle'])
    # PCB pocket on the left side keeps the USB and power input accessible.
    tray=cut(box([64,75,18],[-72,21,17]),box([56,67,20],[-72,21,21]))
    add('electronics-tray',tray,spec='PA12-CF open electronics tray; accessible connectors')
    touch('base-plate','electronics-tray')
    add('power-hub-pcb',box([48,57,1.6],[-72,21,20]),category='electronics',material='pcb',spec='ROBOTIS U2D2 Power Hub 48x57; 10 A maximum',mass=15)
    for i,(x,y) in enumerate([(-93,-3),(-51,-3),(-93,45),(-51,45)]):
        add(f'pcb-standoff-{i+1}',ring(2.75,1.4,10,[x,y,14],n=12),category='hardware',material='brass',spec='M3x10 brass standoff')
        touch('power-hub-pcb',f'pcb-standoff-{i+1}','electronics-tray')
    add('u2d2-controller',box([48,18,14.9],[-72,25,30.25]),category='electronics',material='motor',spec='ROBOTIS U2D2 USB / TTL interface; host PC runs controller',mass=9)
    touch('u2d2-controller','power-hub-pcb')
    add('usb-micro-b-plug',box([11,8,4],[-101,25,31]),category='electronics',material='steel',spec='USB Micro-B cable plug; host cable omitted',mass=3)
    touch('usb-micro-b-plug','u2d2-controller')
    add('dc-input-jack',ring(5.5,2.75,12,[-96,4,27],(1,0,0)),category='electronics',material='motor',spec='5.5/2.5 mm DC input barrel; 12 V',mass=4)
    touch('dc-input-jack','power-hub-pcb')
    add('power-terminal',box([12,9,10],[-55,2,26]),category='electronics',material='pcb',spec='5.08 mm two-position screw terminal; fused 12 V input',mass=4)
    touch('power-terminal','power-hub-pcb')
    for i in range(3):
        add(f'hub-jst-plug-{i+1}',box([8,8,7],[-88+i*14,46,25]),category='electronics',material='plug',spec='JST X3P 3-pin TTL power/data plug',mass=1)
        touch(f'hub-jst-plug-{i+1}','power-hub-pcb')
    add('stop-switch-body',cyl(11,13,[-74,-54,17]),category='electronics',material='motor',spec='22 mm latching NC emergency stop; DC-rated power contact',mass=25)
    add('stop-switch-pedestal',union(ring(18,11.15,10,[-74,-54,13]),ring(23,11.15,4,[-74,-54,10])),spec='PA12-CF 22 mm switch mounting collar')
    add('stop-switch-nut',ring(14,10.7,3,[-74,-54,19.5]),category='hardware',material='steel',spec='M22 switch panel retaining nut')
    touch('stop-switch-pedestal','base-plate');touch('stop-switch-nut','stop-switch-body');touch('stop-switch-nut','stop-switch-pedestal')
    add('stop-switch-cap',cyl(16,7,[-74,-54,27]),category='electronics',material='accent',spec='Emergency-stop mushroom cap',mass=5)
    touch('stop-switch-body','base-plate');touch('stop-switch-body','stop-switch-cap')

def build_arm():
    S=np.array(G.SHOULDER_ORIGIN); E=np.array(G.ELBOW_ORIGIN); W=np.array(G.WRIST_ORIGIN)
    pitch_motor_mount('shoulder','540',S,'yaw',['yaw-turntable'],42)
    for side,yy in [('left',-38),('right',38)]:
        frame_rail(f'upper-link-{side}',(0,135),(0,295),yy,30,6,20,19,'shoulder',4.15)
    # Drive horn, bored cylindrical spacer, four screws through rail and horn.
    hp,d=horn('shoulder-horn','540',S+[0,24,0],(0,1,0),'shoulder','shoulder-motor')
    spacer=plate_holes(ring(13,4.15,9.5,S+[0,30.25,0],(0,1,0)),[p+[0,6,0] for p in hp],1.4,15)
    add('shoulder-drive-spacer',spacer,'shoulder',spec='PA12-CF horn to upper rail spacer')
    touch('shoulder-horn','shoulder-drive-spacer','upper-link-right')
    # Add actual horn clearance holes to the rail.
    drill_part('upper-link-right',hp,1.4,(0,1,0))
    for i,p in enumerate(hp): bolt(f'shoulder-horn-{i+1}-bolt',2.5,18,p+[0,17,0],(0,-1,0),'shoulder',['upper-link-right','shoulder-drive-spacer','shoulder-horn'])
    idler_support('shoulder',S,-38,-49,'yaw','shoulder','shoulder-cradle','upper-link-left',20)
    # Cross ties have fastened end faces, no floating rails.
    for i,z in enumerate([183,225]): cross_tie(f'upper-cross-tie-{i+1}',[0,0,z],70,18,12,'shoulder','upper-link-left','upper-link-right')
    pitch_motor_mount('elbow','430',E,'shoulder',['upper-link-left','upper-link-right'],38)
    # Integral elbow cradle foot bridges to both upper rails at y +/-35.
    for i,x in enumerate([-8,8]):
        bolt(f'elbow-mount-{i+1}-bolt',3,85,[x,-41,254],(0,1,0),'shoulder',
             ['elbow-cradle','upper-link-left','upper-link-right'],nut=True)
    for side,yy in [('left',-27),('right',27)]:
        frame_rail(f'forearm-link-{side}',(0,295),(160,295),yy,26,5,17,17,'elbow',4.15)
        drill_part(f'forearm-link-{side}',[W],12.5,(0,1,0))
    hp,d=horn('elbow-horn','430',E+[0,19,0],(0,1,0),'elbow','elbow-motor')
    m=plate_holes(ring(10,4.15,4,E+[0,22.5,0],(0,1,0)),[p+[0,4,0] for p in hp],1.15,12)
    add('elbow-drive-spacer',m,'elbow',spec='PA12-CF horn spacer')
    drill_part('forearm-link-right',hp,1.15,(0,1,0))
    touch('elbow-horn','elbow-drive-spacer','forearm-link-right')
    for i,p in enumerate(hp):bolt(f'elbow-horn-{i+1}-bolt',2,12,p+[0,10.5,0],(0,-1,0),'elbow',['elbow-horn','elbow-drive-spacer','forearm-link-right'])
    idler_support('elbow',E,-27,-35,'shoulder','elbow','elbow-cradle','forearm-link-left',17)
    for i,x in enumerate([55,99]):cross_tie(f'forearm-cross-tie-{i+1}',[x,0,295],49,12,16,'elbow','forearm-link-left','forearm-link-right')
    pitch_motor_mount('wrist','430',W,'elbow',['forearm-link-left','forearm-link-right'],49,down=(-1,0,0))
    for side,yy in [('left',-27),('right',27)]:
        p=PARTS['forearm-link-'+side];m=p['mesh'].copy();m.apply_translation(p['origin'])
        m=union(m,*(cyl(6,5,[123.75,yy,z],(0,1,0),20) for z in [281,309]))
        m.apply_translation(-p['origin']);p['mesh']=m
    for i,z in enumerate([281,309]):
        bolt(f'wrist-mount-{i+1}-bolt',3,60,[123.75,-29.5,z],(0,1,0),'elbow',
             ['wrist-cradle','forearm-link-left','forearm-link-right'],nut=True)
    # Wrist yoke straddles the forearm rails. Its bridge carries the roll motor.
    for side,yy in [('left',-38),('right',38)]:
        m=union(cyl(17,5,[160,yy,295],(0,1,0)),box([44,5,55],[160,yy,267.5]))
        m=cut(m,cyl(4.15,9,[160,yy,295],(0,1,0)))
        add('wrist-yoke-'+side,m,'wrist',spec='PA12-CF pitch fork',print_rotation=(90,0,0))
    hp,d=horn('wrist-horn','430',W+[0,19,0],(0,1,0),'wrist','wrist-motor')
    spacer=plate_holes(ring(10,4.15,15,W+[0,28,0],(0,1,0)),[p+[0,9,0] for p in hp],1.15,20)
    add('wrist-drive-spacer',spacer,'wrist',spec='PA12-CF pitch horn stand-off')
    drill_part('wrist-yoke-right',hp,1.15,(0,1,0))
    touch('wrist-horn','wrist-drive-spacer','wrist-yoke-right')
    for i,p in enumerate(hp):bolt(f'wrist-horn-{i+1}-bolt',2,22,p+[0,21.5,0],(0,-1,0),'wrist',['wrist-horn','wrist-drive-spacer','wrist-yoke-right'])
    idler_support('wrist',W,-38,-47,'elbow','wrist','wrist-cradle','wrist-yoke-left',17,down=(-1,0,0))
    bridge=cut(box([44,71,6],[160,0,259]),box([20.5,34.5,10],[160,7,259]))
    add('roll-motor-bridge',bridge,'wrist',spec='PA12-CF roll cradle with 0.5 mm body clearance')
    touch('roll-motor-bridge','wrist-yoke-left');touch('roll-motor-bridge','wrist-yoke-right')
    for i,x in enumerate([143,177]):
        bolt(f'wrist-bridge-{i+1}-bolt',3,85,[x,-41,239],(0,1,0),'wrist',
             ['roll-motor-bridge','wrist-yoke-left','wrist-yoke-right'],nut=True)
    servo('roll-motor','330',[160,0,263],direction=(0,0,-1),down=(0,1,0),owner='wrist')
    # Motor shaft top-to-face distance is 13 mm; horn is at z247.
    hp,d=horn('roll-horn','330',np.array(G.ROLL_ORIGIN)+[0,0,20],(0,0,-1),'tool-roll','roll-motor')
    add('roll-retainer',cut(box([30,44,4],[160,7,278]),box([14,24,6],[160,7,278])),'wrist',spec='PA12-CF roll motor clamp cap')
    touch('roll-retainer','roll-motor')
    for i,(x,y) in enumerate([(148,-13),(172,-13),(148,27),(172,27)]):
        bolt(f'roll-clamp-{i+1}-bolt',3,25,[x,y,280],(0,0,-1),'wrist',['roll-retainer','roll-motor-bridge'],nut=True)
    palm=box([56,38,5],[160,0,242.5])
    palm=plate_holes(palm,[[p[0],p[1],242.5] for p in hp],1.15,9,(0,0,1))
    add('gripper-palm',palm,'tool-roll',spec='PA12-CF tool flange; HNX330 horn bolt pattern')
    touch('gripper-palm','roll-horn')
    for i,p in enumerate(hp):bolt(f'roll-horn-{i+1}-bolt',2,8,[p[0],p[1],240],(0,0,1),'tool-roll',['gripper-palm','roll-horn'])

def drill_part(pid,points,r,axis):
    p=PARTS[pid]; world=p['mesh'].copy();world.apply_translation(p['origin'])
    # project holes to the part's center along the drilling direction
    a=np.array(axis,float)
    pts=[np.array(v)+a*np.dot(p['origin']-v,a) for v in points]
    world=plate_holes(world,pts,r,float(max(world.extents)+10),axis)
    world.apply_translation(-p['origin']);p['mesh']=world;p['mass_g']=world.volume*.0012

def cross_tie(pid,c,length,wx,h,owner,left,right):
    c=np.array(c,float)
    m=cut(box([wx,length,h],c),cyl(1.65,length+2,c,(0,1,0),16))
    add(pid,m,owner,spec='PA12-CF transverse rib; M3 through bolt')
    drill_part(left,[c],1.65,(0,1,0));drill_part(right,[c],1.65,(0,1,0))
    touch(pid,left);touch(pid,right)
    lengthbolt=math.ceil((length+16)/5)*5
    bolt(pid+'-bolt',3,lengthbolt,c+[0,-length/2-6,0],(0,1,0),owner,[pid,left,right],nut=True)

def idler_support(name,origin,y_bearing,y_bracket,stationary,rotating,mount,rail,radius,down=(0,0,-1)):
    c=np.array(origin,float); down=np.array(down,float)
    # A stationary L bracket returns below/behind the servo, carrying an 8 mm stub axle.
    p=c+np.array([0,y_bracket,0]); q=p+down*43
    leg=rod(p,q,3.5,16)
    shoe=box([20,abs(y_bracket)+4,7],q+np.array([0,-y_bracket/2,0]))
    if abs(down[0])>.5:
        shoe=box([7,abs(y_bracket)+4,20],q+np.array([0,-y_bracket/2,0]))
    if name=='wrist':
        shoe=box([8.5,19.5,20],q+np.array([0,9.75,0]))
    leg=union(leg,shoe,cyl(9,6,p,(0,1,0)))
    if name=='elbow':leg=box([20,6,36],p)
    leg=cut(leg,cyl(4.05,10,p,(0,1,0)))
    add(name+'-idler-bracket',leg,stationary,spec='PA12-CF stationary rear axle outrigger')
    touch(name+'-idler-bracket',mount)
    mid=(y_bracket+y_bearing)/2
    add(name+'-idler-axle',cyl(4,abs(y_bracket-y_bearing)+10,c+[0,mid,0],(0,1,0),24),stationary,
        'hardware','steel','8 mm h6 ground steel stub axle; 2 shaft collars')
    touch(name+'-idler-axle',name+'-idler-bracket')
    if name=='elbow':
        for i,x in enumerate([-7,7]):
            bolt(f'elbow-idler-mount-{i+1}-bolt',3,10,[x,-41,281],(0,1,0),stationary,
                 [name+'-idler-bracket','upper-link-left'],nut=True)
    if name=='wrist':
        for i,z in enumerate([289,301]):
            bolt(f'wrist-idler-mount-{i+1}-bolt',3,25,[117,-49,z],(0,1,0),stationary,
                 [name+'-idler-bracket','forearm-link-left'],nut=True)
    # Counterbore rail with standard 608 bearing; boss adds required 7 mm seat depth.
    p=PARTS[rail];world=p['mesh'].copy();world.apply_translation(p['origin'])
    world=union(world,cyl(14,8,c+[0,y_bearing,0],(0,1,0),32))
    world=cut(world,cyl(11.05,12,c+[0,y_bearing,0],(0,1,0),32))
    world.apply_translation(-p['origin']);p['mesh']=world;p['mass_g']=world.volume*.0012
    bearing(name+'-608',8,22,7,c+[0,y_bearing,0],(0,1,0),rail,name+'-idler-axle',rotating,stationary)
    for i,yy in enumerate([y_bearing-5.5,y_bearing+5.5]):
        add(name+f'-axle-collar-{i+1}',ring(6,4,3,c+[0,yy,0],(0,1,0),20),stationary,
            'hardware','steel','8 mm shaft collar, radial set screw simplified')
        touch(name+f'-axle-collar-{i+1}',name+'-idler-axle');touch(name+f'-axle-collar-{i+1}',name+'-608-inner')

def gear_profile(teeth=28,module=1.,pressure=20.,backlash=.2,phase=0.):
    """Sampled involute spur gear with radial dedendum and 0.2 mm tooth thinning.
    28 teeth avoids undercut at 20 degrees. Tip/root arcs are polygonal.
    """
    rp=module*teeth/2; rb=rp*math.cos(math.radians(pressure)); rr=rp-1.25*module; ra=rp+module
    inv=lambda r: math.sqrt(max(0,(r/rb)**2-1))-math.acos(min(1,rb/r))
    half=(math.pi*module/2-backlash)/(2*rp)
    pts=[]
    for i in range(teeth):
        t=phase+i*2*math.pi/teeth
        aa=half+inv(rp)-inv(max(rb,rr))
        pts.append([rr*math.cos(t-aa),rr*math.sin(t-aa)])
        for r in np.linspace(max(rr,rb),ra,4):
            a=t-half-inv(rp)+inv(r);pts.append([r*math.cos(a),r*math.sin(a)])
        for r in np.linspace(ra,max(rr,rb),4):
            a=t+half+inv(rp)-inv(r);pts.append([r*math.cos(a),r*math.sin(a)])
        pts.append([rr*math.cos(t+aa),rr*math.sin(t+aa)])
    return np.array(pts)

def extrude_polygon(points,height):
    # manifold's cross section provides robust triangulation without shapely.
    import manifold3d as md
    solid=md.CrossSection([points.tolist()]).extrude(height).translate([0,0,-height/2])
    out=solid.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:,:3],np.asarray(out.tri_verts),process=True)

def build_gripper():
    # Motor lies behind gear plane, supported by palm-attached cradle.
    c=np.array(G.JAW_LEFT_ORIGIN)+[0,0,20]
    servo('gripper-motor','330',c+[0,-17,0],owner='tool-roll')
    mount=union(box([29,28,4],[146,-18,194]),box([5,28,43],[133,-18,215.5]),box([36,28,4],[148,-18,237.5]))
    add('gripper-motor-cradle',mount,'tool-roll',spec='PA12-CF gripper servo cradle under palm')
    touch('gripper-motor-cradle','gripper-motor');touch('gripper-motor-cradle','gripper-palm')
    for i,x in enumerate([133,162]):
        bolt(f'gripper-palm-{i+1}-bolt',3,12,[x,-12,245],(0,0,-1),'tool-roll',
             ['gripper-motor-cradle','gripper-palm'],nut=True)
    add('gripper-motor-cap',box([4,28,38],[158,-18,214]),'tool-roll',spec='PA12-CF split clamp cap')
    touch('gripper-motor-cap','gripper-motor')
    for i,z in enumerate([194,235]):
        bolt(f'gripper-clamp-{i+1}-bolt',3,32,[160,-28,z],(-1,0,0),'tool-roll',['gripper-motor-cap','gripper-motor-cradle'],nut=True)
    hp,d=horn('gripper-horn','330',c+[0,-2.5,0],(0,1,0),'grip','gripper-motor')
    # Pair of identical involute gears, one half-tooth shifted at home.
    for side,x,owner,phase in [('left',146,'grip',0),('right',174,'jaw-r',math.pi/28)]:
        gear=extrude_polygon(gear_profile(phase=phase),5)
        T=trimesh.geometry.align_vectors([0,0,1],[0,1,0]);T[:3,3]=[x,2,221];gear.apply_transform(T)
        gear=cut(gear,cyl(2.6,10,[x,2,221],(0,1,0),20))
        # Finger web attaches below the gear, away from the engaged teeth at +/-x.
        finger=box([7,9,28],[x,6,197.5])
        root=box([7,9,13],[x,6,211])
        gear=union(gear,finger,root)
        gear=cut(gear,cyl(2.6,20,[x,5,221],(0,1,0),20))
        if side=='left': gear=plate_holes(gear,[[p[0],2,p[2]] for p in hp],1.15,14)
        add('gripper-jaw-'+side,gear,owner,spec='PA12-CF m1 28T 20-degree involute gear + 41 mm finger; 0.2 mm backlash',print_rotation=(90,0,0))
        # TPU shoe nests onto finger's lower end with two retaining ribs.
        pad=box([3,12,16],[x+(5 if side=='left' else -5),6,188])
        add('gripper-pad-'+side,pad,owner,'pad','rubber','TPU 95A pad, cyanoacrylate bond; mu >=0.5 assumed')
        touch('gripper-jaw-'+side,'gripper-pad-'+side)
    touch('gripper-jaw-left','gripper-jaw-right')
    touch('gripper-horn','gripper-jaw-left')
    for i,p in enumerate(hp): bolt(f'gripper-horn-{i+1}-bolt',2,8,[p[0],4.5,p[2]],(0,-1,0),'grip',['gripper-horn','gripper-jaw-left'])
    # Follower fixed 5 mm axle in two ears; flanged 5x10x4 bearings in jaw.
    support=union(box([9,6,24],[174,-7,231]),box([9,6,24],[174,15,231]),box([9,28,5],[174,4,239]))
    support=plate_holes(support,[[174,4,221]],2.6,40)
    add('jaw-idler-clevis',support,'tool-roll',spec='PA12-CF double-supported follower pivot')
    touch('jaw-idler-clevis','gripper-palm')
    add('jaw-idler-axle',cyl(2.5,32,[174,4,221],(0,1,0),20),'tool-roll','hardware','steel','5 mm h6 ground axle')
    touch('jaw-idler-axle','jaw-idler-clevis')
    # Seat is independent of the teeth, cut through the central hub only.
    p=PARTS['gripper-jaw-right']; m=p['mesh'].copy();m.apply_translation(p['origin'])
    m=cut(m,cyl(5.05,8,[174,2,221],(0,1,0),24));m.apply_translation(-p['origin']);p['mesh']=m;p['mass_g']=m.volume*.0012
    bearing('jaw-105',5,10,4,[174,2,221],(0,1,0),'gripper-jaw-right','jaw-idler-axle','jaw-r','tool-roll')
    # Guard leaves 1 mm axial clearance from the gear faces; no hand access to mesh.
    guard=cut(box([64,3,34],[160,19,221]),box([45,5,34],[160,19,210]))
    add('gear-guard',guard,'tool-roll',spec='PA12-CF rear gear guard; open bottom for fingers')
    touch('gear-guard','jaw-idler-clevis')

def lower_tool():
    # 20 mm extra pitch-to-roll standoff clears the pitch servo through useful travel.
    for pid,p in PARTS.items():
        if p['owner'] in ['tool-roll','grip','jaw-r'] or pid.startswith(('roll-motor','roll-clamp','roll-retainer')):
            p['origin'][2]-=20

def finish_mating_features():
    """Machine the static assembly interfaces into the printable parts.

    Captured nuts, motor/connector reliefs and intersecting mounting tabs become
    real negative space in the exported STL. This never excludes a moving pair.
    Every removed interface is recorded for inspection, with its actual volume.
    """
    records=[]
    def world(pid):
        p=PARTS[pid];m=p['mesh'].copy();m.apply_translation(p['origin']);return m
    def overlaps(a,b):return np.all(a.bounds[1]>b.bounds[0]+1e-5) and np.all(b.bounds[1]>a.bounds[0]+1e-5)
    for pid,p in PARTS.items():
        if p['category']!='printed':continue
        m=world(pid)
        # Purchased components and fastening hardware have geometry priority.
        for qid,q in PARTS.items():
            if q['owner']!=p['owner'] or q['category'] in ['printed','pad'] or qid==pid:continue
            n=world(qid)
            if not overlaps(m,n):continue
            # Only cutter geometries actually overlapping the target are applied.
            inter=trimesh.boolean.intersection([m,n],engine='manifold')
            if inter.is_empty or inter.volume<.005:continue
            # 0.15 mm fit clearance for bearings/connectors/motor and hardware.
            expand=np.maximum(n.extents,.1)
            n.vertices=(n.vertices-n.bounds.mean(axis=0))*(1+.30/expand)+n.bounds.mean(axis=0)
            candidate=cut(m,n)
            if candidate.is_empty:raise ValueError('Relief erased '+pid)
            records.append({'part':pid,'mate':qid,'removed_mm3':round(float(m.volume-candidate.volume),3)})
            m=candidate;touch(pid,qid)
        # Later printed pieces seat against earlier ones rather than interpenetrating.
        for qid,q in PARTS.items():
            if qid==pid:break
            if q['owner']!=p['owner'] or q['category']!='printed':continue
            n=world(qid)
            if not overlaps(m,n):continue
            inter=trimesh.boolean.intersection([m,n],engine='manifold')
            if inter.is_empty or inter.volume<.005:continue
            candidate=cut(m,n)
            if candidate.is_empty:raise ValueError('Seat erased '+pid)
            records.append({'part':pid,'mate':qid,'removed_mm3':round(float(m.volume-candidate.volume),3)})
            m=candidate;touch(pid,qid)
        # Remove detached machining chips below 0.5 mm³, never structural islands.
        chunks=m.split(only_watertight=False)
        if len(chunks)>1:
            large=[x for x in chunks if x.volume>.5]
            if len(large)!=1:raise ValueError(f'{pid}: relief disconnected {[(len(x.faces),round(x.volume,3)) for x in large]}')
            m=large[0]
        m.apply_translation(-p['origin']);p['mesh']=m;p['mass_g']=float(m.volume*.0012)
    (ROOT/'mating-features.json').write_text(json.dumps(records,indent=2)+'\n')

def build_cables():
    # Each jacket is a rigid retained run. Flexible spans crossing joints are
    # intentionally NOT represented as rigid rods that would constrain motion.
    runs=[('base-harness',None,[[-45,46,25],[-30,46,30],[-2,25,25]],'hub-jst-plug-3'),
          ('upper-harness','shoulder',[[18,-35,174],[18,-35,240],[18,-30,245]],'upper-link-left'),
          ('forearm-harness','elbow',[[35,-24,310],[112,-24,310]],'forearm-link-left'),
          ('wrist-harness','wrist',[[178,-33,281],[178,-33,261]],'wrist-yoke-left')]
    for pid,owner,pts,mate in runs:
        m=union(*(rod(a,b,1.6) for a,b in zip(pts,pts[1:])))
        add(pid,m,owner,'cable','cable','3-core silicone jacket, fixed run; 50-80 mm loose service loops at pivots')
        touch(pid,mate)
        for i,p in enumerate([pts[0],pts[-1]]):
            add(pid+f'-plug-{i+1}',box([8,7,5],p),owner,'electronics','plug','JST X3P cable plug; keyed, crimped',mass=.8)
            touch(pid,pid+f'-plug-{i+1}')

def joints():
    data=[('yaw',None,G.YAW_ORIGIN,(0,0,1),0,G.YAW_LIMITS,'Base yaw'),
          ('shoulder','yaw',G.SHOULDER_ORIGIN,(0,-1,0),90,G.SHOULDER_LIMITS,'Shoulder elevation'),
          ('elbow','shoulder',G.ELBOW_ORIGIN,(0,-1,0),-90,G.ELBOW_LIMITS,'Elbow bend'),
          ('wrist','elbow',G.WRIST_ORIGIN,(0,-1,0),-90,G.WRIST_LIMITS,'Wrist pitch'),
          ('tool-roll','wrist',G.ROLL_ORIGIN,(0,0,-1),0,G.ROLL_LIMITS,'Tool roll'),
          ('grip','tool-roll',G.JAW_LEFT_ORIGIN,(0,1,0),0,G.JAW_LIMITS,'Gripper drive'),
          ('jaw-r','tool-roll',G.JAW_RIGHT_ORIGIN,(0,1,0),0,(-25,10),'Geared right jaw')]
    out=[]
    for jid,parent,origin,axis,home,limits,label in data:
        j=dict(id=jid,type='revolute',parent=parent,origin=list(origin),axis=list(axis),
               parts=[pid for pid,p in PARTS.items() if p['owner']==jid],home=home,limits=list(limits),label=label)
        if jid=='jaw-r':j['coupled']=[dict(joint='grip',ratio=-1.0)]
        out.append(j)
    return out

POSES=[
    {'name':'home','values':{'yaw':0,'shoulder':90,'elbow':-90,'wrist':-90,'tool-roll':0,'grip':0}},
    {'name':'reach-310mm','values':{'yaw':0,'shoulder':20,'elbow':-20,'wrist':-90,'tool-roll':0,'grip':0}},
    {'name':'table-pick','values':{'yaw':25,'shoulder':45,'elbow':-85,'wrist':-50,'tool-roll':0,'grip':-8}},
    {'name':'stowed','values':{'yaw':0,'shoulder':100,'elbow':-120,'wrist':-70,'tool-roll':0,'grip':-8}},
    {'name':'handoff','values':{'yaw':-60,'shoulder':65,'elbow':-75,'wrist':-80,'tool-roll':30,'grip':5}},
]

def export_glb():
    buf=bytearray();views=[];access=[];meshes=[];nodes=[]
    root={'name':'assembly','rotation':[-0.7071068,0,0,0.7071068],'children':list(range(1,len(PARTS)+1))}
    nodes.append(root)
    materials=[]
    for name,color in COLORS.items():
        materials.append({'name':name,'pbrMetallicRoughness':{'baseColorFactor':list(color),
             'metallicFactor':.75 if name in ['steel','aluminum','brass'] else 0.,'roughnessFactor':.4 if name=='steel' else .68},'doubleSided':False})
    def append(a,kind,component,target):
        while len(buf)%4:buf.append(0)
        offset=len(buf);raw=a.tobytes(order='C');buf.extend(raw)
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(raw),'target':target})
        entry={'bufferView':len(views)-1,'componentType':component,'count':len(a),'type':kind}
        if kind=='VEC3':entry.update(min=a.min(axis=0).tolist(),max=a.max(axis=0).tolist())
        access.append(entry);return len(access)-1
    for pid,p in PARTS.items():
        m=p['mesh'];v=(m.vertices*.001).astype('<f4');f=m.faces.astype('<u4').reshape(-1)
        vi=append(v,'VEC3',5126,34962);ni=append(m.vertex_normals.astype('<f4'),'VEC3',5126,34962);fi=append(f,'SCALAR',5125,34963)
        meshes.append({'name':pid,'primitives':[{'attributes':{'POSITION':vi,'NORMAL':ni},'indices':fi,'material':list(COLORS).index(p['material']),'mode':4}]})
        nodes.append({'name':pid,'mesh':len(meshes)-1,'translation':(p['origin']*.001).tolist(),
            'rotation':[0,0,0,1],'extras':{'category':p['category'],'specification':p['spec'],'mass_g':round(p['mass_g'],5)}})
    doc={'asset':{'version':'2.0','generator':'Aster 320 deterministic generator / Python 3.11'},'scene':0,'scenes':[{'nodes':[0]}],
         'nodes':nodes,'meshes':meshes,'materials':materials,'accessors':access,'bufferViews':views,'buffers':[{'byteLength':len(buf)}]}
    raw=json.dumps(doc,separators=(',',':'),ensure_ascii=True).encode();raw+=b' '*((-len(raw))%4);buf+=b'\0'*((-len(buf))%4)
    output=struct.pack('<III',0x46546c67,2,12+8+len(raw)+8+len(buf))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(buf),0x004e4942)+buf
    (ROOT/'assembly.glb').write_bytes(output)
    return hashlib.sha256(output).hexdigest()

def export_stls():
    folder=ROOT/'stl';folder.mkdir(exist_ok=True)
    for p in folder.glob('*.stl'):
        if p.stem not in PARTS:p.unlink()
    records=[]
    for pid,p in PARTS.items():
        if p['category'] not in ['printed','pad']: continue
        m=p['mesh'].copy();m.apply_transform(trimesh.transformations.euler_matrix(*np.radians(p['print_rotation'])))
        m.apply_translation([-m.bounds.mean(axis=0)[0],-m.bounds.mean(axis=0)[1],-m.bounds[0,2]])
        (folder/(pid+'.stl')).write_bytes(trimesh.exchange.stl.export_stl(m))
        records.append({'part':pid,'file':'stl/'+pid+'.stl','material':'TPU 95A' if p['category']=='pad' else 'PA12-CF',
            'size_mm':[round(float(x),3) for x in m.extents],'solid_mass_g':round(float(p['mass_g']),2),'quantity':1})
    (ROOT/'print-manifest.yaml').write_text(yaml.safe_dump({'units':'mm','parts':records},sort_keys=False))

def export_bom():
    out=io.StringIO();w=csv.writer(out,lineterminator='\n')
    w.writerow(['part_id','quantity','category','owner_joint','specification','mass_g','source'])
    for pid,p in PARTS.items():
        src='generated STL' if p['category'] in ['printed','pad'] else 'see DESIGN.md supplier references'
        w.writerow([pid,1,p['category'],p['owner'] or 'ground',p['spec'],f'{p["mass_g"]:.3f}',src])
    (ROOT/'bom.csv').write_text(out.getvalue())

def main():
    if sys.version_info[:2] != (3,11):
        raise SystemExit('Use Python 3.11 to preserve the validated build environment.')
    PARTS.clear();CONTACT.clear()
    build_base();build_arm();build_gripper();build_cables();lower_tool();finish_mating_features()
    sha=export_glb()
    (ROOT/'joints.yaml').write_text(yaml.safe_dump({'glb_sha256':sha,'joints':joints(),'poses':POSES},sort_keys=False))
    (ROOT/'assembly.yaml').write_text(yaml.safe_dump({'allow_contact':[list(p) for p in sorted(CONTACT)]},sort_keys=False))
    export_stls();export_bom()
    from validate import validate
    report=validate(ROOT,write=True)
    from check_motion import check_motion
    check_motion(ROOT)
    from deliverables import render,write_design
    render(ROOT,PARTS,joints(),POSES,report)
    write_design(ROOT,PARTS,report)
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.rglob('*')) if p.is_file() and p.suffix not in ['.py','.pyc']
        and p.name not in ['manifest.sha256.json'] and '__pycache__' not in p.parts}
    (ROOT/'manifest.sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['part_count','joint_count','triangle_count','glb_sha256']},indent=2))

if __name__=='__main__':main()
