const softwareModules = new Map(
  [...DATA.software.modules, ...DATA.software.ota.modules].map(module => [module.id, module])
);
let selectedOtaModule = null;

function setSoftwareArchitectureView(view) {
  const ota = view === 'ota';
  $('sw-high-level-view').hidden = ota;
  $('sw-ota-view').hidden = !ota;
  showTab('software');
  $('software-panel').scrollTop = 0;
  $('live').textContent = ota ? 'OTA software architecture' : 'High-Level software architecture';
}

function refreshOtaGraph() {
  const focus = document.querySelector('#sw-ota-view [data-ota-focus][aria-pressed="true"]')?.dataset.otaFocus || 'all';
  const selected = selectedOtaModule;
  document.querySelectorAll('#sw-ota-diagram .ota-edge').forEach(edge => {
    const flows = edge.dataset.otaFlow.split(',');
    const inFocus = focus === 'all' || flows.includes(focus) || (focus !== 'feedback' && flows.includes('shared'));
    const adjacent = !selected || edge.dataset.otaFrom === selected || edge.dataset.otaTo === selected;
    edge.classList.toggle('is-dim', !inFocus || !adjacent);
    edge.classList.toggle('is-active', inFocus && adjacent && !!selected);
  });
  $('sw-ota-diagram').querySelector('.ota-return-lane').classList.toggle('is-dim', focus !== 'all' && focus !== 'feedback');
  document.querySelectorAll('#sw-ota-diagram .ota-edge-label').forEach(label => {
    const flows = label.dataset.otaFlow.split(',');
    label.classList.toggle('is-dim', focus !== 'all' && !flows.includes(focus) && !(focus !== 'feedback' && flows.includes('shared')));
  });
}

function selectSoftwareModule(id) {
  const module = softwareModules.get(id);
  if (!module) return;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.swModule === id));
  });
  if ($('sw-ota-view').hidden) {
    selectedOtaModule = null;
  } else {
    selectedOtaModule = id;
    const inspector = $('sw-ota-inspector');
    inspector.replaceChildren();
    const name = document.createElement('strong');
    name.textContent = module.name;
    const duty = document.createElement('span');
    duty.lang = 'zh-CN';
    duty.textContent = module.duty;
    inspector.append(name, duty);
    refreshOtaGraph();
  }
  $('live').textContent = `Selected software module: ${module.name}`;
}

$('software-panel').addEventListener('click', event => {
  const back = event.target.closest('#sw-ota-back');
  if (back) { setSoftwareArchitectureView('high'); return; }
  const focusButton = event.target.closest('[data-ota-focus]');
  if (focusButton) {
    document.querySelectorAll('#sw-ota-view [data-ota-focus]').forEach(button => {
      button.setAttribute('aria-pressed', String(button === focusButton));
    });
    selectedOtaModule = null;
    document.querySelectorAll('#sw-ota-view [data-sw-module]').forEach(node => node.setAttribute('aria-pressed', 'false'));
    $('sw-ota-inspector').textContent = `Showing ${focusButton.textContent.trim()} interaction path. Select a component to highlight its connections.`;
    refreshOtaGraph();
    return;
  }
  const button = event.target.closest('[data-sw-module]');
  if (!button || !$('software-panel').contains(button)) return;
  const id = button.dataset.swModule;
  if (button.classList.contains('sw-module') && (id === 'ota-update' || id === 'mcu-ota')) {
    setSoftwareArchitectureView('ota');
    return;
  }
  selectSoftwareModule(id);
  if (button.classList.contains('sw-module')) {
    $('sw-index-' + id)?.scrollIntoView({behavior:'smooth', block:'center'});
  }
});

$('sw-ota-diagram').addEventListener('keydown', event => {
  const node = event.target.closest('.ota-node');
  if (node && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    node.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  }
});

if (new URLSearchParams(window.location.search).get('view') === 'ota') {
  setSoftwareArchitectureView('ota');
}
