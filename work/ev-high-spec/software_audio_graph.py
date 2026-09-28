"""Audio dependencies on an explicit execution-domain and software-layer grid.

HFP has separate Bluetooth protocol and AudioManager parameter paths.
The HFP extension is inside the Audio HAL implementation boundary. HCI
controller commands and I2S speech samples terminate on different ports.
"""
from html import escape
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 2250, 1930
NODES = {
    'audio-client': (70,210,205,64),
    'audio-manager': (315,210,205,64),
    'audio-avas': (550,210,205,64),
    'audio-csd-client': (315,380,205,64),
    'audio-acdb': (70,680,205,64),
    'audio-service': (315,680,205,64),
    'audio-gsl-be': (550,680,205,64),
    'audio-codec': (70,1005,205,64),
    'audio-a2b-driver': (70,1200,205,64),
    'audio-gpr': (315,1200,205,64),
    'audio-pcm-driver': (550,1200,205,64),
    'audio-apps': (1020,210,740,64),
    'audio-audio-manager': (1280,380,220,64),
    'audio-car': (1540,380,220,64),
    'audio-bt-hfp': (1900,380,260,64),
    'audio-framework-system': (1280,540,220,64),
    'audio-flinger': (1020,700,220,64),
    'audio-policy': (1540,700,220,64),
    'audio-bt-jni': (1900,540,260,64),
    'audio-bt-stack': (1900,700,260,64),
    'audio-hal': (1020,1020,220,64),
    'audio-hfp-ext': (1280,1020,220,64),
    'audio-control': (1540,1020,220,64),
    'audio-bt-hal': (1900,1020,260,64),
    'audio-pal': (1020,1200,220,64),
    'audio-agm': (1280,1200,220,64),
    'audio-gsl-fe': (1540,1200,220,64),
    'audio-hypervisor': (1010,1435,330,48),
    'audio-shmem': (1390,1435,360,48),
    'audio-dsp': (315,1555,490,68),
    'audio-a2b-hw': (70,1770,210,64),
    'audio-amp': (390,1770,230,64),
    'audio-mic': (780,1770,245,64),
    'audio-radio': (1480,1770,280,64),
    'audio-bt-chip': (1900,1770,260,64),
}
LAYERS = {
    'qnx': [(150,145,'Vehicle Domain Services'), (315,610,'Platform Services'),
            (945,450,'Device Integration & BSP')],
    'aaos': [(150,145,'Applications'), (315,150,'Framework / System Services'),
             (485,410,'Native Services & Libraries'), (915,480,'Native / HAL')],
}
# These are implementation subcomponents, not separate HAL services.
AUDIO_HAL_CONTAINER = (1005,970,510,145)
LAYER_MEMBERS = {
    'Framework / System Services': ['audio-bt-hfp','audio-audio-manager','audio-car'],
    'Native Services & Libraries': ['audio-framework-system','audio-flinger','audio-policy','audio-bt-jni','audio-bt-stack'],
    'Native / HAL': ['audio-hal','audio-hfp-ext','audio-control','audio-bt-hal','audio-pal','audio-agm','audio-gsl-fe'],
}


def make_routes():
    r=Routes()
    r.add('audio-client','audio-manager',[(275,242),(315,242)],flow='chime',both=True,note='Project IPC requests and playback notifications')
    r.add('audio-manager','audio-csd-client',[(417,274),(417,380)],flow='chime',label='CSD2 API',at=(417,344))
    r.add('audio-avas','audio-csd-client',[(652,274),(652,412),(520,412)],kind='reference',flow='chime',label='Document API',at=(652,345))
    r.add('audio-csd-client','audio-service',[(417,444),(417,680)],flow='chime',both=True,label='QNX IPC / buffers',at=(417,550))
    r.add('audio-acdb','audio-service',[(275,712),(315,712)],flow='media,chime,phone,device',note='ACDB graphs, calibration and OEM startup configuration')
    r.add('audio-gsl-be','audio-service',[(550,712),(520,712)],flow='media,phone,policy,radio',both=True,note='GSL graph backend within audio_service runtime')
    r.add('audio-service','audio-gpr',[(417,744),(417,1200)],flow='media,chime,phone,policy,radio',both=True,label='DSP requests / buffers',at=(417,880))
    r.add('audio-gpr','audio-dsp',[(417,1264),(417,1555)],flow='media,chime,phone,policy,radio',both=True,label='GPR / SPF',at=(417,1480))
    r.add('audio-codec','audio-a2b-driver',[(172,1069),(172,1200)],flow='device',label='plugin API',at=(172,1145))
    r.add('audio-codec','audio-pcm-driver',[(275,1037),(780,1037),(780,1135),(652,1135),(652,1200)],flow='device',label='plugin API',at=(652,1037))
    for driver,device,x,px,label in [('audio-a2b-driver','audio-a2b-hw',172,235,'A2B'),('audio-pcm-driver','audio-mic',652,902,'MIC')]:
        note=f'Matched {label} ports: driver and device exchange register configuration / fault state over I2C and GPIO'
        r.add(driver,device,[(x,1264),(x,1308)],flow='device',both=True,note=note)
        r.port(driver,device,x,1320,label,'device',note)
        r.port(driver,device,px,1738,label,'device',note)
        r.add(driver,device,[(px,1750),(px,1770)],flow='device',both=True,note=note)
    # HFP protocol path: Java service -> JNI/profile adapter -> native stack -> HCI HAL.
    r.add('audio-bt-hfp','audio-bt-jni',[(2030,444),(2030,540)],flow='phone',both=True,label='JNI / callbacks',at=(2030,505))
    r.add('audio-bt-jni','audio-bt-stack',[(2030,604),(2030,700)],flow='phone',both=True,label='HFP profile API',at=(2030,656))
    r.add('audio-bt-stack','audio-bt-hal',[(2030,764),(2030,1020)],flow='phone',both=True,label='HCI commands / events',at=(2030,860))
    r.add('audio-bt-hal','audio-bt-chip',[(2030,1084),(2030,1770)],flow='phone',both=True,label='HCI / vendor transport',at=(2030,1345),note='Controller command/event path; physical UART/USB binding and deployed HAL version are not expanded')
    # HFP local audio parameters: there is no Bluetooth HCI HAL -> Audio HAL arrow.
    r.add('audio-bt-hfp','audio-audio-manager',[(1900,412),(1850,412),(1850,358),(1390,358),(1390,380)],flow='phone',label='HFP enable / rate / volume',at=(1740,358))
    r.add('audio-audio-manager','audio-framework-system',[(1390,444),(1390,540)],flow='phone',label='AudioSystem JNI',at=(1390,505))
    r.add('audio-framework-system','audio-flinger',[(1390,604),(1390,654),(1130,654),(1130,700)],flow='phone',label='Binder: setParameters',at=(1280,654))
    r.add('audio-flinger','audio-hal',[(1180,764),(1180,980),(1130,980),(1130,1020)],flow='phone,policy',label='HAL setParameters',at=(1180,890))
    r.add('audio-hal','audio-hfp-ext',[(1240,1052),(1280,1052)],flow='phone',note='AudioDevice -> AudioExtn -> libhfp_pal::hfp_set_parameters')
    r.add('audio-hfp-ext','audio-pal',[(1390,1084),(1390,1155),(1200,1155),(1200,1200)],flow='phone',label='PAL HFP RX / TX',at=(1300,1155),note='pal_stream_open/start/stop/close; HFP RX and TX loopback streams and volume')
    # Media PCM and automotive policy follow their own anchors and channels.
    r.add('audio-apps','audio-flinger',[(1195,274),(1195,620),(1080,620),(1080,700)],kind='install',flow='media',both=True,label='AudioTrack / AudioRecord',at=(1195,570))
    r.add('audio-apps','audio-car',[(1220,274),(1220,330),(1650,330),(1650,380)],flow='policy',label='Car audio API',at=(1490,330))
    r.add('audio-car','audio-policy',[(1650,444),(1650,700)],flow='policy',label='Policy configuration',at=(1650,610))
    r.add('audio-policy','audio-flinger',[(1540,732),(1240,732)],flow='policy',label='Route / port gain',at=(1390,732))
    r.add('audio-car','audio-control',[(1760,412),(1820,412),(1820,1052),(1760,1052)],flow='policy',label='AudioControl AIDL',at=(1820,860))
    r.add('audio-control','audio-hal',[(1650,1020),(1650,950),(1200,950),(1200,1020)],flow='policy',label='Mute callback',at=(1450,950))
    r.add('audio-flinger','audio-hal',[(1080,764),(1080,1020)],kind='install',flow='media,radio',both=True,label='HAL stream I/O',at=(1080,825))
    r.add('audio-hal','audio-pal',[(1130,1084),(1130,1200)],kind='install',flow='media,policy,radio',both=True,label='PAL stream API',at=(1130,1178))
    r.add('audio-pal','audio-agm',[(1240,1232),(1280,1232)],kind='install',flow='media,phone,policy,radio',both=True,note='SessionAgm: session configuration, read/write and events')
    r.add('audio-agm','audio-gsl-fe',[(1500,1232),(1540,1232)],kind='install',flow='media,phone,policy,radio',both=True,note='AGM graph.c: gsl_open, gsl_ioctl, read/write')
    r.add('audio-gsl-fe','audio-gsl-be',[(1650,1264),(1650,1370),(870,1370),(870,712),(755,712)],kind='storage',flow='media,phone,policy,radio',both=True,label='HAB',at=(870,1000),note='Commands, replies and events; audio buffers shared using habmm_import/export')
    # I2S is a data path between the controller and DSP, independent of the HCI control branch.
    r.add('audio-dsp','audio-a2b-hw',[(475,1623),(475,1685),(175,1685),(175,1770)],kind='install',flow='media,chime,phone,radio',label='TDM playback',at=(325,1685))
    r.add('audio-a2b-hw','audio-amp',[(280,1802),(390,1802)],kind='install',flow='media,chime,phone,radio',label='A2B PCM',at=(335,1802))
    r.add('audio-mic','audio-dsp',[(850,1770),(850,1700),(670,1700),(670,1623)],kind='install',flow='media,phone',label='TDM capture',at=(750,1700))
    r.add('audio-bt-chip','audio-dsp',[(1900,1802),(1830,1802),(1830,1589),(805,1589)],kind='install',flow='phone',both=True,label='I2S call audio: uplink / downlink',at=(1400,1589))
    note='Matched RADIO ports: documented FM/DAB USB input to Android audio framework; project implementation not fully verified'
    r.port('audio-radio','audio-flinger',985,732,'RADIO','radio',note)
    r.add('audio-radio','audio-flinger',[(1011,732),(1020,732)],kind='reference',flow='radio',note=note)
    r.port('audio-radio','audio-flinger',1620,1738,'RADIO','radio',note)
    r.add('audio-radio','audio-flinger',[(1620,1770),(1620,1750)],kind='reference',flow='radio',note=note)
    for i,s in enumerate(r.ports):
        if 'RADIO' not in s:
            r.ports[i]=s.replace(COLORS['storage'],COLORS['call']).replace('#f5f1ff','#f1f6ff')
        else:
            r.ports[i]=s.replace(COLORS['storage'],COLORS['reference']).replace('#f5f1ff','#fff8f1')
    return r


def validate_layers(modules):
    by_id={m['id']:m for m in modules}
    if set(NODES)!=set(by_id):
        raise ValueError(f'Audio graph/module mismatch: {set(NODES)^set(by_id)}')
    for mid,(_,ny,_,nh) in NODES.items():
        domain=by_id[mid]['domain']
        if domain not in LAYERS: continue
        owners=[title for y,h,title in LAYERS[domain] if y<ny and ny+nh<=y+h]
        if len(owners)!=1: raise ValueError(f'{mid} must belong to exactly one layer: {owners}')
        expected=next((layer for layer,members in LAYER_MEMBERS.items() if mid in members),None)
        if expected and owners!=[expected]: raise ValueError(f'{mid} is outside {expected}')
    x,y,w,h=AUDIO_HAL_CONTAINER
    for mid in ['audio-hal','audio-hfp-ext']:
        nx,ny,nw,nh=NODES[mid]
        if not (x<nx and y<ny and nx+nw<x+w and ny+nh<y+h):
            raise ValueError(f'{mid} must be inside Audio HAL Implementation')


def render_graph(modules):
    validate_layers(modules)
    by_id={m['id']:m for m in modules}
    frame=[_rect(15,60,2220,1655,'#fbfcff','#e0e5ed',20),
           _text(34,88,'SoC Platform',17,'#202124',700),
           _text(175,88,'QNX host + Android guest',11,'#738092'),
           _rect(30,110,770,1297,'#eaf1fe','#bfd3f8',17),
           _rect(970,110,1250,1297,'#eaf6ed','#c8e5cf',17),
           _text(50,140,'QNX Cluster',19,'#1d4e9e',700),
           _text(990,140,'AAOS IVI',19,'#176c3b',700),
           _text(885,385,'CROSS-DOMAIN',10,'#526179',700,'middle'),
           _text(885,403,'AUDIO',10,'#526179',700,'middle')]
    styles={'qnx':(42,746,('#ffffffd9','#d6e1f0')),'aaos':(982,1226,('#ffffffd9','#d6e8d9'))}
    for domain,layers in LAYERS.items():
        x,w,palette=styles[domain]
        for y,h,title in layers:
            if not any(by_id[mid]['domain']==domain and y<ny<ny+nh<=y+h for mid,(_,ny,_,nh) in NODES.items()):
                raise ValueError(f'Empty Audio layer: {domain}/{title}')
            frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([
        '<g class="audio-implementation" data-container="Audio HAL Implementation">'
        +_rect(*AUDIO_HAL_CONTAINER,'#f1f7f2','#bdd8c4',10)
        +_text(1280,996,'Audio HAL Implementation',12,'#366547',700)+'</g>',
        _layer(30,1415,2190,82,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
        _layer(30,1515,2190,140,'ADSP Firmware',('#fff8e5','#ead8a6')),
        _layer(30,1665,2190,42,'SoC Hardware',('#fff','#dce1e8')),
        _text(1330,1691,'ADSP · LPASS · Memory controllers',12,'#647184'),
        _layer(30,1725,2190,142,'Audio Devices',('#fff','#dce1e8')),
        _text(50,1894,'A2B / MIC / RADIO: matching ports identify the same connection.',12,'#647184'),
        _text(50,1916,'HCI control and I2S call audio are separate paths. MCU amplifier-control mapping and ECNS activation are not verified.',12,'#647184')])
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
    for x,title,kind in [(1250,'Control / reply','call'),(1470,'Audio / stream API','install'),(1710,'HAB transport','storage'),(1920,'Document reference','reference')]:
        dash=' stroke-dasharray="4 3"' if kind=='reference' else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{COLORS[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,11,COLORS[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-audio-diagram" id="sw-audio-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, sans-serif" role="group" aria-label="Audio software component interactions">'
            '<title>Audio software component interactions</title><desc>QNX and AAOS audio services, Bluetooth HFP protocol and local audio control branches, HAB transport, DSP audio and device control. Brown dashed paths are document references.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'AUDIO SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+make_routes().render().replace('url(#ota-arrow-','url(#audio-arrow-')
            +'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
