import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
const raw = readFileSync(new URL('../../contracts/openapi.json', import.meta.url));
const expected = readFileSync(
  new URL('../../contracts/CONTRACT_SHA256.txt', import.meta.url),
  'utf8',
)
  .trim()
  .split(/\s+/)[0];
const hash = createHash('sha256').update(raw).digest('hex');
if (hash !== expected) throw Error('Contract hash mismatch; coordinate with the integrator.');
const spec = JSON.parse(raw);
function type(s) {
  if (s.$ref) return s.$ref.split('/').at(-1);
  if (s.enum) return s.enum.map((v) => JSON.stringify(v)).join(' | ');
  if (s.anyOf) return s.anyOf.map(type).join(' | ');
  if (s.type === 'array') return `Array<${type(s.items)}>`;
  if (s.type === 'object')
    return `{\n${Object.entries(s.properties)
      .map(([key, v]) => `  ${key}${s.required?.includes(key) ? '' : '?'}: ${type(v)};`)
      .join('\n')}\n}`;
  return (
    { integer: 'number', number: 'number', string: 'string', boolean: 'boolean', null: 'null' }[
      s.type
    ] ?? 'unknown'
  );
}
const outputs = {
  'src/api/types.ts':
    `// Generated from contracts/openapi.json. Do not edit. SHA256: ${hash}\n` +
    Object.entries(spec.components.schemas)
      .map(([n, s]) => `export type ${n} = ${type(s)};`)
      .join('\n\n') +
    '\n',
  'src/api/schemas.json':
    JSON.stringify({ $id: 'qurylym-contract', components: spec.components }, null, 2) + '\n',
};
for (const name of ['analysis_input', 'analysis_result', 'analysis_state', 'source_evidence'])
  outputs[`src/demo/${name}.example.json`] = readFileSync(
    new URL(`../../contracts/${name}.example.json`, import.meta.url),
    'utf8',
  ).replace(/\r\n/g, '\n');
for (const [path, content] of Object.entries(outputs)) {
  const target = new URL(path, root);
  if (process.argv.includes('--check')) {
    if (readFileSync(target, 'utf8') !== content) throw Error(`Generated contract drift: ${path}`);
  } else {
    mkdirSync(fileURLToPath(new URL('.', target)), { recursive: true });
    writeFileSync(target, content);
  }
}
console.log(`Contract 1.0.0 verified: ${hash}`);
