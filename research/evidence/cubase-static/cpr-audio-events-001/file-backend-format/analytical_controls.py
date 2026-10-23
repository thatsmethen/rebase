"""Independent supplied-value controls. Executes no target bytes."""
from pathlib import Path
import json,struct
H=Path(__file__).resolve().parent
def signature(b):
 if len(b)<15:return None
 if b[:4]==b'RIFF' and b[8:12]==b'WAVE':
  if b[12:15]==b'fmt':return '0x104fecbb8'
  if len(b)>=16 and b[12:16]==b'bext':return 'return from 0x10031f7d8'
 if len(b)>=16 and b[:4]==b'RF64' and b[8:16]==b'WAVEds64':return '0x10502d9f8'
 return None
sig=[]
for name,b,expected in [('fmt15',b'RIFF\0\0\0\0WAVEfmt','0x104fecbb8'),('fmt16',b'RIFF\0\0\0\0WAVEfmt ','0x104fecbb8'),('fmt nonspace is still only signature',b'RIFF\0\0\0\0WAVEfmtX','0x104fecbb8'),('short14',b'RIFF\0\0\0\0WAVEfm',None),('first chunk JUNK',b'RIFF\0\0\0\0WAVEJUNK',None),('RF64',b'RF64\0\0\0\0WAVEds64','0x10502d9f8'),('RF64 short',b'RF64\0\0\0\0WAVEds6',None),('BWF',b'RIFF\0\0\0\0WAVEbext','return from 0x10031f7d8'),('RIFX',b'RIFX\0\0\0\0WAVEfmt ',None)]:
 value=signature(b);assert value==expected;sig.append(dict(name=name,bytes_hex=b.hex(),expected=expected))
def select(entries):
 for name,type_match,probe,creator in entries:
  if (type_match or probe) and creator is not None:return name
 return None
cases=[('first-success',[('A',True,False,'handleA'),('B',True,False,'handleB')],'A'),('null-creator-continues',[('A',True,False,None),('B',True,False,'handleB')],'B'),('probe-match',[('A',False,True,'handleA')],'A'),('no-match',[('A',False,False,'handleA')],None),('priority-changes-selection',[('plugin',True,False,'p'),('built-in',True,False,'w')],'plugin')]
registry=[]
for name,entries,expected in cases:assert select(entries)==expected;registry.append(dict(name=name,entries=entries,expected=expected))
metadata=[]
for bits,channels,rate,header_align in [(24,2,44100,6),(24,1,48000,3),(16,2,32000,4),(8,1,8000,1),(20,2,44100,6),(24,2,44100,8)]:
 raw=struct.pack('<HHIIHH',1,channels,rate,rate*header_align,header_align,bits)
 tag,ch,rate,avg,align,b=struct.unpack('<HHIIHH',raw)
 n=(b+7)//8
 row=dict(tag=tag,bits=b,channels=ch,rate=rate,header_block_alignment=align,kind=0 if b<9 else 1,stored_sample_bits=n*8,stored_frame_bytes=n*ch,stored_rate_double=float(rate))
 assert row['stored_frame_bytes']==((bits+7)//8)*channels
 metadata.append(row)
assert metadata[-1]['stored_frame_bytes']==6 and metadata[-1]['header_block_alignment']==8
result=dict(passed=True,target_executed=False,signature_controls=sig,registry_controls=registry,pcm_metadata_controls=metadata,scope='Analytical source-derived branch/value controls only; not native execution, no actual backend selection, no PCM read or malformed-WAV acceptance claim.',limitations=['Registry controls model only the first pass; filesystem-type fallback is recorded separately in the finding.','Metadata controls assume successful primitive reads and plain PCM tag1; extended/compressed tags, errors and malformed files remain outside the model.','The signature recognizer is deliberately weaker than full file validation.'])
with (H/'analytical-controls.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(len(sig),len(registry),len(metadata))
