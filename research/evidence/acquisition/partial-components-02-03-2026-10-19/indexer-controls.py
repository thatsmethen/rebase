"""Defect-injection controls for our static XML/hash indexer, not Cubase tests."""
import importlib.util
import json
import pathlib
import plistlib
import shutil
import tempfile

root = pathlib.Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('indexer', root / 'scripts/index_vst_representations.py')
indexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexer)
source = root / 'research/targets/downloads/partial-components-03/components/Cubase 15.app/Contents/VST3/Cubase Plug-in Set.vst3/Contents'
verification = pathlib.Path(__file__).parent / 'plugin-set-code-verification'
name = 'Resources/VST XMLs/TestGenerator/Generic 8 Cells.xml'
raw = (source / name).read_bytes()
results = []

def check(name, condition):
    assert condition, name
    results.append({'control': name, 'passed': True})

with tempfile.TemporaryDirectory(prefix='vst-indexer-control-') as directory:
    contents = pathlib.Path(directory)
    target = contents / name
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    (contents / '_CodeSignature').mkdir()
    seal = contents / '_CodeSignature/CodeResources'
    shutil.copyfile(source / '_CodeSignature/CodeResources', seal)
    pristine = indexer.analyze(contents, verification)
    check('pristine available resource matches; missing resources remain explicit',
          not pristine['failures'] and pristine['counts']['complete_resources'] == 1
          and not pristine['all_sealed_xml_recovered_and_parsed'])
    target.write_bytes(raw.replace(b'automatically', b'manually', 1))
    changed = indexer.analyze(contents, verification)
    check('parseable XML comment mutation fails signed resource hash',
          any('resource hash mismatch' in f for f in changed['failures'])
          and changed['counts']['parsed_xml'] == 1)
    target.write_bytes(raw)
    modifiedseal = plistlib.loads(seal.read_bytes())
    modifiedseal['files2'][name]['hash2'] = bytes(32)
    seal.write_bytes(plistlib.dumps(modifiedseal))
    changedseal = indexer.analyze(contents, verification)
    check('modified resource seal fails both CodeDirectory resource slots',
          len([f for f in changedseal['failures'] if 'resource slot mismatch' in f]) == 2)

generic = indexer.representation(raw)['representations'][0]['pages'][0]['cells']
check('blank cells retained; frequency is cell3 rather than compressed cell2',
      len(generic) == 8 and 'parameterID' not in generic[1]['layers'][0]['attributes']
      and generic[2]['layers'][0]['attributes']['parameterID'] == '1')
s6 = indexer.representation((source / 'Resources/VST XMLs/TestGenerator/S6.xml').read_bytes())
bypass = s6['representations'][0]['pages'][0]['cells'][3]['layers']
check('multiple layer bindings to one parameter preserved',
      bypass[0]['attributes']['parameterID'] == bypass[1]['attributes']['parameterID'] == '10000001')
for name, data, function in [
    ('truncated XML rejected', b'<vstXML><plugin', indexer.representation),
    ('custom entity declaration rejected', b'<!ENTITY surprise "x"><vstXML/>', indexer.representation),
    ('truncated CodeDirectory rejected', b'\xfa\xde\x0c\x02', indexer.slot3),
]:
    try:
        function(data)
    except Exception:
        check(name, True)
    else:
        check(name, False)
output = {'scope': __doc__, 'indexer_sha256': indexer.sha((root / 'scripts/index_vst_representations.py').read_bytes()),
          'controls_sha256': indexer.sha(pathlib.Path(__file__).read_bytes()), 'results': results}
with pathlib.Path(__file__).with_name('indexer-controls.json').open('x') as f:
    json.dump(output, f, indent=2)
print(json.dumps(output, indent=2))
