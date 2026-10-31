#!/usr/bin/env python3
"""Fixed local workload ONLY. Not an AI compliance test or production runner."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'graph-loop/scripts'))
import recovery_store as store


def record(s, root, ref, text, role='output'):
    store.atomic(root/ref,text.encode())
    s['tracked_files']=[f for f in s['tracked_files'] if f['ref']!=ref]
    s['tracked_files'].append({'ref':ref,'sha256':store.digest(text.encode()),'role':role,'graph_version':s['graph_version']})


def done(s,root,n,ref,value):
    n.update(status='succeeded',attempts=1,phase='done',committed_step=1,next_safe_action='Reuse verified result',pending_steps=[])
    record(s,root,ref,value)
    e='evidence/'+n['id']+'.json';record(s,root,e,json.dumps({'method':'compare literal expected fixture value','expected':value,'actual':(root/ref).read_text(),'pass':True}), 'evidence')
    n['outputs']=[ref];n['artifacts']=[{'ref':ref,'validity':'current','graph_version':1,'sha256':store.digest(value.encode())}]
    n['evidence']=[{'ref':e,'kind':'execution','verdict':'pass','graph_version':1}]


def initialize(root):
    root=Path(root);root.mkdir(parents=True)
    s=json.loads((BASE/'graph-loop/assets/state-template.json').read_text())
    s.update(graph_id='portable-demo',lineage_id='the30-fixed-local-fixture',external_requirements=[])
    s['authorization']=['context/authority.txt: simulated local fixture authority ONLY; no provider writes']
    s['context_sources']=[{'ref':'context/authority.txt','trust':'fixture source, not real external authority'}]
    s['limits']['deadline_utc']='2099-01-01T00:00:00Z'
    s['recovery'].update(authority_location='state.json',retrieval='Read the task store; export a versioned ZIP with recovery_store.py')
    record(s,root,'context/authority.txt','Local deterministic fixture: no external services or AI agents.','context')
    base=s['nodes'][0];s['nodes']=[]
    for name,deps in [('select',[]),('small',['select']),('large',['select']),('work',['small','large'])]:
        n=deepcopy(base);n.update(id=name,inputs=['context/authority.txt'],outputs=[],depends_on=deps)
        s['nodes'].append(n)
    a,b,c,n=s['nodes'];a['selection']='small';done(s,root,a,'artifacts/route.txt','small')
    b['branch']={'node':'select','equals':'small'};done(s,root,b,'artifacts/small.txt','6')
    c.update(branch={'node':'select','equals':'large'},status='skipped',next_safe_action='Excluded branch; do not execute')
    n.update(status='ready',next_safe_action='Start attempt then compute immutable step 1')
    return store.commit(root,s,0)


def worker(root,mode):
    root=Path(root);s=store.load(root);n=s['nodes'][-1]
    assert s['lifecycle']['status']=='active'
    assert not store.preflight(s,root)
    if n['status']=='ready':
        n.update(status='running',phase='work',attempts=n['attempts']+1)
        s['revision']+=1;store.commit(root,s,s['revision']-1)
    for step in range(n['committed_step']+1,4):
        assert store.load(root)['lifecycle']['status']=='active'
        # Reserve a work unit BEFORE the chunk; interruption never resets it.
        s['usage']['work_units']+=1;n['usage']['work_units']+=1
        s['revision']+=1;store.commit(root,s,s['revision']-1)
        ref=f'artifacts/step-{step}.txt';record(s,root,ref,str(step*step))
        n['committed_step']=step;n['next_safe_action']=f'Compute immutable step {step+1}' if step<3 else 'Verify squares [1,4,9]'
        s['revision']+=1;store.commit(root,s,s['revision']-1)
        if step==1 and mode in {'kill','pause'}:
            print('SAFE_STEP_1',flush=True)
            if mode=='kill':
                # Represents a long uncommitted pure computation. Parent sends SIGKILL here.
                time.sleep(60)
            else:
                assert sys.stdin.readline().strip()=='pause'
                store.suspend(root,'Simulated user pause observed; no in-flight tool remains')
                store.export(root,root.parent/'paused-recovery.zip')
                print('PAUSED_EXPORTED',flush=True);return
    n['status']='verifying';n['phase']='verify';s['revision']+=1;store.commit(root,s,s['revision']-1)
    actual=[int((root/f'artifacts/step-{i}.txt').read_text()) for i in (1,2,3)]
    assert actual==[1,4,9]
    record(s,root,'evidence/work.json',json.dumps({'expected':[1,4,9],'actual':actual,'pass':True}), 'evidence')
    n.update(status='succeeded',phase='done',next_safe_action='All required selected work verified',pending_steps=[],outputs=[f'artifacts/step-{i}.txt' for i in (1,2,3)])
    n['artifacts']=[{'ref':ref,'graph_version':1,'validity':'current','sha256':store.digest((root/ref).read_bytes())} for ref in n['outputs']]
    n['evidence']=[{'ref':'evidence/work.json','kind':'execution','verdict':'pass','graph_version':1}]
    s['lifecycle'].update(status='completed',reason='Fixed local workload verified')
    s['revision']+=1;store.commit(root,s,s['revision']-1)
    print('VERIFIED [1,4,9]',flush=True)


if __name__=='__main__':
    if sys.argv[1]=='init':initialize(Path(sys.argv[2]))
    else:worker(Path(sys.argv[2]),sys.argv[1])
