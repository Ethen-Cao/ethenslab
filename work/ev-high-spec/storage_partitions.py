"""Render the diagnostic snapshot as a single, static partition table."""
from pathlib import Path
from html import escape
from datetime import datetime, timezone, timedelta
import json

ROOT = Path(__file__).parent


def size(value):
    if value is None:
        return 'Not reported'
    for unit, scale in [('GiB', 2**30), ('MiB', 2**20), ('KiB', 2**10)]:
        if value >= scale:
            return f'{value/scale:,.2f} {unit}'
    return f'{value:,} B'


def code(value):
    return '<code>' + escape(str(value)) + '</code>'


def render_storage():
    data = json.loads((ROOT / 'storage-8295.json').read_text())
    slots = {}
    for pair in data['pairs']:
        for slot in ('a', 'b'):
            bank = pair['slot' + slot.upper()]
            active = pair['activeSlot']
            state = ('Active' if active == slot else 'Inactive') if active in ('a', 'b') else 'Unknown'
            slots[bank['target']] = (bank['alias'], slot.upper() + ' · ' + state)

    mounts = {}
    for mount in data['mounted']:
        mounts.setdefault(mount['devicePath'], []).append(mount)
    partitions = sorted(
        (d for d in data['devices'] if '.' in d['node']),
        key=lambda d: (int(d['lu'][3:]), int(d['node'].rsplit('.', 1)[1])),
    )
    rows = []
    for device in partitions:
        node = device['node']
        name, state = slots.get(node, (', '.join(device['aliases']) or 'Unnamed', '—'))
        mounted = mounts.get('/dev/disk/' + node, [])
        filesystems = ', '.join(dict.fromkeys(m['fsType'] for m in mounted)) or '—'
        points = list(dict.fromkeys(
            point for m in mounted
            for point in [m['primaryMountPoint'], *m.get('extraMountPoints', [])]
        ))
        mount_points = '<br>'.join(code(point) for point in points) or '—'
        rows.append(
            f'<tr data-device="{escape(node, quote=True)}">'
            f'<th scope="row">{code(name)}</th>'
            f'<td>{code("/dev/disk/" + node)}</td>'
            f'<td class="state">{escape(state)}</td>'
            f'<td class="capacity">{size(device["capacityBytes"])}</td>'
            f'<td>{escape(filesystems)}</td><td>{mount_points}</td></tr>'
        )
    captured = datetime.fromisoformat(data['capturedAt'].replace('Z', '+00:00'))
    captured = captured.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC+08:00')
    fields = dict(
        CAPTURED=captured, ROWS='\n'.join(rows),
        CSS=(ROOT / 'storage_partitions.css').read_text(),
    )
    html = (ROOT / 'storage_partitions_template.html').read_text()
    for key, value in fields.items():
        html = html.replace('<!-- ' + key + ' -->', value)
    return html


if __name__ == '__main__':
    (ROOT / 'storage-partitions.html').write_text(render_storage())
