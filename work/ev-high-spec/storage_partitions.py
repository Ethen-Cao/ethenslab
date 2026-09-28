"""Build a self-contained QNX partition explorer from the checked diagnostic snapshot."""
from pathlib import Path
from html import escape as e
from datetime import datetime, timezone, timedelta
import json

ROOT=Path(__file__).parent
CORE=('system','ifs2','hyp')


def size(value):
    if value is None:
        return 'Not reported'
    for unit,scale in [('GiB',2**30),('MiB',2**20),('KiB',2**10)]:
        if value>=scale:
            return f'{value/scale:,.2f} {unit}'
    return f'{value:,} B'


def device_id(node):
    return 'device-'+node


def code(value):
    return '<code>'+e(str(value))+'</code>'


def render_storage():
    data=json.loads((ROOT/'storage-8295.json').read_text())
    devices={d['node']:d for d in data['devices']}
    pairs={p['name']:p for p in data['pairs']}
    lus=[d for d in devices.values() if '.' not in d['node']]
    partitions=[d for d in devices.values() if '.' in d['node']]
    observed=sum(1 for d in lus if d['capacityBytes'] and d['capacityBytes']>0)
    captured=datetime.fromisoformat(data['capturedAt'].replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC+08:00')
    def target(node):
        return f'<a class="device-link" href="#{e(device_id(node))}">{code("/dev/disk/"+node)}</a>'
    def bank_cell(p,slot):
        bank=p['slot'+slot.upper()];active=p['activeSlot']==slot
        resolved=p['activeSlot'] in ('a','b')
        alias=p['activeAlias'] if active else p['inactiveAlias']
        state=('Active alias' if active else 'Inactive alias') if resolved else 'Unresolved alias'
        mapping=code(alias)+' → '+code(bank['alias']) if resolved else 'Active / inactive mapping not confirmed'
        capacity=devices[bank['target']]['capacityBytes']
        return (f'<div class="bank-cell {"active" if active else "inactive"}"><div class="bank-names">'
                +code(bank['alias'])+f'<span class="badge">{state}</span></div>'
                +f'<div class="alias">{mapping}</div>'
                +target(bank['target'])+f'<div class="capacity">Partition capacity: <strong>{size(capacity)}</strong></div></div>')
    bank_rows=''.join(f'<div class="bank-row"><div class="image-name">{code(name)}<small>{ {"system":"System image","ifs2":"Boot image filesystem","hyp":"Hypervisor image"}[name]}</small></div>'+bank_cell(pairs[name],'a')+bank_cell(pairs[name],'b')+'</div>' for name in CORE)
    pair_rows=[]
    for p in sorted(pairs.values(),key=lambda p:(p['name'] not in CORE,p['name'])):
        cells=[]
        for slot in ('A','B'):
            b=p['slot'+slot];d=devices[b['target']]
            cells.append('<td>'+code(b['alias'])+target(b['target'])+'<small>Partition: '+size(d['capacityBytes'])+'</small></td>')
        pair_rows.append(f'<tr data-search="{e(json.dumps(p).lower(),quote=True)}" data-core="{str(p["name"] in CORE).lower()}"><th scope="row">'+code(p['name'])+'</th>'+''.join(cells)+f'<td><span class="badge">{e((p["activeSlot"] or "unknown").upper())}</span><small>from alias targets</small></td></tr>')
    mount_rows=[]
    for m in data['mounted']:
        backing='UFS' if m['devicePath'].startswith('/dev/disk/') else 'RAM' if m['devicePath'].startswith('/dev/ram') else 'IFS image'
        rate=m.get('usageRate')
        percent=f'{rate*100:.1f}%' if rate is not None else 'Not reported'
        usage=f'<progress max="1" value="{rate}"></progress><span>{percent}</span>' if rate is not None else percent
        mount_rows.append('<tr data-search="'+e(json.dumps(m).lower(),quote=True)+'"><th scope="row">'+code(m['primaryMountPoint'])+'</th><td>'+code(m.get('partLabel') or m['kernelName'])+f'<small>{backing}</small></td><td>'+e(m['fsType'])+'</td><td>'+('Read only' if m['readOnly'] else 'Read / write')+'</td><td class="number">'+size(m['totalBytes'])+'</td><td class="number">'+size(m['usedBytes'])+'</td><td class="usage">'+usage+'</td></tr>')
    lun_cards=''.join(f'<div class="lu"><strong>{e(d["node"])}</strong><span>{size(d["capacityBytes"])}</span><small>{sum(p["lu"]==d["lu"] for p in partitions)} partition nodes</small></div>' for d in lus)
    device_rows=[]
    for d in partitions:
        # Slot-qualified aliases make the physical A/B identity visible even on the active side.
        aliases=sorted(d['aliases'],key=lambda a:(not a.endswith(('_a','_b')),a.endswith('_inactive'),a))
        device_rows.append(f'<tr id="{e(device_id(d["node"]))}" data-search="{e(json.dumps(d).lower(),quote=True)}"><th scope="row">{e(d["lu"])}</th><td>'+code('/dev/disk/'+d['node'])+'</td><td><div class="alias-list">'+''.join(code(a) for a in aliases)+'</div></td><td class="number">'+size(d['capacityBytes'])+'</td></tr>')
    sources=''.join('<li>'+code(s['file'])+'<details><summary>SHA-256</summary>'+code(s['sha256'])+'</details></li>' for s in data['sources'])
    table=lambda ident,head,rows: f'<div class="table-scroll"><table id="{ident}"><thead><tr>'+''.join('<th scope="col">'+h+'</th>' for h in head)+'</tr></thead><tbody>'+''.join(rows)+f'</tbody></table><p class="empty" id="{ident}-empty" hidden>No matching records.</p></div>'
    active_slots={pairs[n]['activeSlot'] for n in CORE}
    active=next(iter(active_slots)).upper() if len(active_slots)==1 and None not in active_slots else 'Mixed / unknown'
    note=('此快照中 OTA 非活动侧为 '+('A' if active=='B' else 'B')+'。') if active in ('A','B') else '各镜像的活动侧请以逐项别名映射为准。'
    html=(ROOT/'storage_partitions_template.html').read_text()
    fields=dict(ACTIVE_CORE=active,CORE_STATE_NOTE=note,CAPTURED=captured,PAIR_COUNT=str(len(pairs)),PARTITION_COUNT=str(len(partitions)),LU_COUNT=f'{observed} sized / {len(lus)} exposed',
                BANK_ROWS=bank_rows,PAIR_TABLE=table('pairs',['Image / firmware','Bank A','Bank B','Active alias'],pair_rows),
                MOUNT_TABLE=table('mounts',['Mount point','Backing label','Filesystem','Access','FS total','FS used','FS usage'],mount_rows),
                LUN_CARDS=lun_cards,DEVICE_TABLE=table('devices',['LU','Physical device node','Aliases','Partition capacity'],device_rows),
                SOURCES=sources,BOOT_LU=e(data['bootLu'] or 'Not reported'),
                CSS=(ROOT/'storage_partitions.css').read_text(),JS=(ROOT/'storage_partitions.js').read_text())
    for key,value in fields.items():
        html=html.replace('<!-- '+key+' -->',value)
    return html


if __name__=='__main__':
    (ROOT/'storage-partitions.html').write_text(render_storage())
