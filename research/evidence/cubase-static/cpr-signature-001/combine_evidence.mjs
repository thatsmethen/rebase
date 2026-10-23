import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records = [];
for (const dir of ['.', ...Array.from({length:12}, (_,i)=>`pass${i+2}`)]) {
  const base = new URL(`./${dir}/`, import.meta.url);
  const { derivatives } = JSON.parse(await readFile(new URL('derivation.json',base),'utf8'));
  for (const row of derivatives) {
    const wrapper = JSON.parse(await readFile(new URL(`bundle-${row.entry.slice(2)}.json`,base),'utf8'));
    if (wrapper.isError) throw new Error(row.entry);
    const content = wrapper.structuredContent;
    const bundle = content.bundle ?? content.result ?? content;
    records.push(...bundle.records);
  }
}
const canonical = createEvidenceBundle(records);
await writeFile(new URL('./native-evidence-bundle.json',import.meta.url),JSON.stringify(canonical,null,2)+'\n');
console.log(JSON.stringify({records:canonical.records.length,method:'Pinned REA createEvidenceBundle; original records unchanged'}));
