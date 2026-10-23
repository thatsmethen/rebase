// Isolated static-only REA client. Does not share or modify root's main session.
import { Client } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import { StdioClientTransport, getDefaultEnvironment } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import { readFile, writeFile, appendFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const evidence = fileURLToPath(new URL('./pass1/', import.meta.url));
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const env = { ...getDefaultEnvironment(), GHIDRA_HEADLESS_MAXMEM: '2G' };
// Use the default analyzer profile; don't inherit another session's experiments.
delete env.REA_GHIDRA_DISABLE_ANALYZERS;
delete env.REA_GHIDRA_LANGUAGE_ID;
const transport = new StdioClientTransport({
  command: '/bin/sh', args: [root + 'scripts/rea', '--mcp'], cwd: root,
  env, stderr: 'pipe', maxBufferSize: 32 * 1024 * 1024,
});
transport.stderr.on('data', data => appendFile(evidence + 'rea.stderr.txt', data));
const client = new Client({ name: 'rebase-cpr-renderer-selection-static', version: '1.0' });
await client.connect(transport);
const inventory = await client.listTools();
await writeFile(evidence + 'mcp-tool-inventory.json', JSON.stringify(inventory, null, 2));
const rows = JSON.parse(await readFile(evidence + 'derivation.json', 'utf8')).derivatives;
async function call(name, args, file) {
  const request = { name, arguments: args };
  await appendFile(evidence + 'requests.jsonl', JSON.stringify({ ...request, output: file }) + '\n');
  const result = await client.callTool(request, { timeout: 330000 });
  await writeFile(evidence + file, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ file, isError: result.isError ?? false }));
  return result;
}
try {
  for (const row of rows) {
    const id = row.entry.slice(2);
    try {
      const opened = await call('open_binary', {
        path: evidence + row.raw_file, format: 'raw-binary', architecture: 'arm64',
        entry_point: row.entry, provider_id: 'ghidra',
      }, `open-${id}.json`);
      if (opened.isError) continue;
      await call('analyze_function', { procedure: row.entry }, `function-${id}.json`);
      await call('read_bytes', { address: row.entry, length: row.length }, `bytes-${id}.json`);
      await call('get_evidence_bundle', { detail: 'complete' }, `bundle-${id}.json`);
    } catch (error) {
      await writeFile(evidence + `failure-${id}.json`, JSON.stringify({ error: String(error) }));
      console.log(JSON.stringify({ failed: id, error: String(error) }));
    } finally {
      await call('close_binary', { snapshot_path: evidence + `snapshot-${id}.json` }, `close-${id}.json`);
    }
  }
} finally {
  await client.close();
  console.log('CLOSED: isolated raw-slice MCP session');
}
