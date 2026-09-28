"""Source-checked OTA interactions, arranged on a domain/layer grid.

Only populated layers are rendered. Matched SPI and PKG ports keep remote
connections explicit without routing through unrelated execution domains.
"""
from html import escape

WIDTH, HEIGHT = 1850, 1480
NODES = {
    'ota-qnx-updater': (440, 202, 164, 54),
    'ota-qnx-ipc': (60, 322, 164, 54),
    'ota-qnx-lcd': (250, 322, 164, 54),
    'ota-qnx-dms': (440, 322, 164, 54),
    'ota-qnx-script': (60, 482, 164, 54),
    'ota-qnx-slot': (250, 872, 164, 54),
    'ota-qnx-mcu': (440, 482, 164, 54),
    'ota-qnx-fifo': (60, 630, 164, 54),
    'ota-qnx-mcu-progress': (440, 630, 164, 54),
    'ota-qnx-banks': (250, 1116, 164, 54),
    'ota-qnx-network': (60, 872, 164, 54),
    'ota-qnx-rpcif': (250, 482, 164, 54),
    'ota-qnx-rpcd': (250, 630, 164, 54),
    'ota-qnx-os': (60, 986, 164, 54),
    'ota-aaos-ui': (792, 202, 180, 54),
    'ota-aaos-sdk': (1012, 202, 180, 54),
    'ota-aaos-doip': (792, 326, 180, 54),
    'ota-aaos-service': (1012, 326, 180, 54),
    'ota-aaos-notifier': (1232, 326, 180, 54),
    'ota-aaos-scheduler': (1012, 436, 180, 54),
    'ota-aaos-load': (792, 562, 180, 54),
    'ota-aaos-flash': (1012, 562, 180, 54),
    'ota-aaos-activate': (1232, 562, 180, 54),
    'ota-aaos-device': (1012, 692, 180, 54),
    'ota-aaos-protocol': (1232, 692, 180, 54),
    'ota-aaos-jmq': (792, 812, 180, 54),
    'ota-aaos-impl': (1232, 812, 180, 54),
    'ota-aaos-recovery': (792, 996, 180, 54),
    'ota-aaos-engine': (1232, 996, 180, 54),
    'ota-aaos-storage': (792, 1116, 180, 54),
    'ota-aaos-slot': (1232, 1116, 180, 54),
    'ota-mcu-task': (1580, 202, 200, 54),
    'ota-mcu-rtos': (1580, 334, 200, 54),
    'ota-mcu-spi': (1580, 464, 200, 54),
    'ota-mcu-flash': (1580, 584, 200, 54),
    'ota-mcu-boot': (1580, 716, 200, 54),
    'ota-mcu-hw': (1580, 848, 200, 54),
}

# Domain envelopes preserve the high-level view; layer heights fit their content.
LAYERS = {
    'qnx': [(160, 245, 'Vehicle Domain Services'),
            (417, 383, 'Platform Services'),
            (812, 120, 'Device Integration & BSP'),
            (944, 118, 'QNX Neutrino Core')],
    'aaos': [(160, 112, 'Applications'),
             (284, 658, 'Framework'),
             (954, 106, 'Native / HAL'),
             (1072, 114, 'Android OS')],
    'mcu': [(160, 120, 'Applications'),
            (292, 120, 'BSW & RTOS'),
            (424, 240, 'Drivers'),
            (676, 120, 'Bootloader'),
            (808, 120, 'Hardware')],
}

DISPLAY = {
    'ota-aaos-recovery': ('icupdater', 'Recovery-only REQ'),
    'ota-aaos-service': ('UpdateService /', 'UpdateBinder'),
    'ota-aaos-protocol': ('Target Protocols', 'QNX · Android · MCU'),
    'ota-aaos-storage': ('OTA Package Staging', 'manifest.json · payloads'),
    'ota-aaos-slot': ('Android A/B Slot', 'inactive target'),
    'ota-qnx-fifo': ('fifo_progress', 'QNX progress file'),
    'ota-qnx-mcu-progress': ('mcu_update_process', 'MCU progress file'),
    'ota-qnx-banks': ('System Image Banks (A/B)', 'system · ifs2 · hyp'),
    'ota-aaos-notifier': ('UpdateNotifier', 'client callbacks'),
    'ota-aaos-device': ('DeviceManager', 'target routing'),
    'ota-aaos-sdk': ('VoyahOtaUpdateImpl', 'client SDK'),
    'ota-qnx-rpcif': ('librpcif', 'RPC client API'),
    'ota-qnx-rpcd': ('rpcd', 'SPI bridge'),
    'ota-qnx-network': ('Network & Block I/O', 'TCP/IP · storage'),
    'ota-mcu-hw': ('Automotive MCU', 'Flash · SPI'),
}

COLORS = {
    'call': '#3974d9',
    'install': '#d98324',
    'status': '#23845b',
    'storage': '#8364b7',
    'reference': '#9b6d5c',
}


def _rect(x, y, w, h, fill, stroke, rx=12, sw=1):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def _text(x, y, value, size=12, color='#253242', weight=500, anchor='start', extra=''):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" {extra}>{escape(value)}</text>')


def _layer(x, y, w, h, title, palette):
    fill, stroke = palette
    return (f'<g class="ota-layer" data-layer="{escape(title)}">'
            + _rect(x, y, w, h, fill, stroke)
            + _text(x+14, y+23, title, 12, '#415168', 700) + '</g>')


class Routes:
    """Keep paths, crossing bridges, labels and ports in separate paint layers."""
    def __init__(self):
        self.items = []
        self.labels = []
        self.ports = []

    def add(self, source, target, points, kind='call', flow='shared', label='',
            at=None, both=False, note=''):
        if any(x1 != x2 and y1 != y2 for (x1,y1),(x2,y2) in zip(points,points[1:])):
            raise ValueError(f'Non-orthogonal OTA route: {source} -> {target}')
        self.items.append(dict(source=source,target=target,points=points,kind=kind,
                               flow=flow,both=both,note=note or label))
        if label:
            self.label(source,target,kind,flow,label,at)

    def label(self, source, target, kind, flow, label, at):
        x,y = at
        # Text is centered on its own segment; all labels are painted after paths.
        w = max(40, len(label)*5.5+18)
        self.labels.append(
            f'<g class="ota-edge-label" data-ota-from="{source}" data-ota-to="{target}" data-ota-flow="{flow}">'
            + _rect(x-w/2,y-13,w,20,'#fff',COLORS[kind],5,.45)
            + _text(x,y,label,10,COLORS[kind],600,'middle') + '</g>')

    def port(self, source, target, x, y, name, flow, note):
        w = 52
        self.ports.append(
            f'<g class="ota-link-port ota-edge-label" data-ota-from="{source}" data-ota-to="{target}" data-ota-flow="{flow}">'
            f'<title>{escape(note)}</title>'
            f'<path d="M{x-w/2},{y-12} H{x+w/2-7} L{x+w/2},{y} L{x+w/2-7},{y+12} H{x-w/2} Z" '
            f'fill="#f5f1ff" stroke="{COLORS["storage"]}" stroke-width="1.2"/>'
            + _text(x-2,y+4,name,10,COLORS['storage'],700,'middle') + '</g>')

    def render(self):
        edges = []
        previous_segments = []
        for item in self.items:
            source,target,points,kind,flow,both,note = (item[k] for k in
                ('source','target','points','kind','flow','both','note'))
            # A short white bridge at perpendicular crossings means no junction.
            # Collinear trunks and endpoint junctions remain connected.
            bridges = set()
            for (x1,y1),(x2,y2) in zip(points,points[1:]):
                for a,b,other_source,other_target in previous_segments:
                    if x1 == x2 and a[1] == b[1] and min(a[0],b[0])+4 < x1 < max(a[0],b[0])-4 and min(y1,y2)+4 < a[1] < max(y1,y2)-4:
                        bridges.add((x1,a[1],'v'))
                    if y1 == y2 and a[0] == b[0] and min(a[1],b[1])+4 < y1 < max(a[1],b[1])-4 and min(x1,x2)+4 < a[0] < max(x1,x2)-4:
                        bridges.add((a[0],y1,'h'))
            for x,y,orientation in sorted(bridges):
                d = f'M{x},{y-5} V{y+5}' if orientation == 'v' else f'M{x-5},{y} H{x+5}'
                edges.append(f'<path d="{d}" stroke="#fff" stroke-width="6" fill="none"/>')
            d = 'M' + ' L'.join(f'{x},{y}' for x,y in points)
            dash = ' stroke-dasharray="6 5"' if kind in ('status','reference') else ''
            start = f' marker-start="url(#ota-arrow-{kind})"' if both else ''
            edges.append(f'<path class="ota-edge" data-ota-from="{source}" data-ota-to="{target}" data-ota-flow="{flow}" '
                         f'd="{d}" fill="none" stroke="{COLORS[kind]}" stroke-width="1.8" '
                         f'stroke-linecap="round" stroke-linejoin="round" marker-end="url(#ota-arrow-{kind})"{start}{dash}>'
                         f'<title>{escape(note or source + " → " + target)}</title></path>')
            previous_segments.extend((a,b,source,target) for a,b in zip(points,points[1:]))
        return '<g class="ota-connections">'+''.join(edges)+'</g><g class="ota-labels">'+''.join(self.labels+self.ports)+'</g>'


def render_graph(modules):
    by_id = {m['id']:m for m in modules}
    if set(NODES) != set(by_id):
        raise ValueError(f'OTA graph/module mismatch: {set(NODES) ^ set(by_id)}')
    frame = [
        _rect(15,60,1495,1280,'#fbfcff','#e0e5ed',20),
        _text(34,87,'SoC Platform',17,'#202124',700),
        _text(175,87,'QNX host + Android guest',10,'#738092'),
        _rect(30,110,608,1090,'#eaf1fe','#bfd3f8',17),
        _rect(768,110,730,1090,'#eaf6ed','#c8e5cf',17),
        _rect(1540,110,280,832,'#fff2e6','#efcbab',17),
        _text(48,140,'QNX Cluster',18,'#1d4e9e',700),
        _text(786,140,'AAOS IVI',18,'#176c3b',700),
        _text(1558,140,'MCU',18,'#99602e',700),
        _text(1620,140,'Reference only',10,'#99602e'),
        _text(655,137,'CROSS-DOMAIN',10,'#526179',700),
    ]
    layer_styles = {
        'qnx': (42,584,('#ffffffd9','#d6e1f0')),
        'aaos': (780,706,('#ffffffd9','#d6e8d9')),
        'mcu': (1552,256,('#ffffffd9','#f0dccb')),
    }
    for domain,layers in LAYERS.items():
        x,w,palette = layer_styles[domain]
        for y,h,title in layers:
            if not any(by_id[mid]['domain'] == domain and y < ny < ny+nh <= y+h
                       for mid,(_,ny,_,nh) in NODES.items()):
                raise ValueError(f'Empty OTA layer: {domain}/{title}')
            frame.append(_layer(x,y,w,h,title,palette))
    # Image banks are storage targets, not a software service or an OS layer.
    frame.append('<g class="ota-storage-region" data-region="Image Storage">'
                 '<rect x="42" y="1074" width="584" height="112" rx="12" fill="#f8f5fd" '
                 'stroke="#cbbce4" stroke-dasharray="5 4"/>'
                 + _text(56,1097,'Image Storage',12,'#675284',700) + '</g>')
    frame.extend([
        _layer(30,1212,1468,54,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
        _text(240,1244,'QNX / Android isolation · virtual network I/O',11,'#5b6075'),
        _layer(30,1278,1468,48,'SoC Hardware',('#fff','#dce1e8')),
        _text(240,1308,'CPU · storage · TCP/IP · SPI',11,'#5b6075'),
        _text(1554,980,'CONNECTION KEY',11,'#526179',700),
        _text(1554,1004,'SPI / PKG: matched link ports',11,'#526179'),
        _text(1554,1024,'Crossings with gaps are not junctions.',10,'#738092'),
        _text(1554,1044,'Dashed MCU paths: reference only.',10,'#738092'),
    ])
    r = Routes()
    # AAOS: ingress, scheduling, target routing; one column per task branch.
    r.add('ota-aaos-ui','ota-aaos-sdk',[(975,229),(1009,229)],both=True,note='SDK trigger and client callback')
    r.add('ota-aaos-sdk','ota-aaos-service',[(1102,259),(1102,323)],both=True,label='Binder',at=(1102,291),note='Binder request and callback')
    r.add('external-doip','ota-aaos-doip',[(920,299),(920,323)],label='DoIP',at=(920,307))
    r.add('ota-aaos-doip','ota-aaos-service',[(975,353),(1009,353)],note='Verified install request: applyAction')
    r.add('ota-aaos-service','ota-aaos-scheduler',[(1102,383),(1102,433)],label='schedule',at=(1102,412))
    for target,cx,stage in [('ota-aaos-load',882,'LOAD'),('ota-aaos-flash',1102,'FLASH'),('ota-aaos-activate',1322,'ACTIVATE')]:
        pts = [(1102,493),(1102,524)]
        if cx != 1102:
            pts.append((cx,524))
        pts.append((cx,559))
        r.add('ota-aaos-scheduler',target,pts,label=stage,at=(cx,545))
    r.add('ota-aaos-flash','ota-aaos-device',[(1102,619),(1102,689)],label='onFlash',at=(1102,659))
    r.add('ota-aaos-device','ota-aaos-protocol',[(1195,719),(1229,719)],note='Route target from manifest.json')
    r.add('ota-aaos-protocol','ota-aaos-impl',[(1322,749),(1322,809)],label='target update',at=(1322,782))
    r.add('ota-aaos-impl','ota-aaos-jmq',[(1229,839),(975,839)],flow='qnx,mcu',label='request / poll',at=(1102,839),both=True)
    r.add('ota-aaos-jmq','ota-qnx-updater',[(789,839),(676,839),(676,222),(607,222)],flow='qnx,mcu,feedback',label='ZeroMQ · TCP/IP',at=(676,602),both=True,note='REQ/REP over TCP/IP 10.10.200.1:5030; upgrade commands and polled progress/result')
    r.add('ota-aaos-recovery','ota-qnx-updater',[(789,1023),(740,1023),(740,244),(607,244)],flow='qnx',label='Recovery only',at=(740,916),note='icupdater bypasses Android UpdateService')
    # Staging is a file dependency, not a call through the intervening modules.
    r.add('ota-aaos-load','ota-aaos-storage',[(882,619),(882,635)],kind='storage')
    r.port('ota-aaos-load','ota-aaos-storage',882,650,'PKG','shared','Matched PKG ports: LoadTask reads manifest.json and stages package files')
    r.port('ota-aaos-load','ota-aaos-storage',922,1090,'PKG','shared','Matched PKG ports: OTA Package Staging ↔ LoadTask')
    r.add('ota-aaos-load','ota-aaos-storage',[(922,1105),(922,1113)],kind='storage')
    # QNX: one common start trunk; independent bank selection and MCU process.
    for target,cx in [('ota-qnx-ipc',142),('ota-qnx-lcd',332),('ota-qnx-dms',522)]:
        pts = [(522,259),(522,286)]
        if cx != 522:
            pts.append((cx,286))
        pts.append((cx,319))
        r.add('ota-qnx-updater',target,pts,kind='install',flow='qnx')
    r.label('ota-qnx-updater','ota-qnx-ipc','install','qnx','IPC start · 0xA1',(252,286))
    r.add('ota-qnx-ipc','ota-qnx-script',[(142,379),(142,396),(236,396),(236,459),(142,459),(142,479)],kind='install',flow='qnx',label='run script',at=(236,441))
    r.add('ota-qnx-updater','ota-qnx-slot',[(437,246),(428,246),(428,899),(417,899)],flow='qnx',label='bank request',at=(428,836))
    r.add('ota-qnx-slot','ota-qnx-banks',[(332,929),(332,1113)],kind='storage',flow='qnx',label='select bank',at=(332,1040))
    r.add('ota-qnx-script','ota-qnx-banks',[(227,509),(236,509),(236,1143),(247,1143)],kind='install',flow='qnx',label='write image',at=(236,700))
    r.add('ota-qnx-updater','ota-qnx-mcu',[(590,259),(590,270),(620,270),(620,509),(607,509)],kind='install',flow='mcu',label='launch',at=(620,433))
    r.add('ota-qnx-script','ota-qnx-fifo',[(142,539),(142,627)],kind='status',flow='feedback',label='write progress',at=(142,590))
    r.add('ota-qnx-mcu','ota-qnx-mcu-progress',[(522,539),(522,627)],kind='status',flow='feedback',label='write progress',at=(522,590))
    for mid,cx in [('ota-qnx-fifo',142),('ota-qnx-mcu-progress',522)]:
        r.add(mid,'ota-qnx-updater',[(cx,687),(cx,710),(46,710),(46,222),(437,222)],kind='status',flow='feedback')
    r.label('ota-qnx-fifo','ota-qnx-updater','status','feedback','read / poll progress files',(248,222))
    r.add('ota-qnx-mcu','ota-qnx-rpcif',[(522,479),(522,457),(332,457),(332,479)],flow='mcu',label='API call',at=(366,457))
    r.add('ota-qnx-rpcif','ota-qnx-rpcd',[(332,539),(332,627)],flow='mcu',label='local IPC',at=(332,590))
    # Physical SPI is a matched interface pair, not a path through AAOS or SoC hardware.
    spi_note = 'Matched SPI ports: QNX rpcd ↔ MCU SPI Driver; physical SPI message blocks'
    r.add('ota-qnx-rpcd','ota-mcu-spi',[(332,687),(332,759)],kind='storage',flow='mcu',both=True,note=spi_note)
    r.port('ota-qnx-rpcd','ota-mcu-spi',332,774,'SPI','mcu',spi_note)
    r.add('ota-qnx-rpcd','ota-mcu-spi',[(1680,535),(1680,521)],kind='storage',flow='mcu',both=True,note=spi_note)
    r.port('ota-qnx-rpcd','ota-mcu-spi',1680,550,'SPI','mcu',spi_note)
    # MCU internals follow the supplied reference; their spacing is content-driven.
    r.add('ota-mcu-spi','ota-mcu-task',[(1577,491),(1546,491),(1546,229),(1577,229)],kind='reference',flow='mcu',note='Received firmware frame')
    r.add('ota-mcu-task','ota-mcu-flash',[(1783,229),(1796,229),(1796,611),(1783,611)],kind='reference',flow='mcu',note='Firmware data')
    r.add('ota-mcu-flash','ota-mcu-boot',[(1680,641),(1680,713)],kind='reference',flow='mcu',label='image handoff',at=(1680,681))
    r.add('ota-mcu-boot','ota-mcu-hw',[(1680,773),(1680,845)],kind='reference',flow='mcu',label='boot image',at=(1680,813))
    # Android installation and a dedicated outside return channel.
    r.add('ota-aaos-impl','ota-aaos-engine',[(1322,869),(1322,993)],kind='install',flow='android',label='applyPayload',at=(1322,919))
    r.add('ota-aaos-engine','ota-aaos-slot',[(1322,1053),(1322,1113)],kind='storage',flow='android',label='inactive slot',at=(1322,1089))
    r.add('ota-aaos-engine','ota-aaos-impl',[(1415,1023),(1458,1023),(1458,839),(1415,839)],kind='status',flow='feedback',label='callback',at=(1458,914))
    # Status channels occupy their own lanes next to the control spine.
    r.add('ota-aaos-flash','ota-aaos-scheduler',[(1156,559),(1156,493)],kind='status',flow='feedback',note='Task state / result')
    r.add('ota-aaos-scheduler','ota-aaos-notifier',[(1195,463),(1322,463),(1322,383)],kind='status',flow='feedback',label='task status',at=(1322,418))
    r.add('ota-aaos-notifier','ota-aaos-service',[(1229,353),(1195,353)],kind='status',flow='feedback',note='Notify registered service clients')
    # Shared scheduling trunks have explicit branch points.
    junctions = (_rect(1100,522,4,4,COLORS['call'],COLORS['call'],2)
                 + _rect(520,284,4,4,COLORS['install'],COLORS['install'],2))
    status = [_rect(30,1352,1790,108,'#f5faf7','#cfe5d6',13),
              _text(48,1377,'STATUS & RESULT RETURN',12,'#28724c',700),
              _text(48,1396,'QNX/MCU: progress files → updater. Android: UpdateEngine callback → UpdateImpl.',10,'#537565')]
    return_nodes = [('QNX / MCU files',50,165),('updater',237,118),('JMQClient',377,127),
                    ('UpdateImpl',526,127),('Target Protocols',675,148),('FlashTask',845,122),
                    ('TaskScheduler',989,145),('UpdateNotifier',1156,154),
                    ('UpdateBinder',1332,147),('SDK / UI',1501,124)]
    return_routes = Routes()
    for i,(title,x,w) in enumerate(return_nodes):
        status.append(_rect(x,1414,w,30,'#fff','#a8d3b8',6))
        status.append(_text(x+w/2,1434,title,10,'#276b49',700,'middle'))
        if i:
            prev_x,prev_w = return_nodes[i-1][1:]
            return_routes.add('status-'+str(i-1),'status-'+str(i),[(prev_x+prev_w+3,1429),(x-4,1429)],kind='status',flow='feedback')
    status.append(return_routes.render())
    nodes = []
    for mid,(x,y,w,h) in NODES.items():
        module = by_id[mid]
        name,sub = DISPLAY.get(mid,(module['name'],module['short']))
        fill,stroke = {'qnx':('#fff','#91b1ed'),'aaos':('#fff','#9fceb0'),'mcu':('#fffaf5','#d7aa83')}[module['domain']]
        storage = module.get('kind') == 'storage'
        if storage:
            fill,stroke = '#f5effc','#a18bc2'
        dash = ' stroke-dasharray="5 4"' if module.get('reference') else ''
        kind = 'storage' if storage else 'component'
        # A double base line distinguishes a stored image object from a service.
        detail = (f'<path d="M{x+1},{y+h-6} H{x+w-1}" stroke="{stroke}" fill="none"/>' if storage else '')
        name_size = 10.5 if len(name)>22 else 11.5
        sub_size = 9 if len(sub)>24 else 10
        nodes.append(f'<g class="ota-node" data-sw-module="{mid}" data-node-kind="{kind}" role="button" tabindex="0" aria-label="{escape(module["name"],quote=True)}" aria-pressed="false">'
                     f'<title>{escape(module["name"])}</title><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{dash}/>'
                     + _text(x+12,y+23,name,name_size,'#1f2e40',700)
                     + _text(x+12,y+42,sub,sub_size,'#647184')+detail+'</g>')
    defs = ['<defs>']
    for kind,color in COLORS.items():
        defs.append(f'<marker id="ota-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                    f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend = []
    for x,title,kind in [(1020,'Call / reply','call'),(1160,'Install','install'),(1270,'Status','status'),(1380,'Data / link','storage'),(1520,'MCU reference','reference')]:
        dash = ' stroke-dasharray="4 3"' if kind in ('status','reference') else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{COLORS[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,10,COLORS[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram" id="sw-ota-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, Roboto, sans-serif" role="group" aria-label="OTA component interaction architecture">'
            '<title>OTA software component interactions</title>'
            '<desc>Populated QNX, AAOS and MCU layers. Orthogonal calls and status paths. Matching SPI and PKG ports identify continuous remote connections.</desc>'
            + ''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            + _text(30,36,'OTA SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            + ''.join(legend)+''.join(frame)+r.render()+junctions
            + '<g class="ota-return-lane">'+''.join(status)+'</g>'
            + '<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
