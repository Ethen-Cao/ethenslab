const softwareModules = new Map(DATA.software.modules.map(module => [module.id, module]));

function selectSoftwareModule(id) {
  const module = softwareModules.get(id);
  if (!module) return;
  document.querySelectorAll('#software-panel [data-sw-module]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.swModule === id));
  });
  $('live').textContent = `Selected software module: ${module.name}`;
}

$('software-panel').addEventListener('click', event => {
  const button = event.target.closest('[data-sw-module]');
  if (!button || !$('software-panel').contains(button)) return;
  const id = button.dataset.swModule;
  selectSoftwareModule(id);
  if (button.classList.contains('sw-module')) {
    $('sw-index-' + id)?.scrollIntoView({behavior:'smooth', block:'center'});
  }
});
