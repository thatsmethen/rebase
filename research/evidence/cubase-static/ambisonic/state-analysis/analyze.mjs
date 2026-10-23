// Isolated, static-only raw code slice. Never invokes the target component.
import { Client } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import { StdioClientTransport, getDefaultEnvironment } from '../../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import { writeFile, appendFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const dir = fileURLToPath(new URL('./', import.meta.url));
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const transport = new StdioClientTransport({ command: '/bin/sh', args: [root + 'scripts/rea', '--mcp'],
  cwd: root, env: { ...getDefaultEnvironment(), GHIDRA_HEADLESS_MAXMEM: '2G' },
  stderr: 'pipe', maxBufferSize: 32 * 1024 * 1024 });
transport.stderr.on('data', data => appendFile(dir + 'rea.stderr.txt', data));
const client = new Client({ name: 'rebase-ambisonic-state-static', version: '1.0' });
await client.connect(transport);
async function call(name, args, file) {
  await appendFile(dir + 'requests.jsonl', JSON.stringify({ name, arguments: args, output: file }) + '\n');
  const result = await client.callTool({ name, arguments: args }, { timeout: 330000 });
  await writeFile(dir + file, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ file, isError: result.isError ?? false }));
  if (result.isError) throw new Error('REA returned error; retained in ' + file);
}
try {
  await call('open_binary', { path: dir + 'double-bypass.arm64.bin', format: 'raw-binary',
    architecture: 'arm64', entry_point: '0x154b64', provider_id: 'ghidra' }, 'open.json');
  await call('analyze_function', { procedure: '0x154b64' }, 'double-bypass-function.json');
  await call('read_bytes', { address: '0x154b64', length: 120 }, 'double-bypass-bytes.json');
  await call('get_evidence_bundle', { detail: 'complete' }, 'evidence-bundle.json');
} finally {
  await call('close_binary', { snapshot_path: dir + 'snapshot.json' }, 'close.json');
  await client.close();
  console.log('CLOSED: isolated raw-slice MCP session');
}
