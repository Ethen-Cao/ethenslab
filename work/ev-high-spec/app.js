const $ = id => document.getElementById(id);
const norm = s => String(s).toLowerCase().replace(/[\s_\-.*#]/g, '');
const glossaryMap = new Map(DATA.glossary.map(g => [norm(g.abbr), g]));
const palette = {CANFD:'#27ac49', CAN:'#ff4338', LIN:'#efb517', Ethernet:'#287ad5', LVDS:'#834cb4', DSI:'#e8b52d', Signal:'#555'};
const kindNames = {base:'基础配置', external:'外部设备', reserved:'预留功能', power:'供电电源'};
const kindColors = {base:'#ffecd7', external:'#dfe7fb', reserved:'#bdc1c6', power:'#f56566'};
const tabNames = ['diagram', 'hardware', 'software', 'glossary'];
const queries = {diagram:'', hardware:'', software:'', glossary:''};
const tabSubtitles = {diagram:'车载网络拓扑', hardware:'IVI 硬件连接与接口', software:'High-Level 软件架构', glossary:'控制器与传感器缩写'};
let activeTab = 'diagram';

function makeScene(id, svgId, viewportId, width, height, nodes) {
  const s = {id, svg:$(svgId), viewport:$(viewportId), width, height, nodes,
    byId:new Map(nodes.map(n => [n.id, n])), scale:1, tx:0, ty:0,
    fitted:true, initialized:false, selected:null, activeNet:null};
  s.svg.classList.add('diagram-svg');
  s.svg.style.width = width + 'px';
  s.svg.style.height = height + 'px';
  return s;
}
const scenes = {
  diagram:makeScene('diagram','drawing','viewport',1946,800,DATA.nodes),
  hardware:makeScene('hardware','hardware-drawing','hardware-viewport',DATA.hardware.width,DATA.hardware.height,DATA.hardware.nodes)
};
const currentScene = () => scenes[activeTab];

function definition(n) { return glossaryMap.get(norm(n.key || n.name)) || null; }
function cn(n) {
  return definition(n)?.cn || (n.name.startsWith('VIU_') ? '区域控制单元（全称待核对）' : n.name.startsWith('To ') ? '跨区域网络引用端口' : '所附缩写表未列出对应释义');
}
function defaultStatus() {
  return activeTab === 'hardware' ? '按提供的 IVI 硬件图纸重绘' : activeTab === 'software' ? 'High-Level 软件架构' : '按提供的图纸重绘';
}
function syncZoom(s) {
  if (s.id !== activeTab) return;
  $('zoom-value').textContent = `${Math.round(s.scale * 100)}%`;
  $('zoom-out').disabled = s.scale <= .1;
  $('zoom-in').disabled = s.scale >= 8;
}
function apply(s) {
  s.svg.style.transform = `translate(${s.tx}px,${s.ty}px) scale(${s.scale})`;
  syncZoom(s);
}
function fit(s = currentScene()) {
  if (!s) return;
  const {width, height} = s.viewport.getBoundingClientRect();
  if (!width || !height) return;
  s.scale = Math.max(.1, Math.min((width - 24) / s.width, (height - 24) / s.height));
  s.tx = (width - s.width * s.scale) / 2;
  s.ty = (height - s.height * s.scale) / 2;
  s.fitted = true;
  s.initialized = true;
  apply(s);
}
function zoom(factor, cx, cy, s = currentScene()) {
  if (!s) return;
  cx ??= s.viewport.clientWidth / 2;
  cy ??= s.viewport.clientHeight / 2;
  const next = Math.max(.1, Math.min(8, s.scale * factor));
  s.tx = cx - (cx - s.tx) * next / s.scale;
  s.ty = cy - (cy - s.ty) * next / s.scale;
  s.scale = next;
  s.fitted = false;
  apply(s);
}
function highlight(s) {
  s.svg.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
  if (s.selected) $(s.selected).classList.add('selected');
  if (s.id !== 'diagram') return;
  const n = s.byId.get(s.selected);
  const selectedNets = new Set(s.activeNet ? [s.activeNet] : n?.nets || []);
  s.svg.querySelectorAll('.wire').forEach(el => {
    const active = selectedNets.has(el.dataset.net);
    el.classList.toggle('active', active);
    el.classList.toggle('dim', selectedNets.size > 0 && !active);
  });
}
function closeDetail() {
  for (const s of Object.values(scenes)) {
    s.selected = null;
    s.activeNet = null;
    highlight(s);
  }
  $('detail').hidden = true;
  $('selection-status').textContent = defaultStatus();
}
function addStatus(value) {
  const span = document.createElement('span');
  span.className = 'status-label';
  span.textContent = value;
  $('detail-status').append(span);
}
function selectNode(id, center = false, s = currentScene()) {
  const n = s?.byId.get(id);
  if (!n) return;
  s.selected = id;
  s.activeNet = null;
  $('detail').hidden = false;
  $('detail').scrollTop = 0;
  $('detail-title').textContent = n.name;
  $('detail-domain').replaceChildren();
  $('detail-status').replaceChildren();
  $('detail-nets').replaceChildren();
  const isHardware = s.id === 'hardware';
  const dot = document.createElement('span');
  dot.className = 'domain-dot';
  dot.style.background = isHardware ? kindColors[n.kind] : DATA.colors[n.domain];
  $('detail-domain').append(dot, isHardware ? kindNames[n.kind] : DATA.domains[n.domain]);
  $('detail-connection-label').hidden = isHardware;
  $('detail-nets').hidden = isHardware;
  if (isHardware) {
    $('detail-cn').textContent = n.lines[0] === n.name ? '' : n.lines[0];
    $('detail-en').textContent = n.lines.slice(1).join('\n');
    if (n.kind === 'reserved') addStatus('预留功能');
    $('detail-note').textContent = n.note || '标识与参数按所附 IVI 硬件图纸保留。';
  } else {
    $('detail-cn').textContent = cn(n);
    $('detail-en').textContent = definition(n)?.en || '英文全称未在所附缩写表中注明';
    [n.removed ? '本车型不装配' : '', n.optional ? '选配' : '', n.nm ? '网络管理 NM' : '',
      n.marks.includes('*') ? 'KL30 常电供电' : '', n.marks.includes('#') ? 'KL15 受控供电' : '']
      .filter(Boolean).forEach(addStatus);
    for (const netId of n.nets) {
      const net = DATA.nets[netId], button = document.createElement('button'), swatch = document.createElement('span');
      swatch.className = 'net-swatch';
      swatch.style.borderColor = palette[net.kind];
      if (net.kind === 'LIN') swatch.style.borderTopStyle = 'dashed';
      button.append(swatch, net.title);
      button.onclick = () => {
        s.activeNet = s.activeNet === netId ? null : netId;
        for (const b of $('detail-nets').children) b.classList.remove('active');
        button.classList.toggle('active', s.activeNet === netId);
        highlight(s);
      };
      $('detail-nets').append(button);
    }
    $('detail-note').textContent = n.note || (!definition(n) ? '保留原图标识，未自行扩展英文全称。' : '中文与英文名称依据所附缩写表；图中名称可能包含位置或供电后缀。');
  }
  $('selection-status').textContent = `已选：${n.name}`;
  $('live').textContent = `已选择 ${n.name}`;
  highlight(s);
  if (center) {
    const usable = Math.max(180, s.viewport.clientWidth - 340);
    s.scale = Math.max(.1, Math.min(Math.max(s.scale, 1.8), (usable - 32) / n.w, (s.viewport.clientHeight - 32) / n.h));
    s.tx = usable / 2 - (n.x + n.w / 2) * s.scale;
    s.ty = s.viewport.clientHeight / 2 - (n.y + n.h / 2) * s.scale;
    s.fitted = false;
    apply(s);
  }
}
function renderGlossary(q = '') {
  const query = norm(q), entries = DATA.glossary.filter(g => norm(`${g.abbr} ${g.en} ${g.cn}`).includes(query));
  const fragment = document.createDocumentFragment();
  for (const g of entries) {
    const row = document.createElement('tr');
    for (const value of [g.abbr, g.en || '—', g.cn]) {
      const td = document.createElement('td');
      td.textContent = value;
      row.append(td);
    }
    fragment.append(row);
  }
  $('glossary-body').replaceChildren(fragment);
  $('glossary-count').textContent = `· ${entries.length} 项`;
  $('table-empty').hidden = entries.length > 0;
}
function search() {
  const raw = $('search').value.trim(), query = norm(raw);
  queries[activeTab] = raw;
  if (activeTab === 'glossary') { renderGlossary(raw); return; }
  const s = currentScene(), panel = $('search-results');
  s.svg.querySelectorAll('.found').forEach(el => el.classList.remove('found'));
  panel.replaceChildren();
  panel.hidden = !query;
  if (!query) return;
  const hits = s.nodes.filter(n => norm(s.id === 'hardware' ? `${n.name} ${n.lines.join(' ')} ${n.note}` : `${n.name} ${n.key} ${cn(n)} ${definition(n)?.en || ''}`).includes(query));
  for (const n of hits) {
    $(n.id).classList.add('found');
    const button = document.createElement('button'), small = document.createElement('small');
    button.append(n.name);
    small.textContent = s.id === 'hardware' ? n.lines.join(' · ') : cn(n);
    button.append(small);
    button.onclick = () => { selectNode(n.id, true, s); panel.hidden = true; };
    panel.append(button);
  }
  if (!hits.length) {
    const message = document.createElement('p');
    message.textContent = '图中未找到匹配模块。';
    panel.append(message);
  }
  $('live').textContent = `找到 ${hits.length} 个模块`;
}
function showTab(tab) {
  if (!tabNames.includes(tab)) return;
  queries[activeTab] = $('search').value;
  closeDetail();
  activeTab = tab;
  const tabTitle = $(tab + '-tab').textContent.trim();
  $('page-title').textContent = tabTitle;
  $('page-subtitle').textContent = tabSubtitles[tab];
  document.title = tabTitle;
  for (const name of tabNames) {
    $(name + '-panel').hidden = name !== tab;
    $(name + '-tab').setAttribute('aria-selected', String(name === tab));
    $(name + '-tab').tabIndex = name === tab ? 0 : -1;
  }
  const graph = tab === 'diagram' || tab === 'hardware';
  $('global-toolbar').hidden = tab === 'software';
  $('zoom-tools').hidden = !graph;
  $('gesture-hint').hidden = !graph;
  $('export-svg').hidden = !graph;
  $('search-results').hidden = true;
  $('search').value = queries[tab];
  $('search').placeholder = tab === 'hardware' ? '搜索芯片或接口，如 8295、USB、MCU' : tab === 'diagram' ? '搜索模块或中文名称，如 VIU、座椅' : '搜索缩写、英文或中文名称';
  $('counts').textContent = tab === 'software' ? `${DATA.software.modules.length} 个逻辑模块 · ${DATA.software.flows.length} 类链路` : tab === 'hardware' ? `${DATA.hardware.nodes.length} 个模块 / 连接器` : `${DATA.nodes.length} 个节点 · ${DATA.glossary.length} 项缩写`;
  $('selection-status').textContent = defaultStatus();
  $('footnote').textContent = tab === 'software' ? 'QNX 模块基于镜像与预置服务；AAOS/MCU 映射待项目镜像核对。' : tab === 'hardware' ? '图中芯片型号、接口与参数按所附硬件图纸标注。' : '细小总线编号、部分批注及未列出的缩写待原始设计文件核对。';
  if (graph) {
    const s = scenes[tab];
    requestAnimationFrame(() => { if (!s.initialized || s.fitted) fit(s); else apply(s); });
  } else if (tab === 'glossary') renderGlossary(queries.glossary);
}

for (const name of tabNames) $(name + '-tab').onclick = () => showTab(name);
document.querySelector('.tabs').addEventListener('keydown', e => {
  const index = tabNames.indexOf(activeTab);
  let next;
  if (e.key === 'ArrowRight') next = tabNames[(index + 1) % tabNames.length];
  if (e.key === 'ArrowLeft') next = tabNames[(index + tabNames.length - 1) % tabNames.length];
  if (e.key === 'Home') next = tabNames[0];
  if (e.key === 'End') next = tabNames[tabNames.length - 1];
  if (next) { e.preventDefault(); showTab(next); $(next + '-tab').focus(); }
});
$('search').addEventListener('input', search);
$('search').addEventListener('focus', () => { if ($('search').value) search(); });
$('search').addEventListener('keydown', e => {
  if (e.key === 'Escape') $('search-results').hidden = true;
  if (e.key === 'Enter' && activeTab !== 'glossary') $('search-results').querySelector('button')?.click();
});
document.addEventListener('pointerdown', e => { if (!e.target.closest('.search-wrap')) $('search-results').hidden = true; });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeDetail(); $('search-results').hidden = true; }
});
$('zoom-in').onclick = () => zoom(1.3);
$('zoom-out').onclick = () => zoom(1 / 1.3);
$('fit').onclick = () => fit();
$('actual').onclick = () => { const s = currentScene(); if (s) zoom(1 / s.scale); };
$('detail-close').onclick = closeDetail;

function bindViewport(s) {
  const viewport = s.viewport, pointers = new Map();
  let drag = null, moved = false, pinch = null;
  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    const r = viewport.getBoundingClientRect();
    zoom(Math.exp(-e.deltaY * .0015), e.clientX - r.left, e.clientY - r.top, s);
  }, {passive:false});
  viewport.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    pointers.set(e.pointerId, {x:e.clientX, y:e.clientY});
    viewport.setPointerCapture(e.pointerId);
    moved = false;
    const el = e.target.closest('[data-node],[data-hw-node]');
    drag = {x:e.clientX, y:e.clientY, tx:s.tx, ty:s.ty, target:el?.dataset.node || el?.dataset.hwNode};
    if (pointers.size === 2) {
      const p = [...pointers.values()];
      pinch = Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y);
      moved = true;
    }
    viewport.classList.add('dragging');
  });
  viewport.addEventListener('pointermove', e => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, {x:e.clientX, y:e.clientY});
    if (pointers.size === 2) {
      const p = [...pointers.values()], r = viewport.getBoundingClientRect();
      const distance = Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y);
      if (pinch > 0) zoom(distance / pinch, (p[0].x + p[1].x) / 2 - r.left, (p[0].y + p[1].y) / 2 - r.top, s);
      pinch = distance;
      moved = true;
      return;
    }
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.hypot(dx, dy) > 3) moved = true;
    if (moved) { s.tx = drag.tx + dx; s.ty = drag.ty + dy; s.fitted = false; apply(s); }
  });
  function end(e) {
    pointers.delete(e.pointerId);
    if (!pointers.size) {
      if (drag && !moved && e.type !== 'pointercancel') {
        if (drag.target) selectNode(drag.target, false, s); else closeDetail();
      }
      drag = pinch = null;
      viewport.classList.remove('dragging');
    } else {
      const p = [...pointers.values()][0];
      moved = true;
      drag = {x:p.x, y:p.y, tx:s.tx, ty:s.ty, target:null};
      pinch = null;
    }
  }
  viewport.addEventListener('pointerup', end);
  viewport.addEventListener('pointercancel', end);
  s.svg.addEventListener('keydown', e => {
    const node = e.target.closest('[data-node],[data-hw-node]');
    if (node && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      selectNode(node.dataset.node || node.dataset.hwNode, false, s);
    }
  });
  new ResizeObserver(() => { if (s.fitted && activeTab === s.id) fit(s); }).observe(viewport);
}
Object.values(scenes).forEach(bindViewport);

$('export-svg').onclick = () => {
  const s = currentScene();
  if (!s) return;
  const clone = s.svg.cloneNode(true);
  clone.removeAttribute('style');
  clone.setAttribute('width', s.width);
  clone.setAttribute('height', s.height);
  clone.querySelectorAll('.active,.dim,.selected,.found').forEach(el => el.classList.remove('active','dim','selected','found'));
  const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n',new XMLSerializer().serializeToString(clone)], {type:'image/svg+xml;charset=utf-8'});
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url;
  a.download = s.id === 'hardware' ? 'ivi-hardware-architecture.svg' : 'vehicle-network-architecture.svg';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
renderGlossary();
const requestedTab = new URLSearchParams(window.location.search).get('tab');
showTab(tabNames.includes(requestedTab) ? requestedTab : 'diagram');
