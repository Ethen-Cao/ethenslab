"""Audio interactions on the same domain/layer grid as the high-level view.

Device control uses matched ports; PCM paths stay below the host/guest frame.
No empty MCU or OS layers are introduced. Coordinates are deterministic so
routing can be checked independently of browser size.
"""
from html import escape
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 1850, 1575
NODES = {
    'audio-client': (70,210,205,64),
    'audio-manager': (315,210,205,64),
    'audio-avas': (550,210,205,64),
    'audio-csd-client': (315,380,205,64),
    'audio-acdb': (70,580,205,64),
    'audio-service': (315,580,205,64),
    'audio-gsl-be': (550,580,205,64),
    'audio-codec': (70,805,205,64),
    'audio-a2b-driver': (70,925,205,64),
    'audio-gpr': (315,925,205,64),
    'audio-pcm-driver': (550,925,205,64),
    'audio-apps': (1020,210,220,64),
    'audio-bt-hfp': (1540,210,220,64),
    'audio-car': (1540,380,220,64),
    'audio-flinger': (1020,490,220,64),
    'audio-policy': (1280,490,220,64),
    'audio-hal': (1020,675,220,64),
    'audio-control': (1540,675,220,64),
    'audio-pal': (1020,835,220,64),
    'audio-agm': (1280,835,220,64),
    'audio-gsl-fe': (1540,835,220,64),
    'audio-hypervisor': (1010,1052,330,48),
    'audio-shmem': (1390,1052,360,48),
    'audio-dsp': (315,1170,490,68),
    'audio-a2b-hw': (70,1380,210,64),
    'audio-amp': (390,1380,230,64),
    'audio-mic': (780,1380,245,64),
    'audio-bt-chip': (1130,1380,245,64),
    'audio-radio': (1480,1380,280,64),
}
LAYERS = {
    'qnx': [(150,145,'Vehicle Domain Services'), (315,425,'Platform Services'), (760,255,'Device Integration & BSP')],
    'aaos': [(150,145,'Applications'), (315,295,'Framework'), (630,385,'Native / HAL')],
}


def make_routes():
    r=Routes()
    r.add('audio-client','audio-manager',[(275,242),(315,242)],flow='chime',both=True,note='Project IPC requests and playback notifications')
    r.add('audio-manager','audio-csd-client',[(417,274),(417,380)],flow='chime',label='CSD2 API',at=(417,344))
    r.add('audio-avas','audio-csd-client',[(652,274),(652,412),(520,412)],kind='reference',flow='chime',label='Document API',at=(652,345))
    r.add('audio-csd-client','audio-service',[(417,444),(417,580)],flow='chime',both=True,label='QNX IPC / buffers',at=(417,514))
    r.add('audio-acdb','audio-service',[(275,612),(315,612)],flow='media,chime,phone,device',note='ACDB graphs, calibration and OEM startup configuration')
    r.add('audio-gsl-be','audio-service',[(550,612),(520,612)],flow='media,phone,policy,radio',both=True,note='GSL graph backend within audio_service runtime')
    r.add('audio-service','audio-gpr',[(417,644),(417,925)],flow='media,chime,phone,policy,radio',both=True,label='DSP requests / buffers',at=(417,720))
    r.add('audio-gpr','audio-dsp',[(417,989),(417,1170)],flow='media,chime,phone,policy,radio',both=True,label='GPR / SPF',at=(417,1100))
    r.add('audio-codec','audio-a2b-driver',[(172,869),(172,925)],flow='device',label='plugin API',at=(172,900))
    r.add('audio-codec','audio-pcm-driver',[(275,837),(780,837),(780,895),(652,895),(652,925)],flow='device',label='plugin API',at=(652,837))
    # Device control is a separate plane from the audio sample buses.
    for driver,device,x,px,label in [('audio-a2b-driver','audio-a2b-hw',172,235,'A2B'),('audio-pcm-driver','audio-mic',652,902,'MIC')]:
        note=f'Matched {label} ports: driver and device exchange register configuration / fault state over I2C and GPIO'
        r.add(driver,device,[(x,989),(x,998)],flow='device',both=True,note=note)
        r.port(driver,device,x,1010,label,'device',note)
        r.port(driver,device,px,1348,label,'device',note)
        r.add(driver,device,[(px,1360),(px,1380)],flow='device',both=True,note=note)
    # Framework policy and PCM use separate columns and separate anchors.
    r.add('audio-apps','audio-flinger',[(1080,274),(1080,490)],kind='install',flow='media',both=True,label='AudioTrack / AudioRecord',at=(1080,426))
    r.add('audio-apps','audio-car',[(1180,274),(1180,348),(1650,348),(1650,380)],flow='policy',label='Focus / zones / volume',at=(1380,348))
    r.add('audio-car','audio-policy',[(1540,412),(1390,412),(1390,490)],flow='policy',label='Audio policy API',at=(1390,460))
    r.add('audio-policy','audio-flinger',[(1280,522),(1240,522)],flow='policy',note='Route and port configuration through AudioFlinger')
    r.add('audio-flinger','audio-hal',[(1130,554),(1130,675)],kind='install',flow='media,radio',both=True,label='HAL stream I/O',at=(1130,605))
    r.add('audio-car','audio-control',[(1650,444),(1650,675)],flow='policy',label='AudioControl AIDL',at=(1650,570))
    r.add('audio-control','audio-hal',[(1540,707),(1240,707)],flow='policy',label='Mute callback',at=(1390,707))
    r.add('audio-bt-hfp','audio-hal',[(1710,274),(1790,274),(1790,770),(1220,770),(1220,739)],flow='phone',label='HFP parameters',at=(1460,770))
    r.add('audio-hal','audio-pal',[(1130,739),(1130,835)],kind='install',flow='media,phone,policy,radio',both=True,label='PAL stream API',at=(1130,806))
    r.add('audio-pal','audio-agm',[(1240,867),(1280,867)],kind='install',flow='media,phone,policy,radio',both=True,note='SessionAgm: session configuration, read/write and events')
    r.add('audio-agm','audio-gsl-fe',[(1500,867),(1540,867)],kind='install',flow='media,phone,policy,radio',both=True,note='AGM graph.c: gsl_open, gsl_ioctl, read/write')
    r.add('audio-gsl-fe','audio-gsl-be',[(1650,899),(1650,965),(870,965),(870,612),(755,612)],kind='storage',flow='media,phone,policy,radio',both=True,label='HAB',at=(870,752),note='Commands, replies and events; audio buffers shared using habmm_import/export')
    # Hardware paths reflect audio direction, not generic bus bidirectionality.
    r.add('audio-dsp','audio-a2b-hw',[(475,1238),(475,1300),(175,1300),(175,1380)],kind='install',flow='media,chime,phone,radio',label='TDM playback',at=(325,1300))
    r.add('audio-a2b-hw','audio-amp',[(280,1412),(390,1412)],kind='install',flow='media,chime,phone,radio',label='A2B PCM',at=(335,1412))
    r.add('audio-mic','audio-dsp',[(850,1380),(850,1318),(670,1318),(670,1238)],kind='install',flow='media,phone',label='TDM capture',at=(750,1318))
    r.add('audio-bt-chip','audio-dsp',[(1252,1380),(1252,1204),(805,1204)],kind='install',flow='phone',both=True,label='I2S call audio',at=(1080,1204))
    # The radio path is documented, but project USB/radio HAL integration remains unverified.
    note='Matched RADIO ports: documented FM/DAB USB input to Android audio framework; project implementation not fully verified'
    r.port('audio-radio','audio-flinger',985,522,'RADIO','radio',note)
    r.add('audio-radio','audio-flinger',[(1011,522),(1020,522)],kind='reference',flow='radio',note=note)
    r.port('audio-radio','audio-flinger',1620,1348,'RADIO','radio',note)
    r.add('audio-radio','audio-flinger',[(1620,1380),(1620,1360)],kind='reference',flow='radio',note=note)
    # Reference ports use the same brown visual cue as their reference route.
    for i,s in enumerate(r.ports):
        if 'RADIO' not in s:
            r.ports[i]=s.replace(COLORS['storage'],COLORS['call']).replace('#f5f1ff','#f1f6ff')
        else:
            r.ports[i]=s.replace(COLORS['storage'],COLORS['reference']).replace('#f5f1ff','#fff8f1')
    return r


def render_graph(modules):
    by_id={m['id']:m for m in modules}
    if set(NODES)!=set(by_id):
        raise ValueError(f'Audio graph/module mismatch: {set(NODES)^set(by_id)}')
    frame=[_rect(15,60,1820,1270,'#fbfcff','#e0e5ed',20),
           _text(34,88,'SoC Platform',17,'#202124',700),
           _text(175,88,'QNX host + Android guest',11,'#738092'),
           _rect(30,110,770,916,'#eaf1fe','#bfd3f8',17),
           _rect(970,110,850,916,'#eaf6ed','#c8e5cf',17),
           _text(50,140,'QNX Cluster',19,'#1d4e9e',700),
           _text(990,140,'AAOS IVI',19,'#176c3b',700),
           _text(885,385,'CROSS-DOMAIN',10,'#526179',700,'middle'),
           _text(885,403,'AUDIO',10,'#526179',700,'middle')]
    styles={'qnx':(42,746,('#ffffffd9','#d6e1f0')),'aaos':(982,826,('#ffffffd9','#d6e8d9'))}
    for domain,layers in LAYERS.items():
        x,w,palette=styles[domain]
        for y,h,title in layers:
            if not any(by_id[mid]['domain']==domain and y<ny<ny+nh<=y+h for mid,(_,ny,_,nh) in NODES.items()):
                raise ValueError(f'Empty Audio layer: {domain}/{title}')
            frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([_layer(30,1036,1790,78,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
                  _layer(30,1130,1790,138,'ADSP Firmware',('#fff8e5','#ead8a6')),
                  _layer(30,1280,1790,42,'SoC Hardware',('#fff','#dce1e8')),
                  _text(1410,1306,'ADSP · LPASS · Memory controllers',12,'#647184'),
                  _layer(30,1340,1790,142,'Audio Devices',('#fff','#dce1e8')),
                  _text(50,1521,'A2B / MIC / RADIO: matching ports identify the same connection.',12,'#647184'),
                  _text(50,1546,'MCU amplifier-control mapping and ECNS activation are not verified.',12,'#647184')])
    nodes=[]
    for mid,(x,y,w,h) in NODES.items():
        m=by_id[mid]
        fill,stroke={'qnx':('#fff','#91b1ed'),'aaos':('#fff','#9fceb0'),'platform':('#fff','#c8bde6'),'dsp':('#fff','#dfbd61'),'hardware':('#fff','#b8c3d1')}[m['domain']]
        dash=' stroke-dasharray="5 4"' if m.get('reference') else ''
        if m.get('reference'): stroke='#b59075'
        ny,sy=(19,36) if h<54 else (26,47)
        nodes.append(f'<g class="ota-node" data-sw-module="{mid}" role="button" tabindex="0" aria-label="{escape(m["name"],quote=True)}" aria-pressed="false"><title>{escape(m["name"])}</title>'
                     +_rect(x,y,w,h,fill,stroke,8,1.4).replace('/>',f'{dash}/>')
                     +_text(x+12,y+ny,m['name'],13,'#1f2e40',700)
                     +_text(x+12,y+sy,m['short'],10.5,'#647184')+'</g>')
    defs=['<defs>']
    for kind,color in COLORS.items():
        defs.append(f'<marker id="audio-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(1000,'Control / reply','call'),(1200,'Audio / stream API','install'),(1430,'HAB transport','storage'),(1620,'Document reference','reference')]:
        dash=' stroke-dasharray="4 3"' if kind=='reference' else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{COLORS[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,11,COLORS[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-audio-diagram" id="sw-audio-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, sans-serif" role="group" aria-label="Audio software component interactions">'
            '<title>Audio software component interactions</title><desc>QNX and AAOS audio services, HAB transport, DSP audio paths and device control. Brown dashed paths are document references.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'AUDIO SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+make_routes().render().replace('url(#ota-arrow-','url(#audio-arrow-')
            +'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
