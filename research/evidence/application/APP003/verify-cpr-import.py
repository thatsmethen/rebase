#!/usr/bin/env python3
"""Read-only comparison of a GUI-imported package against the independent v09 probe.

No target code runs. Output is exclusive-create JSON; packages are never modified.
"""
from pathlib import Path
import argparse, datetime, hashlib, json

def digest(data): return hashlib.sha256(data).hexdigest()
def walk(v):
    if isinstance(v, dict):
        yield v
        for a in v.values(): yield from walk(a)
    elif isinstance(v, list):
        for a in v: yield from walk(a)

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('fixture', type=Path)
    cli.add_argument('package', type=Path)
    cli.add_argument('--out', required=True, type=Path)
    cli.add_argument('--allow-project-name-change', action='store_true')
    args=cli.parse_args()
    pins=[]
    def read(p):
        before=p.stat(); data=p.read_bytes(); after=p.stat()
        assert (before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino), str(p)
        pins.append({'path':str(p),'bytes':len(data),'sha256':digest(data)})
        return data
    fixture=json.loads(read(args.fixture)); source=read(Path(fixture['source']))
    assert digest(source)==fixture['sha256']
    original=read(args.package/'Compatibility/CPR/Original.cpr')
    assert original==source
    report=json.loads(read(args.package/'Compatibility/CPR/ImportReport.json'))
    project=json.loads(read(args.package/'Project.json'))
    assert report['sourceSHA256']==digest(source) and report['sourceByteCount']==len(source)
    assert report['sourceName']==Path(fixture['source']).name and report['schemaVersion']==1
    objects={v['body_offset']:v for v in walk(fixture) if v.get('kind')=='object'}
    for v in report['nativeObjects']:
        p=v['payloadOffset']; n=v['payloadByteCount']; independent=objects[p]
        assert digest(source[p:p+n])==v['payloadSHA256']==independent['body_sha256']
        for a,b in [('className','class'),('version','version'),('declarationOffset','class_declaration_offset'),('identityOffset','size_offset'),('objectOffset','offset'),('payloadByteCount','body_bytes')]:
            assert v[a]==independent[b],(a,v,independent)
    roots=fixture['roots']
    assert len(report['sections'])==len(roots)
    for r,f in zip(report['sections'],roots):
        for a,b in [('name','name'),('className','class'),('rootOffset','offset'),('archiveOffset','archive_start'),('archiveByteCount','archive_bytes')]: assert r[a]==f[b]
        assert r['archiveSHA256']==digest(source[f['archive_start']:f['archive_start']+f['archive_bytes']])
    kinds={'MFolderTrack':'Folder','MDeviceTrackEvent':'Device / routing','MAudioTrackEvent':'Audio','MMidiTrackEvent':'MIDI','MInstrumentTrackEvent':'Instrument','MSamplerTrackEvent':'Sampler','MDrumTrackEvent':'Drum'}
    tracks=[v for v in walk(fixture) if v.get('class') in kinds and v.get('kind')=='object' and 'node' in v]
    expected=[(v['node']['decoded']['name']['text'],kinds[v['class']],v['class'],v['offset']) for v in tracks]
    assert [(v['name'],v['kind'],v['nativeClassName'],v['sourceOffset']) for v in report['recoveredTracks']]==expected
    imported=[v for v in report['recoveredTracks'] if v['kind']=='Audio']
    assert all('importedTrackID' not in v for v in report['recoveredTracks'] if v['kind']!='Audio')
    assert [(v['name'],v['id']) for v in project['tracks']]==[(v['name'],v['importedTrackID']) for v in imported]
    assert project['sampleRate']==48000 and report['unsupported']
    for t in project['tracks']:
        assert t['gainDB']==0 and t['pan']==0 and t['isMuted'] is False and t['isSolo'] is False
        assert t['timeBase']=='seconds' and not t['clips'] and not t['automation']
    signatures=project['signatureMap']['events']; assert len(signatures)==1
    assert signatures[0]['beat']==0 and signatures[0]['numerator']==4 and signatures[0]['denominator']==4
    tempos=[v['decoded'] for v in walk(fixture) if v.get('class')=='MTempoTrackEvent' and 'decoded' in v]
    assert len(tempos)==1
    expected_bpm=tempos[0]['fixed_bpm_f32'] if tempos[0]['fixed_enabled_u16'] else 120
    events=project['tempoMap']['events']; assert len(events)==1
    assert project['tempo']==events[0]['bpm']==expected_bpm and events[0]['beat']==0 and events[0]['curve']=='jump'
    default_text=' '.join(report['applicationDefaults'])
    assert '48 kHz and 4/4 are application defaults' in default_text
    assert ('120 BPM is an application default' in default_text)==(not tempos[0]['fixed_enabled_u16'])
    baseline=report['recoveredProject']
    differences=[k for k in set(project)|set(baseline) if project.get(k)!=baseline.get(k)]
    assert not differences or (args.allow_project_name_change and differences==['name']), differences
    paths=[v for v in walk(fixture) if 'filename' in v and 'directory' in v and 'consumed_exactly' in v]
    unresolved=' '.join(v['detail'] for v in report['unsupported'] if v['category']=='Unresolved audio source')
    for p in paths: assert p['filename']['text'] in unresolved and p['directory']['text'] in unresolved
    result={'id':'APP003-INDEPENDENT-CPR-PACKAGE-CHECK','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'passed','method':'Read-only independent Python comparison against preexisting structurally decoded v09 fixture and exact original bytes. GUI action provenance is parent-owned; this check only verifies resulting persisted files.','verifier_sha256':digest(Path(__file__).read_bytes()),'input_pins':pins,'checks':{'preserved_original_byte_identical':True,'reported_native_object_ranges_verified':len(report['nativeObjects']),'container_sections_verified':len(roots),'ordered_track_name_class_offset_matches':len(expected),'imported_audio_track_names':[v['name'] for v in imported],'recovered_audio_clips':0,'defaults_explicit':True,'tempo_mode_in_source':tempos[0]['selected_mode'],'project_tempo_bpm':expected_bpm,'unresolved_media_descriptors_checked':len(paths),'project_differences_from_import_baseline':differences},'limits':['No reference target execution or runtime comparison.','Only names/empty audio tracks and supported fixed BPM are recovered; metadata tags do not establish active time maps, track state or media playback.','Saved file hashes describe this checkpoint; later edits may change Project.json.']}
    with args.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(args.out); print(digest(args.out.read_bytes()))
if __name__=='__main__': main()
