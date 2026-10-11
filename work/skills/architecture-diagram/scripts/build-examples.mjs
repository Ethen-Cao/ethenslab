#!/usr/bin/env node
import {readdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildDiagram} from './build-diagram.mjs';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const files = (await readdir(resolve(root, 'assets/models'))).filter(f => f.endsWith('.json')).sort();
for (const file of files) {
  const result = await buildDiagram(resolve(root, 'assets/models', file), resolve(root, 'assets/architecture_diagrams', file.replace(/\.json$/, '.html')));
  if (result.report.warnings.length) console.warn(JSON.stringify(result.report.warnings));
  console.log(`Built ${result.model.meta.id}`);
}
await buildDiagram(resolve(root, 'assets/base-model.json'), resolve(root, 'assets/base-template.html'));
console.log(`Built base-template; ${files.length} reference examples.`);
