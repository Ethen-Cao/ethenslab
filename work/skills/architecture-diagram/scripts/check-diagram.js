/*
 * 架构图几何检查。在浏览器中注入本文件后调用 checkDiagram()，返回 {ok, errors, warnings}。
 *   Playwright: await page.addScriptTag({path: '<skill>/scripts/check-diagram.js'});
 *               const report = await page.evaluate(() => checkDiagram());
 *   也可粘贴到浏览器控制台执行。errors 必须为空；warnings 逐条确认。
 * DOM 约定（与 assets/base-template.html 一致）：
 *   节点 [data-node]，外框 rect.face，可选 data-parent；容器 g[data-container]（首个 rect 为边框，text/path 为标题与分隔线），可选 data-parent；
 *   连线 g[data-edge]，data-from / data-to / data-route / data-keep-anchor（缺省时读页面全局 edges 数组）；
 *   标签 .edge-label（可选 data-label-for）；跨线弧 [data-bridge]；分支点 .flow-junction。
 */
(() => {
  'use strict';
  const TOL = 1.5;

  function parseRoute(d) {
    if (!d || /[^\d\s.,+\-eEMHVL]/.test(d)) return null;
    const tokens = d.match(/[MHVL]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) || [];
    const points = [];
    let command = null, index = 0;
    const read = () => Number(tokens[index++]);
    while (index < tokens.length) {
      if (/^[MHVL]$/.test(tokens[index])) command = tokens[index++];
      const last = points[points.length - 1];
      let next;
      if (command === 'M') {
        if (last) return null;
        next = {x: read(), y: read()};
        command = 'L';
      } else if (!last) return null;
      else if (command === 'L') next = {x: read(), y: read()};
      else if (command === 'H') next = {x: read(), y: last.y};
      else next = {x: last.x, y: read()};
      if (!Number.isFinite(next.x) || !Number.isFinite(next.y)) return null;
      if (last && Math.abs(last.x - next.x) > 1e-6 && Math.abs(last.y - next.y) > 1e-6) return null;
      if (!last || last.x !== next.x || last.y !== next.y) points.push(next);
    }
    return points.length >= 2 ? points : null;
  }

  function segmentsOf(points) {
    return points.slice(1).map((b, i) => {
      const a = points[i];
      const horizontal = Math.abs(a.y - b.y) < 1e-6;
      return horizontal
        ? {horizontal, c: a.y, lo: Math.min(a.x, b.x), hi: Math.max(a.x, b.x)}
        : {horizontal, c: a.x, lo: Math.min(a.y, b.y), hi: Math.max(a.y, b.y)};
    });
  }

  // inset > 0 shrinks the box; inset < 0 grows it.
  function segmentHitsBox(s, box, inset) {
    const x1 = box.x1 + inset, x2 = box.x2 - inset, y1 = box.y1 + inset, y2 = box.y2 - inset;
    if (x1 >= x2 || y1 >= y2) return false;
    return s.horizontal
      ? s.c > y1 && s.c < y2 && s.hi > x1 && s.lo < x2
      : s.c > x1 && s.c < x2 && s.hi > y1 && s.lo < y2;
  }
  const overlapArea = (a, b) => Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1)) * Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const contains = (outer, inner, pad = 0) =>
    inner.x1 >= outer.x1 + pad - TOL && inner.x2 <= outer.x2 - pad + TOL && inner.y1 >= outer.y1 + pad - TOL && inner.y2 <= outer.y2 - pad + TOL;

  function sideOf(p, b) {
    if (p.x < b.x1 - TOL || p.x > b.x2 + TOL || p.y < b.y1 - TOL || p.y > b.y2 + TOL) return null;
    if (Math.abs(p.y - b.y1) <= TOL) return 'top';
    if (Math.abs(p.y - b.y2) <= TOL) return 'bottom';
    if (Math.abs(p.x - b.x1) <= TOL) return 'left';
    if (Math.abs(p.x - b.x2) <= TOL) return 'right';
    return null;
  }
  const OUTWARD = {top: [0, -1], bottom: [0, 1], left: [-1, 0], right: [1, 0]};
  const unit = (a, b) => [Math.sign(b.x - a.x), Math.sign(b.y - a.y)];

  function checkDiagram(options = {}) {
    const svg = options.svg ?? document.querySelector('svg#architecture') ?? document.querySelector('svg');
    if (!svg) throw new Error('No SVG found');
    const root = document.getElementById('viewport') ?? svg;
    const rootMatrix = root.getScreenCTM();
    if (!rootMatrix) throw new Error('Diagram is not rendered');
    const rootInverse = rootMatrix.inverse();
    const errors = [], warnings = [];
    const error = (code, message) => errors.push({code, message});
    const warn = (code, message) => warnings.push({code, message});
    const toRoot = el => rootInverse.multiply(el.getScreenCTM());
    const mapPoint = (m, x, y) => { const p = new DOMPoint(x, y).matrixTransform(m); return {x: p.x, y: p.y}; };
    const boxOf = el => {
      const b = el.getBBox(), m = toRoot(el);
      const a = mapPoint(m, b.x, b.y), c = mapPoint(m, b.x + b.width, b.y + b.height);
      return {x1: Math.min(a.x, c.x), y1: Math.min(a.y, c.y), x2: Math.max(a.x, c.x), y2: Math.max(a.y, c.y)};
    };
    const rendered = el => {
      for (let n = el; n && n !== svg; n = n.parentElement) {
        if (getComputedStyle(n).display === 'none' || n.classList.contains('hidden-flow')) return false;
      }
      return true;
    };

    const idCounts = new Map();
    document.querySelectorAll('[id]').forEach(el => idCounts.set(el.id, (idCounts.get(el.id) ?? 0) + 1));
    idCounts.forEach((count, id) => { if (count > 1) error('duplicate-id', `重复 id：${id}（${count} 次）`); });

    const containerMap = new Map();
    const containerMarks = [];
    svg.querySelectorAll('g[data-container]').forEach(g => {
      const rect = g.querySelector('rect');
      if (!rect || !rendered(g)) return;
      containerMap.set(g.dataset.container, {box: boxOf(rect), parent: g.dataset.parent});
      g.querySelectorAll('text, path').forEach(el => {
        const b = boxOf(el);
        // Rules are zero-height lines; give them thickness so overlaps register.
        const box = el.tagName === 'path' ? {x1: b.x1 - 1, y1: b.y1 - 1, x2: b.x2 + 1, y2: b.y2 + 1} : b;
        containerMarks.push({container: g.dataset.container, text: el.tagName === 'text', label: el.textContent || '分隔线', box});
      });
    });
    containerMap.forEach((c, id) => {
      if (!c.parent) return;
      const parent = containerMap.get(c.parent);
      if (!parent) error('unknown-parent', `容器 ${id} 的父容器不存在：${c.parent}`);
      else if (!contains(parent.box, c.box)) error('outside-parent', `容器 ${id} 超出父容器 ${c.parent}`);
    });

    const allNodeIds = new Set();
    const nodeMap = new Map();
    svg.querySelectorAll('[data-node]').forEach(g => {
      const id = g.dataset.node;
      if (allNodeIds.has(id)) error('duplicate-node', `重复节点：${id}`);
      allNodeIds.add(id);
      if (!rendered(g)) return;
      const face = g.querySelector('rect.face') ?? [...g.querySelectorAll('rect')].pop();
      if (!face) return;
      const box = boxOf(face);
      nodeMap.set(id, {id, box, parent: g.dataset.parent});
      const outline = boxOf(g);
      for (const mark of containerMarks) {
        if (overlapArea(outline, mark.box) > 0) error('title-overlap', `节点 ${id} 压住容器 ${mark.container} 的${mark.text ? '标题：' + mark.label : '分隔线'}`);
      }
      if (g.dataset.parent) {
        const parent = containerMap.get(g.dataset.parent);
        if (!parent) error('unknown-parent', `节点 ${id} 的容器不存在：${g.dataset.parent}`);
        else if (!contains(parent.box, box)) error('outside-parent', `节点 ${id} 超出容器 ${g.dataset.parent}`);
      }
      g.querySelectorAll('text').forEach(text => {
        if (!contains(box, boxOf(text), 2)) error('text-overflow', `节点 ${id} 文字溢出：${text.textContent}`);
      });
      g.querySelectorAll('.node-name').forEach(text => {
        if (parseFloat(getComputedStyle(text).fontSize) < 16) warn('font-shrink', `节点 ${id} 主标题小于 16：${text.textContent}`);
      });
    });
    const nodeList = [...nodeMap.values()];
    for (let i = 0; i < nodeList.length; i++) {
      for (let j = i + 1; j < nodeList.length; j++) {
        if (overlapArea(nodeList[i].box, nodeList[j].box) > 1) error('node-overlap', `节点重叠：${nodeList[i].id} / ${nodeList[j].id}`);
      }
    }

    const edgeData = new Map(typeof edges !== 'undefined' && Array.isArray(edges) ? edges.map(e => [e.id, e]) : []);
    const seenEdges = new Set();
    const edgeList = [];
    svg.querySelectorAll('g[data-edge]').forEach(g => {
      const id = g.dataset.edge;
      if (seenEdges.has(id)) error('duplicate-edge', `重复连线：${id}`);
      seenEdges.add(id);
      if (!rendered(g)) return;
      const data = edgeData.get(id) ?? {};
      const from = g.dataset.from ?? data.from, to = g.dataset.to ?? data.to;
      if (!allNodeIds.has(from) || !allNodeIds.has(to)) { error('unknown-endpoint', `连线 ${id} 端点不存在：${from} → ${to}`); return; }
      const path = g.querySelector('path.edge') ?? g.querySelector('path:not(.edge-halo)');
      const raw = parseRoute(g.dataset.route ?? data.d ?? path?.getAttribute('d'));
      if (!raw) { error('route-format', `连线 ${id} 须为单段绝对坐标正交 M/H/V/L 路径`); return; }
      const m = toRoot(path);
      const points = raw.map(p => mapPoint(m, p.x, p.y));
      const type = data.type ?? ['control', 'data', 'pixel', 'encrypted', 'config'].find(t => path.classList.contains(t));
      const keep = g.dataset.keepAnchor !== undefined || Boolean(data.keepAnchor);
      edgeList.push({id, from, to, type, keep, points, segments: segmentsOf(points)});
    });

    // Distinct attachment points per node side; a side holding a single point must use its center.
    const anchors = new Map();
    const addAnchor = (nodeId, side, p, edge) => {
      const key = `${nodeId}\u0000${side}`;
      const list = anchors.get(key) ?? [];
      const same = list.find(a => Math.hypot(a.p.x - p.x, a.p.y - p.y) < 1);
      if (same) { same.ids.push(edge.id); same.keep = same.keep || edge.keep; }
      else list.push({nodeId, side, p, ids: [edge.id], keep: edge.keep});
      anchors.set(key, list);
    };

    for (const edge of edgeList) {
      const fromNode = nodeMap.get(edge.from), toNode = nodeMap.get(edge.to);
      if (!fromNode || !toNode) continue;
      const start = edge.points[0], end = edge.points[edge.points.length - 1];
      const startSide = sideOf(start, fromNode.box), endSide = sideOf(end, toNode.box);
      if (startSide) addAnchor(edge.from, startSide, start, edge);
      if (endSide) addAnchor(edge.to, endSide, end, edge);
      if (!startSide) error('start-off-boundary', `连线 ${edge.id} 起点不在 ${edge.from} 边框上`);
      else if (unit(start, edge.points[1]).join() !== OUTWARD[startSide].join()) error('start-direction', `连线 ${edge.id} 起始段未垂直离开 ${edge.from} 的 ${startSide} 边`);
      if (!endSide) error('end-off-boundary', `连线 ${edge.id} 箭头未贴 ${edge.to} 边框`);
      else {
        const before = edge.points[edge.points.length - 2];
        const inward = OUTWARD[endSide].map(v => -v).join();
        if (unit(before, end).join() !== inward) error('end-direction', `连线 ${edge.id} 箭头未垂直进入 ${edge.to} 的 ${endSide} 边`);
        if (Math.abs(end.x - before.x) + Math.abs(end.y - before.y) < 12) warn('short-arrow', `连线 ${edge.id} 末段短于 12，箭头会压住拐点`);
      }
      for (const node of nodeList) {
        if (edge.segments.some(s => segmentHitsBox(s, node.box, 2))) error('through-node', `连线 ${edge.id} 穿过节点 ${node.id}`);
      }
      for (const mark of containerMarks) {
        if (mark.text && edge.segments.some(s => segmentHitsBox(s, mark.box, -1))) error('edge-title', `连线 ${edge.id} 穿过容器 ${mark.container} 的标题：${mark.label}`);
      }
      containerMap.forEach((c, cid) => {
        const b = c.box;
        const hugs = edge.segments.some(s => {
          const sides = s.horizontal ? [b.y1, b.y2] : [b.x1, b.x2];
          const [lo, hi] = s.horizontal ? [b.x1, b.x2] : [b.y1, b.y2];
          return sides.some(side => Math.abs(s.c - side) < 6) && Math.min(s.hi, hi) - Math.max(s.lo, lo) > 16;
        });
        if (hugs) warn('edge-on-border', `连线 ${edge.id} 贴着容器 ${cid} 的边框走`);
      });
    }

    anchors.forEach(list => {
      if (list.length !== 1 || list[0].keep) return;
      const {nodeId, side, p, ids} = list[0];
      const b = nodeMap.get(nodeId).box;
      const offset = side === 'top' || side === 'bottom' ? p.x - (b.x1 + b.x2) / 2 : p.y - (b.y1 + b.y2) / 2;
      if (Math.abs(offset) > TOL) error('off-center', `${nodeId} 的 ${side} 边只接了 ${ids.join(' / ')}，应接在中心（当前偏移 ${Math.round(offset)}）`);
    });

    const ends = new Map();
    for (const edge of edgeList) {
      const end = edge.points[edge.points.length - 1];
      const clash = (ends.get(edge.to) ?? []).find(other => Math.hypot(other.p.x - end.x, other.p.y - end.y) < 8);
      if (clash) warn('arrow-stack', `箭头堆叠：${clash.id} / ${edge.id} → ${edge.to}`);
      ends.set(edge.to, [...(ends.get(edge.to) ?? []), {id: edge.id, p: end}]);
    }

    const dots = [...svg.querySelectorAll('.flow-junction')].filter(rendered)
      .map(c => mapPoint(toRoot(c), +c.getAttribute('cx'), +c.getAttribute('cy')));
    const arcs = [...svg.querySelectorAll('[data-bridge] path.edge')].filter(rendered).map(p => {
      const n = (p.getAttribute('d').match(/[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) || []).map(Number);
      const m = toRoot(p), a = mapPoint(m, n[0], n[1]), b = mapPoint(m, n[n.length - 2], n[n.length - 1]);
      return {x1: Math.min(a.x, b.x), x2: Math.max(a.x, b.x), y: a.y};
    });
    const inside = (v, lo, hi) => v > lo + .5 && v < hi - .5;
    const pairCrossings = new Map();
    const sharedNodeCrossings = new Map();
    for (const a of edgeList) {
      for (const b of edgeList) {
        if (a === b) continue;
        for (const h of a.segments.filter(s => s.horizontal)) {
          for (const v of b.segments.filter(s => !s.horizontal)) {
            const x = v.c, y = h.c;
            if (!inside(x, h.lo, h.hi) || !inside(y, v.lo, v.hi)) continue;
            if (dots.some(d => Math.hypot(d.x - x, d.y - y) < 2)) continue;
            const pair = [a.id, b.id].sort().join(' × ');
            pairCrossings.set(pair, (pairCrossings.get(pair) ?? 0) + 1);
            const common = [a.from, a.to].find(n => n === b.from || n === b.to);
            if (common) sharedNodeCrossings.set(pair, common);
            if (!arcs.some(arc => Math.abs(arc.y - y) < .5 && arc.x1 < x && x < arc.x2)) {
              warn('crossing-no-bridge', `交叉无跨线弧：${a.id} × ${b.id} @ (${Math.round(x)}, ${Math.round(y)})，可能离拐点/端点过近或线路过密`);
            }
          }
        }
        if (a.id < b.id) {
          const shared = a.from === b.from && a.type === b.type;
          for (const s of a.segments) {
            for (const t of b.segments) {
              if (s.horizontal !== t.horizontal || Math.abs(s.c - t.c) > .5) continue;
              if (Math.min(s.hi, t.hi) - Math.max(s.lo, t.lo) > 1 && !shared) warn('edge-overlap', `连线重合：${a.id} / ${b.id}`);
            }
          }
        }
      }
    }
    pairCrossings.forEach((count, pair) => {
      if (count > 1) warn('repeat-crossing', `连线 ${pair} 交叉 ${count} 次，调换入口或走线即可消除`);
    });
    sharedNodeCrossings.forEach((node, pair) => {
      warn('shared-node-crossing', `连线 ${pair} 都连接 ${node} 却互相交叉，按来向调整 ${node} 上的入口顺序`);
    });
    for (const edge of edgeList) {
      const bends = edge.segments.filter((s, i) => i > 0 && s.horizontal !== edge.segments[i - 1].horizontal).length;
      if (bends >= 5) warn('complex-route', `连线 ${edge.id} 拐 ${bends} 次，先调整布局再走线`);
      const fromNode = nodeMap.get(edge.from), toNode = nodeMap.get(edge.to);
      if (!fromNode || !toNode) continue;
      // Smallest container holding both endpoints; the route should not leave it.
      let home = null;
      containerMap.forEach((c, cid) => {
        if (!contains(c.box, fromNode.box) || !contains(c.box, toNode.box)) return;
        const area = (c.box.x2 - c.box.x1) * (c.box.y2 - c.box.y1);
        if (!home || area < home.area) home = {cid, box: c.box, area};
      });
      if (home && edge.points.some(p => p.x < home.box.x1 - TOL || p.x > home.box.x2 + TOL || p.y < home.box.y1 - TOL || p.y > home.box.y2 + TOL)) {
        warn('leaves-container', `连线 ${edge.id} 两端都在 ${home.cid} 内，路径却绕到容器外`);
      }
    }

    const labels = [...svg.querySelectorAll('.edge-label')].filter(rendered).map(g => {
      const shape = g.querySelector('rect') ?? g.querySelector('text');
      return {id: g.dataset.labelFor ?? g.textContent.trim(), box: boxOf(shape)};
    });
    labels.forEach((label, i) => {
      for (const node of nodeList) if (overlapArea(label.box, node.box) > 1) warn('label-node', `标签 ${label.id} 压住节点 ${node.id}`);
      for (const other of labels.slice(i + 1)) if (overlapArea(label.box, other.box) > 1) warn('label-overlap', `标签重叠：${label.id} / ${other.id}`);
      for (const edge of edgeList) {
        if (edge.segments.some(s => segmentHitsBox(s, label.box, -1))) warn('label-edge', `标签 ${label.id} 遮挡连线 ${edge.id}`);
      }
    });

    const report = {ok: errors.length === 0, errors, warnings, counts: {nodes: nodeMap.size, edges: edgeList.length, labels: labels.length}};
    if (!options.quiet) {
      console.log(`checkDiagram: ${errors.length} errors, ${warnings.length} warnings`, report.counts);
      if (errors.length) console.table(errors);
      if (warnings.length) console.table(warnings);
    }
    return report;
  }

  window.checkDiagram = checkDiagram;
})();
