#!/usr/bin/env node
import assert from 'node:assert/strict';
import {readFile, readdir, mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {buildDiagram} from './build-diagram.mjs';
const require = createRequire(import.meta.url);
const {validate, displayName, edgeType} = require('../assets/model.js');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = async file => JSON.parse(await readFile(resolve(root, file), 'utf8'));
const base = await read('assets/base-model.json');
let count = 0;
function test(name, fn) {fn(); count++; console.log(`PASS ${name}`);}
function reject(name, mutate, code, original = base) {
  test(name, () => {
    const model = structuredClone(original); mutate(model);
    const report = validate(model);
    assert.equal(report.ok, false, name);
    assert(report.errors.some(e => e.code === code), `${name}: expected ${code}, got ${JSON.stringify(report)}`);
  });
}
for (const file of (await readdir(resolve(root, 'assets/models'))).filter(f => f.endsWith('.json')).sort()) {
  const model = await read(`assets/models/${file}`);
  test(`canonical ${file}`, () => assert.deepEqual(validate(model), {ok: true, errors: [], warnings: []}));
}
test('base model', () => assert.deepEqual(validate(base), {ok: true, errors: [], warnings: []}));
test('malformed root returns errors', () => {for (const model of [null, [], {}, {version: 1}]) assert.equal(validate(model).ok, false);});
test('malformed field types fail without throwing', () => {
  for (const field of ['evidence', 'parent', 'canonicalName']) {
    const model = structuredClone(base), invalid = {toString: null, valueOf: null};
    model.nodes[0][field] = field === 'evidence' ? [invalid] : invalid;
    assert.equal(validate(model).ok, false);
  }
});
reject('no empty model pass', m => {m.nodes = []; m.edges = [];}, 'empty-model');
reject('no legacy v1 pass', m => {m.version = 1;}, 'version');
reject('unknown display-name override', m => {m.nodes[0].name = 'Service';}, 'unknown-field');
reject('English figure text', m => {m.nodes[0].description = '服务';}, 'english');
reject('real library artifact', m => {m.nodes[0].entityType = 'library'; m.nodes[0].canonicalName = 'Logging client';}, 'library-name');
reject('required evidence', m => {m.nodes[0].evidence = [];}, 'evidence');
reject('evidence reference integrity', m => {m.edges[0].evidence = ['missing'];}, 'evidence-ref');
reject('parent reference integrity', m => {m.nodes[0].parent = 'missing';}, 'parent');
reject('containment cycle', m => {m.containers[0].parent = m.containers[1].id;}, 'parent-cycle');
reject('top-down major layers', m => {m.containers[1].order = 2;}, 'layer-order');
reject('node endpoint only', m => {m.edges[0].to = 'services';}, 'edge-endpoint');
reject('IPC needs mechanism', m => {m.edges[0].relation = 'ipc';}, 'ipc-mechanism');
reject('handles are not pixels', m => {m.edges[0].dataKind = 'handle';}, 'handle-not-data');
reject('no diagonal via step', m => {m.edges[0].via = [{x: 1, y: 2}];}, 'route');
reject('anchor exception needs reason', m => {m.edges[0].keepAnchor = true;}, 'anchor-reason');
reject('no invented kernel path', m => {Object.assign(m.nodes[0], {entityType: 'kernel-interface', interfacePath: 'qcom_hgsl', moduleName: 'qcom_hgsl'});}, 'kernel-interface');
reject('kernel path before module', m => {Object.assign(m.nodes[0], {entityType: 'kernel-interface', interfacePath: '/dev/hgsl', moduleName: 'qcom_hgsl', canonicalName: 'qcom_hgsl /dev/hgsl'});}, 'kernel-name-order');
test('kernel display title derived', () => assert.equal(displayName({entityType: 'kernel-interface', interfacePath: '/dev/hgsl', moduleName: 'qcom_hgsl'}), '/dev/hgsl · qcom_hgsl'));
test('relations keep distinct semantics', () => assert.deepEqual(['dependency', 'call', 'read', 'notification', 'configuration'].map(relation => edgeType({relation})), ['dependency', 'control', 'data', 'notification', 'config']));
reject('origin cannot be guessed', m => {m.meta.colorMode = 'origin';}, 'origin');
reject('firmware requires software origin', m => {m.meta.colorMode = 'origin'; m.nodes.forEach(n => {n.origin = 'native';}); m.nodes[0].entityType = 'firmware'; delete m.nodes[0].origin;}, 'origin');
reject('responsibility basis required', m => {m.meta.colorMode = 'responsibility';}, 'enum');
const responsibility = structuredClone(base);
responsibility.meta.colorMode = 'responsibility'; responsibility.meta.responsibilityBasis = 'integration';
responsibility.parties = [{id: 'first', label: 'Integrator A', category: 'tier1'}, {id: 'second', label: 'Integrator B', category: 'tier1', paletteKey: 'cyan'}];
responsibility.nodes.forEach((n, i) => {n.responsibleParty = i ? 'second' : 'first';});
test('responsibility distinct from origin', () => assert.equal(validate(responsibility).ok, true));
reject('distinct parties need distinct colors', m => {delete m.parties[1].paletteKey;}, 'party-color', responsibility);
const subsystem = await read('assets/models/process-library-subsystem.json');
reject('library stays in actual process', m => {m.nodes.find(n => n.entityType === 'library').parent = 'userspace';}, 'process-membership', subsystem);
reject('subsystem needs concrete entities', m => {m.nodes[0].entityType = 'subsystem';}, 'concrete-name', subsystem);
const multi = await read('assets/models/multi-domain-system.json');
reject('Hypervisor spans VM union', m => {m.containers.find(c => c.kind === 'hypervisor').w -= 100;}, 'hypervisor-span', multi);
reject('Hypervisor only hosts VMs', m => {m.containers.find(c => c.kind === 'hypervisor').hosts.push(m.containers.find(c => c.domainType === 'mcu').id);}, 'hypervisor-hosts', multi);
const io = await read('assets/models/shared-memory-io.json');
reject('one physical memory once', m => {const n = structuredClone(m.nodes.find(n => n.entityType === 'memory')); n.id = 'duplicate'; m.nodes.push(n);}, 'duplicate-resource', io);
const specimen = await read('assets/models/layout-primitives.json');
reject('junction needs identity', m => {delete m.junctions[0].id;}, 'id', specimen);
reject('junction identities unique', m => {m.junctions.push(structuredClone(m.junctions[0]));}, 'duplicate-id', specimen);
test('specimen relaxes facts not geometry', () => assert.equal(validate(specimen).ok, true));
reject('specimen cannot escape containment', m => {m.nodes[0].x = -1;}, 'canvas-bounds', specimen);
const temp = await mkdtemp(join(tmpdir(), 'architecture-model-tests-'));
const escaped = structuredClone(base); escaped.meta.title = 'Logging </script><script>bad()</script>';
await buildDiagram(escaped, join(temp, 'escape.html'));
const html = await readFile(join(temp, 'escape.html'), 'utf8');
test('safe JSON and HTML embedding', () => {assert(!html.includes('<script>bad()')); assert(html.includes('\\u003c/script\\u003e'));});
const theme = await read('assets/theme.json');
const fontManifest = await read('assets/fonts/manifest.json');
const embeddedJSON = id => JSON.parse(html.match(new RegExp(`<script id="${id}" type="application/json">([\\s\\S]*?)<\\/script>`))[1]);
test('shared theme embedded without drift', () => assert.deepEqual(embeddedJSON('diagram-theme'), theme));
test('approved visual tokens', () => {
  assert.deepEqual(theme.radii, {label: 4, node: 8, container: 8, domain: 12, shell: 12});
  assert.equal(theme.strokes.control, 1.8); assert.equal(theme.strokes.data, 2.6);
  assert.equal(theme.strokes.notification, 1.8);
  assert.equal(theme.fonts.sans.family, 'Roboto'); assert.equal(theme.fonts.mono.family, 'Roboto Mono');
});
test('fonts bundled with license and pinned metadata', () => {
  const metadata = embeddedJSON('diagram-font-metadata');
  assert.equal(metadata.license, 'OFL-1.1');
  assert(metadata.licenseText.includes('SIL OPEN FONT LICENSE Version 1.1'));
  assert.deepEqual(metadata.fonts, fontManifest.fonts);
  assert.equal((html.match(/src: url\(data:font\/woff2;base64,/g) || []).length, 2);
  for (const font of metadata.fonts) assert.match(font.sha256, /^[a-f0-9]{64}$/);
});
test('no external fonts or UI controls', () => {
  assert(!/<link\b[^>]+href=/i.test(html));
  assert(!/@import\b|url\(["']?https?:\/\//i.test(html));
  assert(!/<(?:button|input|select|textarea)\b/i.test(html));
});
test('complete paths and functions use code typography', () => {
  const pattern = new RegExp(theme.code.textPattern);
  for (const value of ['/dev/hgsl', '/sys/kernel/debug', 'sd_journal_send()', 'CameraService::connect(device)']) assert(pattern.test(value), value);
  for (const value of ['BufferQueue', 'CameraService', 'Read from /dev/kmsg', 'Local socket IPC']) assert(!pattern.test(value), value);
  assert.deepEqual(theme.code.nodeTypes, ['library', 'kernel-interface']);
});
console.log(`${count} semantic/build tests passed. Temporary artifact: ${temp}`);
