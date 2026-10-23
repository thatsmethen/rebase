import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records = [];
for(let pass=1;pass<=7;pass++) {
 const manifest=JSON.parse(await readFile(new URL(`./derivation-pass${pass}.json`,import.meta.url),'utf8'));
 for(const row of manifest.derivatives) {
  const dir=row.entry==='0x10173a5ac'?'retry-factory/':'';
  const f=JSON.parse(await readFile(new URL(`./${dir}function-${row.entry.slice(2)}.json`,import.meta.url),'utf8'));
  const b=JSON.parse(await readFile(new URL(`./${dir}bundle-${row.entry.slice(2)}.json`,import.meta.url),'utf8'));
  if(f.isError || b.isError) throw Error(row.entry);
  records.push(...b.structuredContent.result.records);
 }
}
const bundle=createEvidenceBundle(records);
await writeFile(new URL('./list-evidence-bundle.json',import.meta.url),JSON.stringify(bundle,null,2)+'\n');
console.log(JSON.stringify({records:bundle.records.length}));
