"""Interactive diagnostic graph using the same domain frame and routing language as OTA."""
from html import escape
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 2160, 1308
# Columns follow dependencies: QNX RPC and logging, AAOS handlers and DoIP,
# MCU UDS / event storage / two SoC message tasks.
NODES = {
    'diag-qnx-dtc':(62,240,140,64), 'diag-qnx-did':(222,240,140,64),
    'diag-qnx-log':(382,240,140,64), 'diag-qnx-rpcif':(222,420,140,64),
    'diag-qnx-rpcd':(222,560,140,64),
    'diag-qnx-status':(62,800,140,64), 'diag-qnx-spi':(222,800,140,64),
    'diag-qnx-slog':(382,800,140,64), 'diag-qnx-os':(62,1036,460,64),
    'diag-aaos-service':(870,240,185,64),
    'diag-aaos-dtc':(650,360,185,64), 'diag-aaos-mcu':(1090,360,185,64),
    'diag-aaos-vehicle':(870,480,185,64),
    'diag-aaos-doip':(650,632,185,64), 'diag-aaos-dcm':(650,752,185,64),
    'diag-aaos-binder':(870,752,185,64), 'diag-aaos-uds':(650,872,185,64),
    'diag-aaos-doipvehicle':(870,872,185,64), 'diag-aaos-vhal':(1090,872,185,64),
    'diag-aaos-devices':(650,1036,185,64),
    'diag-mcu-factory':(1430,254,150,64), 'diag-mcu-mfg':(1606,254,150,64),
    'diag-mcu-spi-ic':(1782,254,150,64), 'diag-mcu-spi-ivi':(1958,254,150,64),
    'diag-mcu-dcm':(1430,424,150,64), 'diag-mcu-dem':(1606,424,150,64),
    'diag-mcu-cantp':(1430,540,150,64), 'diag-mcu-canif':(1430,650,150,64),
    'diag-mcu-nvm':(1606,650,150,64),
    'diag-mcu-rtos':(1782,486,150,64), 'diag-mcu-cdd':(1958,486,150,64),
    'diag-mcu-canfd':(1430,806,150,64), 'diag-mcu-flash':(1606,806,150,64),
    'diag-mcu-spi':(1782,806,326,64),
    'diag-mcu-boot':(1438,1004,668,38), 'diag-mcu-hw':(1438,1094,668,38),
    'diag-vm-isolation':(226,1184,508,42), 'diag-vdev-net':(758,1184,538,42),
}
LAYERS = {
    'qnx':[(180,550,'Platform Services'),(750,222,'Device Integration & BSP'),
           (992,152,'QNX Neutrino Core')],
    'aaos':[(180,400,'Applications'),(600,372,'Native Services & HAL'),
            (992,152,'Android OS')],
    'mcu':[(180,170,'Applications'),(370,368,'BSW & RTOS'),
           (758,194,'Drivers'),(972,78,'Bootloader'),(1062,78,'Hardware')],
}
DISPLAY = {
    'diag-aaos-uds':('UDS / DoIP Stack','libvoyuds · libvoydoip'),
    'diag-qnx-spi':('SPI I/O','Board-level link'),
    'diag-qnx-status':('Device Status I/O','Thermal · AV state'),
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
        _rect(15,60,1320,1233,'#fbfcff','#e0e5ed',20),
        _text(34,88,'SoC Platform',17,'#202124',700),
        _text(174,88,'QNX host + Android guest',11,'#738092'),
        _rect(30,110,520,1048,'#eaf1fe','#bfd3f8',17),
        _rect(620,110,700,1048,'#eaf6ed','#c8e5cf',17),
        _rect(1410,110,720,1048,'#fff2e6','#efcbab',17),
        _text(50,143,'QNX Cluster',19,'#1d4e9e',700),
        _text(640,143,'AAOS IVI',19,'#176c3b',700),
        _text(1430,143,'MCU',19,'#99602e',700),
        _text(2110,143,'Reference architecture',11,'#99602e',500,'end'),
    ]
    style={'qnx':(42,496,('#ffffffd9','#d6e1f0')),
           'aaos':(632,676,('#ffffffd9','#d6e8d9')),
           'mcu':(1422,696,('#ffffffd9','#f0dccb'))}
    for domain,layers in LAYERS.items():
        x,w,palette=style[domain]
        for y,h,title in layers:
            if not any(by_id[mid]['domain']==domain and y < ny < ny+nh <= y+h
                       for mid,(_,ny,_,nh) in NODES.items()):
                raise ValueError(f'Empty diagnostic layer: {domain}/{title}')
            frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([
        _layer(30,1174,1290,62,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
        _layer(30,1248,1290,42,'SoC Hardware',('#fff','#dce1e8')),
        _text(226,1274,'CPU · Memory Controller · Ethernet MAC · SPI Controller',12,'#5b6075'),
        _text(1430,1204,'Matching DTC / SPI ports connect the same endpoints.',12,'#647184'),
        _text(1430,1230,'Dashed brown paths: MCU reference or unverified peer mapping.',12,'#647184'),
        _text(1430,1256,'Select a component to trace its immediate dependencies.',12,'#647184'),
    ])
    r=Routes()
    # QNX: the RPC dependency chain occupies one column; log and status
    # sources stay in their own columns instead of circling the whole domain.
    r.add('diag-qnx-dtc','diag-qnx-rpcif',[(170,304),(170,376),(268,376),(268,420)],
          flow='spi',both=True,note='dtcagent links librpcif')
    r.add('diag-qnx-did','diag-qnx-rpcif',[(292,304),(292,420)],
          flow='spi',both=True,label='RPC API',at=(292,347),
          note='ecuinfobe links librpcif; DID request and response')
    r.add('diag-qnx-rpcif','diag-qnx-rpcd',[(292,484),(292,560)],flow='spi',both=True,
          label='local IPC',at=(292,526),note='QNX local RPC client and daemon')
    r.add('diag-qnx-rpcd','diag-qnx-spi',[(292,624),(292,800)],flow='spi',both=True,
          label='SPI I/O',at=(292,714))
    r.add('diag-qnx-status','diag-qnx-dtc',[(62,832),(50,832),(50,272),(62,272)],
          kind='status',flow='dtc',note='QNX device nodes supply fault state')
    r.add('diag-qnx-slog','diag-qnx-log',[(452,800),(452,304)],
          kind='status',flow='logs',label='slog2 records',at=(452,630),
          note='vlogmanager parses QNX slog2 records')
    # AAOS: service -> handlers -> common property API forms a clear tree.
    r.add('diag-aaos-service','diag-aaos-dtc',[(934,304),(934,332),(742,332),(742,360)],
          flow='dtc',note='DiagService starts DtcEventHandler')
    r.add('diag-aaos-service','diag-aaos-mcu',[(990,304),(990,332),(1182,332),(1182,360)],
          flow='dtc,spi',note='DiagService starts MCU diagnostic event handler')
    r.add('diag-aaos-dtc','diag-aaos-vehicle',[(742,424),(742,452),(934,452),(934,480)],
          flow='dtc',label='DTC status',at=(820,452))
    r.add('diag-aaos-mcu','diag-aaos-vehicle',[(1182,424),(1182,452),(990,452),(990,480)],
          flow='spi',both=True,label='MCU events',at=(1106,452))
    r.add('diag-aaos-vehicle','diag-aaos-vhal',[(1055,512),(1294,512),(1294,904),(1275,904)],
          flow='dtc,spi',both=True,label='IVehicle',at=(1294,578))
    r.add('diag-aaos-devices','diag-aaos-dtc',[(650,1068),(640,1068),(640,392),(650,392)],
          kind='status',flow='dtc',note='Android device fault nodes sampled by DtcEventHandler')
    # The native DoIP stack is a vertical chain; its two clients sit to its right.
    r.add('diag-aaos-doip','diag-aaos-dcm',[(742,696),(742,752)],flow='doip',both=True,
          note='DoIP server initializes diagnostic service dispatch')
    r.add('diag-aaos-dcm','diag-aaos-binder',[(835,784),(870,784)],flow='doip',both=True,
          note='DoIP service invokes registered AIDL client callbacks')
    r.add('diag-aaos-dcm','diag-aaos-uds',[(714,816),(714,872)],flow='doip',both=True,
          note='UDS service registration and transport')
    r.add('diag-aaos-dcm','diag-aaos-doipvehicle',[(770,816),(770,844),(962,844),(962,872)],
          flow='doip',both=True,label='vehicle context',at=(886,844),
          note='DoIP context uses Vehicle HAL through DoipVehicleManager')
    r.add('diag-aaos-doipvehicle','diag-aaos-vhal',[(1055,904),(1090,904)],flow='doip',both=True,
          note='Vehicle speed, VIN and power context')
    # Paired endpoints express the uncertain DTC peer mapping without an
    # outer-border wire spanning both domains and crossing every layer.
    dtc_note='Paired DTC endpoints: Android Vehicle HAL -> QNX dtcagent; intermediate mapping unverified'
    r.add('diag-aaos-vhal','diag-qnx-dtc',[(94,334),(94,304)],
          kind='reference',flow='dtc',note=dtc_note)
    r.port('diag-aaos-vhal','diag-qnx-dtc',94,350,'DTC','dtc',dtc_note)
    r.ports[-1]=r.ports[-1].replace(COLORS['storage'],COLORS['reference']).replace('#f5f1ff','#fff8f1')
    r.add('diag-aaos-vhal','diag-qnx-dtc',[(1182,936),(1182,952)],
          kind='reference',flow='dtc',note=dtc_note)
    r.port('diag-aaos-vhal','diag-qnx-dtc',1182,968,'DTC','dtc',dtc_note)
    r.ports[-1]=r.ports[-1].replace(COLORS['storage'],COLORS['reference']).replace('#f5f1ff','#fff8f1')
    r.add('diag-aaos-vhal','diag-mcu-spi-ivi',[(1275,924),(1362,924),(1362,222),(2033,222),(2033,254)],
          kind='reference',flow='spi',both=True,label='MCU property · mapping TBD',at=(1662,222),
          note='Reference SoC/MCU exchange; precise Vehicle HAL-to-SPI task binding unverified')
    # External diagnostic ingress has its own gutter outside each domain.
    r.add('tester-doip','diag-aaos-doip',[(650,70),(608,70),(608,664),(650,664)],
          flow='doip',label='DoIP / Ethernet',at=(608,580),both=True)
    r.add('tester-can','diag-mcu-canfd',[(1430,70),(1390,70),(1390,838),(1430,838)],
          kind='reference',flow='can',label='CAN FD',at=(1390,734),both=True)
    # MCU columns read top to bottom: UDS transport, DTC persistence,
    # and the two message tasks converging on their shared SPI driver.
    r.add('diag-mcu-factory','diag-mcu-dcm',[(1540,318),(1540,424)],
          kind='reference',flow='can',both=True,note='FactoryDiag diagnostic requests')
    r.add('diag-mcu-mfg','diag-mcu-dem',[(1681,318),(1681,424)],
          kind='reference',flow='dtc',both=True,note='Manufacturing diagnostic events')
    r.add('diag-mcu-dcm','diag-mcu-dem',[(1580,456),(1606,456)],
          kind='reference',flow='can,dtc',both=True,note='UDS services and diagnostic events')
    r.add('diag-mcu-dcm','diag-mcu-cantp',[(1505,488),(1505,540)],
          kind='reference',flow='can',both=True,note='UDS transport reassembly')
    r.add('diag-mcu-cantp','diag-mcu-canif',[(1505,604),(1505,650)],
          kind='reference',flow='can',both=True,note='CAN transport and interface')
    r.add('diag-mcu-canif','diag-mcu-canfd',[(1505,714),(1505,806)],
          kind='reference',flow='can',both=True,note='CAN FD physical bus interface')
    r.add('diag-mcu-dem','diag-mcu-nvm',[(1681,488),(1681,650)],
          kind='reference',flow='dtc',both=True,label='DTC records',at=(1681,584))
    r.add('diag-mcu-nvm','diag-mcu-flash',[(1681,714),(1681,806)],
          kind='reference',flow='dtc',both=True,note='NvM to Flash storage')
    r.add('diag-mcu-spi-ic','diag-mcu-spi',[(1857,318),(1857,344),(1945,344),(1945,806)],
          kind='reference',flow='spi',both=True,note='Cluster SPI task and MCU SPI driver')
    r.add('diag-mcu-spi-ivi','diag-mcu-spi',[(2033,318),(2033,344),(1945,344),(1945,806)],
          kind='reference',flow='spi',both=True,label='SPI task I/O',at=(1945,664),
          note='IVI SPI task and MCU SPI driver')
    spi_note='Matched SPI ports: QNX rpcd <-> MCU SPI Driver; task mapping is reference-only'
    r.add('diag-qnx-spi','diag-mcu-spi',[(292,864),(292,900)],kind='storage',flow='spi',both=True,note=spi_note)
    r.port('diag-qnx-spi','diag-mcu-spi',292,916,'SPI','spi',spi_note)
    r.add('diag-qnx-spi','diag-mcu-spi',[(1945,902),(1945,870)],kind='storage',flow='spi',both=True,note=spi_note)
    r.port('diag-qnx-spi','diag-mcu-spi',1945,918,'SPI','spi',spi_note)
    extern=[
        _rect(650,44,185,52,'#fff','#9fceb0',8),
        _text(742,66,'Diagnostic Tester',12,'#273d4c',700,'middle'),
        _text(742,84,'DoIP / Ethernet',11,'#647184',500,'middle'),
        _rect(1430,44,185,52,'#fff','#d7aa83',8),
        _text(1522,66,'Diagnostic Tester',12,'#273d4c',700,'middle'),
        _text(1522,84,'CAN FD / UDS',11,'#647184',500,'middle'),
    ]
    nodes=[]
    for mid,(x,y,w,h) in NODES.items():
        m=by_id[mid]
        name,sub=DISPLAY.get(mid,(m['name'],m['short']))
        fill,stroke={'qnx':('#fff','#91b1ed'),'aaos':('#fff','#9fceb0'),
                     'mcu':('#fffaf5','#d7aa83'),'platform':('#fff','#c8bde6')}[m['domain']]
        dash=' stroke-dasharray="5 4"' if m.get('reference') else ''
        name_size=12 if w>=150 else 11.5
        sub_size=10.5 if w>=150 else 10
        name_y,sub_y=(16,31) if h<54 else (26,46)
        nodes.append(f'<g class="ota-node" data-sw-module="{escape(mid)}" role="button" tabindex="0" '
                     f'aria-label="{escape(name,quote=True)}" aria-pressed="false"><title>{escape(name)}</title>'
                     +_rect(x,y,w,h,fill,stroke,8,1.4).replace('/>',f'{dash}/>')
                     +_text(x+12,y+name_y,name,name_size,'#1f2e40',700)
                     +_text(x+12,y+sub_y,sub,sub_size,'#647184')+'</g>')
    defs=['<defs>']
    for kind,color in COLORS.items():
        defs.append(f'<marker id="diag-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                    f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(1400,'Service call / exchange','call'),(1620,'Status / log','status'),
                         (1780,'SPI link','storage'),(1910,'Reference / TBD','reference')]:
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
            +''.join(legend)+''.join(frame)+r.render().replace('url(#ota-arrow-','url(#diag-arrow-')+''.join(extern)
            +'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
