#!/usr/bin/env python3
"""Read-only independent APP002 GUI exchange audit; writes one new JSON report."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
import audio_probe
BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'gui-exchange-comparison.json'
if OUTPUT.exists():
    raise SystemExit('Refusing to overwrite existing evidence')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record(path):
    data = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(data), 'sha256': sha(data)}


inputs = {}
media = []

def canonical(value, package):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == 'id':
                continue
            if key == 'mediaPath':
                path = (package / item).resolve()
                if not path.is_relative_to(package.resolve()):
                    raise ValueError('Escaping media path')
                info = record(path)
                inputs[info['path']] = info
                media.append({'package': package.name, 'declared_path': item, **info})
                result['mediaSHA256'] = info['sha256']
            else:
                result[key] = canonical(item, package)
        return result
    if isinstance(value, list):
        return [canonical(item, package) for item in value]
    return value


def differences(a, b, path='$'):
    result = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                result.append({'path': path+'.'+key, 'source': a.get(key), 'roundtrip': b.get(key), 'kind':'missing_key'})
            else:
                result.extend(differences(a[key], b[key], path+'.'+key))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            result.append({'path':path,'source_length':len(a),'roundtrip_length':len(b)})
        for i, (left, right) in enumerate(zip(a,b)):
            result.extend(differences(left,right,f'{path}[{i}]'))
    elif a != b or isinstance(a,bool) != isinstance(b,bool):
        result.append({'path':path,'source':a,'roundtrip':b})
    return result


projects = []
for name in ('Exchange Check.rebaseproj', 'Exchange Roundtrip.rebaseproj'):
    package = BASE/name
    path = package/'Project.json'
    info = record(path); inputs[info['path']] = info
    projects.append(canonical(json.loads(path.read_text()), package))
semantic_diff = differences(*projects)
audio = audio_probe.compare(BASE/'Timing and Automation.wav', BASE/'Exchange Roundtrip.wav')
for name in ('Timing and Automation.wav', 'Exchange Roundtrip.wav', 'Exchange Check.dawproject'):
    info=record(BASE/name); inputs[info['path']]=info
schema = ROOT/'research/references/dawproject/Project.xsd'
schema_record=record(schema); inputs[schema_record['path']]=schema_record
expected_schema_sha='58e2fd9864772850aac3eab1f3de8693857dc5384df6d29fbc320ae1de2347cc'
assert schema_record['sha256']==expected_schema_sha
archive_records=[]
with ZipFile(BASE/'Exchange Check.dawproject') as archive:
    assert len(archive.namelist())==len(set(archive.namelist())), 'Duplicate archive names'
    bad_crc=archive.testzip()
    assert bad_crc is None, bad_crc
    for entry in archive.infolist():
        data=archive.read(entry)
        archive_records.append({'name':entry.filename,'bytes':len(data),'sha256':sha(data),'crc32':f'{entry.CRC:08x}'})
    project_xml=archive.read('project.xml')
    command=['/usr/bin/xmllint','--nonet','--noout','--schema',str(schema),'-']
    schema_validation=subprocess.run(command,input=project_xml,capture_output=True)
    xml=ET.fromstring(project_xml)
    arrangement=xml.find('Arrangement'); lanes=arrangement.find('Lanes')
    assert lanes.attrib['timeUnit']=='seconds'
    assert arrangement.attrib['comment'].startswith('Rebase.sampleRate=')
    projection={'name':arrangement.attrib['name'],
        'sampleRate':float(arrangement.attrib['comment'].split('=',1)[1]),
        'tempo':float(xml.find('Transport/Tempo').attrib['value']),
        'tempoMap':{'events':[]},'signatureMap':{'events':[]},'tracks':[]}
    tempos=arrangement.find('TempoAutomation'); signatures=arrangement.find('TimeSignatureAutomation')
    assert tempos.attrib['timeUnit']=='beats' and tempos.attrib['unit']=='bpm'
    assert signatures.attrib['timeUnit']=='beats'
    for point in tempos.findall('RealPoint'):
        assert point.attrib['interpolation']=='hold'
        projection['tempoMap']['events'].append({'beat':float(point.attrib['time']),'bpm':float(point.attrib['value']),'curve':'jump'})
    for point in signatures.findall('TimeSignaturePoint'):
        projection['signatureMap']['events'].append({'beat':float(point.attrib['time']),
            'numerator':int(point.attrib['numerator']),'denominator':int(point.attrib['denominator'])})
    lane_by_track={lane.attrib['track']:lane for lane in lanes.findall('Lanes')}
    assert len(lane_by_track)==len(lanes.findall('Lanes'))
    for track in xml.findall('Structure/Track'):
        channel=track.find('Channel'); volume=channel.find('Volume'); pan=channel.find('Pan'); mute=channel.find('Mute')
        assert channel.attrib['role']=='regular' and track.attrib['contentType']=='audio'
        assert volume.attrib['unit']=='decibel' and pan.attrib['unit']=='normalized'
        assert channel.attrib['solo'] in ('true','false') and mute.attrib['value'] in ('true','false')
        result={'name':track.attrib['name'],'gainDB':float(volume.attrib['value']),
            'pan':float(pan.attrib['value'])*2-1, 'isSolo':channel.attrib['solo']=='true',
            'isMuted':mute.attrib['value']=='true','timeBase':'seconds','clips':[],'automation':[]}
        track_lanes=lane_by_track.pop(track.attrib['id'])
        for clip in track_lanes.findall('Clips/Clip'):
            source=clip.find('Audio'); source_file=source.find('File')
            assert clip.attrib['contentTimeUnit']=='seconds' and source.attrib['timeUnit']=='seconds'
            assert int(source.attrib['channels'])==int(channel.attrib['audioChannels'])==2
            assert int(source.attrib['sampleRate'])==48000 and float(source.attrib['duration'])==12
            media_sha=sha(archive.read(source_file.attrib['path']))
            result['clips'].append({'name':clip.attrib['name'],'position':float(clip.attrib['time']),
                'duration':float(clip.attrib['duration']),'sourceOffset':float(clip.attrib['playStart']),
                'timeBase':'seconds','mediaSHA256':media_sha})
        for points in track_lanes.findall('Points'):
            assert points.attrib['timeUnit']=='seconds'
            target=points.find('Target').attrib['parameter']
            if target==volume.attrib['id']:
                parameter='gainDB'; assert points.attrib['unit']=='decibel'
            else:
                assert target==pan.attrib['id'] and points.attrib['unit']=='normalized'
                parameter='pan'
            lane={'parameter':parameter,'isReadEnabled':True,'points':[]}
            for point in points.findall('RealPoint'):
                interpolation={'linear':'linear','hold':'step'}[point.attrib['interpolation']]
                value=float(point.attrib['value'])
                lane['points'].append({'time':float(point.attrib['time']),'value':value if parameter=='gainDB' else value*2-1,
                                      'interpolation':interpolation})
            result['automation'].append(lane)
        projection['tracks'].append(result)
    assert not lane_by_track
xml_diff=differences(projects[0],projection)
unchanged=[]
for relative, before in inputs.items():
    after=record(ROOT/relative)
    if after!=before: unchanged.append({'before':before,'after':after})
passed=(audio['status']=='pass' and audio['audio_payload_bytes_equal'] and not semantic_diff and
        not xml_diff and schema_validation.returncode==0 and not unchanged)
report={'id':'APP002-GUI-EXCHANGE-INDEPENDENT-COMPARISON','at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'pass' if passed else 'mismatch','target_executed':False,'native_Cubase_runtime_comparison':False,
    'scope':'Independent read-only comparison of supplied GUI-produced Rebase export/import/render artifacts. This auditor did not operate the GUI. No Rebase model/serializer/renderer code imported or executed.',
    'audio':audio,
    'supported_project_semantics':{'status':'pass' if not semantic_diff else 'mismatch','differences':semantic_diff,
        'normalization':'Remove only object id fields; substitute complete media-file SHA256 for mediaPath. Preserve every other manifest key, scalar, list order, track/clip name, map event, curve/interpolation, automation read state, position/duration/source offset and timebase.',
        'canonical_source':projects[0],'canonical_roundtrip':projects[1],
        'source_canonical_sha256':sha(json.dumps(projects[0],sort_keys=True,separators=(',',':')).encode()),
        'roundtrip_canonical_sha256':sha(json.dumps(projects[1],sort_keys=True,separators=(',',':')).encode())},
    'xml_independent_projection':{'status':'pass' if not xml_diff else 'mismatch','differences':xml_diff,
        'checks':'Separately parse exported XML: structure/lanes by track IDs, embedded audio hashes, seconds clips, dB volume, normalized pan converted to signed range, hold/linear point curves, beat-based jump tempo/signature maps. Compare these represented values to source manifest.',
        'scope_notes':['All source clips/tracks are seconds-based after the GUI change. Musical anchoring is not preserved or tested by this exchange.',
                       'Arrangement comment Rebase.sampleRate is an application-specific convention; XSD acceptance does not make it interoperable sample-rate semantics.',
                       'Present gain/pan automation lanes are enabled in this source; no disabled-lane exchange claim.']},
    'schema_validation':{'status':'pass' if schema_validation.returncode==0 else 'fail','schema':schema_record,
        'pinned_review':'research/evidence/cubase-static/dawproject-001/application-review.json',
        'project_xml_sha256':sha(project_xml),'command':command,'stdin':'project.xml exact bytes read from archive',
        'exit_code':schema_validation.returncode,'stdout':schema_validation.stdout.decode(),'stderr':schema_validation.stderr.decode()},
    'archive':{'crc_check':'pass','members':archive_records},'media_files':media,'inputs':list(inputs.values()),
    'inputs_unchanged_during_audit':not unchanged,'changed_inputs':unchanged,
    'checker':record(Path(__file__)),'audio_probe':record(ROOT/'scripts/audio_probe.py'),
    'limitations':['Exact app roundtrip and schema validity do not establish Cubase runtime behavior or another DAW\'s rendering, pan law, automation interpretation or import compatibility.',
                   'Compared actual stored-channel PCM payload with zero tolerance; no alignment, gain fitting, resampling, channel reassignment or silence trimming.']}
OUTPUT.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'audio_payload_exact':audio['audio_payload_bytes_equal'],
                 'frames':audio['reference']['frames'],'payload_sha256':audio['reference']['data_sha256'],
                 'manifest_differences':semantic_diff,'xml_projection_differences':xml_diff,
                 'xsd_exit_code':schema_validation.returncode,'report':str(OUTPUT)},indent=2))
raise SystemExit(0 if passed else 1)
