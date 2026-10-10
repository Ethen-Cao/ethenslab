// Run with: node --test work/architecture_diagrams/pvm-graphics-stack-architecture.test.cjs
// Read the production diagram directly so stale copied geometry cannot pass.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const diagramPath = path.resolve(__dirname, '../../static/diagrams/pvm-graphics-stack-architecture.html');
const html = fs.readFileSync(diagramPath, 'utf8');
function readArray(name) {
  const match = html.match(new RegExp(`const ${name} = (\\[[\\s\\S]*?\\n\\]);`));
  assert.ok(match, `Missing ${name} data in ${diagramPath}`);
  return JSON.parse(match[1]);
}
const nodes = readArray('nodes');
const edges = readArray('edges');
const nodeById = new Map(nodes.map(node => [node.id, node]));
const edgeById = new Map(edges.map(edge => [edge.id, edge]));
const bridgeSource = html.match(/function routeCrossingBridges\([\s\S]*?\n}\n(?=\nconst svg =)/);
assert.ok(bridgeSource, 'Missing production routeCrossingBridges implementation');
const routeCrossingBridges = vm.runInNewContext(`(${bridgeSource[0]})`, {}, {timeout: 1000});
const epsilon = 1e-6;
const near = (a, b) => Math.abs(a - b) < epsilon;

function node(id) {
  assert.ok(nodeById.has(id), `Missing node ${id}`);
  return nodeById.get(id);
}
function edge(id) {
  assert.ok(edgeById.has(id), `Missing edge ${id}`);
  return edgeById.get(id);
}
function routePoints(d) {
  assert.doesNotMatch(d, /[^\d\s.,+\-eEMHVL]/, `Unsupported author route: ${d}`);
  const tokens = d.match(/[MHVL]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) || [];
  const points = [];
  let command;
  let i = 0;
  const read = () => {
    assert.ok(i < tokens.length && !/^[MHVL]$/.test(tokens[i]), `Missing route coordinate: ${d}`);
    const value = Number(tokens[i++]);
    assert.ok(Number.isFinite(value), `Invalid route coordinate: ${d}`);
    return value;
  };
  while (i < tokens.length) {
    if (/^[MHVL]$/.test(tokens[i])) command = tokens[i++];
    assert.ok(command, `Missing route command: ${d}`);
    const previous = points.at(-1);
    if (command !== 'M') assert.ok(previous, `Route must start with M: ${d}`);
    let point;
    if (command === 'M' || command === 'L') point = {x: read(), y: read(), move: command === 'M'};
    if (command === 'H') point = {x: read(), y: previous.y};
    if (command === 'V') point = {x: previous.x, y: read()};
    points.push(point);
    if (command === 'M') command = 'L';
  }
  assert.ok(points.length >= 2, `Route must contain a line: ${d}`);
  return points;
}
function endpoints(item) {
  const points = routePoints(item.d);
  return [points[0], points.at(-1)];
}
function onBorder(point, rectangle) {
  const withinX = point.x >= rectangle.x - epsilon && point.x <= rectangle.x + rectangle.w + epsilon;
  const withinY = point.y >= rectangle.y - epsilon && point.y <= rectangle.y + rectangle.h + epsilon;
  return (withinX && (near(point.y, rectangle.y) || near(point.y, rectangle.y + rectangle.h))) ||
    (withinY && (near(point.x, rectangle.x) || near(point.x, rectangle.x + rectangle.w)));
}
function insideRange(value, a, b) {
  return value > Math.min(a, b) + epsilon && value < Math.max(a, b) - epsilon;
}
function segmentEntersNode(a, b, rectangle) {
  if (near(a.y, b.y)) return insideRange(a.y, rectangle.y, rectangle.y + rectangle.h) &&
    Math.max(a.x, b.x) > rectangle.x + epsilon && Math.min(a.x, b.x) < rectangle.x + rectangle.w - epsilon;
  if (near(a.x, b.x)) return insideRange(a.x, rectangle.x, rectangle.x + rectangle.w) &&
    Math.max(a.y, b.y) > rectangle.y + epsilon && Math.min(a.y, b.y) < rectangle.y + rectangle.h - epsilon;
  assert.fail(`Non-orthogonal route segment: ${JSON.stringify({a, b})}`);
}
function segments(item) {
  const points = routePoints(item.d);
  return points.slice(1).flatMap((point, i) => point.move ? [] : [{
    edgeId: item.id, a: points[i], b: point, horizontal: near(points[i].y, point.y),
  }]);
}
function bridgeGeometry(result, id) {
  return Array.from(result.bridgeArcs.get(id), d => {
    const values = d.match(/[-+]?(?:\d*\.\d+|\d+\.?\d*)/g).map(Number);
    assert.equal(values.length, 9, `Unexpected bridge arc ${d}`);
    const [x1, y1, rx, ry, rotation, large, sweep, x2, y2] = values;
    assert.ok(near(rx, ry) && near(y1, y2) && rotation === 0 && large === 0,
      `Expected an upper semicircle: ${d}`);
    assert.equal(sweep, x2 > x1 ? 1 : 0, `Bridge must jump upwards: ${d}`);
    return {x: (x1 + x2) / 2, y: y1, radius: ry};
  });
}
function groupRectangle(className, process) {
  const match = html.match(new RegExp(`<g class="${className}" data-process="${process}">\\s*<rect ([^>]+)>`));
  assert.ok(match, `Missing ${className} ${process} frame`);
  const attributes = Object.fromEntries(Array.from(match[1].matchAll(/(?:^|\s)(x|y|width|height)="([\d.]+)"/g), item => [item[1], Number(item[2])]));
  return attributes;
}
function strokeWidth(selector) {
  const rule = html.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{([^}]+)}`));
  assert.ok(rule, `Missing ${selector} CSS rule`);
  const width = rule[1].match(/stroke-width:\s*([\d.]+)/);
  assert.ok(width, `Missing ${selector} stroke width`);
  return Number(width[1]);
}

test('node and edge IDs are unique and every edge refers to existing nodes', () => {
  assert.equal(nodeById.size, nodes.length, 'Duplicate node ID');
  assert.equal(edgeById.size, edges.length, 'Duplicate edge ID');
  for (const item of edges) {
    assert.ok(nodeById.has(item.from), `${item.id}: unknown source ${item.from}`);
    assert.ok(nodeById.has(item.to), `${item.id}: unknown target ${item.to}`);
  }
});

test('confirmed user-space blocks retain library, class, or concrete module names', () => {
  const expected = {
    apps: ['TuanjieHmi', 'animmgr'], scene: ['ivi-shell.so', 'ivi-controller.so'],
    drmbackend: ['drm-backend.so'], sdm: ['sdm-service.so'], sdmcore: ['libsdmcore.so'],
    renderer: ['gl-renderer.so'], libdrm: ['libdrm.so'], drmfe: ['lib_drm_fe.so'],
    egl: ['libEGL.so', 'libGLESv2.so'], wclient: ['libopenwfd.so'], bclient: ['libopenwfd.so'],
    backend: ['VirtIOGPU2DCommandProcessor'],
    server0: ['WFD_ClientMgr', 'WFD_CommitMgr'], server1: ['WFD_ClientMgr', 'WFD_CommitMgr'],
    config: ['display_cfg.ini'], gslrpc: ['gsl_hab_server'], gslhab: ['libuhab.so'],
    gsllocal: ['libgsl.so'], viewroot: ['ViewRootImpl'], hwui: ['libhwui.so'],
    gles: ['libEGL.so', 'libGLESv2.so', 'libvulkan.so'],
    umd: ['libGLESv2_adreno.so', 'vulkan.adreno.so'], libgsl: ['libgsl.so'],
    hwc: ['AidlComposer', 'AidlComposerClient'], gralloc: ['QtiAllocatorAIDL'],
  };
  for (const [id, names] of Object.entries(expected)) {
    const title = node(id).name.join(' ');
    for (const name of names) assert.ok(title.includes(name), `${id}: title must identify ${name}, got ${title}`);
  }
  for (const item of nodes) {
    assert.doesNotMatch(item.name.join(' '), /SDM 合成策略|DRM 兼容前端|OpenWFD client 库|Port \/ Pipeline \/ 显示提交/,
      `${item.id}: generic responsibility must not replace the component title`);
  }
});

test('SDM and DRM remain split into their confirmed dependency chain', () => {
  const pairs = [
    ['scene', 'drmbackend'], ['drmbackend', 'sdm'], ['sdm', 'sdmcore'],
    ['drmbackend', 'renderer'], ['sdmcore', 'libdrm'], ['libdrm', 'drmfe'], ['drmfe', 'wclient'],
  ];
  for (const [from, to] of pairs) assert.ok(edges.some(item => item.from === from && item.to === to), `Missing ${from} → ${to}`);
  assert.ok(!edges.some(item => ['sdm', 'sdmcore'].includes(item.from) && item.to === 'renderer'),
    'Weston drm-backend, not SDM itself, dispatches the GL renderer');
});

test('gsl_hab_server has two equal, parallel dependency libraries below it', () => {
  const server = node('gslrpc');
  const hab = node('gslhab');
  const gsl = node('gsllocal');
  assert.equal(hab.y, gsl.y, 'Dependency libraries must share a row');
  assert.equal(hab.w, gsl.w, 'Dependency libraries must have equal widths');
  assert.equal(hab.h, gsl.h, 'Dependency libraries must have equal heights');
  assert.ok(hab.x + hab.w < gsl.x, 'libuhab and libgsl must be separate, parallel blocks');
  assert.ok(server.y + server.h < hab.y, 'Both libraries must be below gsl_hab_server');
  for (const target of ['gslhab', 'gsllocal']) {
    assert.ok(edges.some(item => item.from === 'gslrpc' && item.to === target), `Missing server → ${target} call`);
  }
  assert.ok(!edges.some(item => ['gslhab', 'gsllocal'].includes(item.from) && ['gslhab', 'gsllocal'].includes(item.to)),
    'The diagram must not imply a dependency between libuhab and libgsl');
  assert.equal(edge('gslipc').from, 'gsllocal');
  assert.equal(edge('gslipc').to, 'rgs');
});

test('both OpenWFD clients connect to both independent display services', () => {
  const expected = {weston0: ['wclient', 'server0'], weston1: ['wclient', 'server1'],
    guest0: ['bclient', 'server0'], guest1: ['bclient', 'server1']};
  for (const [id, pair] of Object.entries(expected)) {
    const item = edge(id);
    assert.deepEqual([item.from, item.to], pair, `${id}: incorrect client/server association`);
    const [start, end] = endpoints(item);
    assert.ok(onBorder(start, node(item.from)), `${id}: detached client endpoint`);
    assert.ok(onBorder(end, node(item.to)), `${id}: detached service endpoint`);
  }
});

test('two client arrows entering each WFD service have at least 32 px separation', () => {
  for (const target of ['server0', 'server1']) {
    const connections = edges.filter(item => ['wclient', 'bclient'].includes(item.from) && item.to === target);
    assert.equal(connections.length, 2, `${target}: expected one arrow from each client`);
    const [a, b] = connections.map(item => endpoints(item)[1]);
    assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= 32, `${target}: crowded target ports ${JSON.stringify([a, b])}`);
  }
});

test('LRMC is not a floating edge label over the client-to-service routing corridor', () => {
  assert.deepEqual(edges.filter(item => /LRMC/i.test(item.label || '')).map(item => item.id), [],
    'Place LRMC in a component subtitle or fixed service annotation, not over crossing arcs');
});

test('WFD resource connections leave and enter the horizontal center of their blocks', () => {
  for (const id of ['resource0', 'resource1']) {
    const item = edge(id);
    const source = node(item.from);
    const target = node(item.to);
    const [start, end] = endpoints(item);
    assert.ok(near(start.x, source.x + source.w / 2), `${id}: off-center source port`);
    assert.ok(near(start.y, source.y + source.h), `${id}: expected source bottom port`);
    assert.ok(near(end.x, target.x + target.w / 2), `${id}: off-center kernel port`);
    assert.ok(near(end.y, target.y), `${id}: expected kernel top port`);
  }
});

test('all route endpoints remain on their declared source and target borders', () => {
  for (const item of edges) {
    const [start, end] = endpoints(item);
    assert.ok(onBorder(start, node(item.from)), `${item.id}: ${JSON.stringify(start)} is outside ${item.from} border`);
    assert.ok(onBorder(end, node(item.to)), `${item.id}: ${JSON.stringify(end)} is outside ${item.to} border`);
  }
});

test('node rectangles never overlap', () => {
  const overlaps = [];
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      if (Math.max(a.x, b.x) < Math.min(a.x + a.w, b.x + b.w) - epsilon &&
          Math.max(a.y, b.y) < Math.min(a.y + a.h, b.y + b.h) - epsilon) overlaps.push(`${a.id} / ${b.id}`);
    }
  }
  assert.deepEqual(overlaps, []);
});

test('no author route crosses the interior of an unrelated node', () => {
  const collisions = [];
  for (const item of edges) {
    const points = routePoints(item.d);
    for (let i = 1; i < points.length; i++) {
      if (points[i].move) continue;
      for (const rectangle of nodes) {
        if (rectangle.id === item.from || rectangle.id === item.to) continue;
        if (segmentEntersNode(points[i - 1], points[i], rectangle)) collisions.push(`${item.id} segment ${i} → ${rectangle.id}`);
      }
    }
  }
  assert.deepEqual(collisions, []);
});

test('production crossing bridge jumps at an interior crossing and preserves source data', () => {
  const input = [{id: 'h', d: 'M0 50 H100'}, {id: 'v', d: 'M50 0 V100'}];
  const before = JSON.stringify(input);
  const result = routeCrossingBridges(input);
  assert.equal(result.get('h'), 'M0 50 H44 A6 6 0 0 1 56 50 H100');
  assert.equal(result.get('v'), input[1].d);
  assert.equal(JSON.stringify(input), before);
  assert.deepEqual(Array.from(result.bridgeArcs.get('h')), ['M44 50 A6 6 0 0 1 56 50']);
});

test('crossing bridges respect visibility, direction, shared endpoints and obstructions', () => {
  const h = {id: 'h', d: 'M0 50 H100'};
  const v = {id: 'v', d: 'M50 0 V100'};
  assert.equal(routeCrossingBridges([h, v], new Set(['h'])).get('h'), h.d);
  assert.equal(routeCrossingBridges([{id: 'h', d: 'M100 50 H0'}, v]).get('h'),
    'M100 50 H56 A6 6 0 0 0 44 50 H0');
  for (const d of ['M50 50 V100', 'M50 0 V50', 'M50 0 V50 H100']) {
    assert.equal(routeCrossingBridges([h, {id: 'v', d}]).get('h'), h.d);
  }
  assert.equal(routeCrossingBridges([h, v, {id: 'near', d: 'M30 45 H70'}]).get('h'), h.d);
  assert.equal(routeCrossingBridges([h, v, {id: 'crowded', d: 'M60 0 V100'}]).get('h'), h.d);
});

test('actual routes get deterministic bridge paths without mutating author geometry', () => {
  const before = JSON.stringify(edges);
  const result = routeCrossingBridges(edges);
  const reordered = routeCrossingBridges([...edges].reverse());
  assert.equal(result.size, edges.length);
  assert.ok(edges.some(item => result.get(item.id) !== item.d), 'Real diagram should retain crossing arcs');
  for (const item of edges) assert.equal(result.get(item.id), reordered.get(item.id), `${item.id}: order-dependent crossing geometry`);
  assert.equal(JSON.stringify(edges), before);
});

test('every true crossing in the actual PVM submission corridor has its own visible bridge', () => {
  const frames = ['weston', 'display-be', 'gsl-hab-server'].map(id => groupRectangle('pvm-process', id));
  const corridor = {
    left: Math.min(...frames.map(frame => frame.x)),
    right: Math.max(...frames.map(frame => frame.x + frame.width)),
    top: Math.max(...frames.map(frame => frame.y + frame.height)),
    bottom: Math.min(node('server0').y, node('server1').y, node('rgs').y),
  };
  const result = routeCrossingBridges(edges);
  const allSegments = edges.flatMap(segments);
  const horizontal = allSegments.filter(segment => segment.horizontal);
  const vertical = allSegments.filter(segment => !segment.horizontal);
  const crossings = [];
  const missing = [];
  for (const h of horizontal) {
    for (const v of vertical) {
      if (h.edgeId === v.edgeId) continue;
      const x = v.a.x, y = h.a.y;
      if (!insideRange(x, corridor.left, corridor.right) || !insideRange(y, corridor.top, corridor.bottom) ||
          !insideRange(x, h.a.x, h.b.x) || !insideRange(y, v.a.y, v.b.y)) continue;
      crossings.push(`${h.edgeId}/${v.edgeId}`);
      if (!bridgeGeometry(result, h.edgeId).some(arc => near(arc.x, x) && near(arc.y, y))) {
        missing.push(`${h.edgeId} over ${v.edgeId} at (${x}, ${y})`);
      }
    }
  }
  // These real crossings previously lost their arcs because routes were crowded.
  for (const pair of ['weston1/rendercmd', 'weston1/weston0', 'rendercmd/cfg0',
    'rendercmd/cfg1', 'rendercmd/habgpu', 'rendercmd/gslipc']) {
    assert.ok(crossings.includes(pair), `Expected actual route crossing ${pair} in the PVM corridor`);
  }
  assert.deepEqual(missing, [], 'A true crossing must not silently lose its jump arc');
});

test('configuration detour, bridge halos and adjacent GPU/config/HAB lanes retain clearance', () => {
  const serviceFrames = ['openwfd-0', 'openwfd-1', 'kgsl'].map(id => groupRectangle('pvm-service', id));
  const serviceBottom = Math.max(...serviceFrames.map(frame => frame.y + frame.height));
  const boundary = html.match(/<path class="mode-boundary" d="M[\d.]+ ([\d.]+) H[\d.]+"/);
  assert.ok(boundary, 'Missing horizontal userspace/kernel mode boundary');
  const boundaryY = Number(boundary[1]);
  const result = routeCrossingBridges(edges);
  const cfgSegments = segments(edge('cfg0'));
  const detourY = Math.max(...cfgSegments.flatMap(segment => [segment.a.y, segment.b.y]));
  const detours = cfgSegments.filter(segment => segment.horizontal && near(segment.a.y, detourY));
  assert.ok(detours.length > 0, 'Expected a lower horizontal cfg0 detour');
  const arcs = bridgeGeometry(result, 'cfg0').filter(arc => near(arc.y, detourY));
  assert.ok(arcs.length > 0, 'The actual cfg0 detour must retain its crossing bridges');
  const haloRadius = strokeWidth('.edge-halo') / 2;
  const arcTop = Math.min(detourY, ...arcs.map(arc => arc.y - arc.radius)) - haloRadius;
  const haloBottom = detourY + haloRadius;
  const serviceStrokeBottom = serviceBottom + strokeWidth('.process') / 2;
  const boundaryStrokeTop = boundaryY - strokeWidth('.mode-boundary') / 2;
  assert.ok(arcTop - serviceStrokeBottom >= 6,
    `cfg0 arc/halo grazes service frames: only ${arcTop - serviceStrokeBottom}px clearance`);
  assert.ok(boundaryStrokeTop - haloBottom >= 6,
    `cfg0 halo grazes mode boundary: only ${boundaryStrokeTop - haloBottom}px clearance`);

  const lanes = ['rendercmd', 'cfg0', 'cfg1', 'habdisplay', 'habgpu', 'gslipc', 'setup'].flatMap(id => segments(edge(id)));
  const crowded = [];
  for (let i = 0; i < lanes.length; i++) {
    for (let j = i + 1; j < lanes.length; j++) {
      const a = lanes[i], b = lanes[j];
      if (a.edgeId === b.edgeId || a.horizontal !== b.horizontal) continue;
      const axis = a.horizontal ? 'x' : 'y';
      const across = a.horizontal ? 'y' : 'x';
      const overlap = Math.min(Math.max(a.a[axis], a.b[axis]), Math.max(b.a[axis], b.b[axis])) -
        Math.max(Math.min(a.a[axis], a.b[axis]), Math.min(b.a[axis], b.b[axis]));
      const distance = Math.abs(a.a[across] - b.a[across]);
      // Coincident cfg0/cfg1 trunks intentionally share their configuration source.
      if (overlap > epsilon && distance > epsilon && distance < 16) {
        crowded.push(`${a.edgeId}/${b.edgeId}: ${distance}px parallel spacing`);
      }
    }
  }
  assert.deepEqual(crowded, [], 'GPU/configuration/HAB parallel lanes need at least 16 px separation');
});
