"""Analytical IEEE-binary64/32 rate-state discriminators; no vendor execution."""
import json,struct,math
from pathlib import Path
H=Path(__file__).resolve().parent
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
bits=lambda x:struct.pack('>d',x).hex()
rows=[]
for r in [8000.0,32000.0,44100.0,48000.0,96000.0,192000.0]:
 for k in [0.5,1.0,1.001,0.999]:
  product=r*k;period=1.0/product;reader=f32(1.0/period);engine=float(math.trunc(product))
  rows.append(dict(rate=r,factor=k,product=product,product_bits=bits(product),period_bits=bits(period),reader_multiplier=reader,reader_bits=bits(reader),engine_rate=engine,engine_bits=bits(engine),equal=reader==engine))
assert all(x['equal'] for x in rows if x['factor']==1)
assert any(not x['equal']for x in rows)
report=dict(kind='analytical controls of recovered operation sequences; not host observations',target_execution=False,scope='positive finite rates and products representable in signed32; default Python IEEE binary64 operations and explicit binary32 narrowing',rows=rows,summary=dict(cases=len(rows),reader_engine_differences=sum(not x['equal']for x in rows)),limitations=['Does not establish reachable product values or native runtime state.','Does not assert root-builder rate, physical device rate, source stream rate or transport rate equality.','No sample resampling or native callback executed.'])
(H/'rate-controls.json').write_text(json.dumps(report,indent=2)+'\n');print(report['summary'])
