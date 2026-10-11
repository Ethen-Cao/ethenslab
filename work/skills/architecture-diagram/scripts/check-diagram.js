/* Architecture diagram v2 browser geometry audit. Inject after rendering and call checkDiagram(). */
(() => {
  'use strict';
  const EPS = 0.05, TOL = 1.25;
  const NORMAL = {top: [0, -1], bottom: [0, 1], left: [-1, 0], right: [1, 0]};
  const near = (a, b, t = TOL) => Math.abs(a - b) <= t;
  const equal = (a, b) => near(a.x, b.x) && near(a.y, b.y);
  const overlap = (a, b) => Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1)) * Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const contains = (a, b, p = 0) => b.x1 >= a.x1 + p - TOL && b.y1 >= a.y1 + p - TOL && b.x2 <= a.x2 - p + TOL && b.y2 <= a.y2 - p + TOL;
  const expanded = (b, p) => ({x1: b.x1 - p, y1: b.y1 - p, x2: b.x2 + p, y2: b.y2 + p});
  const distance = (a, b) => Math.hypot(Math.max(a.x1 - b.x2, b.x1 - a.x2, 0), Math.max(a.y1 - b.y2, b.y1 - a.y2, 0));
  const pointInside = (p, b) => p.x >= b.x1 - TOL && p.x <= b.x2 + TOL && p.y >= b.y1 - TOL && p.y <= b.y2 + TOL;
  function parseRoute(d) {
    if (typeof d !== 'string' || !d || /[^\d\s.,+\-eEMHVL]/.test(d)) return null;
    const tokens = d.match(/[MHVL]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) || [];
    const points = []; let command = null, index = 0;
    const read = () => Number(tokens[index++]);
    while (index < tokens.length) {
      if (/^[MHVL]$/.test(tokens[index])) command = tokens[index++];
      const last = points[points.length - 1]; let next;
      if (command === 'M') { if (last) return null; next = {x: read(), y: read()}; command = 'L'; }
      else if (!last) return null;
      else if (command === 'L') next = {x: read(), y: read()};
      else if (command === 'H') next = {x: read(), y: last.y};
      else if (command === 'V') next = {x: last.x, y: read()};
      else return null;
      if (!Number.isFinite(next.x) || !Number.isFinite(next.y)) return null;
      if (last && !near(last.x, next.x, EPS) && !near(last.y, next.y, EPS)) return null;
      if (!last || !equal(last, next)) points.push(next);
    }
    return points.length >= 2 ? points : null;
  }
  function segmentsOf(points) {
    return points.slice(1).map((b, i) => {
      const a = points[i], horizontal = near(a.y, b.y, EPS);
      return {a, b, horizontal, c: horizontal ? a.y : a.x, lo: horizontal ? Math.min(a.x, b.x) : Math.min(a.y, b.y), hi: horizontal ? Math.max(a.x, b.x) : Math.max(a.y, b.y)};
    });
  }
  function hits(s, box, pad = 0) {
    const b = expanded(box, pad);
    return s.horizontal ? s.c > b.y1 + EPS && s.c < b.y2 - EPS && s.hi > b.x1 + EPS && s.lo < b.x2 - EPS :
      s.c > b.x1 + EPS && s.c < b.x2 - EPS && s.hi > b.y1 + EPS && s.lo < b.y2 - EPS;
  }
  function sideOf(p, b) {
    if (!pointInside(p, b)) return null;
    if (near(p.y, b.y1)) return 'top'; if (near(p.y, b.y2)) return 'bottom';
    if (near(p.x, b.x1)) return 'left'; if (near(p.x, b.x2)) return 'right'; return null;
  }
  const direction = (a, b) => [Math.sign(b.x - a.x), Math.sign(b.y - a.y)];
  const away = (s, a, b) => (s === 'top' && b.y1 >= a.y2) || (s === 'bottom' && b.y2 <= a.y1) || (s === 'left' && b.x1 >= a.x2) || (s === 'right' && b.x2 <= a.x1);

  function checkDiagram(options = {}) {
    const errors = [], warnings = [], seenProblems = new Set();
    const issue = (list, code, message) => { const key = `${code}:${message}`; if (!seenProblems.has(key)) { list.push({code, message}); seenProblems.add(key); } };
    const error = (c, m) => issue(errors, c, m), warn = (c, m) => issue(warnings, c, m);
    const model = window.architectureModel, geometry = window.architectureGeometry, theme = window.ArchitectureTheme;
    const counts = {containers: 0, nodes: 0, edges: 0, labels: 0, bridges: 0, junctions: 0};
    const expectedCounts = {containers: Array.isArray(model?.containers) ? model.containers.length : 0,
      nodes: Array.isArray(model?.nodes) ? model.nodes.length : 0, edges: Array.isArray(model?.edges) ? model.edges.length : 0,
      labels: Array.isArray(model?.edges) ? model.edges.filter(e => e.label || e.relation === 'ipc').length : 0};
    const finish = () => {
      const result = {ok: errors.length === 0, errors, warnings, counts, expectedCounts};
      if (!options.quiet) { console.log(`Architecture geometry: ${errors.length} errors, ${warnings.length} warnings`, {counts, expectedCounts}); if (errors.length) console.table(errors); if (warnings.length) console.table(warnings); }
      return result;
    };
    if (!model || model.version !== 2 || !Array.isArray(model.nodes) || !Array.isArray(model.edges) || !Array.isArray(model.containers)) {
      error('unknown-model', 'A v2 architectureModel is required; legacy or arbitrary SVG cannot pass this audit.'); return finish();
    }
    if (!expectedCounts.nodes) error('empty-model', 'The architecture model must contain at least one node.');
    if (!window.ArchitectureModel) error('missing-validator', 'The semantic model validator is not loaded.');
    else for (const p of window.ArchitectureModel.validate(model).errors) error(`model-${p.code}`, p.message);
    if (!geometry) error('missing-geometry', 'The renderer did not publish architectureGeometry.');
    const hasTheme = theme?.version === 1 && theme.fonts && theme.type && theme.radii && theme.strokes && theme.geometry && theme.code;
    if (!hasTheme) error('missing-theme', 'The shared ArchitectureTheme visual contract must be loaded.');
    const familyName = value => String(value || '').trim().replace(/^['"]|['"]$/g, '');
    const weightMatches = (value, weight) => {
      const parts = String(value === 'normal' ? 400 : value === 'bold' ? 700 : value).trim().split(/\s+/).map(Number);
      return parts.length === 1 ? parts[0] === weight : parts.length === 2 && weight >= parts[0] && weight <= parts[1];
    };
    if (hasTheme) {
      const fontRules = [];
      for (const sheet of document.styleSheets) {
        try { for (const rule of sheet.cssRules) if (rule.type === CSSRule.FONT_FACE_RULE) fontRules.push(rule); }
        catch { error('font-stylesheet-access', 'Font stylesheets must be local and inspectable in the standalone document.'); }
      }
      for (const font of Object.values(theme.fonts)) for (const weight of font.weights) {
        const matches = [...document.fonts].filter(face => familyName(face.family) === font.family && weightMatches(face.weight, weight) && face.style === 'normal');
        if (!matches.some(face => face.status === 'loaded')) error('font-not-loaded', `${font.family} ${weight} must be an actually loaded FontFace, not a system fallback.`);
        const rules = fontRules.filter(rule => familyName(rule.style.fontFamily) === font.family && weightMatches(rule.style.fontWeight, weight));
        if (!rules.some(rule => /^url\(["']?data:/i.test(rule.style.getPropertyValue('src').trim()) && !/\blocal\s*\(/i.test(rule.style.getPropertyValue('src')))) {
          error('font-not-embedded', `${font.family} ${weight} needs an embedded data-URL font face; remote or local-only fonts are not self-contained.`);
        }
      }
    }
    const checkFont = (el, mono, label, expectedWeight) => {
      if (!hasTheme) return;
      const style = getComputedStyle(el), expected = theme.fonts[mono ? 'mono' : 'sans'].family;
      if (familyName(style.fontFamily.split(',')[0]) !== expected) error('font-family', `${label} must use ${expected} as its first font family.`);
      if (expectedWeight !== undefined && !weightMatches(style.fontWeight, expectedWeight)) error('font-weight', `${label} must use weight ${expectedWeight}.`);
    };
    const numericStyle = (el, property, expected, code, label) => {
      if (hasTheme && !near(parseFloat(getComputedStyle(el)[property]), expected, EPS)) error(code, `${label} must use ${expected} for ${property}.`);
    };
    const checkRadius = (el, expected, label) => numericStyle(el, 'rx', expected, 'shape-radius', label);
    const isCodeText = value => hasTheme && new RegExp(theme.code.textPattern).test(String(value || '').trim());
    const checkEdgeStyle = (el, type, label) => {
      if (!hasTheme) return;
      numericStyle(el, 'strokeWidth', theme.strokes[type], 'edge-stroke-width', label);
      const actual = getComputedStyle(el).strokeDasharray.match(/[\d.]+/g)?.map(Number) || [];
      const expected = type === 'notification' ? [3, 5] : type === 'config' ? [6, 5] : [];
      if (actual.length !== expected.length || actual.some((value, i) => !near(value, expected[i], EPS))) error('edge-dash-style', `${label} has a dash pattern inconsistent with ${type}.`);
    };
    const svg = document.querySelector('svg#architecture');
    if (!svg) { error('missing-svg', 'No rendered architecture SVG was found.'); return finish(); }
    const root = svg.querySelector('#viewport');
    if (!root || !root.getScreenCTM()) { error('not-rendered', 'The architecture viewport is missing or not rendered.'); return finish(); }
    const inverse = root.getScreenCTM().inverse();
    const toRoot = el => inverse.multiply(el.getScreenCTM());
    const mapPoint = (m, x, y) => { const p = new DOMPoint(x, y).matrixTransform(m); return {x: p.x, y: p.y}; };
    const boxOf = el => { const b = el.getBBox(), m = toRoot(el), a = mapPoint(m, b.x, b.y), c = mapPoint(m, b.x + b.width, b.y + b.height); return {x1: Math.min(a.x, c.x), y1: Math.min(a.y, c.y), x2: Math.max(a.x, c.x), y2: Math.max(a.y, c.y)}; };
    const rendered = el => { for (let p = el; p; p = p.parentElement) { const s = getComputedStyle(p); if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || Number(s.opacity) === 0) return false; } return true; };
    const canvas = {x1: 0, y1: 0, x2: model.canvas.width, y2: model.canvas.height};
    if (!near(svg.getBoundingClientRect().width, model.canvas.width) || !near(svg.getBoundingClientRect().height, model.canvas.height)) error('diagram-scaled', 'The SVG must retain its natural logical-pixel size; scroll instead of fit-shrinking.');
    const title = document.getElementById('diagram-title');
    if (!title || title.textContent !== model.meta.title) error('diagram-title', 'The visible diagram title must match the model title.');
    else {
      if (!near(parseFloat(getComputedStyle(title).fontSize), theme?.type?.title || 24, EPS)) error('diagram-title-size', 'The diagram title must use the shared title size.');
      checkFont(title, false, 'Diagram title', 700);
    }
    const subtitle = document.getElementById('diagram-subtitle');
    if (subtitle) checkFont(subtitle, false, 'Diagram subtitle', 400);
    const shell = document.querySelector('.diagram-shell');
    if (!shell) error('missing-shell', 'The diagram needs its natural-size scrolling shell.');
    else if (hasTheme) for (const property of ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius']) numericStyle(shell, property, theme.radii.shell, 'shell-radius', 'Diagram shell');
    const ids = new Map(); document.querySelectorAll('[id]').forEach(el => ids.set(el.id, (ids.get(el.id) || 0) + 1));
    for (const [id, total] of ids) if (total > 1) error('duplicate-dom-id', `Duplicate DOM id: ${id}`);
    const modeled = {container: new Map(model.containers.map(c => [c.id, c])), node: new Map(model.nodes.map(n => [n.id, n])), edge: new Map(model.edges.map(e => [e.id, e]))};
    function collect(kind, selector) {
      const result = new Map();
      for (const g of svg.querySelectorAll(selector)) {
        const id = g.dataset[kind];
        if (!modeled[kind].has(id)) error('unknown-rendered-id', `Rendered ${kind} ${id} is absent from the model.`);
        if (result.has(id)) error('duplicate-rendered-id', `Rendered ${kind} ${id} occurs more than once.`);
        if (!rendered(g)) { error('hidden-entity', `Modeled ${kind} ${id} is hidden.`); continue; }
        result.set(id, g);
      }
      for (const id of modeled[kind].keys()) if (!result.has(id)) error('missing-entity', `Modeled ${kind} ${id} was not rendered.`);
      return result;
    }
    const containerGroups = collect('container', 'g[data-container]'), nodeGroups = collect('node', 'g[data-node]'), edgeGroups = collect('edge', 'g[data-edge]');
    const containers = new Map(), nodes = new Map(), edges = [], marks = [];
    counts.containers = containerGroups.size; counts.nodes = nodeGroups.size; counts.edges = edgeGroups.size;
    const isAncestor = (parent, child) => { const seen = new Set(); let id = child; while (id && !seen.has(id)) { if (id === parent) return true; seen.add(id); id = modeled.container.get(id)?.parent; } return false; };
    for (const [id, g] of containerGroups) {
      const frame = g.querySelector(':scope > rect.container-frame');
      if (!frame) { error('missing-container-frame', `Container ${id} has no measurable frame.`); continue; }
      if (hasTheme) {
        const domain = modeled.container.get(id)?.kind === 'domain';
        checkRadius(frame, theme.radii[domain ? 'domain' : 'container'], `Container ${id}`);
        numericStyle(frame, 'strokeWidth', theme.strokes[domain ? 'domain' : 'frame'], 'frame-stroke-width', `Container ${id}`);
      }
      const box = boxOf(frame), headerBottom = Number(g.dataset.headerBottom), contentTop = Number(g.dataset.contentTop);
      if (!Number.isFinite(headerBottom) || !Number.isFinite(contentTop)) error('missing-header', `Container ${id} has no measured header boundary.`);
      if (!contains(canvas, box)) error('canvas-overflow', `Container ${id} exceeds the canvas.`);
      if (!g.querySelector(':scope > .container-title')) error('missing-container-title', `Container ${id} has no title.`);
      containers.set(id, {id, box, parent: g.dataset.parent, headerBottom, contentTop});
      for (const text of g.querySelectorAll(':scope > text')) {
        const mark = {id, box: boxOf(text), text: text.textContent}; marks.push(mark);
        if (!contains(box, mark.box, 8)) error('container-text-overflow', `Container ${id} does not fit: ${mark.text}`);
        if (mark.box.y2 > headerBottom - 8 + TOL) error('header-text-clearance', `Container ${id} needs more header room below: ${mark.text}`);
        const isSubtitle = text.classList.contains('container-subtitle');
        const expectedSize = isSubtitle ? theme?.type?.subtitle || 12 : modeled.container.get(id)?.kind === 'domain' ? theme?.type?.domain || 20 : theme?.type?.container || 18;
        if (!near(parseFloat(getComputedStyle(text).fontSize), expectedSize, EPS)) error('container-font-size', `Container ${id} text must use ${expectedSize} px type.`);
        checkFont(text, false, `Container ${id} text`, isSubtitle ? 400 : 700);
      }
    }
    for (const c of containers.values()) {
      if (!c.parent) continue; const p = containers.get(c.parent);
      if (!p) { error('unknown-container-parent', `Container ${c.id} has no rendered parent ${c.parent}.`); continue; }
      if (!contains(p.box, c.box, 16) || c.box.y1 < p.contentTop - TOL) error('container-outside-content', `Container ${c.id} must be inside ${c.parent}, below its header, with 16 px padding.`);
    }
    const containerList = [...containers.values()];
    for (let i = 0; i < containerList.length; i++) for (let j = i + 1; j < containerList.length; j++) {
      const a = containerList[i], b = containerList[j];
      if (!isAncestor(a.id, b.id) && !isAncestor(b.id, a.id) && overlap(a.box, b.box) > TOL) error('container-overlap', `Unrelated containers overlap: ${a.id} / ${b.id}`);
    }
    for (const [id, g] of nodeGroups) {
      const face = g.querySelector(':scope > rect.face');
      if (!face) { error('missing-node-face', `Node ${id} has no measurable face.`); continue; }
      if (hasTheme) for (const sheet of g.querySelectorAll(':scope > rect')) {
        checkRadius(sheet, theme.radii.node, `Node ${id}`);
        numericStyle(sheet, 'strokeWidth', theme.strokes.node, 'node-stroke-width', `Node ${id}`);
      }
      const faceBox = boxOf(face), outline = boxOf(g), parent = containers.get(g.dataset.parent);
      const sheets = [...g.querySelectorAll(':scope > rect')].map(boxOf);
      const box = modeled.node.get(id)?.entityType === 'memory' ? {
        x1: Math.min(...sheets.map(b => b.x1)), y1: Math.min(...sheets.map(b => b.y1)),
        x2: Math.max(...sheets.map(b => b.x2)), y2: Math.max(...sheets.map(b => b.y2))
      } : faceBox;
      nodes.set(id, {id, box, outline, parent: g.dataset.parent});
      if (!contains(canvas, outline)) error('canvas-overflow', `Node ${id} exceeds the canvas.`);
      if (!parent) error('unknown-node-parent', `Node ${id} has no rendered parent ${g.dataset.parent}.`);
      else if (!contains(parent.box, outline, 16) || outline.y1 < parent.contentTop - TOL) error('node-outside-content', `Node ${id} must be inside ${parent.id}, below its header, with 16 px padding.`);
      for (const c of containers.values()) if (!isAncestor(c.id, g.dataset.parent) && overlap(outline, c.box) > TOL) error('node-wrong-container', `Node ${id} visually enters ${c.id}, which is not its declared owner.`);
      for (const mark of marks) if (overlap(outline, expanded(mark.box, 8)) > TOL) error('node-title-overlap', `Node ${id} overlaps the title clearance of ${mark.id}.`);
      const name = [...g.querySelectorAll(':scope > .node-name')];
      if (!name.length) error('missing-node-name', `Node ${id} has no visible canonical name.`);
      const expectedName = modeled.node.has(id) && window.ArchitectureModel?.displayName(modeled.node.get(id));
      if (expectedName && name.map(t => t.textContent).join('').replace(/\s/g, '') !== expectedName.replace(/\s/g, '')) error('name-mismatch', `Node ${id} does not show its model canonical name.`);
      for (const text of g.querySelectorAll(':scope > text')) {
        if (!contains(faceBox, boxOf(text), 8)) error('text-overflow', `Node ${id} needs more room for: ${text.textContent}`);
        const primary = text.classList.contains('node-name');
        const size = parseFloat(getComputedStyle(text).fontSize), expected = primary ? theme?.type?.node || 16 : theme?.type?.subtitle || 12;
        if (!near(size, expected, 0.05)) error('node-font-size', `Node ${id} uses ${size}px; expected ${expected}px.`);
        checkFont(text, primary ? hasTheme && theme.code.nodeTypes.includes(modeled.node.get(id)?.entityType) : isCodeText(modeled.node.get(id)?.description), `Node ${id} ${primary ? 'name' : 'subtitle'}`, primary ? 700 : 400);
        const textBox = boxOf(text);
        if (![textBox.x1, textBox.y1, textBox.x2, textBox.y2].every(Number.isFinite) || textBox.x2 <= textBox.x1 || textBox.y2 <= textBox.y1) error('unmeasurable-text', `Node ${id} has empty or unmeasurable visible text.`);
      }
      const textBoxes = [...g.querySelectorAll(':scope > text')].map(boxOf);
      if (textBoxes.length && !near((Math.min(...textBoxes.map(b => b.y1)) + Math.max(...textBoxes.map(b => b.y2))) / 2, (faceBox.y1 + faceBox.y2) / 2)) error('text-group-center', `Node ${id} text group must be vertically centered using measured font bounds.`);
    }
    const nodeList = [...nodes.values()];
    for (let i = 0; i < nodeList.length; i++) for (let j = i + 1; j < nodeList.length; j++) {
      const a = nodeList[i], b = nodeList[j];
      if (overlap(a.outline, b.outline) > TOL) error('node-overlap', `Nodes overlap: ${a.id} / ${b.id}`);
      else if (distance(a.outline, b.outline) < 24 - TOL) warn('node-gap', `Nodes ${a.id} / ${b.id} have less than 24 px separation.`);
    }
    for (const [id, g] of edgeGroups) {
      const path = g.querySelector(':scope > path.edge'), item = modeled.edge.get(id);
      if (!path || !item) { error('unmeasurable-edge', `Edge ${id} has no recognized path or model entry.`); continue; }
      const expectedType = window.ArchitectureModel?.edgeType(item);
      if (g.dataset.type !== expectedType) error('edge-type-mismatch', `Edge ${id} style type differs from its modeled relationship.`);
      if (expectedType) checkEdgeStyle(path, expectedType, `Edge ${id}`);
      if (g.querySelectorAll(':scope > path.edge').length !== 1) error('ambiguous-edge-path', `Edge ${id} must have exactly one primary path.`);
      const raw = parseRoute(g.dataset.route);
      if (!raw) { error('route-format', `Edge ${id} needs an absolute orthogonal M/H/V/L source route.`); continue; }
      if (g.dataset.from !== item.from || g.dataset.to !== item.to) error('endpoint-mismatch', `Rendered endpoints of ${id} differ from its model.`);
      const matrix = toRoot(path), points = raw.map(p => mapPoint(matrix, p.x, p.y));
      if (!path.getAttribute('d') || path.getTotalLength() < 1) error('empty-path', `Edge ${id} has no visible route.`);
      if (geometry?.routes?.[id]?.renderedD !== path.getAttribute('d')) error('rendered-route-mismatch', `Visible edge ${id} differs from its generated route; no path may be silently ignored.`);
      if (!path.getAttribute('marker-end')) error('missing-arrow', `Edge ${id} has no direction marker.`);
      else if (expectedType && path.getAttribute('marker-end') !== `url(#arrow-${expectedType})`) error('arrow-type-mismatch', `Edge ${id} must use its relationship's arrow marker.`);
      edges.push({...item, points, segments: segmentsOf(points), type: g.dataset.type, keep: Boolean(item.keepAnchor)});
    }
    for (const path of svg.querySelectorAll('path.edge')) if (!path.closest('[data-edge]') && !path.closest('[data-bridge]')) error('unmodeled-path', 'A visible edge path has no model edge or bridge owner.');
    if (edges.length !== model.edges.length) error('edge-check-coverage', `Only ${edges.length} of ${model.edges.length} edges could be geometrically checked.`);
    const attachments = new Map();
    const addAttachment = (node, side, point, edge, end) => {
      const key = `${node.id}:${side}`, list = attachments.get(key) || []; let item = list.find(p => equal(p.point, point));
      if (!item) { item = {node, side, point, edges: [], keep: false, arrivals: []}; list.push(item); }
      item.edges.push(edge.id); item.keep ||= edge.keep; if (end) item.arrivals.push(edge.id); attachments.set(key, list);
    };
    for (const edge of edges) {
      const from = nodes.get(edge.from), to = nodes.get(edge.to);
      if (!from || !to) { error('unknown-endpoint', `Edge ${edge.id} has an unrendered endpoint.`); continue; }
      const first = edge.points[0], last = edge.points[edge.points.length - 1], startSide = sideOf(first, from.box), endSide = sideOf(last, to.box);
      if (!startSide) error('start-off-boundary', `Edge ${edge.id} does not start on ${from.id}.`);
      else {
        addAttachment(from, startSide, first, edge, false);
        if (direction(first, edge.points[1]).join() !== NORMAL[startSide].join()) error('start-direction', `Edge ${edge.id} must leave ${from.id} perpendicularly outward.`);
        if (away(startSide, from.box, to.box)) warn('away-side', `Edge ${edge.id} leaves ${from.id} facing away from ${to.id}; review routing.`);
      }
      if (!endSide) error('end-off-boundary', `Edge ${edge.id} does not end on ${to.id}.`);
      else {
        addAttachment(to, endSide, last, edge, true); const before = edge.points[edge.points.length - 2];
        if (direction(before, last).join() !== NORMAL[endSide].map(v => -v).join()) error('end-direction', `Edge ${edge.id} must enter ${to.id} perpendicularly inward.`);
        if (Math.abs(last.x - before.x) + Math.abs(last.y - before.y) < 16 - TOL) error('short-arrow', `Edge ${edge.id} needs a final straight segment of at least 16 px.`);
        if (away(endSide, to.box, from.box)) warn('away-side', `Edge ${edge.id} enters ${to.id} facing away from ${from.id}; review routing.`);
      }
      for (const n of nodeList) {
        if (edge.segments.some(s => hits(s, n.box, -0.25))) error('through-node', `Edge ${edge.id} passes through node ${n.id}.`);
        else if (n.id !== from.id && n.id !== to.id && edge.segments.some(s => hits(s, n.outline, 8 - TOL))) error('edge-node-clearance', `Edge ${edge.id} needs 8 px clearance from node ${n.id}.`);
      }
      for (const mark of marks) if (edge.segments.some(s => hits(s, mark.box, 8 - TOL))) error('edge-title-clearance', `Edge ${edge.id} enters the title clearance of ${mark.id}: ${mark.text}`);
      for (const c of containers.values()) if (edge.segments.some(s => (s.horizontal ? [c.box.y1, c.box.y2] : [c.box.x1, c.box.x2]).some(v => Math.abs(s.c - v) < 8 - TOL) &&
        Math.min(s.hi, s.horizontal ? c.box.x2 : c.box.y2) - Math.max(s.lo, s.horizontal ? c.box.x1 : c.box.y1) > 16)) warn('edge-on-border', `Edge ${edge.id} follows the border of ${c.id}.`);
      if (edge.points.some(p => !pointInside(p, canvas))) error('route-outside-canvas', `Edge ${edge.id} leaves the canvas.`);
      const common = containerList.filter(c => isAncestor(c.id, from.parent) && isAncestor(c.id, to.parent)).sort((a, b) => (a.box.x2 - a.box.x1) * (a.box.y2 - a.box.y1) - (b.box.x2 - b.box.x1) * (b.box.y2 - b.box.y1))[0];
      if (common && edge.points.some(p => !pointInside(p, common.box))) warn('leaves-container', `Edge ${edge.id} leaves its smallest common container ${common.id}.`);
      const bends = edge.segments.filter((s, i) => i && s.horizontal !== edge.segments[i - 1].horizontal).length;
      if (bends >= 5) warn('complex-route', `Edge ${edge.id} has ${bends} bends; review the layout.`);
    }
    for (const list of attachments.values()) {
      if (list.length === 1 && !list[0].keep) {
        const {node, side, point, edges: names} = list[0], offset = ['top', 'bottom'].includes(side) ? point.x - (node.box.x1 + node.box.x2) / 2 : point.y - (node.box.y1 + node.box.y2) / 2;
        if (Math.abs(offset) > TOL) error('off-center-anchor', `The single attachment on ${node.id}.${side} must be centered (${names.join(', ')}).`);
      }
      for (let i = 0; i < list.length; i++) {
        if (list[i].arrivals.length > 1) error('stacked-arrows', `Multiple arrows share one point on ${list[i].node.id}: ${list[i].arrivals.join(', ')}.`);
        for (let j = i + 1; j < list.length; j++) if (Math.hypot(list[i].point.x - list[j].point.x, list[i].point.y - list[j].point.y) < 12 - TOL) error('port-spacing', `Ports on ${list[i].node.id}.${list[i].side} need at least 12 px separation.`);
      }
    }
    const junctions = [...svg.querySelectorAll('.flow-junction')].filter(rendered).map(el => {
      const edgeIds = (el.dataset.junctionEdges || '').split(' '), owner = edgeGroups.get(edgeIds[0])?.querySelector('path.edge');
      if (hasTheme && !near(Number(el.getAttribute('r')), theme.geometry.junctionRadius, EPS)) error('junction-radius', 'A true junction must use the shared junction radius.');
      if (owner && getComputedStyle(el).fill !== getComputedStyle(owner).stroke) error('junction-color', 'A junction must match its relationship color.');
      return {...mapPoint(toRoot(el), Number(el.getAttribute('cx')), Number(el.getAttribute('cy'))), edges: edgeIds};
    });
    const bridges = [...svg.querySelectorAll('[data-bridge]')].filter(rendered).map(el => {
      const item = modeled.edge.get(el.dataset.bridge), type = item && window.ArchitectureModel?.edgeType(item);
      const halo = el.querySelector('.bridge-halo'), line = el.querySelector('path.edge');
      if (!item || !halo || !line) error('bridge-style-coverage', `Bridge ${el.dataset.bridge} needs a modeled owner, halo and visible line.`);
      else if (hasTheme) {
        numericStyle(halo, 'strokeWidth', theme.strokes[type] + 2 * theme.geometry.bridgeHaloPadding, 'bridge-halo-width', `Bridge ${item.id}`);
        checkEdgeStyle(line, type, `Bridge ${item.id}`);
        if (halo.getAttribute('d') !== line.getAttribute('d')) error('bridge-halo-route', `Bridge ${item.id} halo must follow its visible arc.`);
      }
      return {id: el.dataset.bridge, ...mapPoint(toRoot(el), Number(el.dataset.x), Number(el.dataset.y)), radius: Number(el.dataset.radius), box: boxOf(el)};
    });
    counts.bridges = bridges.length; counts.junctions = junctions.length;
    for (const bridge of bridges) {
      if (![bridge.x, bridge.y, bridge.radius].every(Number.isFinite) || bridge.radius <= 0) error('invalid-bridge', `Bridge for ${bridge.id} has invalid geometry.`);
      if (hasTheme && !near(bridge.radius, theme.geometry.bridgeRadius, EPS)) error('bridge-radius', `Bridge ${bridge.id} must use the shared bridge radius.`);
      for (const n of nodeList) if (overlap(bridge.box, expanded(n.outline, 8 - TOL)) > TOL) error('bridge-node-clearance', `Bridge for ${bridge.id} crowds node ${n.id}.`);
      for (const m of marks) if (overlap(bridge.box, expanded(m.box, 8 - TOL)) > TOL) error('bridge-title-clearance', `Bridge for ${bridge.id} crowds the title of ${m.id}.`);
    }
    const junctionAt = (p, a, b) => junctions.some(j => equal(j, p) && j.edges.includes(a.id) && j.edges.includes(b.id));
    const declaredTrunk = (a, b) => (model.junctions || []).some(j => j.edges.includes(a.id) && j.edges.includes(b.id));
    const sharedEndpoint = (p, a, b) => [[a.from, a.points[0]], [a.to, a.points[a.points.length - 1]]].some(([id, q]) => equal(q, p) && [[b.from, b.points[0]], [b.to, b.points[b.points.length - 1]]].some(([other, r]) => other === id && equal(r, p)));
    for (let i = 0; i < edges.length; i++) for (let j = i + 1; j < edges.length; j++) {
      const a = edges[i], b = edges[j], crossings = [];
      for (const s of a.segments) for (const t of b.segments) {
        if (s.horizontal === t.horizontal) {
          const length = Math.min(s.hi, t.hi) - Math.max(s.lo, t.lo), gap = Math.abs(s.c - t.c);
          if (length > 1 && gap < EPS && !declaredTrunk(a, b)) error('undeclared-edge-overlap', `Edges ${a.id} / ${b.id} overlap without a declared shared trunk.`);
          else if (length > 16 && gap > EPS && gap < 12 - TOL) warn('parallel-line-spacing', `Edges ${a.id} / ${b.id} have less than 12 px parallel separation.`);
          continue;
        }
        const h = s.horizontal ? s : t, v = s.horizontal ? t : s, p = {x: v.c, y: h.c};
        if (p.x < h.lo - EPS || p.x > h.hi + EPS || p.y < v.lo - EPS || p.y > v.hi + EPS) continue;
        if (junctionAt(p, a, b) || sharedEndpoint(p, a, b)) continue;
        if (!crossings.some(q => equal(p, q))) crossings.push(p);
        const interior = p.x > h.lo + EPS && p.x < h.hi - EPS && p.y > v.lo + EPS && p.y < v.hi - EPS, horizontalEdge = s.horizontal ? a : b;
        if (!interior) error('ambiguous-route-contact', `Edges ${a.id} / ${b.id} touch at an elbow or endpoint (${p.x}, ${p.y}) without a true junction.`);
        else if (!bridges.some(bridge => bridge.id === horizontalEdge.id && equal(bridge, p))) error('crossing-without-bridge', `Edges ${a.id} / ${b.id} cross without a bridge at (${p.x}, ${p.y}).`);
      }
      if (crossings.length > 1) warn('repeated-crossing', `Edges ${a.id} / ${b.id} cross ${crossings.length} times.`);
      if (crossings.length && [a.from, a.to].some(id => id === b.from || id === b.to)) warn('shared-node-crossing', `Edges ${a.id} / ${b.id} share a node and cross; order ports by approach.`);
    }
    const labels = [...svg.querySelectorAll('.edge-label')].filter(rendered).map(g => {
      const shape = g.querySelector('rect'), text = g.querySelector('text'), id = g.dataset.labelFor;
      if (!shape || !text) { error('unmeasurable-label', `Label ${id} needs text and a measurable background.`); return null; }
      if (!modeled.edge.has(id)) error('unknown-label', `Label ${id} does not belong to a model edge.`);
      if (!near(parseFloat(getComputedStyle(text).fontSize), theme?.type?.label || 13, 0.05)) error('label-font-size', `Label ${id} must use the shared label size.`);
      checkFont(text, isCodeText(text.textContent), `Edge label ${id}`, 400);
      if (hasTheme) checkRadius(shape, theme.radii.label, `Edge label ${id}`);
      if (!contains(boxOf(shape), boxOf(text))) error('label-text-overflow', `Label ${id} text must fit its measured background.`);
      return {id, box: boxOf(shape)};
    }).filter(Boolean);
    counts.labels = labels.length;
    for (let i = 0; i < labels.length; i++) {
      const label = labels[i];
      if (!contains(canvas, label.box)) error('label-outside-canvas', `Label ${label.id} leaves the canvas.`);
      for (const n of nodeList) if (overlap(label.box, expanded(n.outline, 8 - TOL)) > TOL) error('label-node-clearance', `Label ${label.id} crowds node ${n.id}.`);
      for (const m of marks) if (overlap(label.box, expanded(m.box, 8 - TOL)) > TOL) error('label-title-clearance', `Label ${label.id} crowds the title of ${m.id}.`);
      for (const e of edges) if (e.segments.some(s => hits(s, label.box, 8 - TOL))) error('label-edge-clearance', `Label ${label.id} needs 8 px clearance from edge ${e.id}.`);
      for (const b of bridges) if (overlap(label.box, expanded(b.box, 8 - TOL)) > TOL) error('label-bridge-clearance', `Label ${label.id} crowds the bridge on ${b.id}.`);
      for (let j = i + 1; j < labels.length; j++) if (overlap(label.box, expanded(labels[j].box, 8 - TOL)) > TOL) error('label-overlap', `Labels ${label.id} / ${labels[j].id} overlap or are too close.`);
    }
    const labelsByEdge = new Map(); for (const l of labels) labelsByEdge.set(l.id, (labelsByEdge.get(l.id) || 0) + 1);
    for (const e of model.edges) if ((e.label || e.relation === 'ipc') && labelsByEdge.get(e.id) !== 1) error('label-coverage', `Edge ${e.id} must have exactly one rendered label.`);
    const usedTypes = new Set(model.edges.map(edge => window.ArchitectureModel?.edgeType(edge)));
    const legend = document.querySelector('.diagram-legend');
    if (!legend && usedTypes.size) error('missing-legend', 'Used relationship styles need a legend.');
    if (legend) {
      checkFont(legend, false, 'Legend', 400);
      if (hasTheme) numericStyle(legend, 'fontSize', theme.type.legend, 'legend-font-size', 'Legend');
      for (const text of legend.querySelectorAll('.legend-item, .legend-heading')) checkFont(text, false, 'Legend text', text.classList.contains('legend-heading') ? 700 : 400);
      for (const chip of legend.querySelectorAll('.legend-chip')) if (hasTheme) for (const property of ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius']) numericStyle(chip, property, theme.radii.label, 'legend-chip-radius', 'Legend color swatch');
      const swatches = [...legend.querySelectorAll('.legend-line')];
      for (const type of usedTypes) {
        const matching = swatches.filter(swatch => swatch.dataset.type === type && rendered(swatch));
        if (matching.length !== 1) error('legend-coverage', `Relationship ${type} needs exactly one visible legend swatch.`);
      }
      for (const swatch of swatches) {
        const type = swatch.dataset.type, path = swatch.querySelector('path.edge');
        if (!usedTypes.has(type) || swatch.tagName.toLowerCase() !== 'svg' || !path) { error('legend-style-coverage', 'Legend lines must be measured SVG swatches for actual modeled relationship types.'); continue; }
        if (!rendered(path) || path.getTotalLength() < 1) error('legend-empty-line', `Legend ${type} needs a visible nonempty line.`);
        checkEdgeStyle(path, type, `Legend ${type}`);
        const owner = edges.find(edge => edge.type === type), diagramPath = owner && edgeGroups.get(owner.id)?.querySelector('path.edge');
        if (diagramPath && getComputedStyle(path).stroke !== getComputedStyle(diagramPath).stroke) error('legend-color', `Legend ${type} must match its diagram line color.`);
      }
    }
    for (const type of usedTypes) {
      const marker = svg.querySelector(`#arrow-${type}`), shape = marker?.querySelector('path');
      if (!marker || !shape) { error('missing-arrow-shape', `Relationship ${type} lacks a measurable arrow marker.`); continue; }
      if (hasTheme) {
        numericStyle(shape, 'strokeWidth', theme.strokes[type === 'data' ? 'arrowData' : 'arrow'], 'arrow-stroke-width', `Arrow ${type}`);
        const bounds = shape.getBBox();
        if (!near(bounds.width, theme.geometry.arrowLength, EPS) || !near(bounds.height, theme.geometry.arrowHalfWidth * 2, EPS) ||
          !near(Number(marker.getAttribute('refX')), bounds.x + bounds.width, EPS) || !near(Number(marker.getAttribute('refY')), bounds.y + bounds.height / 2, EPS) ||
          marker.getAttribute('markerUnits') !== 'userSpaceOnUse') error('arrow-geometry', `Arrow ${type} must use shared logical-pixel geometry with the tip on its endpoint.`);
      }
      const owner = edges.find(edge => edge.type === type), path = owner && edgeGroups.get(owner.id)?.querySelector('path.edge');
      if (path && getComputedStyle(shape).stroke !== getComputedStyle(path).stroke) error('arrow-color', `Arrow ${type} must match its relationship color.`);
    }
    for (const kind of ['containers', 'nodes', 'edges', 'labels']) if (counts[kind] !== expectedCounts[kind]) error('render-coverage', `Expected ${expectedCounts[kind]} ${kind}; rendered and checked ${counts[kind]}.`);
    return finish();
  }
  window.checkDiagram = checkDiagram;
})();
