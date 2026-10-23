import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records = [];
for (const dir of [".", "ctor-tail", "constructor-context", "host-gate-service", "host-gate-service/pass2", "host-gate-service/pass3", "host-gate-service/pass4", "host-gate-service/pass5", "host-gate-service/pass6", "host-gate-service/pass7", "host-gate-service/pass8", "host-gate-service/pass9", "host-gate-service/pass10", "host-gate-service/pass11", "host-gate-service/pass12"]) {
  const base = new URL(`./${dir}/`, import.meta.url);
  const { derivatives } = JSON.parse(await readFile(new URL('derivation.json', base), 'utf8'));
  for (const row of derivatives) {
    const wrapper = JSON.parse(await readFile(new URL(`bundle-${row.entry.slice(2)}.json`, base), 'utf8'));
    if (wrapper.isError) throw new Error(row.entry);
    records.push(...wrapper.structuredContent.result.records);
  }
}
const supporting = JSON.parse(await readFile(new URL('./supporting-evidence-checks-v2.json', import.meta.url), 'utf8'));
for (const row of supporting.functions) {
 const fp = row.pins.find(p => p.path.endsWith(`/function-${row.entry.slice(2)}.json`)).path;
 const bp = fp.replace('/function-', '/bundle-');
 const wrapper = JSON.parse(await readFile(new URL(`../../../../../${bp}`, import.meta.url), 'utf8'));
 if (wrapper.isError) throw new Error(bp);
 records.push(...wrapper.structuredContent.result.records);
}
const bundle = createEvidenceBundle(records);
await writeFile(new URL('./closure-evidence-bundle-v2.json', import.meta.url), JSON.stringify(bundle, null, 2) + '\n');
console.log(JSON.stringify({ records: bundle.records.length, method: 'Pinned REA canonical bundle API; original records unchanged' }));
