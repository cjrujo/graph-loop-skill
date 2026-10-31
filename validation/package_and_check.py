#!/usr/bin/env python3
"""Rebuild rc3 skill/review ZIPs and verify references, archive bytes and per-file hashes.
Standard library only. Test reports are required; negative fixtures intentionally remain invalid.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

BASE=Path(__file__).resolve().parents[1]
V=BASE/'validation'
ARCHIVES={'graph-loop.zip','graph-loop-review-bundle.zip'}
GENERATED={'release-manifest.json','validation/source-manifest.json','validation/package-check.json','validation/archive-manifest.json'}


def need(ok,msg):
    if not ok:raise ValueError(msg)


def sha(data):return hashlib.sha256(data).hexdigest()


def safe(ref):
    p=PurePosixPath(ref)
    return bool(ref) and not p.is_absolute() and '..' not in p.parts and '\\' not in ref and not re.match(r'^[A-Za-z]:',ref)


def write_json(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def collect():
    out=[]
    for f in sorted(BASE.rglob('*')):
        need(not f.is_symlink(),'symlink in source')
        rel=f.relative_to(BASE).as_posix()
        if not f.is_file() or '__pycache__' in f.parts or f.suffix=='.pyc' or rel in GENERATED|ARCHIVES:
            continue
        need(safe(rel),'unsafe source path')
        need(not any(p.startswith('.') for p in Path(rel).parts),'hidden/private file in source')
        out.append(f)
    return out


def archive(name,files):
    path=BASE/name
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:
            info=zipfile.ZipInfo(f.relative_to(BASE).as_posix(),date_time=(2026,10,31,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
            z.writestr(info,f.read_bytes())
    with zipfile.ZipFile(path) as z:
        need(z.testzip() is None,'CRC failed')
        need(len(z.namelist())==len(set(z.namelist()))==len(files),'duplicate/missing archive entries')
        for f in files:
            ref=f.relative_to(BASE).as_posix();need(safe(ref),'unsafe member')
            need(z.read(ref)==f.read_bytes(),'archive/source byte mismatch')
            need(not stat.S_ISLNK(z.getinfo(ref).external_attr>>16),'archive symlink')
    return {'file':name,'files':len(files),'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}


def main():
    for name,count in [('results.json',20),('recovery-results.json',18)]:
        r=json.loads((V/name).read_text());need(r['successful'] and r['tests_run']==count and r['failures']==r['errors']==0,'validation not successful: '+name)
    need((V/'skill-creator-check.log').read_text().strip()=='Skill is valid!','skill-creator result absent')
    if (V/'isolated-package-check.json').exists():
        isolated=json.loads((V/'isolated-package-check.json').read_text())
        need(isolated['success'], 'isolated standard package check failed')
        if (BASE/'graph-loop.zip').exists():
            need(isolated['standard_zip_sha256']==sha((BASE/'graph-loop.zip').read_bytes()), 'isolated check is for a different standard ZIP; rerun it')
    core=(BASE/'graph-loop/SKILL.md').read_text()
    need(core.startswith('---\nname: graph-loop\n') and 'version: "1.0.0-rc3"' in core,'version/name mismatch')
    need(len(core.splitlines())<500,'core disclosure too large')
    need((BASE/'resume-prompt.en.md').read_bytes()==(BASE/'graph-loop/assets/resume-prompt.en.md').read_bytes(),'resume prompts differ')
    baseline=BASE.parents[1]/'english-revision/source'
    recorded=json.loads((V/'baseline-rc2-sha256.json').read_text())
    baseline_check='unavailable in extracted review copy; original-run evidence in baseline-unchanged.json'
    if baseline.is_dir():
        actual={f.relative_to(baseline).as_posix():sha(f.read_bytes()) for f in baseline.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
        need(actual==recorded,'frozen rc2 changed')
        baseline_check=f'{len(actual)} original baseline files byte-identical'
        write_json(V/'baseline-unchanged.json',{'success':True,'files':len(actual),'method':'full SHA-256 map equality against pre-work baseline capture','excluded':'__pycache__ only'})
    sources=collect();links=0
    for f in sources:
        if f.suffix!='.md':continue
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',f.read_text()):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('#'):continue
            path=(f.parent/target.split('#')[0]).resolve()
            need(path.is_relative_to(BASE),'local link escapes package: '+str(f.relative_to(BASE)))
            need(path.exists() or path.relative_to(BASE).as_posix() in GENERATED|ARCHIVES,'broken link: '+str(f.relative_to(BASE))+' -> '+target)
            links+=1
    private_values=[v.encode() for k,v in os.environ.items() if any(w in k.upper() for w in ('TOKEN','KEY','SECRET','PASSWORD','PRIVATE')) and len(v)>=12]
    # Include nested ZIP members in the limited exact-match secret scan, never print values.
    scanned=0
    for f in sources:
        data=f.read_bytes();need(not any(v in data for v in private_values),'private env value in source');scanned+=1
        if f.suffix=='.zip':
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    need(safe(n),'unsafe nested ZIP path')
                    need(not any(v in z.read(n) for v in private_values),'private env value in nested ZIP');scanned+=1
    need(all(not safe(x) for x in ('../x','/absolute','a/../../b','C:/x','a\\b')),'path rejection probe failed')
    manifest={f.relative_to(BASE).as_posix():sha(f.read_bytes()) for f in sources}
    write_json(V/'source-manifest.json',manifest)
    check={'success':True,'candidate':'1.0.0-rc3','core_lines':len(core.splitlines()),'source_files':len(sources),'local_markdown_links_checked':links,'secret_scan':'exact secret-like environment-value matching in sources/nested ZIPs; no matches; not universal secret detection','scanned_files_and_nested_members':scanned,'baseline':baseline_check,'archive_validation':'CRC, unique safe members, no symlinks, every member byte-compared against source','source_manifest':'SHA-256 for every payload source; manifest/check files excluded from their own hashes','scope':'local structure/files/archive checks, not host activation or model adherence'}
    write_json(V/'package-check.json',check)
    skill=[f for f in sources if f.is_relative_to(BASE/'graph-loop')]
    archives=[archive('graph-loop.zip',skill),archive('graph-loop-review-bundle.zip',sources+[V/'source-manifest.json',V/'package-check.json'])]
    write_json(V/'archive-manifest.json',archives)
    release_files=sources+[V/'source-manifest.json',V/'package-check.json',V/'archive-manifest.json']+[BASE/r['file'] for r in archives]
    release={'candidate':'1.0.0-rc3','status':'unpublished revision candidate; independent CEO review pending','files':{f.relative_to(BASE).as_posix():sha(f.read_bytes()) for f in release_files},'note':'All payload/source/generated archive hashes except this manifest itself. The review ZIP contains payload plus source-manifest and package-check; archive-manifest and release-manifest remain alongside to avoid self-reference.'}
    write_json(BASE/'release-manifest.json',release)
    for ref,hash_ in release['files'].items():need(sha((BASE/ref).read_bytes())==hash_,'release hash mismatch')
    with zipfile.ZipFile(BASE/'graph-loop-review-bundle.zip') as z:
        inside=json.loads(z.read('validation/source-manifest.json'))
        need(set(inside)==set(z.namelist())-{'validation/source-manifest.json','validation/package-check.json'},'review manifest coverage mismatch')
        for ref,h in inside.items():need(sha(z.read(ref))==h,'review per-file hash mismatch')
    print(json.dumps({'checks':check,'archives':archives,'release_hashes_verified':len(release['files'])},indent=2))


if __name__=='__main__':main()
