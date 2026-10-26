#!/usr/bin/env python3
"""Private package audit; matched private values are never printed or recorded."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


def main():
    from audit_context import load, decode
    context = load()
    from types import SimpleNamespace
    a = SimpleNamespace(zip=context.archive, output=context.output/'zip-audit', commit=context.commit)
    a.output.mkdir(parents=True, exist_ok=False); a.output.chmod(0o700)
    c=decode(context.privacy_rules.read_bytes())
    extra=decode(context.additional_privacy_rules.read_bytes())
    literals=[(f'known_private_literal_{i+1:02}',r['source']) for i,r in enumerate(c['literal_replacements_longest_first'])]
    literals += [(f'additional_temp_prefix_{i+1:02}',r['exact_prefix']) for i,r in enumerate(extra['additional_exact_prefix_replacements'])]
    regexes=[]
    for i,r in enumerate(c['regex_replacements_after_protection']):
        flags=0
        for name in r['flags']: flags|=getattr(re,name)
        regexes.append((f'known_private_regex_{i+1:02}',re.compile(r['pattern'],flags)))
    protected=[re.compile(r,re.I) for r in c['protected_current_repository_url_patterns']]
    secret_rules=[
        ('private_key',r'-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----'),
        ('github_token',r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
        ('aws_access_key',r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
        ('slack_token',r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
        ('provider_api_key',r'\b(?:sk-[A-Za-z0-9_-]{32,}|AIza[0-9A-Za-z_-]{35})\b'),
        ('credential_url',r'https?://[^\s/@:]+:[^\s/@]+@[^\s/]+'),
        ('jwt',r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{15,}\b')]
    secrets=[(name,re.compile(pattern)) for name,pattern in secret_rules]
    source_paths=re.compile(r'(?:[A-Za-z]:[\\/]a[\\/]rebase[\\/]rebase|[A-Za-z]:[\\/]Users[\\/][^\s\x00"<>]{1,160}|/(?:Users|home)/[^/\s\x00"<>]{1,100})',re.I)
    blockers=[];reviews=[];checked=[];seen=set()
    def record(collection,path,category,encoding,count):
        if count: collection.append({'path':path,'category':category,'encoding':encoding,'occurrences':count})
    def scan(path,data):
        low=data.lower()
        for category,value in literals:
            for encoding in ('utf-8','utf-16le'):
                needle=value.encode(encoding).lower()
                record(blockers,path,category,encoding,low.count(needle))
        # Both UTF-16 byte alignments are inspected for embedded PE/assembly strings.
        texts=[('utf-8',data.decode('utf-8','ignore'))]
        if b'\0' in data:
            texts.extend((f'utf-16le-offset-{offset}',data[offset:].decode('utf-16le','ignore')) for offset in (0,1))
        for encoding,text in texts:
            protected_text=text
            for rule in protected:protected_text=rule.sub('<CURRENT_PUBLIC_REPOSITORY_URL>',protected_text)
            for category,rule in regexes:record(blockers,path,category,encoding,sum(1 for _ in rule.finditer(protected_text)))
            for category,rule in secrets:record(blockers,path,category,encoding,sum(1 for _ in rule.finditer(text)))
            record(reviews,path,'source_or_host_path',encoding,sum(1 for _ in source_paths.finditer(text)))
    with zipfile.ZipFile(a.zip) as z:
        infos=z.infolist()
        if z.testzip() is not None:raise RuntimeError('ZIP CRC failure')
        for info in infos:
            name=info.filename;parts=PurePosixPath(name).parts
            if (info.is_dir() or not name.startswith('Rebase/') or '\\' in name or ':' in name
                    or '..' in parts or name.startswith('/') or name.casefold() in seen):
                raise RuntimeError('Unsafe, duplicate or unexpected archive path')
            seen.add(name.casefold())
            if stat.S_ISLNK(info.external_attr >> 16):raise RuntimeError('Archive symbolic link')
            if info.flag_bits & 1:raise RuntimeError('Encrypted archive entry')
            if name.lower().endswith(('.pdb','.dSYM'.lower())):record(blockers,name,'debug_file','filename',1)
        manifest=decode(z.read('Rebase/package-manifest.json'))
        if manifest.get('schema')!='rebase.windows-package.v1' or manifest.get('commit')!=a.commit:
            raise RuntimeError('Package manifest identity mismatch')
        expected={item['path']:item for item in manifest['files']}
        if len(expected)!=len(manifest['files']):raise RuntimeError('Duplicate manifest entry')
        actual={i.filename.removeprefix('Rebase/') for i in infos}-{'package-manifest.json'}
        if actual!=set(expected):raise RuntimeError('Package manifest does not cover exact ZIP contents')
        required={'Rebase.exe','rebase-session.exe','RebaseWindowsAudio.dll','Rebase.runtimeconfig.json',
                  'Examples/Rebase Preview.rebaseproj/Project.json','ThirdPartyNotices/sources.json'}
        if not required.issubset(actual):raise RuntimeError('Required application content missing')
        for info in infos:
            data=z.read(info);path=info.filename.removeprefix('Rebase/')
            sha=hashlib.sha256(data).hexdigest()
            if path in expected and (len(data)!=expected[path]['bytes'] or sha!=expected[path]['sha256']):
                raise RuntimeError('Package manifest content mismatch')
            scan(info.filename,info.filename.encode('utf-8'));scan(info.filename,data)
            checked.append({'path':info.filename,'bytes':len(data),'sha256':sha})
    report={'schema':'rebase.private-windows-package-audit.v1','zip_name':a.zip.name,'zip_bytes':a.zip.stat().st_size,
            'zip_sha256':hashlib.sha256(a.zip.read_bytes()).hexdigest(),'commit':a.commit,
            'manifest_exact_coverage':True,'manifest_all_hashes_match':True,'crc_verified':True,
            'file_count':len(checked),'uncompressed_bytes':sum(r['bytes'] for r in checked),'blockers':blockers,'reviews':reviews,
            'scope':'Known personal literals/regexes and credential patterns in UTF-8 and both UTF-16LE alignments; not a universal disclosure guarantee',
            'files':checked}
    (a.output/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    summary={k:report[k] for k in ['zip_name','zip_bytes','zip_sha256','commit','manifest_exact_coverage','manifest_all_hashes_match','crc_verified','file_count','uncompressed_bytes']}
    summary.update(blocker_records=len(blockers),review_records=len(reviews),blocker_categories=dict(Counter(r['category'] for r in blockers)),review_categories=dict(Counter(r['category'] for r in reviews)))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    return 0 if not blockers else 1


if __name__=='__main__':raise SystemExit(main())
