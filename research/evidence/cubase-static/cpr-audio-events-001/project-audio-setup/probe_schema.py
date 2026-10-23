"""Bounded PArrangement v4 / PArrangeSetup v8 forward probe. No target execution.

A schema/custody instrument, not a general CPR importer or native runtime emulator.
Only scalar datum tags1/10 are admitted; the native reader has additional context-
dependent branches. Strings remain bounded carriers and other fields unnamed.
"""
from pathlib import Path
import sys, importlib.util, json, struct, hashlib, math
sys.dont_write_bytecode = True
H=Path(__file__).resolve().parent; R=H.parents[4]
spec=importlib.util.spec_from_file_location('prior_cpr_probe',R/'scripts/cpr_probe.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def digest(b): return hashlib.sha256(b).hexdigest()
def pin(path):
 b=path.read_bytes();return dict(path=str(path.relative_to(R)),bytes=len(b),sha256=digest(b))
def scalar(r,name):
 at=r.pos;value=r.take(8);tag=r.number('i')
 if tag not in (1,10):raise p.ProbeError('datum outside admitted scalar tags1/10')
 scale=r.take(8)
 return dict(name=name,offset=at,bytes=r.pos-at,value_bits=value.hex(),tag=tag,scalar_bits=scale.hex())
def string(r,name):
 at=r.pos;n=r.number('i')
 if not 0<=n<=50000:raise p.ProbeError('bounded string length')
 b=r.take(n)
 if b:
  logical=b
  if logical.endswith(b'\xef\xbb\xbf'):logical=logical[:-3]
  elif logical.startswith(b'\xef\xbb\xbf'):logical=logical[3:]
  if not logical.endswith(b'\0') or b'\0' in logical[:-1]:raise p.ProbeError('strict terminated string carrier')
  text=logical[:-1].decode('utf-8')
 else:text=''
 return dict(name=name,offset=at,length=n,bytes=4+n,raw_sha256=digest(b),text=text)
def parse_setup(b,start,end,version=8):
 if version!=8:raise p.ProbeError('only bounded version8 schema implemented')
 r=p.Reader(b,start,end);fields=[]
 fields.extend([scalar(r,'embedded_datum_+10'),scalar(r,'embedded_datum_+40')])
 def n(fmt,name):
  at=r.pos;raw=r.take(struct.calcsize('>'+fmt));value=struct.unpack('>'+fmt,raw)[0]
  row=dict(name=name,offset=at,bytes=len(raw),bits=raw.hex())
  if not isinstance(value,float) or math.isfinite(value):row['decoded']=value
  else:row['nonfinite']=str(value)
  fields.append(row);return row
 n('i','config_+70');n('i','config_+74');base=n('f','base_rate_+ac');n('i','legacy_format_mapping_input')
 fields.append(scalar(r,'embedded_datum_+78'))
 for name in ['config_+cc','config_+160','config_+a8','discarded_word']:n('i',name)
 factor=n('d','factor_+b0');n('d','config_+c0');n('i','config_+158');n('h','config_+ba');n('h','config_+b8')
 n('I','FFileType_+c')
 for name in ['FFileType_+10','FFileType_+28','FFileType_+70']:fields.append(string(r,name))
 token_at=r.pos;token=bytearray()
 for _ in range(10):
  v=r.take(1)[0]
  if v==0:break
  if not 0x20<=v<0x7f:raise p.ProbeError('strict ASCII NUL-only format token')
  token.append(v)
 else:raise p.ProbeError('unterminated format token')
 fields.append(dict(name='format_token',offset=token_at,bytes=r.pos-token_at,text=token.decode('ascii')))
 n('i','config_+15c')
 if r.pos!=end:raise p.ProbeError('setup extent not exactly consumed')
 return dict(version=version,body_offset=start,body_bytes=end-start,fields=fields,base_rate=base,factor=factor,consumed_exactly=True)
def parse_source(path,row):
 b=path.read_bytes();assert digest(b)==row['sha256']
 ch=row['parsed_chunks'][3];a=p.Archive(b,ch['offset']+8,ch['offset']+8+ch['payload_bytes']);ar=p.Reader(b,a.start,a.end)
 arrangement=a.object(ar)
 if arrangement['class']!='PArrangement' or arrangement['version']!=4:raise p.ProbeError('arrangement type')
 r=a.body(arrangement);root=a.object(r)
 if root.get('class')!='MRoot' or root.get('version')!=6:raise p.ProbeError('root type')
 setup=a.object(r)
 if setup.get('class')!='PArrangeSetup':raise p.ProbeError('setup type')
 decoded=parse_setup(b,setup['body_offset'],setup['end'],setup['version'])
 tails=[string(r,'arrangement_string_'+str(i))for i in range(7)]
 if r.pos!=r.end or ar.pos!=a.end:raise p.ProbeError('arrangement/archive extent')
 return dict(source=pin(path),arrangement=arrangement,root=root,setup=setup,decoded=decoded,arrangement_strings=tails,arrangement_consumed_exactly=True)

def controls(body):
 out=[]
 def case(name,data,accept,check=None):
  try:
   x=parse_setup(data,0,len(data));ok=True
   if check:check(x)
  except (ValueError,UnicodeError,struct.error):ok=False
  assert ok==accept,name
  out.append(dict(name=name,accepted=ok,expected=accept,input_bytes=len(data),input_sha256=digest(data)))
 def changed(offset,new):return body[:offset]+new+body[offset+len(new):]
 case('factory_v8_scalar',body,True)
 for bits in [0x46fa0000,0x473b8000,0x461c4000,0x497a0000,0x7fc00000,0x7f800000]:
  case('raw_base_bits_'+hex(bits),changed(48,struct.pack('>I',bits)),True)
 case('nonunity_factor_is_preserved_not_admitted',changed(92,struct.pack('>d',1.001)),True)
 case('scalar_tag10_same_width',changed(8,struct.pack('>i',10)),True)
 for tag in [0,17,16,999]:case('unsupported_datum_'+str(tag),changed(8,struct.pack('>i',tag)),False)
 # Replacing a length-prefixed string shifts all following positions; no hardcoded
 # token/finalword offset may be used by the parser.
 replacement=b'extended-wave-extension\0\xef\xbb\xbf'
 varied=body[:120]+struct.pack('>i',len(replacement))+replacement+body[131:]
 case('variable_string_forward_offsets',varied,True,lambda x:(_ for _ in ()).throw(ValueError()) if x['fields'][-1]['offset']!=165+len(replacement)-7 else None)
 for k in [0,48,51,92,99,116,120,130,158,164,168]:case('truncated_'+str(k),body[:k],False)
 case('trailing_bytes',body+b'\0',False)
 case('negative_string_length',changed(120,struct.pack('>i',-1)),False)
 case('overlarge_string_length',changed(120,struct.pack('>i',50001)),False)
 case('format_token_without_terminator',body[:159]+b'1234567890'+body[165:],False)
 case('newline_native_branch_deliberately_unsupported',changed(164,b'\n'),False)
 return out

def clamp_controls():
 # Exact AArch64 FCMP flags followed by FCCMP conditionPL and branchLE.
 def flags(a,b):
  if math.isnan(a) or math.isnan(b):return (0,0,1,1)
  if a<b:return (1,0,0,0)
  if a==b:return (0,1,1,0)
  return (0,0,1,0)
 rows=[]
 for bits in [0,0x80000000,0x45fa0000,0x461c3fff,0x461c4000,0x472c4400,0x473b8000,0x497a0000,0x497a0001,0x7f800000,0xff800000,0x7fc00000,0xffc00000]:
  f=struct.unpack('>f',struct.pack('>I',bits))[0];first=flags(f,10000.0)
  second=flags(f,1024000.0) if first[0]==0 else (0,0,0,0)
  branch_le=bool(second[1] or second[0]!=second[3]);result=bits if branch_le else 0x472c4400
  expected=bits if math.isnan(f) or 10000<=f<=1024000 else 0x472c4400
  assert result==expected
  rows.append(dict(input_bits=f'{bits:08x}',first_nzcv=first,second_nzcv=second,skip_default=branch_le,result_bits=f'{result:08x}'))
 return rows

if __name__=='__main__':
 inv=json.loads((R/'research/evidence/cubase-static/cpr-container-001/inventory.json').read_text());base=R/inv['source_directory']
 rows=[parse_source(base/row['name'],row)for row in inv['records']]
 b=(R/rows[1]['source']['path']).read_bytes();o=rows[1]['setup'];cs=controls(b[o['body_offset']:o['end']])
 out=dict(scope='Forward structural/native-field checks and synthetic instrument controls only; target not executed',target_executed=False,source_probe=pin(R/'scripts/cpr_probe.py'),fixtures=rows,controls=cs,clamp_controls=clamp_controls(),summary=dict(factory_sources=len(rows),synthetic_parser_controls=len(cs),original_instruction_flag_controls=13))
 (H/'schema-probe.json').write_text(json.dumps(out,indent=2)+'\n');print(out['summary'])
