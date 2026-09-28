"""Interactive diagnostic graph using the same domain frame and routing language as OTA."""
from html import escape
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 1850, 1450
NODES = {
    'diag-qnx-dtc':(60,210,164,54), 'diag-qnx-did':(250,210,164,54),
    'diag-qnx-log':(440,210,164,54), 'diag-qnx-rpcif':(60,390,164,54),
    'diag-qnx-rpcd':(250,390,164,54),
    'diag-qnx-status':(60,770,164,54), 'diag-qnx-spi':(250,770,164,54),
    'diag-qnx-slog':(440,770,164,54), 'diag-qnx-os':(60,970,164,54),
    'diag-aaos-service':(790,208,180,54), 'diag-aaos-dtc':(1010,208,180,54),
    'diag-aaos-mcu':(1230,208,180,54), 'diag-aaos-vehicle':(1010,338,180,54),
    'diag-aaos-doip':(790,502,180,54), 'diag-aaos-dcm':(1010,502,180,54),
    'diag-aaos-binder':(1230,502,180,54), 'diag-aaos-uds':(790,642,180,54),
    'diag-aaos-doipvehicle':(1010,642,180,54), 'diag-aaos-vhal':(1230,642,180,54),
    'diag-aaos-devices':(1010,842,180,54),
    'diag-mcu-factory':(1560,208,112,54), 'diag-mcu-mfg':(1692,208,112,54),
    'diag-mcu-spi-ivi':(1560,300,112,54), 'diag-mcu-spi-ic':(1692,300,112,54),
    'diag-mcu-dcm':(1560,426,112,54), 'diag-mcu-dem':(1692,426,112,54),
    'diag-mcu-cantp':(1560,518,112,54), 'diag-mcu-canif':(1692,518,112,54),
    'diag-mcu-nvm':(1560,610,112,54), 'diag-mcu-rtos':(1692,610,112,54),
    'diag-mcu-cdd':(1692,696,112,54),
    'diag-mcu-canfd':(1692,800,112,54), 'diag-mcu-spi':(1560,800,112,54),
    'diag-mcu-flash':(1560,895,112,54),
    'diag-mcu-boot':(1580,1090,200,54), 'diag-mcu-hw':(1580,1220,200,54),
    'diag-vm-isolation':(230,1321,600,38), 'diag-vdev-net':(850,1321,600,38),
}
LAYERS = {
    'qnx':[(170,510,'Platform Services'),(700,200,'Device Integration & BSP'),
           (920,145,'QNX Neutrino Core')],
    'aaos':[(170,300,'Applications'),(480,300,'Native Services & HAL'),
            (800,130,'Android OS')],
    'mcu':[(170,215,'Applications'),(395,360,'BSW & RTOS'),
           (765,280,'Drivers'),(1060,115,'Bootloader'),(1190,105,'Hardware')],
}
DISPLAY = {
    'diag-aaos-uds':('UDS / DoIP Stack','libvoyuds · libvoydoip'),
    'diag-qnx-spi':('SPI I/O','Board-level link'),
    'diag-qnx-status':('Device Status I/O','Thermal · video · audio'),
    'diag-mcu-factory':('FactoryDiag','Factory tests'),
    'diag-mcu-spi-ivi':('SPI IVI Task','IVI frames'),
    'diag-mcu-spi-ic':('SPI IC Task','Cluster frames'),
    'diag-mcu-hw':('Automotive MCU','CAN FD · SPI · Flash'),
}


def render_graph(modules):
    by_id={m['id']:m for m in modules}
    if set(NODES)!=set(by_id):
        raise ValueError(f'Diagnostic graph/module mismatch: {set(NODES)^set(by_id)}')
    frame=[
        _rect(15,60,1495,1370,'#fbfcff','#e0e5ed',20),
        _text(34,87,'SoC Platform',17,'#202124',700),
        _text(175,87,'QNX host + Android guest',10,'#738092'),
        _rect(30,110,608,1195,'#eaf1fe','#bfd3f8',17),
        _rect(768,110,730,1195,'#eaf6ed','#c8e5cf',17),
        _rect(1540,110,280,1195,'#fff2e6','#efcbab',17),
        _text(48,140,'QNX Cluster',18,'#1d4e9e',700),
        _text(786,140,'AAOS IVI',18,'#176c3b',700),
        _text(1558,140,'MCU',18,'#99602e',700),
        _text(1630,140,'Reference only',10,'#99602e'),
        _text(655,137,'CROSS-DOMAIN',10,'#526179',700),
        _text(655,152,'DATA FLOW',10,'#526179',700),
    ]
    style={'qnx':(42,584,('#ffffffd9','#d6e1f0')),
           'aaos':(780,706,('#ffffffd9','#d6e8d9')),
           'mcu':(1552,256,('#ffffffd9','#f0dccb'))}
    for domain,layers in LAYERS.items():
        x,w,palette=style[domain]
        for y,h,title in layers:
            if not any(by_id[mid]['domain']==domain and y < ny < ny+nh <= y+h
                       for mid,(_,ny,_,nh) in NODES.items()):
                raise ValueError(f'Empty diagnostic layer: {domain}/{title}')
            frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([
        _layer(30,1313,1468,54,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
        _layer(30,1379,1468,48,'SoC Hardware',('#fff','#dce1e8')),
        _text(240,1410,'CPU · Memory Controller · Ethernet MAC · SPI Controller',11,'#5b6075'),
        _text(1554,1350,'Dashed MCU paths: reference only.',10,'#738092'),
        _text(1554,1370,'DTC peer mapping: unverified.',10,'#738092'),
    ])
    r=Routes()
    # QNX: confirmed SLM services, rpcif dependency, device status and logs.
    r.add('diag-qnx-dtc','diag-qnx-rpcif',[(142,264),(142,390)],flow='spi',both=True,
          label='rpcif',at=(142,328),note='dtcagent links librpcif')
    r.add('diag-qnx-did','diag-qnx-rpcif',[(250,237),(234,237),(234,365),(142,365),(142,390)],
          flow='spi',both=True,note='ecuinfobe links librpcif; DID request and response')
    r.add('diag-qnx-rpcif','diag-qnx-rpcd',[(224,417),(250,417)],flow='spi',both=True,
          note='QNX local RPC client and daemon')
    r.add('diag-qnx-rpcd','diag-qnx-spi',[(332,444),(332,770)],flow='spi',both=True,
          label='local RPC / SPI',at=(332,606))
    r.add('diag-qnx-status','diag-qnx-dtc',[(60,797),(48,797),(48,237),(60,237)],
          flow='dtc',note='QNX device nodes supply fault state')
    r.add('diag-qnx-slog','diag-qnx-log',[(604,797),(620,797),(620,237),(604,237)],
          flow='logs',label='slog2',at=(620,620),note='vlogmanager parses QNX slog2 records')
    # AAOS: independent DoIP/UDS and property-driven diagnostic paths.
    r.add('diag-aaos-service','diag-aaos-dtc',[(970,235),(1010,235)],flow='dtc',
          note='DiagService starts DtcEventHandler')
    r.add('diag-aaos-service','diag-aaos-mcu',[(880,262),(880,290),(1210,290),(1210,235),(1230,235)],
          flow='dtc,spi',note='DiagService starts MCU diagnostic event handler')
    r.add('diag-aaos-dtc','diag-aaos-vehicle',[(1100,262),(1100,338)],flow='dtc',
          label='DTC status',at=(1100,303))
    r.add('diag-aaos-mcu','diag-aaos-vehicle',[(1230,235),(1210,235),(1210,365),(1190,365)],
          flow='spi',both=True,note='MCU routine property events and responses')
    r.add('diag-aaos-vehicle','diag-aaos-vhal',[(1190,365),(1214,365),(1214,669),(1230,669)],
          flow='dtc,spi',both=True,label='IVehicle',at=(1214,604))
    r.add('diag-aaos-devices','diag-aaos-dtc',[(1190,869),(1470,869),(1470,190),(1100,190),(1100,208)],
          flow='dtc',label='fault nodes',at=(1470,750))
    r.add('diag-aaos-doip','diag-aaos-dcm',[(970,529),(1010,529)],flow='doip',both=True,
          note='DoIP server and UDS dispatch')
    r.add('diag-aaos-dcm','diag-aaos-binder',[(1190,529),(1230,529)],flow='doip',both=True,
          note='AIDL callback')
    r.add('diag-aaos-dcm','diag-aaos-uds',[(1010,529),(990,529),(990,669),(970,669)],
          flow='doip',both=True,label='UDS',at=(990,610))
    r.add('diag-aaos-dcm','diag-aaos-doipvehicle',[(1100,556),(1100,642)],flow='doip',both=True,
          note='DoIP context uses Vehicle HAL through DoipVehicleManager')
    r.add('diag-aaos-doipvehicle','diag-aaos-vhal',[(1190,669),(1230,669)],flow='doip',both=True,
          note='Vehicle speed, VIN and power context')
    # Android Vehicle HAL property reaches a QNX DTC peer; the exact bridge mapping is unverified.
    r.add('diag-aaos-vhal','diag-qnx-dtc',[(1410,654),(1458,654),(1458,99),(23,99),(23,237),(60,237)],
          kind='reference',flow='dtc',label='DTC property · peer TBD',at=(712,99),
          note='Android TOPIC_DTC_UPDATE and QNX dtcagent are confirmed; the full peer mapping is not')
    # Vehicle properties from the MCU are confirmed; physical endpoint binding remains a reference.
    r.add('diag-aaos-vhal','diag-mcu-spi-ivi',[(1410,682),(1518,682),(1518,327),(1560,327)],
          kind='reference',flow='spi',label='MCU property · path TBD',at=(1518,600),
          note='Reference SoC/MCU exchange; precise Vehicle HAL-to-SPI task binding unverified')
    # External testers enter either DoIP (Android) or CAN FD (MCU).
    r.add('tester-doip','diag-aaos-doip',[(800,64),(778,64),(778,529),(790,529)],
          flow='doip',label='DoIP / Ethernet',at=(778,450),both=True)
    r.add('tester-can','diag-mcu-canfd',[(1780,64),(1832,64),(1832,827),(1804,827)],
          kind='reference',flow='can',label='CAN FD UDS',at=(1780,980),both=True)
    # Supplied MCU reference: request/response chain and nonvolatile DTC path.
    r.add('diag-mcu-factory','diag-mcu-dcm',[(1560,235),(1536,235),(1536,453),(1560,453)],
          kind='reference',flow='can',both=True,note='FactoryDiag diagnostic requests')
    r.add('diag-mcu-mfg','diag-mcu-dem',[(1748,262),(1748,426)],
          kind='reference',flow='dtc',both=True,note='Manufacturing diagnostic events')
    r.add('diag-mcu-dcm','diag-mcu-dem',[(1672,453),(1692,453)],
          kind='reference',flow='can,dtc',both=True,note='UDS services and diagnostic events')
    r.add('diag-mcu-dcm','diag-mcu-cantp',[(1616,480),(1616,518)],
          kind='reference',flow='can',both=True,note='UDS transport reassembly')
    r.add('diag-mcu-cantp','diag-mcu-canif',[(1672,545),(1692,545)],
          kind='reference',flow='can',both=True,note='CAN transport and interface')
    r.add('diag-mcu-canif','diag-mcu-canfd',[(1804,545),(1818,545),(1818,827),(1804,827)],
          kind='reference',flow='can',both=True,note='CAN FD physical bus interface')
    r.add('diag-mcu-dem','diag-mcu-nvm',[(1692,465),(1682,465),(1682,637),(1672,637)],
          kind='reference',flow='dtc',both=True,note='DTC persistence requests')
    r.add('diag-mcu-nvm','diag-mcu-flash',[(1560,637),(1548,637),(1548,922),(1560,922)],
          kind='reference',flow='dtc',both=True,note='NvM to Flash storage')
    r.add('diag-mcu-spi-ivi','diag-mcu-spi',[(1560,327),(1548,327),(1548,817),(1560,817)],
          kind='reference',flow='spi',both=True,note='IVI SPI task and MCU SPI driver')
    r.add('diag-mcu-spi-ic','diag-mcu-spi',[(1804,327),(1824,327),(1824,780),(1682,780),(1682,836),(1672,836)],
          kind='reference',flow='spi',both=True,note='Cluster SPI task and MCU SPI driver')
    # Matched ports show the same physical link without a misleading line across AAOS.
    spi_note='Matched SPI ports: QNX rpcd ↔ MCU SPI Driver; task mapping is reference-only'
    r.add('diag-qnx-spi','diag-mcu-spi',[(332,824),(332,848)],kind='storage',flow='spi',both=True,note=spi_note)
    r.port('diag-qnx-spi','diag-mcu-spi',332,865,'SPI','spi',spi_note)
    r.add('diag-qnx-spi','diag-mcu-spi',[(1672,836),(1682,836),(1682,982)],kind='storage',flow='spi',both=True,note=spi_note)
    r.port('diag-qnx-spi','diag-mcu-spi',1682,1000,'SPI','spi',spi_note)
    # Independent external endpoints and a small in-diagram key.
    extern=[
        _rect(800,38,180,52,'#fff','#9fceb0',8),
        _text(890,60,'Diagnostic Tester',11,'#273d4c',700,'middle'),
        _text(890,78,'DoIP / Ethernet',10,'#647184',500,'middle'),
        _rect(1580,38,200,52,'#fff','#d7aa83',8),
        _text(1680,60,'Diagnostic Tester',11,'#273d4c',700,'middle'),
        _text(1680,78,'CAN FD / UDS',10,'#647184',500,'middle'),
    ]
    nodes=[]
    for mid,(x,y,w,h) in NODES.items():
        m=by_id[mid]
        name,sub=DISPLAY.get(mid,(m['name'],m['short']))
        fill,stroke={'qnx':('#fff','#91b1ed'),'aaos':('#fff','#9fceb0'),
                     'mcu':('#fffaf5','#d7aa83'),'platform':('#fff','#c8bde6')}[m['domain']]
        dash=' stroke-dasharray="5 4"' if m.get('reference') else ''
        name_size=10 if len(name)>20 else 11 if w>140 else 10
        sub_size=9 if len(sub)>22 else 10
        name_y,sub_y=(16,30) if h<54 else (23,42)
        nodes.append(f'<g class="ota-node" data-sw-module="{escape(mid)}" role="button" tabindex="0" '
                     f'aria-label="{escape(name,quote=True)}" aria-pressed="false"><title>{escape(name)}</title>'
                     +_rect(x,y,w,h,fill,stroke,8,1.4).replace('/>',f'{dash}/>')
                     +_text(x+12,y+name_y,name,name_size,'#1f2e40',700)
                     +_text(x+12,y+sub_y,sub,sub_size,'#647184')+'</g>')
    defs=['<defs>']
    for kind,color in COLORS.items():
        defs.append(f'<marker id="ota-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                    f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(900,'Confirmed flow','call'),(1060,'Status / log','status'),
                         (1210,'SPI link','storage'),(1340,'Reference / TBD','reference')]:
        dash=' stroke-dasharray="4 3"' if kind in ('status','reference') else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{COLORS[kind]}" stroke-width="2"{dash}/>'
                      +_text(x+30,35,title,10,COLORS[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-diag-diagram" id="sw-diag-diagram" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" role="group" '
            f'aria-label="Diagnostic component interaction architecture">'
            '<title>Diagnostic software component interactions</title>'
            '<desc>QNX, Android and reference MCU diagnostic components with UDS, DTC, SPI and DoIP paths.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'DIAGNOSTIC SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+r.render()+''.join(extern)
            +'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
