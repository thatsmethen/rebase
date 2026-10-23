import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records=[];
for(let i=1;i<=17;i++){
 const base=new URL(`./pass${i}/`,import.meta.url);
 const {derivatives}=JSON.parse(await readFile(new URL('derivation.json',base),'utf8'));
 for(const row of derivatives){
  const w=JSON.parse(await readFile(new URL(`bundle-${row.entry.slice(2)}.json`,base),'utf8'));
  if(w.isError)throw new Error(row.entry);
  records.push(...w.structuredContent.result.records);
 }
}
const support=JSON.parse(await readFile(new URL('./support-verification.json',import.meta.url),'utf8'));
for(const row of support.functions){
 const p=row.pins.find(x=>x.path.endsWith(`/bundle-${row.entry.slice(2)}.json`)).path;
 const w=JSON.parse(await readFile(new URL(`../../../../../${p}`,import.meta.url),'utf8'));
 if(w.isError)throw new Error(p);records.push(...w.structuredContent.result.records);
}
const bundle=createEvidenceBundle(records);
await writeFile(new URL('./evidence-bundle.json',import.meta.url),JSON.stringify(bundle,null,2)+'\n');
console.log(JSON.stringify({records:bundle.records.length,method:'Pinned REA canonical bundle API; original records unchanged'}));
