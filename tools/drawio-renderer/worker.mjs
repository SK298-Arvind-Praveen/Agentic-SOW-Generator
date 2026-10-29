import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { fileURLToPath } from 'node:url';
import { inflateRawSync } from 'node:zlib';

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
const timeout = Math.min(60000, Math.max(1000, input.timeout_ms || 30000));
const transport = new StdioClientTransport({
  command: process.execPath,
  args: ['--import', new URL('./headless.mjs', import.meta.url).href,
    fileURLToPath(new URL('./node_modules/@drawio/mcp/src/index.js', import.meta.url))],
  env: {...process.env, DRAWIO_ICON_SERVICE_URL: 'off'},
  stderr: 'pipe',
});
const client = new Client({name: 'sow-local-drawio', version: '1.0.0'});
// Never log the returned URL: its fragment contains the entire diagram.
transport.stderr?.on('data', data => {
  if (process.env.DRAWIO_DEBUG === '1') process.stderr.write(data);
});
try {
  await client.connect(transport, {timeout});
  const result = await client.callTool({name: 'open_drawio_xml',
    arguments: {content: input.xml, dark: 'false'}}, undefined, {timeout});
  if (result.isError) throw new Error('Official draw.io MCP rejected the diagram');
  const text = result.content.filter(c => c.type === 'text').map(c => c.text).join('\n');
  const match = text.match(/https?:\/\/[^\s]+#R([^\s]+)/);
  if (!match) throw new Error('Official draw.io MCP returned no XML diagram');
  const xml = decodeURIComponent(inflateRawSync(Buffer.from(decodeURIComponent(match[1]), 'base64'),
    {maxOutputLength: 20000000}).toString('utf8'));
  process.stdout.write(JSON.stringify({xml, mcp_version: client.getServerVersion()?.version}));
} catch (error) {
  process.stderr.write('Draw.io MCP processing failed: ' + error.message + '\n');
  process.exitCode = 1;
} finally {
  await client.close();
}
