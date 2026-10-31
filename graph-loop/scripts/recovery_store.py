#!/usr/bin/env python3
"""Optional local checkpoint/export utility. No business runner, tool cancellation or wake service.
Python 3.10+, standard library. Single writer; lock collision fails closed, never auto-steals.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

from inspect_state import validate, render


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(ref):
    p = PurePosixPath(ref)
    return bool(ref) and str(p) == ref and not p.is_absolute() and '..' not in p.parts and '\\' not in ref and ':' not in ref and all(not x.startswith('.') for x in p.parts)


def local(root, ref):
    require(safe(ref), 'unsafe file reference: ' + ref)
    require(ref.split('/')[0] not in {'state.json', 'previous.json', 'imported-source.json'}, 'reserved store path')
    root = Path(root).resolve()
    p = root / ref
    require(not any(x.is_symlink() for x in [p, *p.parents] if x != root.parent), 'symlinks are not portable')
    require(p.resolve().is_relative_to(root), 'file escapes root')
    return p


def atomic(path, data):
    """Same-filesystem replace + fsync data and parent. POSIX local filesystem assumed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.checkpoint-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / '.writer.lock'
    # Fail closed after a killed writer: operator confirms no live writer before removing.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        yield
    finally:
        path.unlink()


def envelope(s):
    return encode({'format': 'graph-loop-checkpoint-v1', 'sha256': digest(encode(s)), 'state': s})


def read_envelope(p):
    e = json.loads(Path(p).read_text())
    require(e['format'] == 'graph-loop-checkpoint-v1' and digest(encode(e['state'])) == e['sha256'], 'checkpoint checksum mismatch')
    s = validate(e['state'])
    require(s['schema_version'] == 2, 'explicit v1 migration required')
    return s


def load(root, previous=False):
    """Never automatically fall back: old cursors can hide already issued operations."""
    path = Path(root) / ('previous.json' if previous else 'state.json')
    try:
        return read_envelope(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f'{path.name} missing/corrupt; inspect previous.json read-only, reconcile newer actions before explicit repair: {exc}') from exc


def monotonic(old, new, allow_resume=False):
    require(new['graph_id'] == old['graph_id'] and new['lineage_id'] == old['lineage_id'], 'identity changed')
    require(new['revision'] == old['revision'] + 1 and new['graph_version'] >= old['graph_version'], 'stale revision/version')
    require(old['lifecycle']['status'] != 'cancelled' or new['lifecycle']['status'] == 'cancelled', 'cancelled task is terminal')
    if old['lifecycle']['status'] in {'paused', 'pause_requested', 'interrupted'} and new['lifecycle']['status'] == 'active':
        require(allow_resume, 'explicit resume command required')
    for k in ('work_units', 'elapsed_seconds', 'tokens', 'cost_usd'):
        if old['usage'].get(k) is not None:
            require(new['usage'].get(k) is not None and new['usage'][k] >= old['usage'][k], 'usage cannot reset: ' + k)
    for k, v in old['limits'].items():
        if k.startswith('max_') and type(v) in {int, float}:
            require(new['limits'].get(k, float('inf')) <= v, 'helper cannot raise limits')
    require(new['limits']['deadline_utc'] <= old['limits']['deadline_utc'], 'helper cannot extend deadline')
    nodes = {n['id']: n for n in new['nodes']}
    for before in old['nodes']:
        require(before['id'] in nodes, 'retain consumed node counters/history')
        after = nodes[before['id']]
        require(after['attempts'] >= before['attempts'], 'attempts cannot reset')
        require(all(after['usage'][k] >= before['usage'][k] for k in ('work_units', 'elapsed_seconds')), 'node usage cannot reset')
        if new['graph_version'] == old['graph_version']:
            require(after['committed_step'] >= before['committed_step'], 'safe cursor cannot regress without replan')
        ops = {o['id']: o for o in after['operations']}
        for op in before['operations']:
            require(op['id'] in ops, 'retain operation history')
            require(ops[op['id']]['kind'] == op['kind'] and ops[op['id']]['provider_ref'] == op['provider_ref'], 'operation identity changed')
            if op['status'] in {'sent', 'unknown', 'confirmed'} and ops[op['id']]['status'] != op['status']:
                require(ops[op['id']].get('reconciliation_ref'), 'operation disposition requires reconciliation evidence')


def commit(root, s, expected, allow_resume=False):
    validate(s)
    require(s['schema_version'] == 2, 'v2 required')
    root = Path(root)
    with lock(root):
        if expected == 0:
            require(not (root/'state.json').exists() and not (root/'previous.json').exists(), 'store already exists')
            require(s['revision'] == 1, 'initial revision must be 1')
        else:
            old = load(root)
            require(old['revision'] == expected, 'stale expected revision')
            monotonic(old, s, allow_resume)
            atomic(root/'previous.json', (root/'state.json').read_bytes())
        atomic(root/'state.json', envelope(s))
    return s


def preflight(s, root):
    """Return blockers; never unlock or mutate nodes. Coordinator validates semantic evidence."""
    validate(s)
    issues = []
    records = {f['ref']: f for f in s['tracked_files']}
    for f in records.values():
        try:
            p = local(root, f['ref'])
            require(p.is_file() and digest(p.read_bytes()) == f['sha256'], 'missing/changed file')
        except (OSError, ValueError) as exc:
            issues.append(f"{f['ref']}: {exc}")
    external = {e['ref'] for e in s['external_requirements']}
    for n in s['nodes']:
        needed = list(n['inputs']) + [a['ref'] for a in n['artifacts'] if a['validity'] == 'current'] + [e['ref'] for e in n['evidence'] if e['graph_version'] == s['graph_version']]
        for ref in needed:
            if ref not in records and ref not in external:
                issues.append(n['id'] + ': untracked reference ' + ref)
        for o in n['operations']:
            if o.get('reconciliation_ref') and o['reconciliation_ref'] not in records:
                issues.append(n['id'] + ': untracked reconciliation evidence ' + o['id'])
            if o['status'] in {'prepared', 'sent', 'unknown'}:
                issues.append(n['id'] + ': reconcile operation ' + o['id'] + ' before any replay')
        if (n['status'] in {'running', 'verifying'} or n['status'] == 'paused' and n.get('resume_status') != 'ready') and n['attempts'] == 0:
            issues.append(n['id'] + ': no started attempt')
    for e in s['external_requirements']:
        # Summaries cannot prove current external availability/permission.
        issues.append('external requirement needs current verification: ' + e['ref'])
    for used, cap in [('work_units', 'max_work_units'), ('elapsed_seconds', 'max_elapsed_seconds'), ('tokens', 'max_tokens'), ('cost_usd', 'max_cost_usd')]:
        if cap in s['limits']:
            if s['usage'].get(used) is None:
                issues.append('usage unobservable for cap: ' + cap)
            elif s['usage'][used] >= s['limits'][cap]:
                issues.append('budget exhausted: ' + used)
    if datetime.now(timezone.utc) >= datetime.fromisoformat(s['limits']['deadline_utc'].replace('Z', '+00:00')):
        issues.append('deadline exhausted')
    if s['lifecycle']['status'] == 'cancelled':
        issues.append('cancelled task is terminal')
    return issues


def suspend(root, reason, cancel=False):
    s = deepcopy(load(root)); base = s['revision']; s['revision'] += 1
    s['lifecycle'].update(status='cancelled' if cancel else 'paused', reason=reason, resume_request_ref=None)
    for n in s['nodes']:
        if n['status'] in {'running', 'verifying', 'ready'}:
            if not cancel:
                n['resume_status'] = n['status']; n['resume_phase'] = n['phase']
            n['status'] = 'cancelled' if cancel else 'paused'; n['phase'] = 'suspended'; n['reason'] = reason
        elif cancel and n['status'] in {'pending', 'blocked', 'failed', 'paused'}:
            n.update(status='cancelled', reason=reason)
    return commit(root, s, base)


def resume(root, request_ref, permission_ref, freshness_ref):
    s = deepcopy(load(root))
    require(s['lifecycle']['status'] in {'paused', 'interrupted', 'pause_requested'}, 'resume requires paused/interrupted state; crash must first be acknowledged as interrupted')
    require(all(isinstance(x, str) and x.strip() for x in (request_ref, permission_ref, freshness_ref)), 'current request/permission/freshness source references required')
    issues = preflight(s, root)
    require(not issues, 'preflight blocked: ' + '; '.join(issues))
    base = s['revision']; s['revision'] += 1
    s['lifecycle'].update(status='active', reason='explicit user resume after preflight', resume_request_ref=request_ref, permission_ref=permission_ref, freshness_ref=freshness_ref)
    for n in s['nodes']:
        if n['status'] == 'paused':
            n['status'] = n.pop('resume_status'); n['phase'] = n.pop('resume_phase', 'work')
    return commit(root, s, base, allow_resume=True)


def export(root, output):
    """Publish a portable snapshot even if files are missing; missing items stay explicit."""
    root, output = Path(root), Path(output)
    require(not output.exists(), 'export is immutable; choose a new versioned filename')
    with lock(root):
        s = load(root)
        origin = {'format':'graph-loop-portable-v1', 'graph_id':s['graph_id'], 'lineage_id':s['lineage_id'], 'graph_version':s['graph_version'], 'revision':s['revision'], 'state_sha256':digest(encode(s)), 'source_authority':s['recovery']['authority_location'], 'missing':[]}
        payload = {'state.json':encode(s)}
        for f in s['tracked_files']:
            try:
                p = local(root, f['ref']); data = p.read_bytes()
                require(digest(data) == f['sha256'], 'hash mismatch')
                payload['files/'+f['ref']] = data
            except (OSError, ValueError) as exc:
                origin['missing'].append({'ref':f['ref'], 'reason':str(exc)})
        origin['external_requirements'] = s['external_requirements']
        payload['ORIGIN.json'] = encode(origin)
        projection = deepcopy(s)
        for node in projection['nodes']:
            for evidence in node['evidence']:
                if 'files/'+evidence['ref'] in payload:
                    evidence['ref'] = 'files/'+evidence['ref']
        payload['PROGRESS.md'] = (render(projection) + '\nNext: validate provenance, freshness, current permission, files and in-flight operations before explicit resume.\n' + '\n'.join(n['id'] + ': committed step ' + str(n['committed_step']) + '; next ' + n['next_safe_action'] for n in s['nodes']) + '\nMissing: ' + json.dumps(origin['missing']) + '\nExternal: ' + json.dumps(s['external_requirements']) + '\n').encode()
        payload['RESUME_PROMPT.en.md'] = (Path(__file__).resolve().parents[1]/'assets/resume-prompt.en.md').read_bytes()
        payload['MANIFEST.json'] = encode({k:digest(v) for k,v in payload.items()})
    private_values = [v.encode() for k,v in os.environ.items() if any(w in k.upper() for w in ('TOKEN','SECRET','PRIVATE','PASSWORD','KEY')) and len(v) >= 12]
    require(not any(v in data for data in payload.values() for v in private_values), 'sensitive environment value in export payload; review/redact sources')
    # Build fully before publishing. Integrity detects byte changes, not malicious provenance.
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output.parent, prefix='.export-'); os.close(fd)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for k,v in sorted(payload.items()):
                z.writestr(k,v)
        with open(tmp, 'rb') as f:
            os.fsync(f.fileno())
        # Hard-link is an atomic no-overwrite publication on this filesystem.
        os.link(tmp, output)
    finally:
        os.unlink(tmp)
    return {'file':str(output), 'sha256':digest(output.read_bytes()), 'revision':s['revision'], 'missing':origin['missing'], 'external_requirements':s['external_requirements']}


def inspect_package(package):
    with zipfile.ZipFile(package) as z:
        infos=z.infolist()
        require(len(infos) <= 10000 and sum(i.file_size for i in infos) <= 100*1024*1024, 'package exceeds helper inspection limits')
        require(len({i.filename for i in infos}) == len(infos), 'duplicate archive names')
        for i in infos:
            require(safe(i.filename) and not stat.S_ISLNK(i.external_attr >> 16) and not i.is_dir(), 'unsafe archive member')
        data={i.filename:z.read(i) for i in infos}
    manifest=json.loads(data['MANIFEST.json'])
    require(set(manifest) == set(data)-{'MANIFEST.json'}, 'manifest coverage mismatch')
    require(all(digest(data[k]) == v for k,v in manifest.items()), 'portable checksum mismatch')
    s=validate(json.loads(data['state.json'])); origin=json.loads(data['ORIGIN.json'])
    require(s['schema_version']==2 and origin['format']=='graph-loop-portable-v1', 'unsupported package version')
    require(all(origin[k]==s[k] for k in ('graph_id','lineage_id','graph_version','revision')) and origin['state_sha256']==digest(encode(s)), 'origin/state mismatch')
    allowed={'state.json','ORIGIN.json','PROGRESS.md','RESUME_PROMPT.en.md','MANIFEST.json'}|{'files/'+f['ref'] for f in s['tracked_files']}
    require(set(data)<=allowed, 'unrelated package member')
    return s,origin,data


def import_package(package, target, expected_graph, expected_lineage, current_store=None):
    s, origin, data = inspect_package(package)
    require(s['graph_id']==expected_graph and s['lineage_id']==expected_lineage, 'untrusted graph/lineage')
    target=Path(target)
    require(not target.exists(), 'never overwrite a target store; select an empty new directory')
    if current_store:
        current=load(current_store)
        require((current['graph_id'],current['lineage_id'])==(s['graph_id'],s['lineage_id']), 'current authority identity mismatch')
        require((s['graph_version'],s['revision'])==(current['graph_version'],current['revision']) and digest(encode(s))==digest(encode(current)), 'stale or divergent import; current authority wins')
    # Stage the whole copy; no extraction of arbitrary paths, no business execution.
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='.import-',dir=target.parent))
    try:
        for f in s['tracked_files']:
            key='files/'+f['ref']
            if key in data:
                require(digest(data[key])==f['sha256'], 'file hash disagrees with state')
                atomic(local(tmp,f['ref']),data[key])
        atomic(tmp/'state.json',envelope(s))
        # Source is retained read-only in imported-source; old export cannot become active implicitly.
        atomic(tmp/'imported-source.json',data['ORIGIN.json'])
        base=s['revision'];s=deepcopy(s);s['revision']+=1
        if s['lifecycle']['status']!='cancelled':
            s['lifecycle'].update(status='interrupted',reason='imported snapshot; explicit current resume and authority transfer required',resume_request_ref=None)
        s['import_checks']={'freshness':'matched-current' if current_store else 'unverified; current authority unavailable','source_authority':origin['source_authority'],'missing':origin['missing']}
        s['recovery']['authority_location']=str(target/'state.json')
        s['recovery']['retrieval']='Read '+str(target/'state.json')+'; export a new revision before handoff'
        commit(tmp,s,base)
        os.rename(tmp,target)
    finally:
        if tmp.exists():
            import shutil
            shutil.rmtree(tmp)
    return {'store':str(target),'revision':s['revision'],'blockers':preflight(s,target),'freshness':s['import_checks']['freshness']}


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    for cmd in ('show','check','save','pause','cancel','resume','export'):
        a=sub.add_parser(cmd);a.add_argument('store',type=Path)
        if cmd=='show':a.add_argument('--previous',action='store_true')
        if cmd=='save':a.add_argument('candidate',type=Path);a.add_argument('--expected',required=True,type=int)
        if cmd in {'pause','cancel'}:a.add_argument('--reason',required=True)
        if cmd=='resume':
            for k in ('request-ref','permission-ref','freshness-ref'):a.add_argument('--'+k,required=True)
        if cmd=='export':a.add_argument('output',type=Path)
    a=sub.add_parser('import');a.add_argument('package',type=Path);a.add_argument('target',type=Path);a.add_argument('--expected-graph',required=True);a.add_argument('--expected-lineage',required=True);a.add_argument('--current-store',type=Path)
    a=p.parse_args()
    try:
        if a.cmd=='show':result=load(a.store,a.previous)
        elif a.cmd=='check':result={'blockers':preflight(load(a.store),a.store)}
        elif a.cmd=='save':result=commit(a.store,json.loads(a.candidate.read_text()),a.expected)
        elif a.cmd in {'pause','cancel'}:result=suspend(a.store,a.reason,a.cmd=='cancel')
        elif a.cmd=='resume':result=resume(a.store,a.request_ref,a.permission_ref,a.freshness_ref)
        elif a.cmd=='export':result=export(a.store,a.output)
        else:result=import_package(a.package,a.target,a.expected_graph,a.expected_lineage,a.current_store)
        print(json.dumps(result,indent=2,ensure_ascii=False));return 2 if a.cmd=='check' and result['blockers'] else 0
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        print('BLOCKED: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':
    sys.exit(main())
