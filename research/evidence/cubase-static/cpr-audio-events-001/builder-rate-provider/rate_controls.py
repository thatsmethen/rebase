"""Analytical stored-rate controls, never native target execution."""
from pathlib import Path
import json,struct,math,hashlib
H=Path(__file__).resolve().parent
f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
b64=lambda v:struct.pack('>d',v).hex()
rows=[]
for requested in [8000.0,44100.0,44100.001,48000.0,48000.001,192000.0]:
 for factor in [1.0,0.5,0.999,1.001]:
  base=f32(requested);product=base*factor
  period=1.0/product;reader=f32(1.0/period);engine=float(math.trunc(product))
  rows.append(dict(input_double_rate=requested,stored_float32_bits=struct.pack('>f',base).hex(),stored_factor_bits=b64(factor),provider_product_bits=b64(product),base_getter_bits=b64(base),conditional_shared_product_reader_bits=b64(reader),conditional_shared_product_engine_bits=b64(engine),provider_equals_reader=product==reader,provider_equals_engine=product==engine))
assert any(not x['provider_equals_reader']for x in rows)
h=hashlib.sha256();mismatches=[]
for rate in range(8000,192001):
 base=f32(float(rate));product=base*1.0;reader=f32(1.0/(1.0/product));engine=float(math.trunc(product))
 h.update(struct.pack('<Iddd',rate,product,reader,engine))
 if not (product==reader==engine==rate):mismatches.append(rate)
assert not mismatches
report=dict(kind='analytical IEEE controls of explicit stored values; not target observations',target_executed=False,rows=rows,integral_factor_one_control=dict(minimum=8000,maximum=192000,cases=184001,mismatches=mismatches,ordered_little_endian_rate_u32_provider_reader_engine_f64_sha256=h.hexdigest()),limits=['Python binary64 arithmetic and struct binary32 narrowing assume round-to-nearest ties-even.','The reader/engine columns deliberately assume those receivers use the same product; no observed host equality or source-rate binding is inferred.','No native reachability, callback state, sample generation, clipping, or runtime comparison is tested.'])
(H/'rate-controls.json').write_text(json.dumps(report,indent=2)+'\n');print(dict(cases=len(rows),integral_cases=184001,mismatches=len(mismatches)))
