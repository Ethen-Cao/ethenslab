/* Architecture diagram v2. Static browser renderer; technical model validation is separate. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const THEME = window.ArchitectureTheme;
  const TYPES = ['dependency', 'control', 'data', 'notification', 'config'];
  const NORMAL = {top: [0, -1], bottom: [0, 1], left: [-1, 0], right: [1, 0]};
  const ORIGINS = {oem: '#4285F4', native: '#34A853', vendor: '#FBBC04'};
  const PARTY_COLORS = {oem: '#4285F4', tier1: '#FBBC04', 'soc-vendor': '#A78BFA', 'os-vendor': '#34A853', other: '#38BDF8'};
  const PALETTE_COLORS = {blue: '#4285F4', green: '#34A853', amber: '#FBBC04', purple: '#A78BFA', cyan: '#38BDF8', orange: '#FB923C', pink: '#F472B6', indigo: '#818CF8'};
  const EDGE_LABELS = {dependency: 'Dependency', control: 'Call / IPC', data: 'Data', notification: 'Notification / interrupt', config: 'Configuration / allocation'};
  const same = (a, b) => Math.abs(a - b) < 0.001;
  const fmt = n => String(Math.round(n * 1000) / 1000);
  const equal = (a, b) => same(a.x, b.x) && same(a.y, b.y);
  let heightObserver = null;

  function svgElement(tag, attrs, parent, text) {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null) el.setAttribute(key, String(value));
    });
    if (text !== undefined) el.textContent = String(text);
    if (parent) parent.append(el);
    return el;
  }
  function htmlElement(tag, attrs, parent, text) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, String(value)));
    if (text !== undefined) el.textContent = String(text);
    if (parent) parent.append(el);
    return el;
  }
  function uniqueMap(items, kind) {
    const map = new Map();
    for (const item of items) {
      if (!item.id || map.has(item.id)) throw new Error(`Missing or duplicate ${kind} id: ${item.id}`);
      map.set(item.id, item);
    }
    return map;
  }
  function anchor(node, side, offset = 0) {
    if (side === 'top') return {x: node.x + node.w / 2 + offset, y: node.y};
    if (side === 'bottom') return {x: node.x + node.w / 2 + offset, y: node.y + node.h};
    if (side === 'left') return {x: node.x, y: node.y + node.h / 2 + offset};
    if (side === 'right') return {x: node.x + node.w, y: node.y + node.h / 2 + offset};
    throw new Error(`Unknown anchor side: ${side}`);
  }
  function cleanPoints(points, id) {
    const out = [];
    for (const point of points) {
      if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) throw new Error(`Invalid route coordinate: ${id}`);
      const prev = out[out.length - 1];
      if (prev && equal(prev, point)) continue;
      if (prev && !same(prev.x, point.x) && !same(prev.y, point.y)) throw new Error(`Non-orthogonal route: ${id}`);
      if (out.length > 1) {
        const before = out[out.length - 2];
        if ((same(before.x, prev.x) && same(prev.x, point.x) && (prev.y - before.y) * (point.y - prev.y) > 0) ||
            (same(before.y, prev.y) && same(prev.y, point.y) && (prev.x - before.x) * (point.x - prev.x) > 0)) out.pop();
      }
      out.push({...point});
    }
    if (out.length < 2) throw new Error(`Route has fewer than two distinct points: ${id}`);
    return out;
  }
  function buildRoute(edge, nodes) {
    const fromSide = edge.fromSide || 'bottom', toSide = edge.toSide || 'top';
    const from = nodes.get(edge.from), to = nodes.get(edge.to);
    if (!from || !to) throw new Error(`Unknown route endpoint: ${edge.id}`);
    const start = anchor(from, fromSide, edge.fromOffset || 0);
    const end = anchor(to, toSide, edge.toOffset || 0);
    let points = [start];
    if (edge.via && edge.via.length) {
      let point = start;
      for (const step of edge.via) {
        if (('x' in step) === ('y' in step)) throw new Error(`A via step must set exactly one of x or y: ${edge.id}`);
        point = {x: step.x === undefined ? point.x : step.x, y: step.y === undefined ? point.y : step.y};
        points.push(point);
      }
      if (!same(point.x, end.x) && !same(point.y, end.y)) points.push(toSide === 'top' || toSide === 'bottom' ? {x: end.x, y: point.y} : {x: point.x, y: end.y});
      points.push(end);
    } else {
      const a = NORMAL[fromSide], b = NORMAL[toSide];
      if (!a || !b) throw new Error(`Unknown route side: ${edge.id}`);
      const aligned = (same(start.x, end.x) && a[0] === 0 && b[0] === 0 && a[1] === -b[1] && Math.sign(end.y - start.y) === a[1]) ||
        (same(start.y, end.y) && a[1] === 0 && b[1] === 0 && a[0] === -b[0] && Math.sign(end.x - start.x) === a[0]);
      if (aligned) points.push(end);
      else if (a[0] === 0 && b[0] === 0 && a[1] !== b[1]) {
        const y = (start.y + end.y) / 2;
        points.push({x: start.x, y}, {x: end.x, y}, end);
      } else if (a[1] === 0 && b[1] === 0 && a[0] !== b[0]) {
        const x = (start.x + end.x) / 2;
        points.push({x, y: start.y}, {x, y: end.y}, end);
      } else if (a[0] === 0 && b[0] === 0) {
        const y = a[1] < 0 ? Math.min(start.y, end.y) - 24 : Math.max(start.y, end.y) + 24;
        points.push({x: start.x, y}, {x: end.x, y}, end);
      } else if (a[1] === 0 && b[1] === 0) {
        const x = a[0] < 0 ? Math.min(start.x, end.x) - 24 : Math.max(start.x, end.x) + 24;
        points.push({x, y: start.y}, {x, y: end.y}, end);
      } else {
        const corner = a[0] === 0 ? {x: start.x, y: end.y} : {x: end.x, y: start.y};
        points.push(corner, end);
      }
    }
    points = cleanPoints(points, edge.id);
    const d = points.map((p, i) => i === 0 ? `M${fmt(p.x)} ${fmt(p.y)}` : same(p.y, points[i - 1].y) ? `H${fmt(p.x)}` : `V${fmt(p.y)}`).join(' ');
    return {...edge, fromSide, toSide, points, d};
  }
  function segmentsOf(route) {
    return route.points.slice(1).map((b, i) => ({a: route.points[i], b, edgeId: route.id,
      horizontal: same(route.points[i].y, b.y), crossings: []}));
  }
  function branchPoint(a, b) {
    if (!equal(a[0], b[0])) return null;
    let i = 1, j = 1, p = {...a[0]};
    while (i < a.length && j < b.length) {
      const da = {x: Math.sign(a[i].x - p.x), y: Math.sign(a[i].y - p.y)};
      const db = {x: Math.sign(b[j].x - p.x), y: Math.sign(b[j].y - p.y)};
      if (da.x !== db.x || da.y !== db.y) break;
      const ra = Math.abs(a[i].x - p.x) + Math.abs(a[i].y - p.y);
      const rb = Math.abs(b[j].x - p.x) + Math.abs(b[j].y - p.y);
      const step = Math.min(ra, rb);
      p = {x: p.x + da.x * step, y: p.y + da.y * step};
      if (same(step, ra)) i++;
      if (same(step, rb)) j++;
    }
    return equal(p, a[0]) || i === a.length || j === b.length ? null : p;
  }
  function makeJunctions(groups, routeMap) {
    const points = [];
    for (const group of groups) {
      if (!Array.isArray(group.edges) || group.edges.length < 2) throw new Error('A junction needs at least two edges');
      const routes = group.edges.map(id => {
        const route = routeMap.get(id);
        if (!route) throw new Error(`Unknown junction edge: ${id}`);
        return route;
      });
      if (routes.some(r => r.from !== routes[0].from || r.relation !== routes[0].relation)) throw new Error('Junction routes must have one source and one relationship');
      for (let i = 0; i < routes.length; i++) for (let j = i + 1; j < routes.length; j++) {
        const p = branchPoint(routes[i].points, routes[j].points);
        if (!p) throw new Error(`Junction routes have no actual shared trunk: ${routes[i].id} / ${routes[j].id}`);
        let found = points.find(point => equal(point, p));
        if (!found) { found = {...p, type: routes[0].type, edges: []}; points.push(found); }
        for (const route of [routes[i], routes[j]]) if (!found.edges.includes(route.id)) found.edges.push(route.id);
      }
    }
    return points;
  }
  function bridgeRoutes(routes, junctions) {
    const {bridgeRadius: radius, bridgeClearance: clearance, bridgeSeparation: separation} = THEME.geometry;
    const segments = routes.flatMap(segmentsOf);
    const interior = (v, a, b, margin = 0) => v > Math.min(a, b) + margin + 0.001 && v < Math.max(a, b) - margin - 0.001;
    const horizontal = segments.filter(s => s.horizontal), vertical = segments.filter(s => !s.horizontal);
    for (const h of horizontal) for (const v of vertical) {
      if (h.edgeId === v.edgeId) continue;
      const x = v.a.x, y = h.a.y;
      if (!interior(x, h.a.x, h.b.x, radius + clearance) || !interior(y, v.a.y, v.b.y, radius + clearance)) continue;
      if (junctions.some(j => equal(j, {x, y}) && j.edges.includes(h.edgeId) && j.edges.includes(v.edgeId))) continue;
      let crossing = h.crossings.find(c => same(c.x, x));
      if (!crossing) { crossing = {x, y, under: []}; h.crossings.push(crossing); }
      crossing.under.push(v);
    }
    const result = new Map(routes.map(r => [r.id, {d: r.d, bridges: []}]));
    for (const route of routes) {
      const parts = segments.filter(s => s.edgeId === route.id);
      const commands = [`M${fmt(route.points[0].x)} ${fmt(route.points[0].y)}`];
      for (const part of parts) {
        const safe = part.crossings.filter(c => {
          if (part.crossings.some(other => other !== c && Math.abs(other.x - c.x) < 2 * radius + separation)) return false;
          return !segments.some(s => {
            if (s === part || c.under.includes(s)) return false;
            const sameTrunk = junctions.some(j => j.edges.includes(part.edgeId) && j.edges.includes(s.edgeId));
            if (sameTrunk && s.horizontal && same(s.a.y, part.a.y) && Math.min(s.a.x, s.b.x) <= c.x - radius && Math.max(s.a.x, s.b.x) >= c.x + radius) return false;
            const left = c.x - radius - clearance, right = c.x + radius + clearance, top = c.y - radius - clearance, bottom = c.y + clearance;
            return s.horizontal ? interior(s.a.y, top, bottom) && Math.max(s.a.x, s.b.x) > left && Math.min(s.a.x, s.b.x) < right :
              interior(s.a.x, left, right) && Math.max(s.a.y, s.b.y) > top && Math.min(s.a.y, s.b.y) < bottom;
          });
        });
        const direction = Math.sign(part.b.x - part.a.x) || 1;
        safe.sort((a, b) => direction * (a.x - b.x));
        for (const c of safe) {
          const start = c.x - direction * radius, end = c.x + direction * radius;
          const arc = `A${radius} ${radius} 0 0 ${direction > 0 ? 1 : 0} ${fmt(end)} ${fmt(c.y)}`;
          commands.push(`H${fmt(start)} ${arc}`);
          result.get(route.id).bridges.push({x: c.x, y: c.y, radius, d: `M${fmt(start)} ${fmt(c.y)} ${arc}`});
        }
        commands.push(part.horizontal ? `H${fmt(part.b.x)}` : `V${fmt(part.b.y)}`);
      }
      result.get(route.id).d = commands.join(' ');
    }
    return result;
  }

  // Break only at existing whitespace or identifier separators; never truncate, shrink or insert characters.
  function wrapText(value, width, className, parent) {
    const measure = svgElement('text', {class: className, visibility: 'hidden'}, parent);
    const fits = text => { measure.textContent = text; return measure.getComputedTextLength() <= width; };
    const lines = [];
    for (const paragraph of String(value || '').split('\n')) {
      let line = '';
      for (const word of paragraph.trim().split(/\s+/).filter(Boolean)) {
        const trial = line ? `${line} ${word}` : word;
        if (fits(trial)) { line = trial; continue; }
        if (line) { lines.push(line); line = ''; }
        if (fits(word)) { line = word; continue; }
        const parts = word.match(/[^/_.:\-]+[/_.:\-]*|[/_.:\-]+/g) || [word];
        for (const part of parts) {
          if (line && !fits(line + part)) { lines.push(line); line = ''; }
          line += part;
        }
      }
      if (line) lines.push(line);
    }
    measure.remove();
    return lines;
  }
  function canonicalName(node) {
    if (node.entityType === 'kernel-interface' && node.interfacePath && node.moduleName) return `${node.interfacePath} · ${node.moduleName}`;
    return window.ArchitectureModel.displayName(node);
  }
  // Only filenames and exported kernel paths use code typography. Classes and
  // process titles stay sans-serif so long identifiers retain readable density.
  function nodeNameClass(node) {
    return THEME.code.nodeTypes.includes(node.entityType) ? 'node-name code' : 'node-name';
  }
  function textClass(base, value) {
    return new RegExp(THEME.code.textPattern).test(String(value || '')) ? `${base} code`.trim() : base;
  }
  function paletteFill(node, model) {
    if (['hardware', 'memory', 'register'].includes(node.entityType)) return null;
    const mode = model.meta.colorMode || 'technical';
    if (mode === 'origin') return ORIGINS[node.origin] || '#ffffff';
    if (mode === 'responsibility') {
      const party = (model.parties || []).find(p => p.id === node.responsibleParty);
      return PALETTE_COLORS[party?.paletteKey] || PARTY_COLORS[party?.category] || '#ffffff';
    }
    return null;
  }
  function renderArchitecture(model, target) {
    if (heightObserver) { heightObserver.disconnect(); heightObserver = null; }
    window.architectureModel = model;
    window.architectureGeometry = null;
    if (!THEME || THEME.version !== 1) throw new Error('ArchitectureTheme tokens must be loaded before the renderer');
    if (!window.ArchitectureModel) throw new Error('ArchitectureModel validator must be loaded before the renderer');
    const validation = window.ArchitectureModel.validate(model);
    if (!validation.ok) throw new Error(`Invalid architecture model: ${validation.errors.map(e => e.message).join('; ')}`);
    if (!model || !model.meta || !model.canvas) throw new Error('Architecture model requires meta and canvas');
    const containers = model.containers || [], nodes = model.nodes || [], edges = model.edges || [];
    if (!containers.length && !nodes.length) throw new Error('Architecture model is empty');
    const containerMap = uniqueMap(containers, 'container'), nodeMap = uniqueMap(nodes, 'node');
    uniqueMap(edges, 'edge');
    const documentRoot = target || document.getElementById('diagram-root') || htmlElement('main', {id: 'diagram-root'}, document.body);
    documentRoot.replaceChildren();
    documentRoot.classList.add('architecture-document');
    documentRoot.dataset.colorMode = model.meta.colorMode || 'technical';
    document.documentElement.lang = 'en';
    document.title = model.meta.title;
    const header = htmlElement('header', {class: 'diagram-header'}, documentRoot);
    htmlElement('h1', {id: 'diagram-title'}, header, model.meta.title);
    if (model.meta.subtitle) htmlElement('p', {id: 'diagram-subtitle'}, header, model.meta.subtitle);
    const shell = htmlElement('section', {class: 'diagram-shell', 'aria-label': 'Architecture diagram'}, documentRoot);
    const svg = svgElement('svg', {id: 'architecture', width: model.canvas.width, height: model.canvas.height,
      viewBox: `0 0 ${model.canvas.width} ${model.canvas.height}`, role: 'img', 'aria-labelledby': 'svg-title svg-description'}, shell);
    svgElement('title', {id: 'svg-title'}, svg, model.meta.title);
    svgElement('desc', {id: 'svg-description'}, svg, model.meta.description || model.meta.subtitle || model.meta.title);
    const defs = svgElement('defs', {}, svg);
    for (const type of TYPES) {
      const {arrowLength, arrowHalfWidth} = THEME.geometry;
      const padding = Math.max(THEME.strokes.arrow, THEME.strokes.arrowData);
      const tipX = padding + arrowLength, centerY = padding + arrowHalfWidth;
      const marker = svgElement('marker', {id: `arrow-${type}`, markerWidth: arrowLength + 2 * padding, markerHeight: 2 * (arrowHalfWidth + padding), refX: tipX, refY: centerY,
        orient: 'auto', markerUnits: 'userSpaceOnUse'}, defs);
      svgElement('path', {class: `marker ${type}`, d: `M${fmt(padding)} ${fmt(padding)} L${fmt(tipX)} ${fmt(centerY)} L${fmt(padding)} ${fmt(centerY + arrowHalfWidth)}`}, marker);
    }
    const viewport = svgElement('g', {id: 'viewport'}, svg);
    const containerLayer = svgElement('g', {id: 'containers'}, viewport);
    const edgeLayer = svgElement('g', {id: 'edges'}, viewport);
    const bridgeLayer = svgElement('g', {id: 'bridge-overlays'}, viewport);
    const nodeLayer = svgElement('g', {id: 'nodes'}, viewport);
    const labelLayer = svgElement('g', {id: 'edge-labels'}, viewport);
    const geometry = {containers: {}, nodes: {}, routes: {}, bridges: [], junctions: [], errors: [], expected: {
      containers: containers.length, nodes: nodes.length, edges: edges.length, labels: edges.filter(e => e.label || e.relation === 'ipc').length}};

    // Paint parents before children, independent of their order in the input model.
    const depth = c => { let n = 0, p = c.parent, visited = new Set([c.id]); while (p) {
      if (visited.has(p)) throw new Error(`Container cycle: ${c.id}`);
      visited.add(p); const parent = containerMap.get(p); if (!parent) throw new Error(`Unknown parent: ${c.id}`);
      n++; p = parent.parent;
    } return n; };
    for (const c of [...containers].sort((a, b) => depth(a) - depth(b))) {
      const kind = c.kind || 'layer';
      const group = svgElement('g', {class: `container ${kind}`, 'data-container': c.id, 'data-parent': c.parent}, containerLayer);
      svgElement('rect', {class: 'container-frame', x: c.x, y: c.y, width: c.w, height: c.h, rx: kind === 'domain' ? THEME.radii.domain : THEME.radii.container}, group);
      const size = kind === 'domain' ? THEME.type.domain : THEME.type.container, leading = size + 5;
      const names = wrapText(c.title, c.w - 32, 'container-title', group);
      let cursor = c.y + 16 + size;
      for (const text of names) {
        svgElement('text', {class: 'container-title', x: c.x + 16, y: cursor}, group, text); cursor += leading;
      }
      if (c.subtitle) {
        cursor += 1;
        for (const text of wrapText(c.subtitle, c.w - 32, 'container-subtitle', group)) {
          svgElement('text', {class: 'container-subtitle', x: c.x + 16, y: cursor - 5}, group, text); cursor += THEME.type.subtitle + 5;
        }
      }
      const headerBottom = Math.max(...[...group.querySelectorAll('text')].map(t => { const b = t.getBBox(); return b.y + b.height; })) + 16;
      group.dataset.headerBottom = String(headerBottom);
      group.dataset.contentTop = String(headerBottom + 16);
      if (kind === 'layer') svgElement('line', {class: 'container-rule', x1: c.x, x2: c.x + c.w, y1: headerBottom, y2: headerBottom}, group);
      geometry.containers[c.id] = {x: c.x, y: c.y, w: c.w, h: c.h, headerBottom, contentTop: headerBottom + 16, parent: c.parent};
    }
    for (const node of nodes) {
      const classes = ['node', node.entityType, node.configured && 'configured'].filter(Boolean).join(' ');
      const group = svgElement('g', {class: classes, 'data-node': node.id, 'data-parent': node.parent,
        'data-entity-type': node.entityType, 'aria-label': canonicalName(node)}, nodeLayer);
      const fill = paletteFill(node, model);
      if (fill) { group.style.setProperty('--node-fill', fill); group.style.setProperty('--node-stroke', '#72808f'); group.style.setProperty('--node-ink', '#102116'); }
      const memory = node.entityType === 'memory';
      const face = memory ? {x: node.x, y: node.y + 8, w: node.w - 8, h: node.h - 8} : node;
      if (memory) {
        svgElement('rect', {x: node.x + 8, y: node.y, width: node.w - 8, height: node.h - 8, rx: THEME.radii.node}, group);
        svgElement('rect', {x: node.x + 4, y: node.y + 4, width: node.w - 8, height: node.h - 8, rx: THEME.radii.node}, group);
      }
      svgElement('rect', {class: 'face', x: face.x, y: face.y, width: face.w, height: face.h, rx: THEME.radii.node}, group);
      const nameClass = nodeNameClass(node);
      const subtitleClass = textClass('node-subtitle', node.description);
      const names = wrapText(canonicalName(node), face.w - 24, nameClass, group);
      const subtitles = wrapText(node.description || '', face.w - 24, subtitleClass, group);
      const nameLeading = THEME.type.node + 4, subtitleLeading = THEME.type.subtitle + 5;
      const textHeight = names.length * nameLeading + (subtitles.length ? 5 + subtitles.length * subtitleLeading : 0);
      let cursor = face.y + (face.h - textHeight) / 2 + THEME.type.node;
      for (const text of names) { svgElement('text', {class: nameClass, x: face.x + face.w / 2, y: cursor, 'text-anchor': 'middle'}, group, text); cursor += nameLeading; }
      if (subtitles.length) cursor += 1;
      for (const text of subtitles) { svgElement('text', {class: subtitleClass, x: face.x + face.w / 2, y: cursor, 'text-anchor': 'middle'}, group, text); cursor += subtitleLeading; }
      // The loaded face determines its real ascent/descent; center the measured
      // group instead of assuming a particular font's alphabetic baseline.
      const nodeTexts = [...group.querySelectorAll('text')];
      const textBounds = nodeTexts.map(text => text.getBBox());
      const textTop = Math.min(...textBounds.map(box => box.y));
      const textBottom = Math.max(...textBounds.map(box => box.y + box.height));
      const shift = face.y + face.h / 2 - (textTop + textBottom) / 2;
      for (const text of nodeTexts) text.setAttribute('y', fmt(Number(text.getAttribute('y')) + shift));
      for (const text of group.querySelectorAll('text')) {
        const box = text.getBBox();
        if (box.x < face.x + 8 || box.x + box.width > face.x + face.w - 8 || box.y < face.y + 8 || box.y + box.height > face.y + face.h - 8) {
          geometry.errors.push({code: 'text-overflow', message: `Node ${node.id} needs more room for: ${text.textContent}`});
        }
      }
      geometry.nodes[node.id] = {x: node.x, y: node.y, w: node.w, h: node.h, parent: node.parent};
    }
    const routes = edges.map(edge => {
      const type = window.ArchitectureModel.edgeType(edge);
      if (!TYPES.includes(type)) throw new Error(`Unknown relationship type: ${edge.id}`);
      return buildRoute({...edge, type, label: edge.label || (edge.relation === 'ipc' ? edge.mechanism : undefined)}, nodeMap);
    });
    const routeMap = new Map(routes.map(r => [r.id, r]));
    const junctions = makeJunctions(model.junctions || [], routeMap);
    const bridged = bridgeRoutes(routes, junctions);
    for (const route of routes) {
      const group = svgElement('g', {class: 'edge-group', 'data-edge': route.id, 'data-from': route.from, 'data-to': route.to,
        'data-type': route.type, 'data-route': route.d, 'data-keep-anchor': route.keepAnchor ? 'true' : undefined}, edgeLayer);
      svgElement('path', {class: `edge ${route.type}`, d: bridged.get(route.id).d, 'marker-end': `url(#arrow-${route.type})`}, group);
      geometry.routes[route.id] = {...route, renderedD: bridged.get(route.id).d};
      for (const bridge of bridged.get(route.id).bridges) {
        const overlay = svgElement('g', {'data-bridge': route.id, 'data-x': bridge.x, 'data-y': bridge.y, 'data-radius': bridge.radius}, bridgeLayer);
        overlay.style.setProperty('--bridge-halo-width', `${THEME.strokes[route.type] + 2 * THEME.geometry.bridgeHaloPadding}px`);
        svgElement('path', {class: 'bridge-halo', d: bridge.d}, overlay);
        svgElement('path', {class: `edge ${route.type}`, d: bridge.d}, overlay);
        geometry.bridges.push({...bridge, edgeId: route.id});
      }
      if (route.label) {
        const explicit = route.labelPosition;
        const longest = segmentsOf(route).sort((a, b) => (Math.abs(b.b.x - b.a.x) + Math.abs(b.b.y - b.a.y)) - (Math.abs(a.b.x - a.a.x) + Math.abs(a.b.y - a.a.y)))[0];
        const position = explicit || (longest.horizontal ? {x: (longest.a.x + longest.b.x) / 2, y: longest.a.y - 18, anchor: 'middle'} :
          {x: longest.a.x + 14, y: (longest.a.y + longest.b.y) / 2, anchor: 'start'});
        const label = svgElement('g', {class: `edge-label ${route.type}`, 'data-label-for': route.id}, labelLayer);
        const rect = svgElement('rect', {rx: THEME.radii.label}, label);
        const text = svgElement('text', {class: textClass('', route.label), x: position.x, y: position.y, 'text-anchor': position.anchor || 'middle', 'dominant-baseline': 'central'}, label, route.label);
        const box = text.getBBox();
        Object.entries({x: box.x - 4, y: box.y - 2, width: box.width + 8, height: box.height + 4}).forEach(([key, value]) => rect.setAttribute(key, value));
      }
    }
    for (const junction of junctions) {
      svgElement('circle', {class: `flow-junction ${junction.type}`, cx: junction.x, cy: junction.y, r: THEME.geometry.junctionRadius,
        'data-junction-edges': junction.edges.join(' ')}, bridgeLayer);
      geometry.junctions.push(junction);
    }
    const legend = htmlElement('footer', {class: 'diagram-legend', 'aria-label': 'Legend'}, documentRoot);
    const legendChip = (text, color) => {
      const entry = htmlElement('span', {class: 'legend-item'}, legend);
      const chip = htmlElement('i', {class: 'legend-chip', 'aria-hidden': 'true'}, entry);
      chip.style.setProperty('--chip-fill', color); entry.append(document.createTextNode(text));
    };
    if (model.meta.colorMode === 'origin') {
      htmlElement('span', {class: 'legend-heading'}, legend, 'Component origin');
      const used = new Set(nodes.filter(n => !['hardware', 'memory', 'register'].includes(n.entityType)).map(n => n.origin));
      for (const [origin, label] of [['native', 'Platform native'], ['vendor', 'Vendor / Tier1'], ['oem', 'OEM']]) if (used.has(origin)) legendChip(label, ORIGINS[origin]);
      if (used.has('unknown') || used.has(undefined)) legendChip('Unspecified origin', '#ffffff');
    } else if (model.meta.colorMode === 'responsibility') {
      htmlElement('span', {class: 'legend-heading'}, legend, `${model.meta.responsibilityBasis[0].toUpperCase()}${model.meta.responsibilityBasis.slice(1)} responsibility`);
      for (const party of new Set(nodes.map(n => n.responsibleParty).filter(Boolean))) {
        const entry = (model.parties || []).find(p => p.id === party);
        legendChip(entry?.label || 'Unspecified party', PALETTE_COLORS[entry?.paletteKey] || PARTY_COLORS[entry?.category] || '#ffffff');
      }
    }
    const edgeTypes = new Set(routes.map(e => e.type));
    for (const type of TYPES) if (edgeTypes.has(type)) {
      const entry = htmlElement('span', {class: 'legend-item'}, legend);
      const swatch = svgElement('svg', {class: `legend-line ${type}`, 'data-type': type, 'aria-hidden': 'true', width: 28, height: 12, viewBox: '0 0 28 12'}, entry);
      svgElement('path', {class: `edge ${type}`, d: 'M1 6 H27'}, swatch);
      entry.append(document.createTextNode(EDGE_LABELS[type]));
    }
    window.architectureGeometry = geometry;
    window.dispatchEvent(new CustomEvent('architecture-rendered', {detail: geometry}));
    if (window.parent !== window && model.meta.id) {
      let lastHeight = 0;
      const reportHeight = () => {
        const padding = parseFloat(getComputedStyle(document.body).paddingBottom) || 0;
        const height = Math.ceil(documentRoot.getBoundingClientRect().bottom + window.scrollY + padding);
        if (Number.isFinite(height) && height > 0 && height !== lastHeight) {
          lastHeight = height;
          window.parent.postMessage({type: `${model.meta.id}-height`, height}, '*');
        }
      };
      reportHeight();
      if (typeof ResizeObserver === 'function') {
        heightObserver = new ResizeObserver(reportHeight);
        heightObserver.observe(documentRoot);
      }
    }
    return geometry;
  }
  window.renderArchitecture = renderArchitecture;
})();
