const softwareModules = new Map(
  [...DATA.software.modules, ...DATA.software.ota.modules].map(module => [module.id, module])
);

function setSoftwareArchitectureView(view) {
  const ota = view === 'ota';
  $('sw-high-level-view').hidden = ota;
  $('sw-ota-view').hidden = !ota;
  showTab('software');
  $('software-panel').scrollTop = 0;
  $('live').textContent = ota ? 'OTA software architecture' : 'High-Level software architecture';
}

function selectSoftwareModule(id) {
  const module = softwareModules.get(id);
  if (!module) return;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.swModule === id));
  });
  $('live').textContent = `Selected software module: ${module.name}`;
}

$('software-panel').addEventListener('click', event => {
  const back = event.target.closest('#sw-ota-back');
  if (back) { setSoftwareArchitectureView('high'); return; }
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

if (new URLSearchParams(window.location.search).get('view') === 'ota') {
  setSoftwareArchitectureView('ota');
}
