#!/usr/bin/env python3
"""Independent GLB round-trip / graph / FK / payload / FCL validation."""
from __future__ import annotations
import ast
import hashlib
import json
import re
import struct
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
import yaml
import geometry as G

def read_glb(path):
    raw=path.read_bytes()
    magic,version,length=struct.unpack_from('<III',raw)
    assert magic==0x46546c67 and version==2 and length==len(raw)
    size,kind=struct.unpack_from('<II',raw,12)
    assert kind==0x4e4f534a
    return json.loads(raw[20:20+size])

def transforms(joints,values):
    jd={j['id']:j for j in joints};actual={};M={None:np.eye(4)};active=set()
    def val(jid):
        if jid in actual:return actual[jid]
        assert jid not in active,'coupling cycle'
        active.add(jid);j=jd[jid]
        v=j['home']+sum(c['ratio']*(val(c['joint'])-jd[c['joint']]['home']) for c in j['coupled']) if j.get('coupled') else values.get(jid,j['home'])
        active.remove(jid);actual[jid]=float(v);return float(v)
    def mat(jid):
        if jid in M:return M[jid]
        assert jid not in active,'parent cycle'
        active.add(jid);j=jd[jid];P=mat(j['parent']);active.remove(jid)
        r=Rotation.from_rotvec(np.array(j['axis'])*np.radians(val(jid)-j['home'])).as_matrix()
        o=np.array(j['origin']);T=np.eye(4);T[:3,:3]=r;T[:3,3]=o-r@o;M[jid]=P@T;return M[jid]
    for jid in jd:mat(jid)
    return M,actual

def world_point(p,M):return (M@np.r_[p,1])[:3]

def validate(folder,write=False):
    folder=Path(folder);doc=read_glb(folder/'assembly.glb')
    motion=yaml.safe_load((folder/'joints.yaml').read_text());js=motion['joints'];ids={j['id'] for j in js}
    rawhash=hashlib.sha256((folder/'assembly.glb').read_bytes()).hexdigest()
    assert rawhash==motion['glb_sha256'],'hash mismatch'
    assert len(ids)==len(js)
    assert doc['scenes'][doc['scene']]['nodes']==[0]
    assert doc['nodes'][0]['name']=='assembly'
    assert doc['nodes'][0]['rotation']==[-0.7071068,0,0,0.7071068]
    assert 'animations' not in doc
    assert sorted(doc['nodes'][0]['children'])==list(range(1,len(doc['nodes'])))
    nodes={n['name']:n for n in doc['nodes'][1:]}
    assert len(nodes)==len(doc['nodes'])-1
    assert len(doc['meshes'])==len(nodes)
    for pid,n in nodes.items():
        assert re.fullmatch('[a-z][a-z0-9]*(?:-[a-z0-9]+)*',pid),pid
        assert 'children' not in n and len(doc['meshes'][n['mesh']]['primitives'])==1
    owner={pid:None for pid in nodes};assigned=[]
    assert len(motion['poses'])>=3
    assert len({p['name'] for p in motion['poses']})==len(motion['poses'])
    for j in js:
        assert j['type']=='revolute'
        assert j['parent'] is None or j['parent'] in ids
        assert len(j['origin'])==3 and np.isclose(np.linalg.norm(j['axis']),1)
        assert j['limits'][0]<=j['home']<=j['limits'][1]
        for p in j['parts']:
            assert p in nodes,p
            assert p not in assigned,p
            assigned.append(p);owner[p]=j['id']
        for c in j.get('coupled',[]):assert c['joint'] in ids
    assert all(set(p['values']).issubset(ids) for p in motion['poses'])
    # Strict literal-only geometry file, including the required tuple assignment.
    for node in ast.parse((folder/'geometry.py').read_text()).body:
        assert isinstance(node,ast.Assign)
        ast.literal_eval(node.value)
    scene=trimesh.load(folder/'assembly.glb',force='scene',process=False)
    rootinv=np.linalg.inv(scene.graph['assembly'][0]);parts={}
    tri=0
    for pid in nodes:
        T,g=scene.graph[pid];m=scene.geometry[g].copy();m.apply_transform(rootinv@T);m.apply_scale(1000)
        # GLB preserves indexed topology. Verify closed and outward after round trip.
        assert m.is_watertight and m.is_winding_consistent and m.volume>0,pid
        if nodes[pid]['extras']['category'] in ['printed','pad']:
            assert len(m.split(only_watertight=False))==1,pid
        parts[pid]=m;tri+=len(m.faces)
    assert tri<50000,tri
    allow={frozenset(p) for p in yaml.safe_load((folder/'assembly.yaml').read_text())['allow_contact']}
    assert all(len(pair)==2 and pair.issubset(nodes) for pair in allow)
    homeM,homevals=transforms(js,{})
    assert all(np.allclose(T,np.eye(4)) for T in homeM.values())
    # Deterministic broad-phase/FCL BVH checks. Same-body pairs are also reported,
    # but not interpreted as motion hazards (purchased envelopes omit internals).
    cm=trimesh.collision.CollisionManager()
    for pid,m in parts.items():cm.add_object(pid,m)
    poses=[]
    masses={pid:n['extras']['mass_g']/1000 for pid,n in nodes.items()}
    def descends(o,ancestor):
        jd={j['id']:j for j in js}
        while o is not None:
            if o==ancestor:return True
            o=jd[o]['parent']
        return False
    for pose in motion['poses']:
        M,vals=transforms(js,pose['values'])
        assert all(j['limits'][0]-1e-8<=vals[j['id']]<=j['limits'][1]+1e-8 for j in js),pose['name']
        wrist=world_point(G.WRIST_ORIGIN,M['elbow']);tip=world_point(np.array(G.WRIST_ORIGIN)+[0,0,-G.TOOL],M['wrist'])
        radial=float(np.linalg.norm(wrist[:2]))
        safe=wrist[2]>=G.W_Z_MIN and (radial>=G.NEAR_R or wrist[2]>=G.W_Z_NEAR) and tip[2]>=G.TIP_Z_MIN
        actual_tip_min=min(float((trimesh.transform_points(parts[p].vertices,M[owner[p]]))[:,2].min()) for p in ['gripper-pad-left','gripper-pad-right'])
        for pid in parts:cm.set_transform(pid,M[owner[pid]])
        _,pairs,contacts=cm.in_collision_internal(return_names=True,return_data=True)
        depth={frozenset(c.names):max(float(c.depth),0) for c in contacts}
        unexpected=[];same=[]
        for a,b in sorted(pairs):
            pair=frozenset((a,b))
            if pair in allow:continue
            record={'parts':[a,b],'depth_mm':round(depth.get(pair,0),5)}
            if owner[a]==owner[b]:same.append(record)
            else:unexpected.append(record)
        torques={}
        for jid in ['shoulder','elbow','wrist','tool-roll']:
            j=next(j for j in js if j['id']==jid)
            pivot=world_point(j['origin'],M[j['parent']]);axis=M[j['parent']][:3,:3]@j['axis']
            moment=np.zeros(3)
            for pid,m in parts.items():
                if descends(owner[pid],jid):
                    com=world_point(m.center_mass,M[owner[pid]])
                    moment+=np.cross((com-pivot)/1000,[0,0,-9.80665*masses[pid]])
            moment+=np.cross((tip-pivot)/1000,[0,0,-9.80665*G.PAYLOAD_G/1000])
            torques[jid]=round(abs(float(axis@moment)),5)
        poses.append({'name':pose['name'],'wrist_mm':np.round(wrist,5).tolist(),'tip_mm':np.round(tip,5).tolist(),
            'wrist_radius_mm':round(radial,5),'safe_pose_rules':bool(safe),'actual_pad_min_z_mm':round(actual_tip_min,5),
            'static_torque_nm_with_150g':torques,'unexpected_moving_contacts':unexpected,'unlisted_same_body_contacts':same})
        assert safe and actual_tip_min>=G.TIP_Z_MIN,pose['name']
        assert not unexpected and not same,(pose['name'],unexpected,same)
        for jid,budget in zip(['shoulder','elbow','wrist','tool-roll'],G.TORQUE_BUDGET_NM):
            assert torques[jid]*G.DYNAMIC_LOAD_FACTOR<=budget,(pose['name'],jid,torques[jid])
    report={'python':sys.version.split()[0],'part_count':len(parts),'joint_count':len(js),'positioning_dof':5,
        'independent_gripper_dof':1,'coupled_joint_count':sum(bool(j.get('coupled')) for j in js),'triangle_count':tri,
        'glb_sha256':rawhash,'references_valid':True,'hash_matches':True,'root_and_flat_graph_valid':True,
        'all_meshes_closed_outward':True,'geometry_literals_only':True,'home_transforms_identity':True,
        'printable_parts_single_solid':True,'named_poses_safe_and_clear':True,
        'named_pose_torque_budget_pass':True,'dynamic_load_factor':G.DYNAMIC_LOAD_FACTOR,
        'torque_budget_nm':dict(zip(['shoulder','elbow','wrist','tool-roll'],G.TORQUE_BUDGET_NM)),
        'printed_part_count':sum(n['extras']['category']=='printed' for n in nodes.values()),
        'tpu_part_count':sum(n['extras']['category']=='pad' for n in nodes.values()),
        'estimated_total_mass_g':round(sum(masses.values())*1000,2),'poses':poses,
        'scope':'FCL checks named poses; continuous full workspace not certified. Purchase envelopes omit threads and motor internals.'}
    if write:(folder/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    r=validate(Path(__file__).resolve().parent,write=True)
    print(json.dumps(r,indent=2))
