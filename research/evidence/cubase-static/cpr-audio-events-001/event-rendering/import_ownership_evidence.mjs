// Isolated static-only REA client. Does not share or modify root's main session.
import { Client } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import { StdioClientTransport, getDefaultEnvironment } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import { readFile, writeFile, appendFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const evidence = fileURLToPath(new URL('./', import.meta.url));
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const env = { ...getDefaultEnvironment(), GHIDRA_HEADLESS_MAXMEM: '2G' };
// Use the default analyzer profile; don't inherit another session's experiments.
delete env.REA_GHIDRA_DISABLE_ANALYZERS;
delete env.REA_GHIDRA_LANGUAGE_ID;
const transport = new StdioClientTransport({
  command: '/bin/sh', args: [root + 'scripts/rea', '--mcp'], cwd: root,
  env, stderr: 'pipe', maxBufferSize: 32 * 1024 * 1024,
});
transport.stderr.on('data', data => appendFile(evidence + 'ownership-import.stderr.txt', data));
const client = new Client({ name: 'rebase-cpr-event-rendering-import', version: '1.0' });
await client.connect(transport);
const inventory = await client.listTools();
await writeFile(evidence + 'ownership-mcp-tool-inventory-import.json', JSON.stringify(inventory, null, 2));
try {
  const request = {name: 'import_evidence_bundle', arguments: {path: evidence + 'ownership-evidence-bundle.json'}};
  const result = await client.callTool(request);
  await writeFile(evidence + 'ownership-evidence-import.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result.structuredContent ?? {isError:result.isError}));
} finally { await client.close(); console.log('CLOSED: evidence import session'); }
