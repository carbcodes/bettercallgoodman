#!/usr/bin/env python3.11
"""Deterministic, millimetre-native folding quadcopter assembly generator.
Python 3.11; run beside requirements.txt. All outputs are written beside this file.
"""
from pathlib import Path
import ast
import csv
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import zipfile
from itertools import combinations
import numpy as np
import scipy
from scipy.spatial.transform import Rotation
import trimesh
import yaml

HERE = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', '/tmp/backpack-drone-matplotlib')
PARTS = {}
JOINTS = []
CONTACT = set()
COLORS = {
    'carbon': (0.105, .14, .17, 1), 'shell': (.69, .76, .75, 1),
    'orange': (.98, .31, .10, 1), 'steel': (.58, .64, .69, 1),
    'black': (.075, .085, .095, 1), 'bronze': (.65, .43, .20, 1),
    'copper': (.72, .34, .15, 1), 'pcb': (.07, .35, .29, 1),
    'cream': (.86, .84, .70, 1), 'yellow': (.95, .70, .08, 1),
    'red': (.72, .08, .10, 1), 'blue': (.09, .39, .60, 1),
}
N = 24


def move(m, xyz):
    m = m.copy()
    m.apply_translation(xyz)
    return m


def rz(deg):
    return Rotation.from_euler('z', deg, degrees=True).as_matrix()


def box(size, xyz=(0, 0, 0)):
    return move(trimesh.creation.box(size), xyz)


def cyl(r, h, xyz=(0, 0, 0), n=N):
    return move(trimesh.creation.cylinder(r, h, sections=n), xyz)


def union(*meshes):
    return trimesh.boolean.union(list(meshes), engine='manifold')


def cut(mesh, *holes):
    return trimesh.boolean.difference([mesh, *holes], engine='manifold')


def ring(ro, ri, h, xyz=(0, 0, 0), n=N):
    return move(trimesh.creation.annulus(ri, ro, h, sections=n), xyz)


def segment(a, b, r, n=10):
    a, b = np.array(a, float), np.array(b, float)
    return trimesh.creation.cylinder(r, segment=np.array([a, b]), sections=n)


def wire(points, r=.55):
    return union(*[segment(a, b, r) for a, b in zip(points[:-1], points[1:])],
                 *[move(trimesh.creation.icosphere(subdivisions=1, radius=r), p) for p in points[1:-1]])


def plate(size, holes):
    return cut(box(size), *[cyl(r, size[2]+2, (x, y, 0), 16) for x, y, r in holes])


def bolt(d, length, head=None):
    head = head or d * 1.75
    return union(cyl(d/2, length, (0, 0, length/2)),
                 cut(cyl(head/2, d*.7, (0, 0, -d*.35), 18),
                     cyl(d*.31, d*.5, (0, 0, -d*.6), 6)))


def nut(d):
    return cut(cyl(d*.96, d*.8, n=6), cyl(d*.46, d*1.5, n=18))


def part(pid, mesh, xyz=(0, 0, 0), color='steel', rot=None, joint=None,
         spec='', material='', category='custom', mass=None):
    assert re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', pid) and pid not in PARTS
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh, multibody=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0, pid
    R = np.eye(3) if rot is None else np.array(rot)
    PARTS[pid] = dict(mesh=mesh, xyz=np.array(xyz, float), R=R, color=color,
                      joint=joint, spec=spec, material=material, category=category, mass=mass)
    return pid


def contact(a, *others):
    for b in others:
        if a != b:
            CONTACT.add(tuple(sorted((a, b))))


def joint(jid, parent, origin, axis, limits, label, home=0, coupled=None):
    j = dict(id=jid, type='revolute', parent=parent, origin=list(origin), axis=list(axis),
             parts=[], home=home, limits=list(limits), label=label)
    if coupled:
        j['coupled'] = coupled
    JOINTS.append(j)


def make_body():
    holes = [(x,y,1.1) for x in [-30,30] for y in [-16,16]]
    holes += [(x,y,1.1) for x in [-10,10] for y in [-10,10]]
    part('lower-deck', plate((76,40,2),holes), (0,0,21), 'carbon',
         spec='CNC carbon fibre 76 x 40 x 2; M2 clearances',material='carbon fibre')
    part('upper-deck', plate((76,40,1.5),holes[:4]), (0,0,48), 'carbon',
         spec='CNC carbon fibre 76 x 40 x 1.5',material='carbon fibre')
    for i,(x,y,_) in enumerate(holes[:4]):
        stem = f'deck-{i+1}'
        part(stem+'-spacer', ring(2.5,1,25.25), (x,y,34.625), 'orange', spec='M2 female 25.25 mm spacer',material='aluminium')
        part(stem+'-bolt-lower', bolt(2,5), (x,y,20), spec='M2 x 5 socket screw',category='hardware')
        part(stem+'-bolt-upper', bolt(2,5), (x,y,48.75), rot=Rotation.from_euler('x',180,degrees=True).as_matrix(), spec='M2 x 5 socket screw',category='hardware')
        contact(stem+'-spacer','lower-deck','upper-deck',stem+'-bolt-lower',stem+'-bolt-upper')
        contact(stem+'-bolt-lower','lower-deck'); contact(stem+'-bolt-upper','upper-deck')
    # Battery under the deck. Published Tattu 650 3S 75C envelope: 58 x 31 x 16 mm.
    part('battery-3s-650mah', box((58,31,16)), (-3,0,11), 'black', spec='Tattu 650mAh 3S 75C, 58 x 31 x 16, XT30',category='purchased',mass=59)
    part('battery-foam-pad', box((58,31,1)), (-3,0,19.5), 'black',spec='1 mm silicone isolation pad')
    contact('battery-foam-pad','battery-3s-650mah','lower-deck')
    strap = cut(box((9,35,22)), box((11,32,19.5)))
    part('battery-strap', strap, (-3,0,12), 'orange',spec='9 mm hook-and-loop wrap, buckle omitted',material='nylon')
    contact('battery-strap','battery-3s-650mah','lower-deck','battery-foam-pad')
    for side,y in [('left',-20),('right',20)]:
        foot = union(box((66,4,3),(0,0,1.5)),box((5,4,18),(-28,0,11)),box((5,4,18),(28,0,11)))
        part('landing-skid-'+side,foot,(0,y,0),'black',spec='TPU skid with two 18 mm legs',material='TPU')
        contact('landing-skid-'+side,'lower-deck')
    # Protective longitudinal side panels, with actual windows for wiring/cooling.
    for side,y in [('left',-19.5),('right',19.5)]:
        m=box((70,1.2,22))
        for x in [-24,-12,0,12,24]:
            m=cut(m,box((7,4,10),(x,0,0)))
        part('side-panel-'+side,m,(0,y,34),'shell',spec='1.2 mm PA12 vented panel',material='PA12')
        contact('side-panel-'+side,'lower-deck','upper-deck')
    # Stack with 20 mm grommet pattern, 1.6 mm boards and realistic separate components.
    for name,z,size,hole in [('esc',26,(35,30,1.6),1.8),('fc',35,(30,32,1.6),1.75)]:
        pid='speedybee-'+name+'-pcb'
        part(pid,plate(size,[(x,y,hole) for x in [-10,10] for y in [-10,10]]),(0,0,z),'pcb',
             spec='SpeedyBee F405 Mini / BLS 35A Mini V2; 20 x 20 mount',category='purchased')
        for i,(x,y) in enumerate([(x,y) for x in [-10,10] for y in [-10,10]]):
            g=f'{name}-grommet-{i+1}'
            part(g,ring(2.5,1.05,3),(x,y,z),'black',spec='M2 silicone soft mounting grommet',category='hardware')
            contact(g,pid)
        if name=='esc':
            for i in range(8):
                c=f'esc-mosfet-{i+1}'
                part(c,box((4,3,1.3)),(-12+(i%4)*8,-4+(i//4)*8,z+1.45),'black',spec='Simplified power MOSFET package',category='purchased')
                contact(c,pid)
        else:
            for c,size2,pos in [('mcu',(7,7,1.2),(0,0,z+1.4)),('imu',(3,3,1),(7,4,z+1.3)),('barometer',(3,3,1),(5,-5,z+1.3))]:
                part(c,box(size2),pos,'black',spec='Electronic package envelope',category='purchased');contact(c,pid)
            usb=cut(box((7.5,5,3)),box((5.7,6,1.6),(0,.5,0)))
            part('usb-c-shell',usb,(0,-17,37),'steel',spec='USB-C receptacle shell',category='purchased');contact('usb-c-shell',pid)
    for i,(x,y) in enumerate([(x,y) for x in [-10,10] for y in [-10,10]]):
        n=f'stack-{i+1}'
        part(n+'-bolt',bolt(2,20),(x,y,20),'steel',spec='M2 x 20 stack screw',category='hardware')
        for key,z,h in [('lower',23.5,3),('middle',30.5,6)]:
            part(n+'-spacer-'+key,ring(2,1.05,h),(x,y,z),'black',spec='M2 nylon stack spacer',category='hardware')
        part(n+'-nut',nut(2),(x,y,38),'steel',spec='M2 nylon-lock nut envelope',category='hardware')
        contact(n+'-bolt',n+'-nut',n+'-spacer-lower',n+'-spacer-middle',f'fc-grommet-{i+1}',f'esc-grommet-{i+1}','lower-deck')
        contact(n+'-spacer-lower','lower-deck',f'esc-grommet-{i+1}')
        contact(n+'-spacer-middle',f'esc-grommet-{i+1}',f'fc-grommet-{i+1}')
        contact(n+'-nut',f'fc-grommet-{i+1}')
    for name,z in [('esc',28),('fc',33)]:
        p=f'{name}-sh8-socket'
        part(p,box((9,3,2)),(-7,12,z),'cream',spec='JST-SH 1.0 mm eight-pin socket',category='purchased')
        contact(p,'speedybee-'+name+'-pcb')
    part('fc-esc-harness',wire([(-7,13,28),(-7,16,29),(-7,16,32),(-7,13,33)],1),color='black',spec='8-pin flexible silicone harness; home shape',category='purchased')
    contact('fc-esc-harness','esc-sh8-socket','fc-sh8-socket')
    part('xt30-airframe',box((10,8,6)),(-32,0,29),'yellow',spec='AMASS XT30 mating shell envelope',category='purchased')
    part('xt30-battery',box((10,8,6)),(-42,0,29),'yellow',spec='AMASS XT30 mating plug envelope',category='purchased')
    contact('xt30-airframe','xt30-battery')
    for i,col in enumerate(['red','black']):
        y=(-1 if i==0 else 1)*2
        part('power-lead-'+col,wire([(-28,y,29),(-22,y,29),(-17,y,27)],.8),color=col,spec='20AWG silicone wire',category='purchased')
        contact('power-lead-'+col,'xt30-airframe','speedybee-esc-pcb')
        part('battery-lead-'+col,wire([(-46,y,29),(-48,y,22),(-37,y,11),(-32,y,11)],.8),color=col,spec='20AWG silicone battery lead',category='purchased')
        contact('battery-lead-'+col,'xt30-battery','battery-3s-650mah')
    part('balance-jst-xh4',box((11,6,5)),(-34,12,13),'cream',spec='JST-XH 2.54 mm four-pin 3S balance plug',category='purchased')
    part('balance-harness',wire([(-31,10,11),(-36,10,12),(-34,12,13)],1),color='black',spec='3S balance harness',category='purchased');contact('balance-harness','balance-jst-xh4','battery-3s-650mah')
    part('receiver-ep2-pcb',box((10,10,1)),(-24,0,39),'pcb',spec='HappyModel EP2 ELRS receiver 10 x 10 mm nominal envelope',category='purchased')
    part('receiver-ceramic-antenna',box((3,8,2)),(-25,0,40.5),'cream',spec='2.4 GHz integrated antenna envelope',category='purchased');contact('receiver-ceramic-antenna','receiver-ep2-pcb')
    part('receiver-foam',box((10,10,2)),(-24,0,37.5),'black',spec='Foam mounting pad')
    part('receiver-shelf',box((12,12,1)),(-24,0,36),'shell',spec='PA12 receiver shelf bonded to side panel',material='PA12')
    part('receiver-shelf-bracket',box((3,13,1)),(-27,-12,36),'shell',spec='PA12 shelf support',material='PA12')
    contact('receiver-shelf','receiver-foam','receiver-shelf-bracket');contact('receiver-foam','receiver-ep2-pcb');contact('receiver-shelf-bracket','side-panel-left')
    # GNSS envelope; compass deliberately not used at this spacing to motors and ESC.
    part('gps-mount',box((22,22,2)),(-22,0,49.75),'black',spec='Silicone GNSS isolation pad')
    part('gps-pcb',box((20,20,1)),(-22,0,52.25),'pcb',spec='Matek M10Q-5883, 20 x 20 x 12.4 overall',category='purchased')
    part('gps-shield',box((16,16,3.5)),(-22,0,55),'steel',spec='GNSS receiver shield envelope',category='purchased')
    part('gps-patch',box((15,15,4)),(-22,0,60.15),'cream',spec='15 x 15 x 4 ceramic GNSS patch',category='purchased')
    part('gps-patch-spacer',box((15,15,1.4)),(-22,0,57.45),'black',spec='GNSS internal stack envelope',category='purchased')
    contact('gps-mount','upper-deck','gps-pcb');contact('gps-pcb','gps-shield');contact('gps-shield','gps-patch-spacer');contact('gps-patch-spacer','gps-patch')
    part('gps-gh6-plug',box((9,4,3)),(-22,10,54),'cream',spec='JST-GH 6 pin, 1.25 mm nominal pitch',category='purchased');contact('gps-gh6-plug','gps-pcb')
    part('gps-harness',wire([(-22,12,54),(-12,15,54),(1,17,51),(1,17,40),(5,12,37)],.75),color='black',spec='Flexible six-wire GNSS harness',category='purchased')
    contact('gps-harness','gps-gh6-plug','speedybee-fc-pcb','upper-deck')
    part('status-led',box((4,2,1)),(16,0,49.25),'orange',spec='Status light lens on top deck');contact('status-led','upper-deck')


ARM_INFO = []

def make_arm(tag,sx,sy,z):
    O=np.array([sx*28,sy*30,z],float)
    end=np.array([sx*65,sy*65,z],float)
    vec=end-O; L=float(np.linalg.norm(vec[:2])); theta=math.degrees(math.atan2(vec[1],vec[0]))
    fold_end=np.array([-sx*math.sqrt(L*L-12*12),sy*12,0])
    target=math.degrees(math.atan2(fold_end[1],fold_end[0]))
    fold=(target-theta+180)%360-180
    jid='fold-'+tag; spin='rotor-'+tag
    joint(jid,None,O.tolist(),[0,0,1],sorted([0,float(fold)]),'Fold '+tag.upper())
    joint(spin,jid,[float(end[0]),float(end[1]),z+10],[0,0,1],[-180,180],'Motor phase '+tag.upper())
    ARM_INFO.append(dict(tag=tag,origin=O.tolist(),end=end.tolist(),fold=fold,length=L,theta=theta,z=z))
    R=rz(theta)
    def arm_part(name,m,xyz=(0,0,0),color='steel',sp=False,**kw):
        return part(tag+'-'+name,m,O+R@np.array(xyz),color,rot=R,joint=spin if sp else jid,**kw)
    # Carbon arm with real through-holes at its root and motor flange.
    m=union(cyl(6,4),box((L-4,8,4),((L+4)/2,0,0)),cyl(10.5,4,(L,0,0)))
    holes=[cyl(3,8),cyl(2.1,8,(L,0,0))]
    for angle in [0,90,180,270]:
        a=math.radians(angle);holes.append(cyl(1.1,8,(L+4.5*math.cos(a),4.5*math.sin(a),0),16))
    arm_part('arm',cut(m,*holes),color='carbon',spec=f'4 mm CF arm, {L:.4f} mm pivot-to-motor; M2 on 9 mm PCD',material='carbon fibre')
    arm_part('bushing',union(ring(3,1.55,4),ring(4,1.55,.5,(0,0,-2.25)),ring(4,1.55,.5,(0,0,2.25))),color='bronze',spec='Custom flanged bronze bush 3.1 ID / 6 OD, 4 mm journal',material='bronze')
    contact(tag+'-arm',tag+'-bushing')
    # Static clevis: 2.5 mm lower stop plate; 2.5 mm upper ear; inward connecting web.
    clevis=union(cyl(16,2.5,(0,0,-3.75)),cyl(8,2.5,(0,0,3.75)),box((13,7,12),(0,-sy*10,0)))
    clevis=cut(clevis,cyl(1.55,16))
    part(tag+'-clevis',clevis,O,'shell',spec='CNC 6061-T6 double-shear hinge bracket with lower stop flange',material='6061-T6')
    # Join the hinge to the chassis at the inward web.
    root_bottom=20 if sx>0 else 46
    attach=box((13,10,z+6-root_bottom),(sx*28,sy*19,(z+6+root_bottom)/2))
    part(tag+'-mount',attach,color='shell',spec='PA12/6061 frame-to-hinge saddle',material='6061-T6')
    contact(tag+'-mount',tag+'-clevis','lower-deck' if sx>0 else 'upper-deck','side-panel-'+('right' if sy>0 else 'left'))
    for k,xx in enumerate([-4,4]):
        # Mount screws lie outside the arm sweep, in the inboard saddle.
        p=(sx*28+xx,sy*19,z+6)
        part(tag+f'-mount-screw-{k+1}',bolt(2,6),p,rot=Rotation.from_euler('x',180,degrees=True).as_matrix(),spec='M2 x 6 bracket screw',category='hardware')
        contact(tag+f'-mount-screw-{k+1}',tag+'-mount',tag+'-clevis')
    part(tag+'-shoulder-axle',bolt(3,12),O+[0,0,-5],'steel',spec='M3 shoulder axle, 3 mm smooth journal; simplified thread',category='hardware')
    part(tag+'-locknut',nut(3),O+[0,0,6.2],'steel',spec='M3 Nyloc nut; preload/friction lock',category='hardware')
    contact(tag+'-shoulder-axle',tag+'-bushing',tag+'-clevis',tag+'-locknut')
    contact(tag+'-locknut',tag+'-clevis');contact(tag+'-bushing',tag+'-clevis')
    # Stop pins are tangential to the arm flanks at each mechanical endpoint.
    margin=math.degrees(math.asin(5.5/13))
    sign=1 if fold>0 else -1
    for key,a in [('deployed',theta-sign*margin),('stowed',theta+fold+sign*margin)]:
        rad=math.radians(a);p=O+[13*math.cos(rad),13*math.sin(rad),.5]
        part(tag+'-stop-'+key,cyl(1.5,6),p,'steel',spec='3 mm dowel travel stop press-fit into clevis',category='hardware')
        contact(tag+'-stop-'+key,tag+'-clevis',tag+'-arm')
    # EX1404 nominal 17.8 diameter; 12.2 housing height above arm; shaft to 17.6.
    mount=cut(cyl(7,2),cyl(2,5),*[cyl(1,5,(4.5*math.cos(math.radians(a)),4.5*math.sin(math.radians(a)),0),16) for a in [0,90,180,270]])
    arm_part('motor-base',mount,(L,0,3),'steel',spec='HappyModel EX1404 4800KV, 3S, base envelope',category='purchased')
    arm_part('stator',ring(7,3,4),(L,0,6),'copper',spec='EX1404 stator envelope 14 x 4; winding detail omitted',category='purchased')
    arm_part('bearing-tube',ring(2.5,2,7),(L,0,6),'steel',spec='Motor fixed bearing housing envelope',category='purchased')
    for key,zz in [('lower',3.8),('upper',9)]:
        arm_part('bearing-'+key,ring(2,.75,2),(L,0,zz),'steel',spec='Nominal 1.5 x 4 x 2 bearing envelope; verify vendor internals',category='purchased')
        contact(tag+'-bearing-'+key,tag+'-bearing-tube',tag+'-motor-shaft')
    bell=union(ring(8.9,7.5,8,(0,0,-1)),ring(8.9,.75,1.2,(0,0,3.6)))
    arm_part('motor-bell',bell,(L,0,10),'black',sp=True,spec='EX1404 17.8 OD outrunner bell, simplified sealed skin',category='purchased')
    arm_part('motor-shaft',cyl(.75,17.6),(L,0,10.8),'steel',sp=True,spec='1.5 mm steel motor shaft envelope',category='purchased')
    contact(tag+'-motor-bell',tag+'-motor-shaft');contact(tag+'-stator',tag+'-motor-base',tag+'-bearing-tube');contact(tag+'-motor-base',tag+'-arm',tag+'-bearing-tube')
    for i,a in enumerate([0,90,180,270]):
        ar=math.radians(a)
        arm_part(f'motor-screw-{i+1}',bolt(2,6),(L+4.5*math.cos(ar),4.5*math.sin(ar),-2),'steel',spec='M2 x 6 motor screw, 4 mm arm + 2 mm engagement',category='hardware')
        contact(tag+f'-motor-screw-{i+1}',tag+'-arm',tag+'-motor-base')
    # An explicit solid blade profile, with spanwise twist and a bored T-mount hub.
    handed=1 if sx*sy>0 else -1
    prop=propeller(handed)
    # Props are parked along assembly X at home; their node frame is independent of arm yaw.
    part(tag+'-propeller',prop,end+[0,0,16.7], 'orange' if sx>0 else 'black',joint=spin,
         spec='HQProp T65 two-blade, 65 mm dia, 38.1 mm pitch; envelope blade profile',category='purchased')
    contact(tag+'-propeller',tag+'-motor-shaft',tag+'-motor-bell')
    for i,xx in enumerate([-2.5,2.5]):
        part(tag+f'-prop-screw-{i+1}',bolt(1.6,5),(end[0]+xx,end[1],z+19.2),'steel',rot=Rotation.from_euler('x',180,degrees=True).as_matrix(),joint=spin,spec='M1.6 x 5 T-mount screw',category='hardware')
        contact(tag+f'-prop-screw-{i+1}',tag+'-propeller',tag+'-motor-bell')
    for k,col in enumerate(['black','blue','red']):
        arm_part('phase-wire-'+col,wire([(11,k*1.1-1.1,3.2),(L-9,k*1.1-1.1,3.2),(L-7,k*1.1-1.1,4.5)],.4),color=col,
                 spec='26 AWG silicone phase wire fixed to arm; flex loop omitted from rigid kinematics',category='purchased')
        contact(tag+'-phase-wire-'+col,tag+'-motor-base',tag+'-arm')
    arm_part('motor-cable-plug',box((5,4,2)),(12,0,4),'cream',spec='JST 1.25 mm 3-pin motor plug envelope; bench-verify current',category='purchased')
    for col in ['black','blue','red']:contact(tag+'-motor-cable-plug',tag+'-phase-wire-'+col)


def propeller(handed):
    hub=ring(4.9,.76,5,n=32)
    blades=[]
    # Hexagonal airfoil sections, closed with end caps; max radius 32.5 mm.
    for sign in [1,-1]:
        verts=[]
        for r,chord,sweep in [(3.8,3.5,0),(8,7.5,.5),(15,9,1),(24,7,1.2),(31.5,3.5,.6),(32.45,.5,0)]:
            pitch=handed*math.atan2(38.1,2*math.pi*r)
            for u,v in [(-.5,0),(-.2,-.45),(.35,-.35),(.5,0),(.25,.45),(-.25,.6)]:
                yy=u*chord;zz=v*.7
                verts.append([sign*r,sign*(sweep+yy*math.cos(pitch)-zz*math.sin(pitch)),yy*math.sin(pitch)+zz*math.cos(pitch)])
        faces=[]
        for j in range(5):
            for k in range(6):
                a=j*6+k;b=j*6+(k+1)%6;c=(j+1)*6+(k+1)%6;d=(j+1)*6+k
                faces += [[a,b,c],[a,c,d]]
        for k in range(1,5):faces += [[0,k+1,k],[30,30+k,30+k+1]]
        m=trimesh.Trimesh(verts,faces,process=True);trimesh.repair.fix_normals(m);blades.append(m)
    return cut(union(hub,*blades),cyl(.85,8,(-2.5,0,0),12),cyl(.85,8,(2.5,0,0),12))


def make_camera():
    O=np.array([63,0,35],float)
    joint('camera-servo',None,O.tolist(),[0,1,0],[-40,40],'Camera servo')
    joint('camera-tilt',None,O.tolist(),[0,1,0],[-20,60],'Camera depression (+down)',home=20,
          coupled=[dict(joint='camera-servo',ratio=1.0)])
    R=Rotation.from_euler('y',20,degrees=True).as_matrix()
    # Thumb Pro in landscape: long axis along Y, lens on +X near +Y end.
    # Case and lens together are within 21 x 54 x 25.5 camera package envelope.
    case=cut(box((17,54,25.5)),box((14,51,22.5)))
    part('camera-case',case,O+R@[-2,0,0],'black',rot=R,joint='camera-tilt',spec='RunCam Thumb Pro W 54 x 25.5 x 21, landscape orientation',category='purchased')
    part('camera-electronics',box((1.6,48,20)),O+R@[-1,0,0],'pcb',rot=R,joint='camera-tilt',spec='Camera internal PCB envelope; approximate',category='purchased')
    Rlens=R@Rotation.from_euler('y',90,degrees=True).as_matrix()
    part('camera-lens-barrel',ring(7,5.5,4),O+R@[8.5,16,0],'black',rot=Rlens,joint='camera-tilt',spec='Camera optical barrel envelope',category='purchased')
    part('camera-lens-glass',cyl(5.45,.8),O+R@[10.1,16,0],'blue',rot=Rlens,joint='camera-tilt',spec='Protective lens glass envelope',category='purchased')
    contact('camera-lens-barrel','camera-case','camera-lens-glass');contact('camera-case','camera-electronics')
    cradle=union(box((20,2,29),(0,-28,0)),box((20,2,29),(0,28,0)),box((2,58,29),(-11,0,0)))
    cradle=cut(cradle,box((5,40,21),(-11,0,0)))
    part('camera-cradle',cradle,O,'orange',rot=R,joint='camera-tilt',spec='PA12 split cradle, 1 mm lateral clearance and 2 mm side cheeks',material='PA12')
    contact('camera-cradle','camera-case')
    for y in [-27.25,27.25]:
        name='camera-pad-'+('left' if y<0 else 'right')
        part(name,box((12,.5,16)),O+R@[0,y,0],'black',rot=R,joint='camera-tilt',spec='0.5 mm compliant camera isolation pad');contact(name,'camera-case','camera-cradle')
    # Frame-mounted Y brackets stay outside the moving camera/cradle.
    for side,sy in [('left',-1),('right',1)]:
        # arm from chassis nose, outside the side cheeks
        bracket=union(box((31,2,10),(-14,sy*31,0)),box((3,15,10),(-28,sy*24.5,0)))
        bearing_hole=cyl(3 if sy<0 else 4.1,5)
        bearing_hole.apply_transform(trimesh.geometry.align_vectors([0,0,1],[0,1,0]))
        bracket=cut(bracket,move(bearing_hole,(0,sy*31,0)))
        part('camera-bracket-'+side,bracket,O,'shell',spec='6061 camera side bracket; 6 mm idler bearing bore',material='6061-T6')
        contact('camera-bracket-'+side,'side-panel-'+side)
    Ry=Rotation.from_euler('x',-90,degrees=True).as_matrix()
    part('camera-idler-bearing',ring(3,1.5,2.5),O+[0,-31,0],'steel',rot=Ry,spec='MR63 bearing 3 x 6 x 2.5',category='hardware')
    part('camera-idler-axle',cyl(1.5,5),O+[0,-29.5,0],'steel',rot=Ry,joint='camera-tilt',spec='3 mm shoulder trunnion',category='hardware')
    contact('camera-idler-bearing','camera-bracket-left','camera-idler-axle');contact('camera-idler-axle','camera-cradle')
    servo_case=box((20,17,8.6),(-5,41,0))
    bore=cyl(2.1,5);bore.apply_transform(trimesh.geometry.align_vectors([0,0,1],[0,1,0]))
    servo_case=cut(servo_case,move(bore,(0,34.5,0)))
    part('tilt-servo-case',servo_case,O,'black',spec='Hitec HS-40 case 20 x 8.6 x 17, output axis +Y',category='purchased',mass=4.8)
    part('servo-mount',box((24,3,8.6)),O+[-5,51,0],'shell',spec='PA12 servo retention strap',material='PA12')
    contact('servo-mount','tilt-servo-case')
    part('servo-mount-foot',box((4,22,8)),O+[-17,42,0],'shell',spec='PA12 servo mounting bridge',material='PA12')
    contact('servo-mount-foot','servo-mount','camera-bracket-right')
    part('servo-output-horn',union(ring(4,1,3),ring(2,1,4,(0,0,3.5))),O+[0,30,0],'black',rot=Ry,joint='camera-servo',spec='Hitec 15T / 4 mm spline horn; keyed to cradle',category='purchased')
    part('servo-horn-screw',bolt(2,4),O+[0,29.5,0],'steel',rot=Ry,joint='camera-servo',spec='M2 servo spline retention screw',category='hardware')
    contact('servo-output-horn','servo-horn-screw','camera-cradle','tilt-servo-case');contact('servo-horn-screw','camera-cradle')
    part('camera-power-plug',box((4,6,3)),O+R@[-9,-17,0],'cream',rot=R,joint='camera-tilt',spec='RunCam 1.25 mm four-pin power/UART plug envelope',category='purchased');contact('camera-power-plug','camera-case')
    part('camera-tail',wire([(-10,-17,0),(-15,-17,-3),(-16,-21,-4)],.6),O,'black',rot=R,joint='camera-tilt',spec='Camera flex tail, moving end only; service loop not rigidly modeled',category='purchased');contact('camera-tail','camera-power-plug')
    part('servo-jr-plug',box((8,3,5)),(25,11,39),'black',spec='3-pin 2.54 mm servo connector envelope',category='purchased')
    part('servo-wire',wire([(57,49,35),(44,48,35),(39,28,39),(25,11,39)],.8),color='black',spec='3-wire servo cable',category='purchased');contact('servo-wire','servo-jr-plug','tilt-servo-case')


def glb_bytes():
    binary=bytearray();views=[];accessors=[];nodes=[dict(name='assembly',rotation=[-.7071068,0,0,.7071068],children=[])];meshes=[]
    mats=[dict(name=k,pbrMetallicRoughness=dict(baseColorFactor=list(v),metallicFactor=.65 if k in ['steel','bronze','copper'] else .05,roughnessFactor=.38 if k=='steel' else .72),doubleSided=False) for k,v in COLORS.items()]
    def accessor(arr,typ,ct):
        arr=np.ascontiguousarray(arr);offset=len(binary);binary.extend(arr.tobytes());binary.extend(b'\0'*(-len(binary)%4))
        views.append(dict(buffer=0,byteOffset=offset,byteLength=arr.nbytes))
        a=dict(bufferView=len(views)-1,componentType=ct,count=len(arr),type=typ)
        if typ=='VEC3':a.update(min=arr.min(axis=0).tolist(),max=arr.max(axis=0).tolist())
        accessors.append(a);return len(accessors)-1
    for pid,p in PARTS.items():
        m=p['mesh'];v=np.array(m.vertices/1000,dtype='<f4');f=np.array(m.faces.reshape(-1),dtype='<u4')
        pos=accessor(v,'VEC3',5126);normal=accessor(np.array(m.vertex_normals,dtype='<f4'),'VEC3',5126);indices=accessor(f,'SCALAR',5125)
        meshes.append(dict(name=pid,primitives=[dict(attributes=dict(POSITION=pos,NORMAL=normal),indices=indices,material=list(COLORS).index(p['color']),mode=4)]))
        nodes.append(dict(name=pid,mesh=len(meshes)-1,translation=(p['xyz']/1000).tolist(),rotation=Rotation.from_matrix(p['R']).as_quat().tolist()))
        nodes[0]['children'].append(len(nodes)-1)
    d=dict(asset=dict(version='2.0',generator='Backpack video drone / deterministic Python 3.11'),scene=0,scenes=[dict(nodes=[0])],nodes=nodes,meshes=meshes,materials=mats,buffers=[dict(byteLength=len(binary))],bufferViews=views,accessors=accessors)
    js=json.dumps(d,separators=(',',':'),allow_nan=False).encode();js+=b' '*((-len(js))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(js)+len(binary))+struct.pack('<I4s',len(js),b'JSON')+js+struct.pack('<I4s',len(binary),b'BIN\0')+binary


def poses():
    flight={j['id']:j['home'] for j in JOINTS if 'coupled' not in j}
    stow=dict(flight)
    for a in ARM_INFO:
        stow['fold-'+a['tag']]=a['fold'];stow['rotor-'+a['tag']]=-a['fold']
    stow['camera-servo']=20
    selfie=dict(flight);selfie['camera-servo']=-20
    down=dict(flight);down['camera-servo']=40
    service=dict(flight)
    for a in ARM_INFO:
        service['fold-'+a['tag']]=a['fold']/2;service['rotor-'+a['tag']]=-a['fold']/2
    return [dict(name=k,values=v) for k,v in [('flight',flight),('stowed',stow),('selfie',selfie),('look-down',down),('folding-midway',service)]]


def matrices(values):
    js={j['id']:j for j in JOINTS};resolved={};transforms={}
    def value(k):
        if k not in resolved:
            j=js[k];resolved[k]=j['home']+sum(c['ratio']*(value(c['joint'])-js[c['joint']]['home']) for c in j['coupled']) if 'coupled' in j else values.get(k,j['home'])
        return resolved[k]
    def tf(k):
        if k is None:return np.eye(4)
        if k not in transforms:
            j=js[k];r=Rotation.from_rotvec(np.array(j['axis'])*math.radians(value(k)-j['home'])).as_matrix();o=np.array(j['origin']);t=np.eye(4);t[:3,:3]=r;t[:3,3]=o-r@o
            transforms[k]=tf(j['parent'])@t
        return transforms[k]
    for k in js:tf(k)
    return transforms,resolved


def world_meshes(values):
    t,_=matrices(values);out={}
    for pid,p in PARTS.items():
        m=p['mesh'].copy();M=np.eye(4);M[:3,:3]=p['R'];M[:3,3]=p['xyz'];m.apply_transform(t.get(p['joint'],np.eye(4))@M);out[pid]=m
    return out


def validate(data):
    raw=(HERE/'assembly.glb').read_bytes();jl=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+jl]);scene=trimesh.load(HERE/'assembly.glb',force='scene')
    names={n['name'] for n in g['nodes'][1:]};ids={j['id'] for j in data['joints']};owners=[]
    assert g['nodes'][0]['name']=='assembly' and g['nodes'][0]['rotation']==[-.7071068,0,0,.7071068]
    assert g['scenes']==[{'nodes':[0]}] and g['nodes'][0]['children']==list(range(1,len(g['nodes'])))
    assert all('children' not in n and 'mesh' in n for n in g['nodes'][1:])
    assert all(len(m['primitives'])==1 for m in g['meshes']) and len(names)==len(PARTS)
    assert set(scene.graph.nodes_geometry)==names
    for j in data['joints']:
        assert j['parent'] is None or j['parent'] in ids
        assert set(j['parts']) <= names
        assert j['limits'][0]<=j['home']<=j['limits'][1]
        assert abs(np.linalg.norm(j['axis'])-1)<1e-9
        for c in j.get('coupled',[]):assert c['joint'] in ids
        owners+=j['parts']
    assert len(owners)==len(set(owners))
    for field in ['parent','coupled']:
        done=set();active=set()
        def visit(k):
            assert k not in active, f'{field} cycle: {k}'
            if k in done:return
            active.add(k);j=next(x for x in JOINTS if x['id']==k)
            deps=([j['parent']] if j['parent'] else []) if field=='parent' else [c['joint'] for c in j.get('coupled',[])]
            for d in deps:visit(d)
            active.remove(k);done.add(k)
        for jid in ids:visit(jid)
    assert hashlib.sha256(raw).hexdigest()==data['glb_sha256']
    triangles=0
    for node in names:
        _,key=scene.graph[node];m=scene.geometry[key]
        assert m.is_watertight and m.is_winding_consistent and m.volume>0,node
        assert all(s.volume>0 for s in m.split()),node
        triangles+=len(m.faces)
    assert triangles<50000
    for a,b in CONTACT:assert a in names and b in names
    bounds={}
    for p in data['poses']:
        t,v=matrices(p['values'])
        for j in JOINTS:assert j['limits'][0]-1e-7<=v[j['id']]<=j['limits'][1]+1e-7
        pts=np.vstack([m.vertices for m in world_meshes(p['values']).values()]);lo=pts.min(0);hi=pts.max(0)
        bounds[p['name']]=dict(min_mm=np.round(lo,4).tolist(),max_mm=np.round(hi,4).tolist(),size_mm=np.round(hi-lo,4).tolist())
        if p['name']!='folding-midway':assert np.all(hi-lo <= [200,200,100])
    # Analytical full rotating-prop envelope, not just the parked GLB blades.
    flight=world_meshes({});lo=np.min([m.bounds[0] for m in flight.values()],axis=0);hi=np.max([m.bounds[1] for m in flight.values()],axis=0)
    lo[:2]=np.minimum(lo[:2],[-97.5,-97.5]);hi[:2]=np.maximum(hi[:2],[97.5,97.5])
    assert np.all(hi-lo<=[200,200,100])
    tree=ast.parse((HERE/'geometry.py').read_text())
    for n in tree.body:
        assert isinstance(n,ast.Assign)
        ast.literal_eval(n.value)
    return dict(part_count=len(names),joint_count=len(JOINTS),driven_joint_count=sum('coupled' in j for j in JOINTS),triangle_count=triangles,
                glb_sha256=data['glb_sha256'],checks=dict(glb_reloaded=True,all_joint_parts_exist=True,all_parents_exist=True,all_coupled_drivers_exist=True,hash_matches=True,unique_joint_ownership=True,acyclic_dependencies=True,closed_outward_meshes=True,flat_hierarchy=True,triangle_budget=True,pose_limits=True),
                pose_bounds=bounds,rotating_flight_envelope_mm=np.round(hi-lo,4).tolist(),
                note='Geometry and sampled rigid-body motion only; no thrust, fatigue, flight stability, flexible-cable or firmware validation.')


def raster_view(values, width=1100, height=760):
    # Orthographic software Z-buffer: correct visibility even for nested hardware.
    # Only opaque outward faces are drawn. No GPU, display server or random sampling.
    view=np.array([1.0,-1.25,.95]);view/=np.linalg.norm(view)
    right=np.cross([0,0,1],view);right/=np.linalg.norm(right);up=np.cross(view,right)
    basis=np.array([right,up,view]).T
    world=world_meshes(values)
    pp=np.vstack([m.vertices@basis for m in world.values()]);low=pp.min(0);high=pp.max(0);mid=(low+high)/2
    scale=min((width-70)/(high[0]-low[0]),(height-85)/(high[1]-low[1]))
    bg=np.array([237,240,236],dtype=np.uint8)
    canvas=np.zeros((height,width,3),dtype=np.uint8)+bg;depth=np.full((height,width),-np.inf)
    light=np.array([.3,-.5,1.0]);light/=np.linalg.norm(light)
    for pid,m in world.items():
        q=m.vertices@basis
        q[:,0]=(q[:,0]-mid[0])*scale+width/2
        q[:,1]=height/2-(q[:,1]-mid[1])*scale
        base=np.array(COLORS[PARTS[pid]['color']][:3])
        for face,normal in zip(m.faces,m.face_normals):
            if normal@view<=1e-8:continue
            a,b,c=q[face]
            x0=max(0,int(np.floor(min(a[0],b[0],c[0]))));x1=min(width-1,int(np.ceil(max(a[0],b[0],c[0]))))
            y0=max(0,int(np.floor(min(a[1],b[1],c[1]))));y1=min(height-1,int(np.ceil(max(a[1],b[1],c[1]))))
            if x1<x0 or y1<y0:continue
            den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)<1e-9:continue
            yy,xx=np.mgrid[y0:y1+1,x0:x1+1];xx=xx+.5;yy=yy+.5
            wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
            wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;wc=1-wa-wb
            zz=wa*a[2]+wb*b[2]+wc*c[2];d=depth[y0:y1+1,x0:x1+1]
            mask=(wa>=-1e-8)&(wb>=-1e-8)&(wc>=-1e-8)&(zz>d)
            shade=.52+.48*max(0,float(normal@light));color=np.clip(base*shade*255,0,255).astype(np.uint8)
            canvas[y0:y1+1,x0:x1+1][mask]=color;d[mask]=zz[mask]
    return canvas


def preview(data,report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(16,9),facecolor='#edf0ec')
    fig.text(.055,.93,'FIELD / 65',fontweight='bold',fontsize=31,color='#163337')
    fig.text(.055,.887,'FOLDING PERSONAL VIDEO QUADCOPTER',fontsize=11,color='#496263')
    for idx,name in enumerate(['flight','stowed']):
        values=next(p['values'] for p in data['poses'] if p['name']==name)
        ax=fig.add_axes([.03+idx*.49,.26,.46,.57]);ax.imshow(raster_view(values));ax.set_axis_off()
        dim=report['rotating_flight_envelope_mm'] if name=='flight' else report['pose_bounds']['stowed']['size_mm']
        fig.text(.07+idx*.49,.22,'01  /  DEPLOYED' if idx==0 else '02  /  BACKPACK',fontsize=14,fontweight='bold',color='#163337')
        fig.text(.07+idx*.49,.18,' × '.join(f'{x:.1f}' for x in dim)+' mm',fontsize=18,color='#163337')
    fig.text(.055,.087,'65 mm propellers   /   4 independent folding arms   /   1:1 servo camera tilt',fontsize=12,color='#496263')
    fig.text(.055,.05,'Mechanical concept · manufacturer component envelopes · not flight qualified',fontsize=10,color='#496263')
    fig.savefig(HERE/'preview.png',dpi=130,facecolor=fig.get_facecolor(),metadata={'Software':'FIELD 65 deterministic generator'});plt.close(fig)


def motion_audit(data):
    import manifold3d as mf
    fixed=world_meshes({});models={};names=list(PARTS)
    for k,m in fixed.items():
        models[k]=mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices,dtype=np.float32),tri_verts=np.asarray(m.faces,dtype=np.uint32)))
    configs=[(p['name'],p['values']) for p in data['poses']]
    independent=[j for j in JOINTS if 'coupled' not in j]
    for t in np.linspace(0,1,41):
        vals={j['id']:j['home'] for j in independent}
        for a in ARM_INFO:vals['fold-'+a['tag']]=a['fold']*t;vals['rotor-'+a['tag']]=-a['fold']*t
        vals['camera-servo']=20*t;configs.append((f'fold-{t:.3f}',vals))
    for a in np.linspace(-40,40,17):configs.append((f'camera-{a:.1f}',{'camera-servo':float(a)}))
    for angle in np.linspace(-180,180,25):configs.append((f'rotors-{angle:.1f}',{j['id']:float(angle) for j in independent if j['id'].startswith('rotor-')}))
    for arm in ARM_INFO:
        for t in np.linspace(0,1,13):configs.append((f"independent-{arm['tag']}-{t:.3f}",{'fold-'+arm['tag']:t*arm['fold'],'rotor-'+arm['tag']:-t*arm['fold']}))
    candidates=[(a,b) for a,b in combinations(names,2) if PARTS[a]['joint']!=PARTS[b]['joint'] and tuple(sorted((a,b))) not in CONTACT]
    ia=np.array([names.index(a) for a,b in candidates]);ib=np.array([names.index(b) for a,b in candidates]);bad={};cache={};tests=0
    for label,values in configs:
        T,resolved=matrices(values);bounds=[];posed={}
        for name in names:
            tr=T.get(PARTS[name]['joint'],np.eye(4));v=trimesh.transform_points(fixed[name].vertices,tr)
            bounds.append([v.min(0),v.max(0)]);posed[name]=models[name].transform(tr[:3,:])
        bounds=np.array(bounds)
        overlap=np.minimum(bounds[ia,1],bounds[ib,1])-np.maximum(bounds[ia,0],bounds[ib,0])
        for i in np.flatnonzero(np.all(overlap>.02,axis=1)):
            a,b=candidates[i]
            rel=np.linalg.inv(T.get(PARTS[a]['joint'],np.eye(4)))@T.get(PARTS[b]['joint'],np.eye(4))
            key=(a,b,tuple(np.round(rel,7).reshape(-1)))
            if key not in cache:
                tests+=1;cache[key]=float((posed[a]^posed[b]).volume())
            volume=cache[key]
            if volume>.01:
                pair=a+' | '+b
                if pair not in bad:bad[pair]=dict(pose=label,intersection_mm3=round(volume,6))
    result=dict(sample_count=len(configs),solid_boolean_tests=tests,unexpected_intersections=bad,
        scope='Five named poses; coordinated folding at 41 samples; each hinge alone at 13 samples; camera at 17 samples; deployed rotor phases at 25 samples. Same-body and declared interface contacts excluded. AABB threshold 0.02 mm; report solid intersections over 0.01 mm3. Sampled check, not continuous collision certification.')
    assert not bad,json.dumps(result,indent=2)
    return result


def write_bom():
    with (HERE/'parts.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['part_id','joint','category','material','description','mesh_volume_mm3'])
        for pid,p in PARTS.items():w.writerow([pid,p['joint'] or 'fixed',p['category'],p['material'],p['spec'],f"{p['mesh'].volume:.4f}"])


def main():
    assert sys.version_info[:2]==(3,11),'Use Python 3.11 for the pinned reproducible build.'
    make_body()
    for tag,sx,sy,z in [('fl',1,-1,27),('fr',1,1,27),('rl',-1,-1,53),('rr',-1,1,53)]:make_arm(tag,sx,sy,z)
    make_camera()
    for j in JOINTS:j['parts']=[pid for pid,p in PARTS.items() if p['joint']==j['id']]
    raw=glb_bytes();(HERE/'assembly.glb').write_bytes(raw)
    data=dict(glb_sha256=hashlib.sha256(raw).hexdigest(),joints=JOINTS,poses=poses())
    (HERE/'joints.yaml').write_text(yaml.safe_dump(data,sort_keys=False))
    (HERE/'assembly.yaml').write_text(yaml.safe_dump(dict(allow_contact=[list(x) for x in sorted(CONTACT)]),sort_keys=False))
    constants='''MAX_SIZE = (200.0, 200.0, 100.0)
BODY_SIZE = (76.0, 40.0, 29.5)
PROP_DIAMETER = 65.0
PROP_PITCH = 38.1
MOTOR_CENTERS_XY = ((65.0, -65.0), (65.0, 65.0), (-65.0, -65.0), (-65.0, 65.0))
HINGE_ORIGINS = ((28.0, -30.0, 27.0), (28.0, 30.0, 27.0), (-28.0, -30.0, 53.0), (-28.0, 30.0, 53.0))
ARM_THICKNESS = 4.0
ARM_WIDTH = 8.0
ARM_PIVOT_DISTANCE = 50.93132631298737
HINGE_AXLE_DIAMETER = 3.0
HINGE_BUSHING = (3.1, 6.0, 4.0)
MOTOR_SIZE = (17.8, 17.6)
MOTOR_STATOR = (14.0, 4.0)
MOTOR_SHAFT_DIAMETER = 1.5
MOTOR_MOUNT_PCD = 9.0
CAMERA_ORIGIN = (63.0, 0.0, 35.0)
CAMERA_SIZE = (21.0, 54.0, 25.5)
CAMERA_HOME = 20.0
CAMERA_LIMITS = (-20.0, 60.0)
SERVO_SIZE = (20.0, 8.6, 17.0)
SERVO_LIMITS = (-40.0, 40.0)
BATTERY_SIZE = (58.0, 31.0, 16.0)
BATTERY_CELL_COUNT = 3
BATTERY_CAPACITY_MAH = 650.0
FC_BOARD_SIZE = (30.0, 32.0, 1.6)
ESC_BOARD_SIZE = (35.0, 30.0, 1.6)
FC_MOUNT_PITCH = (20.0, 20.0)
GPS_SIZE = (20.0, 20.0, 12.4)
'''
    (HERE/'geometry.py').write_text(constants)
    write_bom();report=validate(data)
    report['motion_audit']=motion_audit(data)
    (HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    preview(data,report)
    make_viewer(data,report)
    write_readme(report)
    # Fixed ZIP metadata: identical contents yield identical archive bytes.
    with zipfile.ZipFile(HERE/'backpack-video-drone.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(HERE.iterdir()):
            if p.is_file() and p.suffix not in ['.zip'] and not p.name.startswith('.'):
                info=zipfile.ZipInfo('backpack-video-drone/'+p.name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,p.read_bytes())
    print(json.dumps({k:report[k] for k in ['part_count','joint_count','driven_joint_count','triangle_count','rotating_flight_envelope_mm','glb_sha256']},indent=2))


def make_viewer(data,report):
    # Filled below: dependency-free, offline canvas viewer with real joint transforms.
    template=(HERE/'viewer-template.html').read_text()
    payload=dict(joints=data['joints'],poses=data['poses'],parts=[dict(id=pid,v=np.round(p['mesh'].vertices@p['R'].T+p['xyz'],5).tolist(),f=p['mesh'].faces.tolist(),c=COLORS[p['color']][:3],j=p['joint']) for pid,p in PARTS.items()])
    (HERE/'viewer.html').write_text(template.replace('__ASSEMBLY_DATA__',json.dumps(payload,separators=(',',':'))))


def write_readme(report):
    template=(HERE/'design-notes-template.md').read_text()
    template=template.replace('__COUNTS__',f"{report['part_count']} parts, {report['joint_count']} joints ({report['driven_joint_count']} driven), {report['triangle_count']:,} triangles")
    template=template.replace('__STOWED__',' × '.join(f'{x:.1f}' for x in report['pose_bounds']['stowed']['size_mm']))
    template=template.replace('__DEPLOYED__',' × '.join(f'{x:.1f}' for x in report['rotating_flight_envelope_mm']))
    (HERE/'README.md').write_text(template)


if __name__=='__main__':main()
