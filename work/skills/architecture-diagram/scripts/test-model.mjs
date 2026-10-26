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
reject('real diagrams need deployment intent', m => {delete m.deployment;}, 'deployment-required');
reject('OS domain platform is explicit', m => {delete m.containers.find(c => c.domainType === 'os').platform;}, 'platform');
reject('domain type cannot hide deployment identity', m => {delete m.containers.find(c => c.kind === 'domain').domainType;}, 'domain-type');
reject('platform layers need technical roles', m => {delete m.containers.find(c => c.kind === 'layer').role;}, 'layer-role');
reject('platform software needs role assignment', m => {delete m.nodes[0].layerRole;}, 'node-layer-role');
reject('node role matches its technical layer', m => {m.nodes[0].layerRole = 'kernel';}, 'node-layer-role');
reject('software role labels do not replace technical layers', m => {m.nodes[0].parent = m.containers.find(c => c.kind === 'domain').id;}, 'node-layer-role');
reject('single-domain cannot include another domain kind', m => {m.containers.push({id: 'extra-mcu', kind: 'domain', domainType: 'mcu', title: 'MCU', x: 24, y: 24, w: 100, h: 100});}, 'deployment-profile');
reject('technical layer rank is not arbitrary order', m => {
  m.containers.find(c => c.id === 'services').role = 'kernel';
  m.containers.find(c => c.id === 'kernel').role = 'services';
}, 'technical-layer-order');
const android = await read('assets/models/android-system.json');
reject('Android API rank stays above service implementation', m => {
  m.containers.find(c => c.role === 'framework-api').role = 'system-services';
  m.containers.find(c => c.role === 'system-services' && c.id === 'services').role = 'framework-api';
}, 'technical-layer-order', android);
test('Android native libraries and runtime are peer technical ranks', () => {
  const native = android.containers.find(c => c.role === 'native-libraries'), runtime = android.containers.find(c => c.role === 'runtime');
  assert.equal(native.order, runtime.order); assert.equal(native.y, runtime.y);
  assert.equal(validate(android).ok, true);
});
reject('Android runtime does not stack below native libraries', m => {m.containers.find(c => c.role === 'runtime').y += 100;}, 'android-native-runtime-peers', android);
reject('Android native/runtime peer layers cannot horizontally overlap', m => {m.containers.find(c => c.role === 'runtime').x = m.containers.find(c => c.role === 'native-libraries').x;}, 'android-native-runtime-peers', android);
const qnx = await read('assets/models/qnx-system.json');
reject('QNX user-space drivers stay above kernel even when numeric order passes', m => {
  const drivers = m.containers.find(c => c.role === 'user-drivers'), kernel = m.containers.find(c => c.role === 'kernel');
  drivers.role = 'kernel'; kernel.role = 'user-drivers';
}, 'technical-layer-order', qnx);
test('QNX services and user-space drivers are peer technical regions', () => {
  const services = qnx.containers.find(c => c.role === 'services'), drivers = qnx.containers.find(c => c.role === 'user-drivers');
  assert.equal(services.order, drivers.order); assert.equal(services.y, drivers.y);
  assert.equal(validate(qnx).ok, true);
});
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
reject('a process node does not duplicate its owning process', m => {
  const process = m.containers.find(c => c.kind === 'process'), source = m.nodes[0];
  m.nodes.push({...structuredClone(source), id: 'duplicate-process-node', entityType: 'process', canonicalName: process.title, parent: process.id, x: process.x + 16, y: process.y + 80, w: 150, h: 50});
}, 'duplicate-process', subsystem);
reject('subsystem needs concrete entities', m => {m.nodes[0].entityType = 'subsystem';}, 'concrete-name', subsystem);
test('explicit one-VM implementation excerpt preserves real identity', () => {
  assert.equal(subsystem.deployment.profile, 'single-domain');
  assert.equal(subsystem.deployment.excerpt, true);
  assert.equal(subsystem.containers.find(c => c.id === subsystem.deployment.domain).domainType, 'vm');
  assert.equal(validate(subsystem).ok, true);
});
reject('scope alone does not exempt a VM', m => {delete m.deployment.excerpt; delete m.deployment.domain;}, 'deployment-profile', subsystem);
reject('VM excerpt needs evidence', m => {m.deployment.evidence = [];}, 'evidence', subsystem);
reject('VM excerpt needs one declared domain', m => {delete m.deployment.domain;}, 'deployment-reference', subsystem);
reject('system overview cannot claim implementation excerpt', m => {m.meta.scope = 'system';}, 'deployment-excerpt', subsystem);
reject('excerpt cannot contain hardware', m => {m.nodes[0].entityType = 'hardware';}, 'deployment-excerpt', subsystem);
reject('excerpt cannot contain hardware regions', m => {m.containers.push({id: 'hardware-region', kind: 'hardware-region', title: 'Hardware', x: 24, y: 24, w: 100, h: 100});}, 'deployment-excerpt', subsystem);
reject('excerpt cannot contain independent MCU', m => {m.containers.push({id: 'extra-mcu', kind: 'domain', domainType: 'mcu', title: 'MCU', x: 24, y: 24, w: 100, h: 100});}, 'deployment-excerpt', subsystem);
reject('excerpt cannot carry edges outside its domain', m => {
  m.containers.push({id: 'outside', kind: 'group', title: 'Outside', x: 24, y: 24, w: 300, h: 200});
  const source = m.nodes[0], outside = {...structuredClone(source), id: 'outside-node', parent: 'outside', x: 44, y: 100, w: 100, h: 60};
  m.nodes.push(outside);
  m.edges.push({id: 'outside-edge', from: source.id, to: outside.id, relation: 'dependency', evidence: source.evidence});
}, 'deployment-excerpt-edge', subsystem);
const multi = await read('assets/models/multi-domain-system.json');
reject('Hypervisor spans VM union', m => {m.containers.find(c => c.kind === 'hypervisor').w -= 100;}, 'hypervisor-span', multi);
reject('Hypervisor only hosts VMs', m => {m.containers.find(c => c.kind === 'hypervisor').hosts.push(m.containers.find(c => c.domainType === 'mcu').id);}, 'hypervisor-hosts', multi);
reject('deleting Hypervisor does not disable deployment checks', m => {m.containers = m.containers.filter(c => c.id !== m.deployment.hypervisor);}, 'deployment-reference', multi);
reject('deleting Hypervisor declaration still fails', m => {m.containers = m.containers.filter(c => c.id !== m.deployment.hypervisor); delete m.deployment.hypervisor;}, 'deployment-reference', multi);
reject('changing deployment profile cannot hide VMs', m => {m.deployment.profile = 'single-domain';}, 'deployment-profile', multi);
reject('deleting all declared VM objects still fails', m => {m.containers = m.containers.filter(c => !m.deployment.vms.includes(c.id));}, 'deployment-reference', multi);
reject('VM declarations cover actual VMs', m => {m.deployment.vms.pop();}, 'deployment-vms', multi);
reject('SoC boundary cannot be deleted', m => {m.containers = m.containers.filter(c => c.id !== m.deployment.soc);}, 'deployment-reference', multi);
reject('VMs are contained by the shared SoC', m => {delete m.containers.find(c => c.id === m.deployment.vms[0]).parent;}, 'deployment-parent', multi);
reject('parallel VMs have aligned tops', m => {m.containers.find(c => c.id === m.deployment.vms[1]).y += 100;}, 'deployment-vm-alignment', multi);
reject('VMs cannot be vertically stacked', m => {const a = m.containers.find(c => c.id === m.deployment.vms[0]), b = m.containers.find(c => c.id === m.deployment.vms[1]); b.x = a.x; b.y = a.y + a.h + 40;}, 'deployment-vm-overlap', multi);
reject('independent MCU cannot follow a software endpoint downward', m => {m.containers.find(c => c.id === m.deployment.independent[0]).y += 100;}, 'deployment-independent-position', multi);
reject('independent MCU cannot be inside the SoC', m => {m.containers.find(c => c.id === m.deployment.independent[0]).parent = m.deployment.soc;}, 'deployment-independent-parent', multi);
reject('independent MCU must remain declared', m => {delete m.deployment.independent;}, 'deployment-independent', multi);
reject('shared Hardware follows hosted software', m => {m.containers.find(c => c.id === m.deployment.hardware).y = m.containers.find(c => c.id === m.deployment.hypervisor).y;}, 'deployment-hardware-position', multi);
reject('shared Hardware covers the hosted regions', m => {m.containers.find(c => c.id === m.deployment.hardware).w /= 2;}, 'deployment-hardware-span', multi);
reject('virtualized deployment needs its own evidence', m => {m.deployment.evidence = [];}, 'evidence', multi);
test('malformed deployment returns a failed report, never throws', () => {
  for (const value of [null, [], 1, {profile: 'virtualized-soc', vms: {}}, {profile: 'virtualized-soc', independent: [null]}]) {
    const m = structuredClone(multi); m.deployment = value;
    assert.equal(validate(m).ok, false);
  }
});
const teeLayout = await read('assets/models/soc-vm-mcu-layout.json');
reject('participating TEE is left/top aligned and reaches Hypervisor bottom', m => {m.containers.find(c => c.id === m.deployment.tee).y += 100;}, 'deployment-tee-position', teeLayout);
reject('participating TEE is explicitly declared', m => {delete m.deployment.tee;}, 'deployment-tee', teeLayout);
reject('deleted TEE declaration still references a required object', m => {m.containers = m.containers.filter(c => c.id !== m.deployment.tee);}, 'deployment-reference', teeLayout);
reject('physical Hardware cannot ignore TEE span', m => {const hw = m.containers.find(c => c.id === m.deployment.hardware), vm = m.containers.find(c => c.id === m.deployment.vms[0]); hw.w -= vm.x - hw.x; hw.x = vm.x;}, 'deployment-hardware-span', teeLayout);
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
test('original presentation remains the compatibility default', () => assert(html.includes('"mode":"original"')));
await buildDiagram(base, join(temp, 'article.html'), {presentation: 'article'});
const articleHTML = await readFile(join(temp, 'article.html'), 'utf8');
test('article build keeps the same technical model', () => {
  const embedded = JSON.parse(articleHTML.match(/<script id="diagram-model" type="application\/json">([\s\S]*?)<\/script>/)[1]);
  assert.deepEqual(embedded, base);
  assert(articleHTML.includes('"mode":"article"'));
});
await assert.rejects(() => buildDiagram(base, join(temp, 'invalid.html'), {presentation: 'fit-anything'}), /presentation must/);
count++;
const theme = await read('assets/theme.json');
const fontManifest = await read('assets/fonts/manifest.json');
const embeddedJSON = id => JSON.parse(html.match(new RegExp(`<script id="${id}" type="application/json">([\\s\\S]*?)<\\/script>`))[1]);
test('shared theme embedded without drift', () => assert.deepEqual(embeddedJSON('diagram-theme'), theme));
test('approved visual tokens', () => {
  assert.deepEqual(theme.type, {title: 36, domain: 30, container: 27, node: 24, subtitle: 18, label: 19.5, body: 21, legend: 18});
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
