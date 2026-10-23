import {readFile,writeFile}from'node:fs/promises';
import {createEvidenceBundle}from'../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const source=JSON.parse(await readFile(new URL('./evidence-bundle.json',import.meta.url),'utf8'));
const seen=new Map(),aliases=[];
for(const record of source.records){
 const prior=seen.get(record.evidence_id);
 if(prior){
  const a=structuredClone(prior),b=structuredClone(record);
  delete a.subject.local_path;delete b.subject.local_path;
  if(JSON.stringify(a)!==JSON.stringify(b))throw new Error('Differing evidence outside original local path');
  aliases.push({evidence_id:record.evidence_id,retained_path:prior.subject.local_path,duplicate_path:record.subject.local_path,comparison:'Identical record after excluding subject.local_path; first record retained unchanged'});
 }else seen.set(record.evidence_id,record);
}
await writeFile(new URL('./duplicate-record-custody.json',import.meta.url),JSON.stringify({initial_records:source.records.length,unique_records:seen.size,aliases},null,2)+'\n');
const bundle=createEvidenceBundle([...seen.values()]);
await writeFile(new URL('./evidence-bundle-unique.json',import.meta.url),JSON.stringify(bundle,null,2)+'\n');
console.log(JSON.stringify({records:bundle.records.length}));
