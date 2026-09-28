"""Import one diagnostic run into the portable, reproducible storage snapshot."""
from pathlib import Path
import argparse, hashlib, json, re


def import_snapshot(run):
    run = Path(run)
    names = ['manifest.json', 'parsed/qnx-storage.json', 'parsed/qnx-partitions.json',
             'raw/qnx/dev-disk-ls.txt', 'raw/qnx/df-P.txt', 'raw/qnx/df-n.txt']
    raw = {name: (run/name).read_text() for name in names}
    storage = json.loads(raw['parsed/qnx-storage.json'])
    mounts = json.loads(raw['parsed/qnx-partitions.json'])
    manifest = json.loads(raw['manifest.json'])
    aliases, devices = {}, {}
    for line in raw['raw/qnx/dev-disk-ls.txt'].splitlines():
        link = re.search(r'\s(\S+) -> /dev/disk/(\S+)$', line)
        if link:
            aliases[link[1]] = link[2]
        elif line.startswith('b'):
            node = line.split()[-1]
            if re.fullmatch(r'uda\d+(?:\..+)?', node):
                devices[node] = dict(node=node, lu=node.split('.')[0], aliases=[], capacityBytes=None, capacitySource=None)
    for alias, target in aliases.items():
        if target in devices:
            devices[target]['aliases'].append(alias)
    # df block-device rows give capacity, not filesystem usage. A truncated
    # partition name is used ONLY when it uniquely identifies one device.
    for line in raw['raw/qnx/df-P.txt'].splitlines():
        cols = line.split()
        if len(cols) < 5 or not re.fullmatch(r'/dev/disk/uda\d+', cols[0]) or not cols[1].isdigit():
            continue
        node = cols[0].removeprefix('/dev/disk/')
        if len(cols) == 5:
            matches = [node] if node in devices else []
        elif cols[5].startswith('/dev/disk/uda'):
            prefix = cols[5].removeprefix('/dev/disk/')
            matches = [n for n in devices if n.startswith(prefix) and n.startswith(node+'.')]
        else:
            matches = []
        if len(matches) == 1:
            devices[matches[0]]['capacityBytes'] = int(cols[1])*512
            devices[matches[0]]['capacitySource'] = 'df -P block-device row; unique device match'
    pairs = []
    for p in storage['abPartitions']:
        base = p['baseLabel']
        a, b = aliases[p['slotA']['alias']], aliases[p['slotB']['alias']]
        active = aliases.get(p['activeAlias'])
        inactive = aliases.get(p['inactiveAlias'])
        slot = 'b' if active == b and inactive == a else 'a' if active == a and inactive == b else None
        pairs.append(dict(name=base, activeSlot=slot, activeAlias=p['activeAlias'], inactiveAlias=p['inactiveAlias'],
                          slotA=dict(alias=p['slotA']['alias'],target=a),slotB=dict(alias=p['slotB']['alias'],target=b)))
    return dict(schemaVersion=1, platform='QNX 8295', capturedAt=manifest['startedAt'],
                capturedUntil=manifest['finishedAt'], sourceDirectory='~/Downloads/polaris_downloads_8295/storage-diagnostic/',
                bootLu=storage['ufs'].get('bootLu'), bootSlotReported=mounts.get('bootSlot'),
                pairs=pairs, devices=sorted(devices.values(), key=lambda d:(int(d['lu'][3:]),d['node'])),
                mounted=mounts['mounted'], sources=[dict(file=n,sha256=hashlib.sha256(raw[n].encode()).hexdigest()) for n in names])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path,help='Directory containing parsed/ and raw/ for one diagnostic run')
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('storage-8295.json'))
    args=parser.parse_args()
    data=import_snapshot(args.run)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(f"Imported {len(data['pairs'])} A/B pairs, {len(data['devices'])} devices and {len(data['mounted'])} filesystem records")
