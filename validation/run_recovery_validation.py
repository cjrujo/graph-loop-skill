#!/usr/bin/env python3
"""Executed filesystem/process fixtures; simulated workload/provider; no model evaluation."""
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import recovery_fixture as fixture
store=fixture.store
BASE=fixture.BASE
OUT=BASE/'validation/recovery-runs'


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.task=self.root/'task';fixture.initialize(self.task)

    def save(self,name):
        target=OUT/name
        if target.exists():shutil.rmtree(target)
        # Avoid runtime lock/temp files; a killed worker is killed outside commit by handshake.
        shutil.copytree(self.root,target)

    def change(self,fn):
        s=deepcopy(store.load(self.task));base=s['revision'];fn(s);s['revision']+=1
        return store.commit(self.task,s,base)

    def child(self,mode):
        p=subprocess.Popen([sys.executable,str(BASE/'validation/recovery_fixture.py'),mode,str(self.task)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertEqual(p.stdout.readline().strip(),'SAFE_STEP_1')
        return p

    def cli(self,*args,expected=0):
        p=subprocess.run([sys.executable,str(BASE/'graph-loop/scripts/recovery_store.py'),*map(str,args)],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,expected,p.stderr)
        return p

    def test_01_real_sigkill_then_resume_safe_cursor(self):
        p=self.child('kill');p.kill();stdout,stderr=p.communicate(timeout=5)
        self.assertLess(p.returncode,0)
        s=store.load(self.task);self.assertEqual(s['nodes'][-1]['committed_step'],1)
        self.assertEqual(s['nodes'][-1]['attempts'],1);self.assertEqual(s['usage']['work_units'],1)
        before={f['ref']:f['sha256'] for f in s['tracked_files']}
        self.change(lambda s:s['lifecycle'].update(status='interrupted',reason='Confirmed worker SIGKILL; immutable local files verified; no external operations'))
        self.cli('resume',self.task,'--request-ref','fixture:new-user-resume','--permission-ref','fixture:local-only','--freshness-ref','fixture:single-writer')
        r=subprocess.run([sys.executable,str(BASE/'validation/recovery_fixture.py'),'resume',str(self.task)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        s=store.load(self.task);self.assertEqual(s['lifecycle']['status'],'completed')
        self.assertEqual(s['nodes'][-1]['attempts'],1);self.assertEqual(s['usage']['work_units'],3)
        self.assertTrue(all(store.digest((self.task/k).read_bytes())==v for k,v in before.items()))
        (self.root/'process-observation.json').write_text(json.dumps({'method':'real local subprocess SIGKILL after committed safe-step handshake','returncode':p.returncode,'last_committed_step':1,'resumed_squares':[1,4,9],'attempts':1,'cumulative_work_units':3,'not_tested':'power loss, arbitrary kill offsets, model adherence'},indent=2))
        self.save('sigkill')

    def test_02_user_pause_export_isolated_process_resume_no_branch_replay(self):
        p=self.child('pause');p.stdin.write('pause\n');p.stdin.flush();out,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,0,err);self.assertIn('PAUSED_EXPORTED',out)
        s=store.load(self.task);self.assertEqual(s['lifecycle']['status'],'paused')
        self.assertFalse((self.task/'artifacts/step-2.txt').exists())
        self.assertEqual(s['nodes'][-1]['committed_step'],1)
        target=self.root/'isolated-new-session'
        self.cli('import',self.root/'paused-recovery.zip',target,'--expected-graph',s['graph_id'],'--expected-lineage',s['lineage_id'],'--current-store',self.task)
        imported=store.load(target);self.assertEqual(imported['lifecycle']['status'],'interrupted')
        # Original store becomes unreachable; recovery must use packaged bytes exclusively.
        shutil.move(self.task,self.root/'retired-original')
        branch_before=(target/'artifacts/small.txt').stat().st_mtime_ns
        self.cli('resume',target,'--request-ref','fixture:user-explicit-resume','--permission-ref','fixture:local-scope','--freshness-ref','fixture:authority-transferred-old-writer-stopped')
        r=subprocess.run([sys.executable,str(BASE/'validation/recovery_fixture.py'),'resume',str(target)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        after=store.load(target)
        self.assertEqual(after['nodes'][1]['attempts'],1);self.assertEqual(after['nodes'][2]['attempts'],0)
        self.assertEqual((target/'artifacts/small.txt').stat().st_mtime_ns,branch_before)
        self.assertEqual(after['nodes'][-1]['attempts'],1)
        self.assertEqual(after['usage']['work_units'],3)
        (self.root/'pause-observation.json').write_text(json.dumps({'pause_at_step':1,'no_step_2_after_pause':True,'isolated_process_and_directory':True,'original_store_unreachable_during_resume':True,'completed_branch_attempts':1,'excluded_branch_attempts':0,'method':'fixed local worker obeys explicit stdin pause command; not an AI stop-button test'},indent=2))
        self.save('pause-portable')

    def test_03_provider_applied_but_ack_missing_never_resends(self):
        # Simulated provider ledger: persist intent, apply once, lose acknowledgement.
        def intent(s):
            n=s['nodes'][-1];n.update(status='running',attempts=1,phase='work')
            n['operations']=[{'id':'sim-provider-op-1','kind':'non_idempotent','status':'prepared','provider_ref':'SIMULATED ledger.json'}]
        self.change(intent)
        ledger={'SIMULATED':True,'applied':['sim-provider-op-1'],'calls':1}
        (self.root/'ledger.json').write_text(json.dumps(ledger))
        blockers=store.preflight(store.load(self.task),self.task)
        self.assertTrue(any('reconcile operation' in x for x in blockers))
        with self.assertRaisesRegex(ValueError,'preflight blocked'):
            self.change(lambda s:s['lifecycle'].update(status='interrupted',reason='simulated missing acknowledgement'))
            store.resume(self.task,'fixture:resume','fixture:permission','fixture:fresh')
        self.assertEqual(json.loads((self.root/'ledger.json').read_text())['calls'],1)
        # Reconciliation, not resend. Provider identity checked against persisted operation ID.
        self.assertIn('sim-provider-op-1',ledger['applied'])
        def reconcile(s):
            fixture.record(s,self.task,'evidence/provider-reconcile.json',json.dumps(ledger),'evidence')
            s['nodes'][-1]['operations'][0].update(status='confirmed',reconciliation_ref='evidence/provider-reconcile.json')
        self.change(reconcile)
        self.assertFalse(store.preflight(store.load(self.task),self.task))
        self.save('simulated-provider')

    def test_04_missing_and_tampered_artifacts_never_unlock(self):
        (self.task/'artifacts/small.txt').unlink()
        self.assertTrue(any('small.txt' in x for x in store.preflight(store.load(self.task),self.task)))
        (self.task/'artifacts/small.txt').write_text('tampered')
        self.assertTrue(any('small.txt' in x for x in store.preflight(store.load(self.task),self.task)))
        self.change(lambda s:s['lifecycle'].update(status='interrupted',reason='recover'))
        with self.assertRaisesRegex(ValueError,'preflight blocked'):store.resume(self.task,'r','p','f')
        self.assertEqual(store.load(self.task)['nodes'][-1]['status'],'ready')
        self.save('tampered-artifact')

    def test_05_latest_corrupt_previous_read_only_not_auto_rollback(self):
        self.change(lambda s:s['usage'].update(work_units=1))
        (self.task/'state.json').write_text('{broken')
        with self.assertRaisesRegex(ValueError,'missing/corrupt'):store.load(self.task)
        self.assertEqual(store.load(self.task,previous=True)['revision'],1)
        with self.assertRaises(ValueError):store.resume(self.task,'r','p','f')
        self.save('corrupt-latest')

    def test_06_stale_import_cannot_replace_newer_authority(self):
        package=self.root/'old.zip';store.export(self.task,package)
        self.change(lambda s:s['usage'].update(work_units=1))
        with self.assertRaisesRegex(ValueError,'stale or divergent'):
            store.import_package(package,self.root/'new','portable-demo','the30-fixed-local-fixture',self.task)
        self.assertFalse((self.root/'new').exists());self.assertEqual(store.load(self.task)['revision'],2)
        self.save('stale-import')

    def test_07_attempt_work_elapsed_cannot_reset(self):
        def use(s):
            s['usage'].update(work_units=2,elapsed_seconds=4)
            s['nodes'][-1].update(attempts=1)
            s['nodes'][-1]['usage'].update(work_units=2,elapsed_seconds=4)
        self.change(use)
        for field in ('work_units','elapsed_seconds'):
            with self.assertRaisesRegex(ValueError,'usage cannot reset'):self.change(lambda s:s['usage'].update({field:0}))
        with self.assertRaisesRegex(ValueError,'attempts cannot reset'):self.change(lambda s:s['nodes'][-1].update(attempts=0))
        self.assertEqual(store.load(self.task)['usage']['work_units'],2)

    def test_08_exhausted_budget_survives_restart(self):
        self.change(lambda s:(s['usage'].update(work_units=20),s['lifecycle'].update(status='interrupted',reason='recover')))
        p=self.cli('check',self.task,expected=2)
        self.assertIn('budget exhausted',p.stdout)
        with self.assertRaisesRegex(ValueError,'preflight blocked'):store.resume(self.task,'r','p','f')

    def test_09_cancel_terminal_pause_requires_explicit_resume(self):
        store.suspend(self.task,'fixture user pause')
        self.assertEqual(store.load(self.task)['lifecycle']['status'],'paused')
        with self.assertRaisesRegex(ValueError,'explicit resume|paused node in active'):
            self.change(lambda s:s['lifecycle'].update(status='active',reason='unauthorized restart'))
        store.suspend(self.task,'fixture explicit cancel',cancel=True)
        with self.assertRaisesRegex(ValueError,'resume requires'):store.resume(self.task,'r','p','f')
        with self.assertRaisesRegex(ValueError,'terminal'):self.change(lambda s:s['lifecycle'].update(status='interrupted',reason='retry'))

    def test_10_manifest_tamper_provenance_and_target_collision(self):
        p=self.root/'ok.zip';store.export(self.task,p)
        with zipfile.ZipFile(p) as z:payload={n:z.read(n) for n in z.namelist()}
        payload['PROGRESS.md']=b'changed'
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:
            for k,v in payload.items():z.writestr(k,v)
        with self.assertRaisesRegex(ValueError,'checksum'):store.inspect_package(bad)
        with self.assertRaisesRegex(ValueError,'untrusted'):store.import_package(p,self.root/'new','other','lineage')
        with self.assertRaisesRegex(ValueError,'never overwrite'):store.import_package(p,self.task,'portable-demo','the30-fixed-local-fixture')
        self.save('portable-integrity')

    def test_11_input_mutation_and_missing_external_stay_blocked(self):
        (self.task/'context/authority.txt').write_text('changed input')
        self.assertTrue(store.preflight(store.load(self.task),self.task))
        self.change(lambda s:s['external_requirements'].append({'ref':'external-service','kind':'permission','required_for':['work'],'reason':'not available'}))
        r=store.export(self.task,self.root/'incomplete.zip')
        self.assertTrue(r['missing']);self.assertTrue(r['external_requirements'])
        result=store.import_package(self.root/'incomplete.zip',self.root/'new','portable-demo','the30-fixed-local-fixture')
        self.assertTrue(result['blockers']);self.assertIn('unverified',result['freshness'])

    def test_12_no_persistence_chat_fallback_document_inspection(self):
        # DOCUMENT CHECK ONLY. No chat host or model behavior is executed.
        text=(BASE/'graph-loop/assets/chat-snapshot-template.md').read_text()
        for label in ('FULL_V2_STATE_JSON_BEGIN','FILE_BEGIN','MISSING_EXTERNAL_ITEMS','RESUME_PROMPT','no background persistence'):
            self.assertIn(label,text)
        prompt=(BASE/'resume-prompt.en.md').read_text()
        self.assertIn('I explicitly request',prompt)
        self.assertEqual(prompt,(BASE/'graph-loop/assets/resume-prompt.en.md').read_text())

    def test_13_stale_writer_and_checksum_valid_json_tamper(self):
        s=deepcopy(store.load(self.task));s['revision']+=1
        with self.assertRaisesRegex(ValueError,'stale expected'):store.commit(self.task,s,88)
        envelope=json.loads((self.task/'state.json').read_text());envelope['state']['usage']['work_units']=0.5
        (self.task/'state.json').write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError,'checksum'):store.load(self.task)

    def test_14_lock_collision_and_missing_latest_fail_closed(self):
        (self.task/'.writer.lock').write_text('fixture existing writer')
        with self.assertRaises(FileExistsError):store.suspend(self.task,'pause')
        (self.task/'.writer.lock').unlink()
        self.change(lambda s:s['usage'].update(work_units=1))
        (self.task/'state.json').unlink()
        with self.assertRaisesRegex(ValueError,'missing/corrupt'):store.load(self.task)
        self.assertEqual(store.load(self.task,True)['revision'],1)

    def test_15_unsafe_zip_paths_and_symlink_input_rejected(self):
        for ref in ('../escape','/absolute','C:/secret','a\\b','state.json/../x'):
            self.assertFalse(store.safe(ref))
        target=self.task/'artifacts/small.txt';target.unlink();target.symlink_to(self.root/'outside')
        self.assertTrue(store.preflight(store.load(self.task),self.task))

    def test_17_reserved_paths_and_export_secret_match_rejected(self):
        import os
        with self.assertRaisesRegex(ValueError,'reserved'):store.local(self.task,'state.json')
        os.environ['THE30_FIXTURE_SECRET']='fixture-only-random-secret-112233'
        try:
            self.change(lambda s:fixture.record(s,self.task,'context/sensitive.txt',os.environ['THE30_FIXTURE_SECRET'],'context'))
            with self.assertRaisesRegex(ValueError,'sensitive'):store.export(self.task,self.root/'secret.zip')
            self.assertFalse((self.root/'secret.zip').exists())
        finally:
            del os.environ['THE30_FIXTURE_SECRET']

    def test_18_pause_ready_can_resume_without_fabricating_attempt(self):
        store.suspend(self.task,'pause before work')
        store.resume(self.task,'fixture:r','fixture:p','fixture:f')
        n=store.load(self.task)['nodes'][-1]
        self.assertEqual((n['status'],n['attempts']),('ready',0))

    def test_16_verifying_phase_restored_without_new_attempt(self):
        self.change(lambda s:s['nodes'][-1].update(status='verifying',phase='verify',attempts=1))
        store.suspend(self.task,'pause while verifying')
        store.resume(self.task,'fixture:r','fixture:p','fixture:f')
        n=store.load(self.task)['nodes'][-1]
        self.assertEqual((n['status'],n['phase'],n['attempts']),('verifying','verify',1))


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    log=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Recovery)
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (BASE/'validation/recovery-test-output.log').write_text(log.getvalue())
    report={'method':'real local subprocess interruption/pause and filesystem helper tests with fixed simulated workload/provider; fallback is document inspection','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.testsRun-len(result.failures)-len(result.errors),'successful':result.wasSuccessful(),'python':sys.version.split()[0],'not_tested':['AI instruction adherence','seven-host integration','actual remote provider','power-loss durability','all crash offsets','chat retention and downloads in other hosts']}
    (BASE/'validation/recovery-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    if not result.wasSuccessful():print(log.getvalue())
    sys.exit(0 if result.wasSuccessful() else 1)
