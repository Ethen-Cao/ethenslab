function filterStorageTable(id) {
  const query = document.getElementById(`${id}-query`).value.trim().toLowerCase();
  const scope = id === 'pairs' ? document.getElementById('pairs-scope').value : 'all';
  const rows = [...document.querySelectorAll(`#${id} tbody tr`)];
  let visible = 0;
  for (const row of rows) {
    row.hidden = !row.dataset.search.includes(query) || (scope === 'core' && row.dataset.core !== 'true');
    if (!row.hidden) visible++;
  }
  document.getElementById(`${id}-count`).textContent = `${visible} / ${rows.length} records`;
  document.getElementById(`${id}-empty`).hidden = visible !== 0;
}
for (const id of ['pairs','mounts','devices']) {
  document.getElementById(`${id}-query`).addEventListener('input', () => filterStorageTable(id));
  filterStorageTable(id);
}
document.getElementById('pairs-scope').addEventListener('change', () => filterStorageTable('pairs'));
function revealStorageDevice() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (!id.startsWith('device-')) return;
  const target = document.getElementById(id);
  if (!target) return;
  document.getElementById('devices-query').value = '';
  filterStorageTable('devices');
  target.scrollIntoView({block:'center'});
}
window.addEventListener('hashchange', revealStorageDevice);
revealStorageDevice();
