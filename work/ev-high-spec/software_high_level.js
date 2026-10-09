const softwareModules = new Map(
  [...DATA.software.modules, ...DATA.software.ota.modules,
   ...DATA.software.diagnostics.modules, ...DATA.software.audio.modules,
   ...DATA.software.widevine.modules].map(module => [module.id, module])
);
const softwareDetailViews = {ota: 'OTA', diag: 'Diagnostic', audio: 'Audio', widevine: 'Widevine DRM'};
const selectedSoftwareModules = {ota: null, diag: null, audio: null, widevine: null};

function activeSoftwareDetailView() {
  for (const view of Object.keys(softwareDetailViews)) {
    if (!$(`sw-${view}-view`).hidden) return view;
  }
  return 'high';
}

function setSoftwareArchitectureView(view) {
  $('sw-high-level-view').hidden = view !== 'high';
  for (const key of Object.keys(softwareDetailViews)) {
    $(`sw-${key}-view`).hidden = view !== key;
  }
  showTab('software');
  $('software-panel').scrollTop = 0;
  $('live').textContent = `${softwareDetailViews[view] || 'High-Level'} software architecture`;
}

function refreshInteractionGraph(view) {
  const prefix = `sw-${view}`;
  const attr = `data-${view}-focus`;
  const focus = document.querySelector(`#${prefix}-view [${attr}][aria-pressed="true"]`)?.dataset[`${view}Focus`] || 'all';
  const selected = selectedSoftwareModules[view];
  document.querySelectorAll(`#${prefix}-diagram .ota-edge`).forEach(edge => {
    const flows = edge.dataset.otaFlow.split(',');
    const inFocus = focus === 'all' || flows.includes(focus) ||
      (view === 'ota' && focus !== 'feedback' && flows.includes('shared'));
    const adjacent = !selected || edge.dataset.otaFrom === selected || edge.dataset.otaTo === selected;
    edge.classList.toggle('is-dim', !inFocus || !adjacent);
    edge.classList.toggle('is-active', inFocus && adjacent && !!selected);
  });
  $(`${prefix}-diagram`).querySelector('.ota-return-lane')?.classList.toggle('is-dim', focus !== 'all' && focus !== 'feedback');
  document.querySelectorAll(`#${prefix}-diagram .ota-edge-label`).forEach(label => {
    const flows = label.dataset.otaFlow.split(',');
    const inFocus = focus === 'all' || flows.includes(focus) ||
      (view === 'ota' && focus !== 'feedback' && flows.includes('shared'));
    const adjacent = !selected || label.dataset.otaFrom === selected || label.dataset.otaTo === selected;
    label.classList.toggle('is-dim', !inFocus || !adjacent);
  });
}

function refreshOtaGraph() { refreshInteractionGraph('ota'); }
function refreshDiagGraph() { refreshInteractionGraph('diag'); }

function clearSoftwareSelection() {
  for (const view of Object.keys(softwareDetailViews)) selectedSoftwareModules[view] = null;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(node => {
    node.setAttribute('aria-pressed', 'false');
  });
  for (const view of Object.keys(softwareDetailViews)) {
    const prefix = `sw-${view}`;
    const attr = `data-${view}-focus`;
    const focusButton = document.querySelector(`#${prefix}-view [${attr}][aria-pressed="true"]`);
    const focusName = focusButton?.textContent.trim() || 'All';
    $(`${prefix}-inspector`).textContent = `Showing ${focusName} interaction path. Select a component to highlight its connections. Right-click to clear selection.`;
    refreshInteractionGraph(view);
  }
  $('live').textContent = 'Software component selection cleared.';
}

function selectSoftwareModule(id) {
  const module = softwareModules.get(id);
  if (!module) return;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.swModule === id));
  });
  const view = activeSoftwareDetailView();
  for (const key of Object.keys(softwareDetailViews)) {
    selectedSoftwareModules[key] = view === key ? id : null;
  }
  if (view !== 'high') {
    const inspector = $(`sw-${view}-inspector`);
    inspector.replaceChildren();
    const name = document.createElement('strong');
    name.textContent = module.name;
    const duty = document.createElement('span');
    duty.lang = 'zh-CN';
    duty.textContent = module.duty;
    inspector.append(name, duty);
    if (view === 'widevine' && module.status) {
      const status = document.createElement('span');
      status.className = 'wv-source wv-status';
      status.textContent = '状态：' + module.status;
      inspector.append(status);
    }
    if (view === 'widevine' && module.source) {
      const source = document.createElement('span');
      source.className = 'wv-source';
      source.textContent = '来源：' + module.source;
      inspector.append(source);
    }
    refreshInteractionGraph(view);
  }
  $('live').textContent = `Selected software module: ${module.name}`;
}

function hasSoftwareTextSelection() {
  const selection = document.getSelection();
  const panel = $('software-panel');
  return Boolean(selection && !selection.isCollapsed && selection.toString().trim() &&
    (panel.contains(selection.anchorNode) || panel.contains(selection.focusNode)));
}

$('software-panel').addEventListener('click', event => {
  const back = event.target.closest('#sw-ota-back, #sw-diag-back, #sw-audio-back, #sw-widevine-back');
  if (back) { setSoftwareArchitectureView('high'); return; }
  const focusButton = event.target.closest('[data-ota-focus], [data-diag-focus], [data-audio-focus], [data-widevine-focus]');
  if (focusButton) {
    const view = activeSoftwareDetailView();
    if (view === 'high') return;
    const selector = `#sw-${view}-view [data-${view}-focus]`;
    document.querySelectorAll(selector).forEach(button => {
      button.setAttribute('aria-pressed', String(button === focusButton));
    });
    clearSoftwareSelection();
    return;
  }
  const button = event.target.closest('[data-sw-module]');
  if (!button || !$('software-panel').contains(button)) return;
  if (event.detail !== 0 && hasSoftwareTextSelection()) {
    event.preventDefault();
    return;
  }
  if (button.dataset.detailPage) return;
  const id = button.dataset.swModule;
  if (button.classList.contains('sw-module')) {
    if (id === 'widevine-drm') {
      clearSoftwareSelection();
      setSoftwareArchitectureView('widevine');
      return;
    }
    if (id === 'audio-system' || id === 'bsp-audio') {
      clearSoftwareSelection();
      setSoftwareArchitectureView('audio');
      return;
    }
    if (id === 'ota-update' || id === 'mcu-ota') {
      clearSoftwareSelection();
      setSoftwareArchitectureView('ota');
      return;
    }
    if (id === 'diagnostics' || id === 'mcu-mfg-diag' || id === 'mcu-dcm') {
      clearSoftwareSelection();
      setSoftwareArchitectureView('diag');
      return;
    }
  }
  selectSoftwareModule(id);
  if (button.classList.contains('sw-module')) {
    $('sw-index-' + id)?.scrollIntoView({behavior:'smooth', block:'center'});
  }
});

$('software-panel').addEventListener('contextmenu', event => {
  if (event.target.closest('#sw-diag-readme') || hasSoftwareTextSelection()) return;
  const view = activeSoftwareDetailView();
  const pane = $(view === 'high' ? 'sw-high-level-view' : `sw-${view}-view`);
  if (!pane.querySelector('[data-sw-module][aria-pressed="true"]')) return;
  event.preventDefault();
  clearSoftwareSelection();
});

for (const id of Object.keys(softwareDetailViews).map(view => `sw-${view}-diagram`)) {
  $(id).addEventListener('keydown', event => {
    const node = event.target.closest('.ota-node');
    if (node?.dataset.detailPage && event.key === 'Enter') return;
    if (node && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      node.dispatchEvent(new MouseEvent('click', {bubbles:true}));
    }
  });
}

const requestedSoftwareView = new URLSearchParams(window.location.search).get('view');
if (Object.hasOwn(softwareDetailViews, requestedSoftwareView)) {
  setSoftwareArchitectureView(requestedSoftwareView);
}

// The guide is embedded in index.html so local/offline viewing needs no fetch or CDN.
const diagnosticReadme = $('sw-diag-readme');
const diagnosticReadmeTrigger = $('sw-diag-readme-open');
function openDiagnosticReadme() {
  if (diagnosticReadme.open) return;
  diagnosticReadme.showModal();
  diagnosticReadme.querySelector('.diag-readme-body').scrollTop = 0;
  diagnosticReadmeTrigger.setAttribute('aria-expanded', 'true');
  $('live').textContent = 'Diagnostic README opened.';
}
diagnosticReadmeTrigger.addEventListener('click', openDiagnosticReadme);
$('sw-diag-readme-close').addEventListener('click', () => diagnosticReadme.close());
diagnosticReadme.addEventListener('close', () => {
  diagnosticReadmeTrigger.setAttribute('aria-expanded', 'false');
  diagnosticReadmeTrigger.focus({preventScroll:true});
  $('live').textContent = 'Diagnostic README closed. Architecture selection preserved.';
});
diagnosticReadme.querySelector('.diag-readme-toc').addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;
  const section = diagnosticReadme.querySelector(link.getAttribute('href'));
  if (!section) return;
  event.preventDefault();
  section.scrollIntoView({block:'start'});
  section.tabIndex = -1;
  section.focus({preventScroll:true});
});
if (requestedSoftwareView === 'diag' && new URLSearchParams(window.location.search).get('readme') === '1') {
  openDiagnosticReadme();
}


// Audio route exploration is independent of component adjacency highlighting.
function setAudioPanel(panel) {
  if (!['components', 'routing'].includes(panel)) return;
  $('sw-audio-components').hidden = panel !== 'components';
  $('sw-audio-routing').hidden = panel !== 'routing';
  document.querySelectorAll('[data-audio-panel]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.audioPanel === panel));
  });
}
function selectAudioRoute(address) {
  const route = DATA.software.audio.routing.routes.find(item => item.address === address);
  if (!route) return;
  $('audio-route-select').value = address;
  const fields = {
    bus: route.address, stream: 'STREAMRX = ' + route.streamKey,
    pp: 'DEVICEPP_RX = ' + route.ppKey, device: route.device,
    devicekey: 'DEVICERX = ' + route.deviceKey,
    backend: route.backend, format: route.format
  };
  for (const [key, value] of Object.entries(fields)) $('audio-route-' + key).textContent = value;
  $('audio-route-status').textContent = route.status;
  document.querySelectorAll('[data-audio-route]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.audioRoute === address));
  });
  document.querySelectorAll('[data-route-row]').forEach(row => {
    row.classList.toggle('is-selected', row.dataset.routeRow === address);
  });
  $('live').textContent = `${address}: ${route.device}; backend ${route.backend}. Business-to-slot mapping unknown.`;
}
document.querySelectorAll('[data-audio-panel]').forEach(button => {
  button.addEventListener('click', () => setAudioPanel(button.dataset.audioPanel));
});
$('audio-route-select').addEventListener('change', event => selectAudioRoute(event.target.value));
$('sw-audio-routing').addEventListener('click', event => {
  const button = event.target.closest('[data-audio-route]');
  if (!button) return;
  if (event.detail !== 0 && hasSoftwareTextSelection()) {
    event.preventDefault();
    return;
  }
  selectAudioRoute(button.dataset.audioRoute);
});
