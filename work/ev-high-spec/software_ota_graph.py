"""Interactive SVG for the source-checked OTA component graph.

The deployment frame follows the high-level view: QNX | cross-domain | AAOS,
then the SoC-to-MCU bridge and the MCU layers. Routes are curated to make
component interactions and their direction visible, rather than implying that
layer membership is itself an interaction.
"""
from html import escape

WIDTH, HEIGHT = 1850, 1465
NODES = {
    # QNX Cluster
    'ota-qnx-updater': (420, 229, 170, 56),
    'ota-qnx-ipc': (58, 340, 168, 54),
    'ota-qnx-lcd': (238, 340, 168, 54),
    'ota-qnx-dms': (418, 340, 168, 54),
    'ota-qnx-script': (58, 490, 168, 54),
    'ota-qnx-slot': (238, 490, 168, 54),
    'ota-qnx-mcu': (418, 490, 168, 54),
    'ota-qnx-fifo': (58, 620, 168, 54),
    'ota-qnx-mcu-progress': (418, 620, 168, 54),
    'ota-qnx-banks': (58, 740, 168, 54),
    'ota-qnx-network': (58, 850, 168, 54),
    'ota-qnx-rpcif': (418, 850, 168, 54),
    'ota-qnx-rpcd': (418, 960, 168, 54),
    'ota-qnx-os': (58, 1100, 168, 54),
    # AAOS IVI and its recovery-only cross-domain client
    'ota-aaos-recovery': (638, 158, 95, 56),
    'ota-aaos-ui': (754, 163, 166, 54),
    'ota-aaos-sdk': (941, 163, 166, 54),
    'ota-aaos-service': (754, 331, 166, 54),
    'ota-aaos-scheduler': (941, 331, 166, 54),
    'ota-aaos-notifier': (1128, 331, 166, 54),
    'ota-aaos-load': (754, 451, 166, 54),
    'ota-aaos-flash': (941, 451, 166, 54),
    'ota-aaos-doip': (1260, 451, 154, 54),
    'ota-aaos-activate': (1128, 551, 166, 54),
    'ota-aaos-device': (754, 571, 166, 54),
    'ota-aaos-protocol': (941, 571, 166, 54),
    'ota-aaos-impl': (1128, 681, 166, 54),
    'ota-aaos-jmq': (754, 791, 166, 54),
    'ota-aaos-engine': (1128, 997, 166, 54),
    'ota-aaos-storage': (754, 1090, 166, 54),
    'ota-aaos-slot': (1128, 1090, 166, 54),
    # MCU (reference-only: firmware source is not available)
    'ota-mcu-task': (1562, 257, 215, 56),
    'ota-mcu-rtos': (1562, 497, 215, 56),
    'ota-mcu-spi': (1562, 697, 215, 56),
    'ota-mcu-flash': (1562, 805, 215, 56),
    'ota-mcu-boot': (1562, 944, 215, 56),
    'ota-mcu-hw': (1562, 1091, 215, 56),
}

# SVG labels are intentionally English-only. Short descriptions appear in the
# responsibility list outside the diagram.
DISPLAY = {
    'ota-aaos-recovery': ('icupdater', 'Recovery-only REQ'),
    'ota-aaos-service': ('UpdateService /', 'UpdateBinder'),
    'ota-aaos-protocol': ('Target Protocols', 'QNX · Android · MCU'),
    'ota-aaos-storage': ('OTA Package Staging', 'manifest.json · payloads'),
    'ota-aaos-slot': ('Android A/B Slot', 'inactive target'),
    'ota-qnx-fifo': ('fifo_progress', 'QNX progress file'),
    'ota-qnx-mcu-progress': ('mcu_update_process', 'MCU progress file'),
    'ota-qnx-banks': ('QNX BANK_A / BANK_B', 'system · ifs2 · hyp'),
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


def _rect(x, y, w, h, fill, stroke, rx=13, sw=1):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def _text(x, y, value, size=12, color='#253242', weight=500, anchor='start', extra=''):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" {extra}>{escape(value)}</text>')


def _layer(x, y, w, h, title, palette):
    fill, stroke = palette
    return (_rect(x, y, w, h, fill, stroke, 13)
            + _text(x+13, y+23, title, 12, '#415168', 700))


def _edge(source, target, points, kind, flow, label='', label_at=None, both=False,
          dashed=False, note=''):
    color = COLORS[kind]
    d = 'M' + ' L'.join(f'{x},{y}' for x, y in points)
    dash = ' stroke-dasharray="6 5"' if dashed or kind == 'status' or kind == 'reference' else ''
    start = f' marker-start="url(#ota-arrow-{kind})"' if both else ''
    route = (f'<path class="ota-edge" data-ota-from="{source}" data-ota-to="{target}" '
             f'data-ota-flow="{flow}" d="{d}" fill="none" stroke="{color}" '
             f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
             f'marker-end="url(#ota-arrow-{kind})"{start}{dash}>'
             f'<title>{escape(note or label or source + " → " + target)}</title></path>')
    if label and label_at:
        lx, ly = label_at
        lw = max(42, min(240, len(label)*6.0+15))
        route += (f'<g class="ota-edge-label" data-ota-flow="{flow}">'
                  f'<rect x="{lx-lw/2:.1f}" y="{ly-14}" width="{lw:.1f}" height="21" rx="7" '
                  f'fill="#fff" stroke="{color}" stroke-opacity=".35"/>'
                  + _text(lx,ly,label,10,color,700,'middle')+'</g>')
    return route


def render_graph(modules):
    by_id = {item['id']: item for item in modules}
    missing = set(NODES)-set(by_id)
    if missing:
        raise ValueError(f'OTA graph nodes missing module descriptions: {sorted(missing)}')
    unused = set(by_id)-set(NODES)
    if unused:
        raise ValueError(f'OTA modules missing graph positions: {sorted(unused)}')

    frame = []
    frame.append(_rect(15, 55, 1441, 1265, '#fbfcff', '#e0e5ed', 22))
    frame.append(_text(34, 84, 'SoC Platform', 17, '#202124', 700))
    frame.append(_text(34, 102, 'QNX host + Android guest', 10, '#738092'))
    frame.append(_rect(30, 113, 588, 1070, '#eaf1fe', '#bfd3f8', 18))
    frame.append(_rect(748, 113, 693, 1070, '#eaf6ed', '#c8e5cf', 18))
    frame.append(_rect(1536, 113, 278, 1070, '#fff2e6', '#efcbab', 18))
    frame.append(_text(48, 144, 'QNX Cluster', 18, '#1d4e9e', 700))
    frame.append(_text(766, 144, 'AAOS IVI', 18, '#176c3b', 700))
    frame.append(_text(1554, 144, 'MCU', 18, '#99602e', 700))
    frame.append(_text(1554, 162, 'Reference-only internals', 10, '#99602e'))
    frame.append(_text(630, 122, 'CROSS-DOMAIN', 10, '#526179', 700))
    frame.append(_text(630, 138, 'TCP/IP', 10, '#526179', 700))
    frame.append(_text(1459, 370, 'QNX rpcd ↔ MCU', 10, '#855432', 700, 'middle'))
    frame.append(_text(1459, 388, 'SPI message blocks', 10, '#855432', 700, 'middle'))
    # The same domains and layer names as the high-level software view.
    qnx_layers = [
        (155, 42, 'Product Experience'),
        (203, 222, 'Vehicle Domain Services'),
        (432, 370, 'Platform Services'),
        (809, 246, 'Device Integration & BSP'),
        (1063, 106, 'QNX Neutrino Core'),
    ]
    for y,h,title in qnx_layers:
        frame.append(_layer(42,y,564,h,title,('#ffffffca','#d6e1f0')))
    aaos_layers = [
        (155, 133, 'Applications'),
        (296, 648, 'Framework'),
        (952, 108, 'Native / HAL'),
        (1067, 102, 'Android OS'),
    ]
    for y,h,title in aaos_layers:
        frame.append(_layer(760,y,668,h,title,('#ffffffcf','#d6e8d9')))
    mcu_layers = [
        (174, 244, 'Applications'),
        (426, 157, 'BSW & RTOS'),
        (591, 268, 'Drivers'),
        (867, 150, 'Bootloader'),
        (1025, 144, 'Hardware'),
    ]
    for y,h,title in mcu_layers:
        frame.append(_layer(1548,y,254,h,title,('#ffffffca','#f0dccb')))
    frame.append(_layer(30,1191,1412,55,'VIRTUALIZATION',('#f2f0fc','#ded9ef')))
    frame.append(_text(240,1224,'QNX / Android isolation · virtual network I/O',11,'#5b6075'))
    frame.append(_layer(30,1254,1412,52,'SoC Hardware',('#fff','#dce1e8')))
    frame.append(_text(240,1286,'CPU · storage · TCP/IP · SPI',11,'#5b6075'))
    frame.append(_rect(30,1332,1784,115,'#f5faf7','#cfe5d6',14))
    frame.append(_text(47,1356,'STATUS & RESULT RETURN',12,'#28724c',700))
    frame.append(_text(47,1375,'QNX/MCU: progress files → updater; Android: UpdateEngine callback → UpdateImpl.',10,'#537565'))

    routes = []
    # Client ingress and task scheduling.
    routes.append(_edge('ota-aaos-ui','ota-aaos-sdk',[(920,190),(937,190)],'call','shared',''))
    routes.append(_edge('ota-aaos-sdk','ota-aaos-service',[(1024,217),(1024,258),(837,258),(837,328)],'call','shared','Binder',(950,249)))
    routes.append(_edge('external-doip','ota-aaos-doip',[(1438,478),(1417,478)],'call','shared',
                        'DoIP request',(1367,431)))
    routes.append(_edge('ota-aaos-doip','ota-aaos-service',[(1260,478),(1244,478),(1244,412),(930,412),(930,357),(923,357)],'call','shared','applyAction',(1080,401)))
    routes.append(_edge('ota-aaos-service','ota-aaos-scheduler',[(920,358),(938,358)],'call','shared',''))
    # LOAD, FLASH and ACTIVATE are scheduled stages, not calls from one task to the next.
    routes.append(_edge('ota-aaos-scheduler','ota-aaos-load',[(1024,385),(1024,423),(837,423),(837,448)],'call','shared','LOAD',(913,415)))
    routes.append(_edge('ota-aaos-scheduler','ota-aaos-flash',[(1024,385),(1024,448)],'call','shared','FLASH',(1065,422)))
    routes.append(_edge('ota-aaos-scheduler','ota-aaos-activate',[(1094,385),(1181,385),(1181,578),(1125,578)],'call','shared','ACTIVATE',(1208,528)))
    routes.append(_edge('ota-aaos-load','ota-aaos-storage',[(754,478),(739,478),(739,1117),(751,1117)],'storage','shared','manifest.json',(808,1045)))
    routes.append(_edge('ota-aaos-flash','ota-aaos-device',[(1024,505),(1024,540),(837,540),(837,568)],'call','shared','onFlash',(931,532)))
    routes.append(_edge('ota-aaos-device','ota-aaos-protocol',[(920,598),(938,598)],'call','shared',''))
    routes.append(_edge('ota-aaos-protocol','ota-aaos-impl',[(1107,598),(1120,598),(1120,708),(1125,708)],'call','shared','target update',(1178,638)))
    routes.append(_edge('ota-aaos-impl','ota-aaos-jmq',[(1128,708),(1020,708),(1020,818),(923,818)],'call','qnx,mcu','request / poll',(1019,747),both=True))
    routes.append(_edge('ota-aaos-jmq','ota-qnx-updater',[(751,818),(689,818),(689,257),(593,257)],'call','qnx,mcu,feedback','ZeroMQ REQ/REP · TCP',(680,564),both=True,
                        note='Bidirectional request/reply over TCP/IP 10.10.200.1:5030; progress and result are polled.'))
    routes.append(_edge('ota-aaos-recovery','ota-qnx-updater',[(638,187),(619,187),(619,238),(593,238)],'call','qnx','Recovery only',(670,248),
                        note='icupdater directly connects to the QNX updater; it bypasses UpdateService.'))
    # QNX updater fans out to three jobs for the IPC start request.
    routes.append(_edge('ota-qnx-updater','ota-qnx-ipc',[(476,285),(476,313),(142,313),(142,337)],'install','qnx','0xA1',(277,304)))
    routes.append(_edge('ota-qnx-updater','ota-qnx-lcd',[(503,285),(503,319),(322,319),(322,337)],'install','qnx'))
    routes.append(_edge('ota-qnx-updater','ota-qnx-dms',[(530,285),(530,337)],'install','qnx'))
    routes.append(_edge('ota-qnx-ipc','ota-qnx-script',[(142,394),(142,487)],'install','qnx','process + script',(190,449)))
    routes.append(_edge('ota-qnx-updater','ota-qnx-slot',[(420,257),(410,257),(410,517),(409,517)],'call','qnx','request slot',(348,453),
                        note='swdl_utils reads current bank and selects the bank requested by slot=1/2.'))
    routes.append(_edge('ota-qnx-slot','ota-qnx-banks',[(238,517),(232,517),(232,767),(229,767)],'storage','qnx','select bank',(274,681)))
    routes.append(_edge('ota-qnx-script','ota-qnx-banks',[(58,517),(49,517),(49,767),(55,767)],'install','qnx','write image',(103,703)))
    routes.append(_edge('ota-qnx-script','ota-qnx-fifo',[(142,544),(142,617)],'status','feedback','write progress',(199,588)))
    routes.append(_edge('ota-qnx-fifo','ota-qnx-updater',[(58,647),(47,647),(47,298),(397,298),(397,257),(417,257)],'status','feedback','read / poll',(127,293)))
    # MCU update: process invocation, library call, local IPC, then physical SPI.
    routes.append(_edge('ota-qnx-updater','ota-qnx-mcu',[(590,257),(609,257),(609,517),(589,517)],'install','mcu','launch process',(548,441)))
    routes.append(_edge('ota-qnx-mcu','ota-qnx-mcu-progress',[(502,544),(502,617)],'status','feedback','write progress',(556,588)))
    routes.append(_edge('ota-qnx-mcu-progress','ota-qnx-updater',[(586,647),(611,647),(611,273),(593,273)],'status','feedback','read / poll',(563,694)))
    routes.append(_edge('ota-qnx-mcu','ota-qnx-rpcif',[(589,517),(610,517),(610,877),(589,877)],'call','mcu','API call',(554,823)))
    routes.append(_edge('ota-qnx-rpcif','ota-qnx-rpcd',[(502,904),(502,957)],'call','mcu','local IPC',(552,937)))
    routes.append(_edge('ota-qnx-rpcd','ota-mcu-spi',[(589,987),(625,987),(625,1316),(1515,1316),(1515,725),(1559,725)],'storage','mcu','SPI command / response',(1464,1309),both=True,
                        note='rpcd and MCU exchange message blocks over the physical SPI link.'))
    routes.append(_edge('ota-mcu-spi','ota-mcu-task',[(1562,725),(1538,725),(1538,286),(1559,286)],'reference','mcu','received frame',(1603,637),dashed=True))
    routes.append(_edge('ota-mcu-task','ota-mcu-flash',[(1777,286),(1790,286),(1790,832),(1780,832)],'reference','mcu','firmware data',(1729,785),dashed=True))
    routes.append(_edge('ota-mcu-flash','ota-mcu-boot',[(1669,861),(1669,941)],'reference','mcu','image handoff',(1720,904),dashed=True))
    routes.append(_edge('ota-mcu-boot','ota-mcu-hw',[(1669,1000),(1669,1088)],'reference','mcu','Flash A/B',(1718,1046),dashed=True))
    # Android A/B branch and its callback.
    routes.append(_edge('ota-aaos-impl','ota-aaos-engine',[(1211,735),(1211,994)],'install','android','applyPayload',(1281,897)))
    routes.append(_edge('ota-aaos-engine','ota-aaos-slot',[(1211,1051),(1211,1087)],'storage','android','inactive slot',(1284,1073)))
    routes.append(_edge('ota-aaos-engine','ota-aaos-impl',[(1297,1024),(1393,1024),(1393,708),(1297,708)],'status','feedback','callback',(1368,956)))
    # Callback path into the OTA client. The full ordered path is also expanded
    # in the status lane below, so the normal control edges remain legible.
    routes.append(_edge('ota-aaos-flash','ota-aaos-scheduler',[(1090,448),(1090,388)],'status','feedback','task status',(1146,421)))
    routes.append(_edge('ota-aaos-scheduler','ota-aaos-notifier',[(1107,358),(1125,358)],'status','feedback',''))
    routes.append(_edge('ota-aaos-notifier','ota-aaos-service',[(1211,331),(1211,306),(837,306),(837,328)],'status','feedback','callback',(1042,299)))
    routes.append(_edge('ota-aaos-service','ota-aaos-sdk',[(895,328),(895,275),(1024,275),(1024,220)],'status','feedback',''))
    routes.append(_edge('ota-aaos-sdk','ota-aaos-ui',[(938,200),(923,200)],'status','feedback'))

    # A compact, explicit return chain makes intermediate callback owners clear.
    return_nodes = [
        ('QNX / MCU files',52,165),('updater',244,118),('JMQClient',382,127),
        ('UpdateImpl',529,127),('Target Protocols',676,148),('FlashTask',844,122),
        ('TaskScheduler',986,145),('UpdateNotifier',1151,154),
        ('UpdateBinder',1325,147),('SDK / UI',1492,124),
    ]
    status = []
    for i,(title,x,w) in enumerate(return_nodes):
        status.append(_rect(x,1393,w,30,'#fff','#a8d3b8',7))
        status.append(_text(x+w/2,1413,title,10,'#276b49',700,'middle'))
        if i:
            prev_x,prev_w = return_nodes[i-1][1],return_nodes[i-1][2]
            status.append(_edge('status-'+str(i-1),'status-'+str(i),[(prev_x+prev_w+3,1408),(x-4,1408)],
                                'status','feedback'))

    nodes = []
    for mid,(x,y,w,h) in NODES.items():
        module = by_id[mid]
        name, sub = DISPLAY.get(mid,(module['name'],module['short']))
        domain = module['domain']
        fill,stroke = {'qnx':('#fff','#91b1ed'),'aaos':('#fff','#9fceb0'),
                       'mcu':('#fffaf5','#d7aa83')}[domain]
        dash = ' stroke-dasharray="5 4"' if module.get('reference') else ''
        name_size = 11 if len(name)>22 else 12
        body = (f'<g class="ota-node" data-sw-module="{mid}" role="button" tabindex="0" '
                f'aria-label="{escape(module["name"],quote=True)}" aria-pressed="false">'
                f'<title>{escape(module["name"])}</title>'
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>'
                + _text(x+12,y+23,name,name_size,'#1f2e40',700)
                + _text(x+12,y+42,sub,10,'#647184')+'</g>')
        nodes.append(body)

    defs = ['<defs>']
    for kind,color in COLORS.items():
        defs.append(f'<marker id="ota-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" '
                    f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                    f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.4"/>'
                    '</marker>')
    defs.append('</defs>')
    svg = (f'<svg class="sw-ota-diagram" id="sw-ota-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'width="{WIDTH}" height="{HEIGHT}" role="group" aria-label="OTA component interaction architecture">'
           '<title>OTA software component interactions</title>'
           '<desc>QNX Cluster, AAOS IVI and MCU domains with directed component calls, package installation, progress return, and SPI exchanges.</desc>'
           + ''.join(defs) + '<rect width="1850" height="1465" fill="#fff"/>'
           + _text(30,31,'OTA SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
           + _text(1240,30,'Blue: call',10,COLORS['call'],700)
           + _text(1320,30,'Orange: install',10,COLORS['install'],700)
           + _text(1429,30,'Green: status',10,COLORS['status'],700)
           + _text(1532,30,'Purple: data',10,COLORS['storage'],700)
           + _text(1635,30,'Dashed: MCU reference',10,COLORS['reference'],700)
           + ''.join(frame)
           + '<g class="ota-connections">'+''.join(routes)+'</g>'
           + '<g class="ota-return-lane">'+''.join(status)+'</g>'
           + '<g class="ota-nodes">'+''.join(nodes)+'</g>'
           + '</svg>')
    return svg
