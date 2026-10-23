import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records = [];
for (const dir of ['.', 'pass2', 'pass3']) {
  const base = new URL(`./${dir}/`, import.meta.url);
  const { derivatives } = JSON.parse(await readFile(new URL('derivation.json', base), 'utf8'));
  for (const row of derivatives) {
    const wrapper = JSON.parse(await readFile(new URL(`bundle-${row.entry.slice(2)}.json`, base), 'utf8'));
    if (wrapper.isError) throw new Error(row.entry);
    records.push(...wrapper.structuredContent.result.records);
  }
}
const reused = JSON.parse(await readFile(new URL('./reused-evidence.json', import.meta.url), 'utf8'));
for (const row of reused.functions) {
  const path = new URL(`../../../../../${row.bundle_path}`, import.meta.url);
  const wrapper = JSON.parse(await readFile(path, 'utf8'));
  if (wrapper.isError) throw new Error(row.entry);
  records.push(...wrapper.structuredContent.result.records);
}
const bundle = createEvidenceBundle(records);
await writeFile(new URL('./native-evidence-bundle.json', import.meta.url), JSON.stringify(bundle, null, 2) + '\n');
console.log(JSON.stringify({ records: bundle.records.length, method: 'Pinned REA canonical bundle API; original records unchanged' }));
