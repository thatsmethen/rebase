import {readFile, writeFile} from 'node:fs/promises';
import {createEvidenceBundle} from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const verification = JSON.parse(await readFile(new URL('./verification.json', import.meta.url), 'utf8'));
const records = new Map();
for (const row of verification.functions) {
  if (!row.evidence_ids.length) continue;
  const path = new URL('../../../../../' + row.directory + '/bundle-' + row.entry.slice(2) + '.json', import.meta.url);
  const wrapped = JSON.parse(await readFile(path, 'utf8'));
  if (wrapped.isError) throw new Error(String(path));
  for (const record of wrapped.structuredContent.result.records) {
    const old = records.get(record.evidence_id);
    if (old) {
      const a = structuredClone(old), b = structuredClone(record);
      delete a.subject.local_path; delete b.subject.local_path;
      if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error('Inconsistent evidence ID');
    } else records.set(record.evidence_id, record);
  }
}
const bundle = createEvidenceBundle([...records.values()]);
await writeFile(new URL('./evidence-bundle.json', import.meta.url), JSON.stringify(bundle, null, 2) + '\n');
console.log(JSON.stringify({records: bundle.records.length, method: 'Pinned REA canonical API, unchanged original records'}));
