const softwareModules = new Map(
  [...DATA.software.modules, ...DATA.software.ota.modules,
   ...DATA.software.diagnostics.modules].map(module => [module.id, module])
);
let selectedOtaModule = null;
let selectedDiagModule = null;

function activeSoftwareDetailView() {
  if (!$('sw-diag-view').hidden) return 'diag';
  if (!$('sw-ota-view').hidden) return 'ota';
  return 'high';
}

function setSoftwareArchitectureView(view) {
  $('sw-high-level-view').hidden = view !== 'high';
  $('sw-ota-view').hidden = view !== 'ota';
  $('sw-diag-view').hidden = view !== 'diag';
  showTab('software');
  $('software-panel').scrollTop = 0;
  $('live').textContent = view === 'ota' ? 'OTA software architecture' :
    view === 'diag' ? 'Diagnostic software architecture' : 'High-Level software architecture';
}

function refreshInteractionGraph(view) {
  const prefix = view === 'ota' ? 'sw-ota' : 'sw-diag';
  const attr = view === 'ota' ? 'data-ota-focus' : 'data-diag-focus';
  const focus = document.querySelector(`#${prefix}-view [${attr}][aria-pressed="true"]`)?.dataset[view === 'ota' ? 'otaFocus' : 'diagFocus'] || 'all';
  const selected = view === 'ota' ? selectedOtaModule : selectedDiagModule;
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
  selectedOtaModule = null;
  selectedDiagModule = null;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(node => {
    node.setAttribute('aria-pressed', 'false');
  });
  for (const view of ['ota', 'diag']) {
    const prefix = view === 'ota' ? 'sw-ota' : 'sw-diag';
    const attr = view === 'ota' ? 'data-ota-focus' : 'data-diag-focus';
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
  selectedOtaModule = view === 'ota' ? id : null;
  selectedDiagModule = view === 'diag' ? id : null;
  if (view !== 'high') {
    const inspector = $(view === 'ota' ? 'sw-ota-inspector' : 'sw-diag-inspector');
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
  const back = event.target.closest('#sw-ota-back, #sw-diag-back');
  if (back) { setSoftwareArchitectureView('high'); return; }
  const focusButton = event.target.closest('[data-ota-focus], [data-diag-focus]');
  if (focusButton) {
    const view = activeSoftwareDetailView();
    if (view === 'high') return;
    const selector = view === 'ota' ? '#sw-ota-view [data-ota-focus]' : '#sw-diag-view [data-diag-focus]';
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
  const pane = $(view === 'ota' ? 'sw-ota-view' : view === 'diag' ? 'sw-diag-view' : 'sw-high-level-view');
  if (!pane.querySelector('[data-sw-module][aria-pressed="true"]')) return;
  event.preventDefault();
  clearSoftwareSelection();
});

for (const id of ['sw-ota-diagram', 'sw-diag-diagram']) {
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
if (requestedSoftwareView === 'ota' || requestedSoftwareView === 'diag') {
  setSoftwareArchitectureView(requestedSoftwareView);
}
