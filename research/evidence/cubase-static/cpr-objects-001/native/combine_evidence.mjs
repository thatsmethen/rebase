import { readFile, writeFile } from 'node:fs/promises';
import { createEvidenceBundle } from '../../../../../.tools/rea/node_modules/rea-agents/dist/domain/evidenceBundle.js';
const records = JSON.parse(await readFile(new URL('./noncanonical-concatenation-attempt.json', import.meta.url),'utf8')).records;
const canonical = createEvidenceBundle(records);
await writeFile(new URL('./native-evidence-bundle.json',import.meta.url),JSON.stringify(canonical,null,2)+'\n');
console.log(JSON.stringify({records:canonical.records.length,method:'Pinned REA createEvidenceBundle; original evidence records unchanged'}));
