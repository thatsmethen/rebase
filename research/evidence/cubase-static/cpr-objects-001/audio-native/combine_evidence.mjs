import { readFile, writeFile, readdir } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';

const files = (await readdir(new URL('.', import.meta.url))).filter(name => /^bundle-[0-9a-f]+\.json$/.test(name)).sort();
const unique = new Map();
for (const name of files) {
  const bundle = JSON.parse(await readFile(new URL(name, import.meta.url), 'utf8')).structuredContent.result;
  for (const record of bundle.records) {
    const prior = unique.get(record.evidence_id);
    if (prior && JSON.stringify(prior) !== JSON.stringify(record)) throw new Error(`Conflicting evidence ${record.evidence_id}`);
    unique.set(record.evidence_id, record);
  }
}
const canonical = createEvidenceBundle([...unique.values()]);
await writeFile(new URL('audio-evidence-bundle.json', import.meta.url), JSON.stringify(canonical, null, 2) + '\n');
console.log(JSON.stringify({bundles:files.length, records:canonical.records.length, method:'Pinned REA createEvidenceBundle; original records unchanged'}));
