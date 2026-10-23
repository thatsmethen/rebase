import {readFile,writeFile}from'node:fs/promises';
import {createEvidenceBundle}from'../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const verification=JSON.parse(await readFile(new URL('./verification.json',import.meta.url),'utf8'));
const records=[];
for(const row of verification.functions){
 const path=new URL('../../../../../'+row.directory+'/bundle-'+row.entry.slice(2)+'.json',import.meta.url);
 const w=JSON.parse(await readFile(path,'utf8'));if(w.isError)throw new Error(path);
 records.push(...w.structuredContent.result.records);
}
const bundle=createEvidenceBundle(records);
await writeFile(new URL('./evidence-bundle-final.json',import.meta.url),JSON.stringify(bundle,null,2)+'\n');
console.log(JSON.stringify({records:bundle.records.length,method:'Pinned REA canonical API with unchanged original records'}));
