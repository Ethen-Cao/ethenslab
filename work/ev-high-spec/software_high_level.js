const softwareModules = new Map(
  [...DATA.software.modules, ...DATA.software.ota.modules,
   ...DATA.software.diagnostics.modules, ...DATA.software.audio.modules].map(module => [module.id, module])
);
const softwareDetailViews = {ota: 'OTA', diag: 'Diagnostic', audio: 'Audio'};
const selectedSoftwareModules = {ota: null, diag: null, audio: null};

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
    refreshInteractionGraph(view);
  }
  $('live').textContent = `Selected software module: ${module.name}`;
}

$('software-panel').addEventListener('click', event => {
  const back = event.target.closest('#sw-ota-back, #sw-diag-back, #sw-audio-back');
  if (back) { setSoftwareArchitectureView('high'); return; }
  const focusButton = event.target.closest('[data-ota-focus], [data-diag-focus], [data-audio-focus]');
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
  if (button.dataset.detailPage) return;
  const id = button.dataset.swModule;
  if (button.classList.contains('sw-module')) {
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
