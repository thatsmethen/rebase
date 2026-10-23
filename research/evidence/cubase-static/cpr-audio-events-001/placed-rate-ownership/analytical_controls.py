"""Supplied-state countermodels for rate ownership; no target or PCM execution."""
from pathlib import Path
import json, struct
HERE=Path(__file__).resolve().parent
def f32(v): return struct.unpack('<f',struct.pack('<f',v))[0]
def ordinary(owner_rate,builder_rate,reader_rate):
    # The latter two inputs deliberately are not operands of the recovered copy/store.
    return f32(owner_rate)
rows=[]
for label,owner,builder,reader,expected in [
 ('matching direct source',44100,44100,44100,44100),
 ('builder-only change',44100,48000,44100,44100),
 ('reader-period-only change',44100,44100,48000,44100),
 ('upstream prepared owner changes rate',48000,44100,44100,48000),
 ('direct source differs from both contexts',96000,44100,48000,96000),
]:
    actual=ordinary(owner,builder,reader);assert actual==expected
    rows.append(dict(case=label,owner_rate=owner,builder_rate=builder,reader_rate=reader,
                     output_rate=actual,output_bits=f'{struct.unpack("<I",struct.pack("<f",actual))[0]:08x}'))
# Inner per-file accessors copy the cluster format even when their original file differs.
assert ordinary(48000,44100,44100)==48000
rows.append(dict(case='mixed cluster',first_file_rate=44100,other_file_rate=48000,
                 inner_accessor_after_ctor=48000,inner_accessor_after_cluster_copy=44100,
                 outer_accessor_rate=44100,
                 meaning='A concrete differing-rate conversion can be internal to a cluster; no project-rate identity follows.'))
rows.append(dict(case='cached processed stream',serialized_file_rate=44100,prepared_reader_owner_rate=48000,
                 output_rate=48000,
                 meaning='This supplied state is not ruled out by the direct-cluster proof; cache/provider lifecycle must be bound.'))
assert len(rows)==7
out=dict(passed=True,control_count=len(rows),cases=rows,target_execution=False,
         evidence_class='Analytical supplied-state discriminators, not observed hosted states or audio samples',
         limits='Only recovered rate-field copy/overwrite dependencies are modeled. No backend identity, rate conversion, reset behavior, scheduling, PCM or whole-host conformance is tested.')
with (HERE/'analytical-controls.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(dict(passed=True,controls=len(rows))))
