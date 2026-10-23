"""Bind missing raw-image jump tables and dependency names to original bytes."""
import hashlib,struct
from derive import data,offset,save,EXPECTED
rows=[]
def capture(name,va,n,extra=None):
    at=offset(va);raw=data[at:at+n]
    row=dict(name=name,address=hex(va),file_offset=at,bytes=n,hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
    if extra:row.update(extra(raw))
    rows.append(row)
for va in [0x103897663,0x103897670,0x10389767c,0x103897688,0x10389769a,0x1038976ac,0x1038976b9,0x1038976d3]:
    at=offset(va);end=data.index(0,at)
    capture('dependency_literal',va,end-at+1,lambda raw:dict(text=raw[:-1].decode()))
for name,va,n,width,base in [
 ('resampler_factory_type',0x103933bf8,5,4,None),
 ('convert_sample_size',0x103934638,8,1,0x1003263b0),
 ('conversion_input_kind',0x1039347f0,8,2,0x100330514),
 ('conversion_output_kind',0x103934800,8,1,0x100330a60),
 ('soxr_input_compact',0x103933c54,4,1,0x1003154ac),
 ('soxr_output_compact',0x103933c58,4,1,0x1003158cc),
 ('soxr_input_append',0x103933c5c,4,1,0x100315cd4),
 ('soxr_process_pointers',0x103933c60,4,1,0x100315e00),
 ('soxr_output_copy',0x103933c64,4,1,0x100315f04)]:
    def interpret(raw,width=width,base=base):
        vals=list(struct.unpack('<'+{1:'B',2:'H',4:'I'}[width]*(len(raw)//width),raw))
        return dict(values=vals,base=hex(base) if base else None,targets=[hex(base+4*v) for v in vals] if base else None)
    capture(name,va,n*width,interpret)
save('original-table-and-name-bindings.json',dict(source_sha256=EXPECTED,records=rows,scope='Original-image bytes only. Dynamic library availability and resampling output have not been observed.'))
for r in rows: print(r['name'],r.get('text',r.get('targets',r.get('values'))))
