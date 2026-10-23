// Disposable local REA client for this static investigation; no target launch.
import { Client } from '../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import { StdioClientTransport, getDefaultEnvironment } from '../../../../.tools/rea/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import { createInterface } from 'node:readline';
import { writeFile, appendFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const evidence = fileURLToPath(new URL('./', import.meta.url));
const root = fileURLToPath(new URL('../../../../', import.meta.url));
const transport = new StdioClientTransport({
  command: '/bin/sh', args: [root + 'scripts/rea', '--mcp'], cwd: root,
  env: { ...getDefaultEnvironment(), GHIDRA_HEADLESS_MAXMEM: '2G' },
  stderr: 'pipe', maxBufferSize: 32 * 1024 * 1024,
});
transport.stderr.on('data', data => appendFile(evidence + 'persistent-rea.stderr.txt', data));
const client = new Client({ name: 'rebase-ambisonic-static', version: '1.0' });
await client.connect(transport);
const tools = await client.listTools();
await writeFile(evidence + 'mcp-tool-inventory.json', JSON.stringify(tools, null, 2));
console.log('READY: tool schemas saved in mcp-tool-inventory.json');
const allowed = new Set(['open_binary', 'close_binary', 'search_strings', 'search_procedures',
  'analyze_function', 'xrefs', 'read_bytes', 'address_to_file_offset', 'procedure_pseudo_code',
  'list_procedures', 'list_segments', 'procedure_callers', 'procedure_callees',
  'inspect_native_instruction', 'resolve_native_call_targets', 'get_evidence_bundle']);
for await (const line of createInterface({ input: process.stdin, terminal: false })) {
  try {
    const request = JSON.parse(line);
    if (request.close) break;
    if (!allowed.has(request.name) || !/^[a-z0-9-]+\.json$/.test(request.out)) throw new Error('Invalid static request');
    await appendFile(evidence + 'persistent-requests.jsonl', JSON.stringify(request) + '\n');
    const result = await client.callTool({ name: request.name, arguments: request.args ?? {} }, { timeout: 330000 });
    await writeFile(evidence + request.out, JSON.stringify(result, null, 2));
    console.log(JSON.stringify({ saved: request.out, isError: result.isError ?? false }));
  } catch (error) { console.log(JSON.stringify({ error: String(error) })); }
}
await client.close();
