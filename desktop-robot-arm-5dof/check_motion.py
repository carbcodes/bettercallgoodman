"""Sampled configuration checks, separate from deterministic interchange checks.

This is deliberately not a continuous collision certificate. Every checked
configuration is reproduced in this script; no randomly chosen samples.
"""
import json
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import numpy as np
import trimesh
import yaml
import geometry as G
from validate import transforms,world_point

def check_motion(root):
    root=Path(root);motion=yaml.safe_load((root/'joints.yaml').read_text());js=motion['joints']
    scene=trimesh.load(root/'assembly.glb',force='scene');inv=np.linalg.inv(scene.graph['assembly'][0])
    owners={p:j['id'] for j in js for p in j['parts']}
    groups={};parts={}
    for pid in scene.graph.nodes_geometry:
        T,g=scene.graph[pid];m=scene.geometry[g].copy();m.apply_transform(inv@T);m.apply_scale(1000)
        parts[pid]=m
        body=owners.get(pid)
        if body not in groups:groups[body]=trimesh.collision.CollisionManager()
        groups[body].add_object(pid,m)
    allow={frozenset(p) for p in yaml.safe_load((root/'assembly.yaml').read_text())['allow_contact']}
    independent=[j for j in js if not j.get('coupled')]
    def check(values):
        M,_=transforms(js,values)
        w=world_point(G.WRIST_ORIGIN,M['elbow']);t=world_point(np.array(G.WRIST_ORIGIN)+[0,0,-G.TOOL],M['wrist'])
        safe=w[2]>=G.W_Z_MIN-1e-6 and (np.linalg.norm(w[:2])>=G.NEAR_R or w[2]>=G.W_Z_NEAR-1e-6) and t[2]>=G.TIP_Z_MIN-1e-6
        for p in parts:groups[owners.get(p)].set_transform(p,M[owners.get(p)])
        pairs=set();managers=list(groups.values())
        for i,a in enumerate(managers):
            for b in managers[i+1:]:
                _,found=a.in_collision_other(b,return_names=True)
                pairs.update(found)
        moving=[sorted(pair) for pair in pairs if frozenset(pair) not in allow]
        return safe,sorted(moving)
    results=[]
    for j in independent:
        vals=np.linspace(*j['limits'],int(np.ceil((j['limits'][1]-j['limits'][0])/2))+1)
        failures=[];rejected=0
        for value in vals:
            safe,pairs=check({j['id']:float(value)})
            if not safe:rejected+=1
            if pairs:failures.append({'value':round(float(value),4),'safe_pose_rules':bool(safe),'contacts':pairs})
        results.append({'joint':j['id'],'samples':len(vals),'rejected_by_pose_rules':rejected,'contacts':failures})
    # A usable sequence uses home as the high-clearance waypoint. Paths have
    # <=2 degree increments in all commanded joints simultaneously.
    home=motion['poses'][0]['values'];paths=[]
    for pose in motion['poses'][1:]:
        end=pose['values'];count=int(np.ceil(max(abs(end[k]-home[k]) for k in home)/2))+1
        failures=[]
        for alpha in np.linspace(0,1,count):
            values={k:float(home[k]+alpha*(end[k]-home[k])) for k in home}
            safe,pairs=check(values)
            if not safe or pairs:failures.append({'fraction':round(float(alpha),5),'safe_pose_rules':bool(safe),'contacts':pairs})
        paths.append({'from':'home','to':pose['name'],'samples':count,'failures':failures})
    result={'step_deg_max':2.0,'single_axis_sweeps':results,'home_to_named_pose_paths':paths,
            'scope':'Discrete mesh checks, not swept-volume proof; payload and deformable service loops excluded.'}
    result['sampled_configurations']=sum(x['samples'] for x in results)+sum(x['samples'] for x in paths)
    result['safe_samples_clear']=all(not c['safe_pose_rules'] for x in results for c in x['contacts'])
    result['all_named_paths_clear']=all(not p['failures'] for p in paths)
    assert result['safe_samples_clear'] and result['all_named_paths_clear']
    (root/'motion-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    result=check_motion(Path(__file__).resolve().parent)
    print(json.dumps({
        'sweeps':[{k:v for k,v in r.items() if k!='contacts'}|{'contact_samples':len(r['contacts'])} for r in result['single_axis_sweeps']],
        'paths':[{k:v for k,v in r.items() if k!='failures'}|{'failed_samples':len(r['failures'])} for r in result['home_to_named_pose_paths']]
    },indent=2))
