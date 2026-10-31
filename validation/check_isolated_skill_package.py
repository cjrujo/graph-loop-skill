#!/usr/bin/env python3
"""Check that the standard ZIP alone supplies every helper resource; no host install."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

BASE=Path(__file__).resolve().parents[1]


def main():
    package=BASE/'graph-loop.zip';example=BASE/'examples/portable-demo-v1-r5.zip'
    calls=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(package) as z:
            assert z.testzip() is None
            for n in z.namelist():
                path=root/n
                assert path.resolve().is_relative_to(root) and not n.startswith('/') and '..' not in Path(n).parts
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(n))
        skill=root/'graph-loop';helper=skill/'scripts/recovery_store.py';target=root/'new-task'
        def run(*args):
            p=subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True,timeout=15,cwd=root)
            assert p.returncode==0,p.stderr
            calls.append({'command':[str(x).replace(str(root),'ISOLATED_ROOT').replace(str(BASE),'SOURCE_ROOT') for x in args],'exit_code':p.returncode})
            return p
        run(skill/'scripts/inspect_state.py',skill/'assets/state-template.json','--check')
        run(helper,'import',example,target,'--expected-graph','portable-demo','--expected-lineage','the30-fixed-local-fixture')
        state=json.loads(run(helper,'show',target).stdout)
        assert state['lifecycle']['status']=='interrupted' and state['nodes'][-1]['committed_step']==1
        assert 'unverified' in state['import_checks']['freshness']
        run(helper,'check',target)
        run(helper,'resume',target,'--request-ref','fixture:explicit-local-resume','--permission-ref','fixture:local-only','--freshness-ref','fixture:isolated-authority-transfer')
        state=json.loads(run(helper,'show',target).stdout)
        assert state['nodes'][-1]['status']=='running' and state['nodes'][-1]['attempts']==1
        run(helper,'pause',target,'--reason','fixed isolated fixture pause; no business operation was launched')
        run(helper,'export',target,root/'roundtrip.zip')
        with zipfile.ZipFile(root/'roundtrip.zip') as z:
            manifest=json.loads(z.read('MANIFEST.json'))
            assert all(hashlib.sha256(z.read(k)).hexdigest()==v for k,v in manifest.items())
            assert z.read('RESUME_PROMPT.en.md')==(skill/'assets/resume-prompt.en.md').read_bytes()
            progress=z.read('PROGRESS.md').decode()
            assert '(files/evidence/small.json)' in progress
            assert 'files/evidence/small.json' in z.namelist()
    result={'success':True,'method':'extract only standard skill ZIP to temp directory; run its own inspector/import/show/check/resume/pause/export and validate roundtrip hashes/resources','standard_zip_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'commands':calls,'scope':'fixed local fixture only, no native host installation, business runner or real authority verification'}
    (BASE/'validation/isolated-package-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'success':True,'commands':len(calls),'standard_zip_sha256':result['standard_zip_sha256']}))


if __name__=='__main__':main()
