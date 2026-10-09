"""HQX/QNX display services, Android WFD frontend and shared scanout resources."""
from html import escape
import re
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 2040, 1730
NODES = {
    'display-cluster': (350,195,270,70),
    'display-qnx-render': (350,335,270,70),
    'display-screen': (350,445,270,70),
    'display-wfd-be': (660,445,240,80),
    'display-wfd-client': (350,615,270,70),
    'display-wfd-server': (350,735,270,70),
    'display-wfd-core': (350,855,270,70),
    'display-mdss': (350,975,270,70),
    'display-panel-driver': (350,1095,270,70),
    'display-interface-driver': (350,1215,270,70),
    'display-screen-config': (65,445,240,70),
    'display-wfd-config': (65,735,240,70),
    'display-qnx-hab': (660,615,240,70),
    'display-gsl-be': (660,735,240,80),
    'display-qnx-gsl': (660,855,240,70),
    'display-qnx-gpu': (660,975,240,70),
    'display-apps': (1440,215,250,70),
    'display-wms': (1140,370,250,70),
    'display-dms': (1740,370,250,70),
    'display-bufferqueue': (1140,570,250,70),
    'display-flinger': (1440,570,250,70),
    'display-hwui': (1740,570,250,70),
    'display-gralloc': (1140,735,250,70),
    'display-opengl': (1740,865,250,70),
    'display-vulkan': (1140,865,250,70),
    'display-gsl-client': (1740,995,250,70),
    'display-composer': (1440,735,250,70),
    'display-renderengine': (1740,735,250,70),
    'display-sdm': (1440,865,250,70),
    'display-drm-adapter': (1440,995,250,70),
    'display-wfd-fe': (1140,1150,250,80),
    'display-android-gpu': (1740,1135,250,60),
    'display-khab': (1740,1230,250,60),
    'display-vm-memory': (690,1355,450,42),
    'display-vm-notify': (1240,1355,450,42),
    'display-gpu': (70,1480,220,70),
    'display-buffers': (640,1480,300,70),
    'display-dpu': (1140,1480,250,70),
    'display-output': (1650,1480,290,70),
    'display-link': (1140,1640,250,64),
    'display-panel': (1650,1640,290,64),
}
LAYERS = {
    'qnx': [(160,125,'Product Experience'), (300,250,'Platform Services'),
            (565,735,'Device Integration & BSP')],
    'aaos': [(160,145,'Applications'), (320,180,'Framework'),
             (520,560,'Native / HAL'), (1095,205,'Android OS')],
}
PALETTE = {'call':'#3974d9','storage':'#8364b7','install':'#23845b','status':'#d98324'}
NATIVE = {'display-screen','display-apps','display-wms','display-dms',
          'display-bufferqueue','display-flinger','display-renderengine','display-hwui'}
HARDWARE = {'display-gpu','display-buffers','display-dpu','display-output',
            'display-link','display-panel'}
DISPLAY_NAMES = {
    'display-cluster': ('Cluster HMI', 'Kanzi · Screen / EGL clients'),
    'display-qnx-render': ('EGL / OpenGL ES', 'QNX rendering libraries'),
    'display-screen': ('QNX Screen', 'Windows · surfaces · composition'),
    'display-wfd-be': ('WFD Backend / wfd_be', 'Guest commands · buffer import'),
    'display-wfd-client': ('WFD Client', 'libopenwfd_qnx.so'),
    'display-wfd-server': ('OpenWFD Server', 'QNX resource-manager endpoint'),
    'display-wfd-core': ('OpenWFD Core', 'Inside server · ports / pipelines'),
    'display-mdss': ('QDI / MDP / MDSS', 'Inside server · scanout programming'),
    'display-interface-driver': ('DSI / DP Driver & HAL', 'Inside server · link / PHY control'),
    'display-screen-config': ('Screen Configuration', 'graphics.conf'),
    'display-wfd-config': ('OpenWFD Configuration', 'qcdisplaycfg.xml'),
    'display-panel-driver': ('Panel / Bridge Libraries', 'Loaded in OpenWFD server'),
    'display-qnx-gpu': ('KGSL', 'QNX driver · kgsl / GSLKernel.so'),
    'display-gsl-be': ('GSL HAB Server', 'gsl_hab_server · HAB endpoint'),
    'display-qnx-gsl': ('GSL', 'libGSLUser.so · host GPU APIs'),
    'display-qnx-hab': ('UHAB / HAB', 'libuhab.so · /dev/hab/hab'),
    'display-apps': ('IVI Application Clients', 'ViewRootImpl · ThreadedRenderer'),
    'display-wms': ('WindowManagerService', 'Layout · visibility · surfaces'),
    'display-dms': ('DisplayManagerService', 'LocalDisplayAdapter · modes / power'),
    'display-bufferqueue': ('BufferQueue / BLAST', 'GraphicBuffer handles · fences'),
    'display-flinger': ('SurfaceFlinger', 'Layer state · composition'),
    'display-gralloc': ('Gralloc / Mapper', 'Buffer allocation · native handles'),
    'display-composer': ('Composer HAL / HWCSession', 'Validate · present · fences'),
    'display-sdm': ('SDM / libsdmcore', 'Hardware composition plan'),
    'display-drm-adapter': ('DRM Adapter / libdrm', 'GEM / FB IDs · atomic properties'),
    'display-renderengine': ('RenderEngine', 'GLES / SkiaGL client composition'),
    'display-hwui': ('HWUI / Skia', 'libhwui · RenderThread · libskia'),
    'display-opengl': ('OpenGL / EGL Subdriver', 'Adreno EGL / GLES implementation'),
    'display-vulkan': ('Vulkan Driver', 'vulkan.adreno.so · Vulkan ICD'),
    'display-gsl-client': ('GSL Client', 'libgsl.so · /dev/hgsl'),
    'display-wfd-fe': ('msm_drm_hyp / wfd_kms', 'WFD sources · commit · HAB export'),
    'display-android-gpu': ('HGSL', 'RPC · shared command queues'),
    'display-khab': ('KHAB / msm_hab', 'Kernel HAB APIs · MM_GFX'),
    'display-vm-memory': ('QVM Shared Communication Pipes', 'HAB transport · shared regions'),
    'display-vm-notify': ('Inter-VM Notifications', 'hyp_shm_poke · pulse handling'),
    'display-gpu': ('GPU', 'Rendering / client composition'),
    'display-buffers': ('Shared Frame Buffers', 'Mapped image storage'),
    'display-dpu': ('Display Processing Unit', 'Fetch · mix · scale · scanout'),
    'display-output': ('DSI / DP Controller & PHY', 'Hardware · pixel link transmission'),
    'display-link': ('Panel / Bridge Link', 'Board-configured physical link'),
    'display-panel': ('Display Panels', 'Cluster · IVI · configured displays'),
}


class DisplayRoutes(Routes):
    def render(self):
        result = super().render().replace('url(#ota-arrow-', 'url(#display-arrow-')
        mapping = {COLORS[kind]:color for kind,color in PALETTE.items()}
        result = re.sub('|'.join(map(re.escape,mapping)), lambda m:mapping[m.group()], result)
        # Buffers/configuration are references; events have their own return lanes.
        return result.replace('stroke="#8364b7" stroke-width="1.8"',
                              'stroke="#8364b7" stroke-width="1.8" stroke-dasharray="5 4"')


def make_routes():
    r = DisplayRoutes()
    r.add('display-cluster','display-qnx-render',[(485,265),(485,335)],flow='control',label='Render API',at=(485,295))
    r.add('display-qnx-render','display-screen',[(485,405),(485,445)],flow='control,buffers',label='Screen surface / post',at=(485,428))
    r.add('display-screen','display-wfd-client',[(485,515),(485,615)],flow='control,buffers',label='WFD API / image handle',at=(485,540))
    r.add('display-wfd-be','display-wfd-client',[(720,525),(720,580),(630,580),(630,650),(620,650)],flow='control,buffers',label='WFD API',at=(720,565))
    r.add('display-wfd-client','display-wfd-server',[(485,685),(485,735)],flow='control,buffers',both=True,label='QNX read / write IPC',at=(485,714))
    r.add('display-wfd-server','display-wfd-core',[(485,805),(485,855)],flow='control,buffers',label='Wire handler dispatch',at=(485,832))
    r.add('display-wfd-core','display-mdss',[(485,925),(485,975)],flow='control,buffers',label='QDI commit',at=(485,952))
    r.add('display-mdss','display-panel-driver',[(485,1045),(485,1095)],flow='control',label='Panel callbacks',at=(485,1072),note='OEM panel and bridge library calls inside OpenWFD server')
    r.add('display-panel-driver','display-interface-driver',[(485,1165),(485,1215)],flow='control',label='DSI / DP host APIs',at=(485,1192),note='OEM panel libraries call the selected DSI or DP host driver to configure its output interface')
    r.add('display-wfd-config','display-wfd-server',[(305,770),(350,770)],kind='storage',flow='control',note='OpenWFD Server loads qcdisplaycfg.xml for clients, devices, ports, pipelines and panel libraries')
    r.add('display-screen-config','display-screen',[(305,480),(350,480)],kind='storage',flow='control',note='QNX Screen reads graphics.conf for rendering libraries, WFD drivers, display modes and window classes')
    r.add('display-qnx-render','display-qnx-gsl',[(620,370),(650,370),(650,890),(660,890)],flow='control',label='Host GSL APIs',at=(650,710))
    r.add('display-wfd-server','display-wfd-be',[(620,750),(635,750),(635,725),(920,725),(920,506),(900,506)],kind='status',flow='events',label='WFD events',at=(920,715))
    # Android window state, buffer ownership and composition are separate relations.
    r.add('display-apps','display-wms',[(1440,250),(1265,250),(1265,370)],flow='control',label='Window / layout API',at=(1265,325))
    r.add('display-apps','display-bufferqueue',[(1440,265),(1120,265),(1120,605),(1140,605)],kind='storage',flow='buffers',label='Surface / BLAST',at=(1120,480))
    r.add('display-wms','display-dms',[(1390,405),(1740,405)],flow='control',label='Display hints',at=(1565,405))
    r.add('display-wms','display-flinger',[(1265,440),(1265,480),(1565,480),(1565,570)],flow='control',label='SurfaceControl transaction',at=(1455,480))
    r.add('display-dms','display-flinger',[(1865,440),(1865,495),(1620,495),(1620,570)],flow='control',label='Display state / mode / power',at=(1790,495))
    r.add('display-bufferqueue','display-flinger',[(1390,605),(1440,605)],kind='storage',flow='buffers',note='BLAST submits GraphicBuffer handles and acquire fences to SurfaceFlinger')
    r.add('display-bufferqueue','display-gralloc',[(1320,640),(1320,735)],kind='storage',flow='buffers',both=True,label='Allocate / map',at=(1320,704))
    r.add('display-gralloc','display-flinger',[(1390,770),(1420,770),(1420,620),(1440,620)],kind='storage',flow='buffers',note='Mapper imports buffer handles for composition')
    r.add('display-flinger','display-composer',[(1515,640),(1515,735)],flow='control,buffers',label='Validate / present',at=(1515,714))
    r.add('display-composer','display-flinger',[(1690,770),(1715,770),(1715,620),(1690,620)],kind='status',flow='events',label='Present / release fences',at=(1715,705))
    r.add('display-flinger','display-renderengine',[(1690,590),(1710,590),(1710,720),(1865,720),(1865,735)],flow='control,buffers',label='Client composition',at=(1865,705))
    r.add('display-renderengine','display-flinger',[(1740,790),(1730,790),(1730,650),(1670,650),(1670,640)],kind='storage',flow='buffers',label='Client target',at=(1730,685))
    r.add('display-gralloc','display-buffers',[(1265,805),(1265,820),(2020,820),(2020,1455),(900,1455),(900,1480)],kind='storage',flow='buffers',note='Image storage is allocated or imported by Gralloc; consumers use native handles')
    # Application rendering and SurfaceFlinger composition use the guest UMD stack.
    r.add('display-apps','display-hwui',[(1690,250),(2000,250),(2000,605),(1990,605)],flow='control',label='Draw / JNI',at=(2000,480))
    r.add('display-hwui','display-bufferqueue',[(1805,640),(1805,670),(1210,670),(1210,640)],kind='storage',flow='buffers',label='queueBuffer',at=(1440,670))
    r.add('display-hwui','display-opengl',[(1990,620),(2010,620),(2010,900),(1990,900)],flow='control',label='GLES',at=(2010,675),note='Selected SkiaGL pipeline uses AOSP EGL/GLES entry points and the Adreno subdriver')
    r.add('display-hwui','display-vulkan',[(1740,620),(1720,620),(1720,855),(1265,855),(1265,865)],flow='control',label='Vulkan loader',at=(1400,855),note='Selected SkiaVulkan pipeline uses libvulkan to load the Adreno ICD')
    r.add('display-renderengine','display-opengl',[(1865,805),(1865,865)],flow='control',label='EGL / GLES',at=(1865,842))
    r.add('display-opengl','display-gsl-client',[(1865,935),(1865,995)],flow='control',label='gsl_*',at=(1865,973))
    r.add('display-vulkan','display-gsl-client',[(1265,935),(1265,955),(1800,955),(1800,995)],flow='control',note='The Adreno Vulkan ICD links libgsl.so')
    r.add('display-gsl-client','display-android-gpu',[(1865,1065),(1865,1135)],flow='control',label='ioctl /dev/hgsl',at=(1865,1110))
    r.add('display-android-gpu','display-khab',[(1865,1195),(1865,1230)],flow='control',label='habmm_*',at=(1865,1215),note='GSL control RPC and memory sharing use the kernel HAB API; HGSL also supports shared command queues and doorbell notification')
    r.add('display-composer','display-sdm',[(1565,805),(1565,865)],flow='control,buffers',label='Prepare / commit',at=(1565,842))
    r.add('display-sdm','display-drm-adapter',[(1565,935),(1565,995)],flow='control,buffers',label='DRM API',at=(1565,973))
    r.add('display-drm-adapter','display-wfd-fe',[(1440,1030),(1265,1030),(1265,1150)],flow='control,buffers',label='Atomic commit / FB IDs',at=(1265,1110))
    r.add('display-wfd-fe','display-drm-adapter',[(1390,1180),(1415,1180),(1415,1045),(1440,1045)],kind='status',flow='events',label='Local fences / events',at=(1415,1120))
    r.add('display-drm-adapter','display-composer',[(1690,1035),(1725,1035),(1725,785),(1690,785)],kind='status',flow='events',label='Fence / VSync',at=(1725,975))
    # Three explicit gutter lanes. Image references cross domains; pixels do not.
    r.add('display-wfd-fe','display-wfd-be',[(1140,1168),(1050,1168),(1050,462),(900,462)],flow='control',label='HAB · OpenWFD commands',at=(1050,810),note='OpenWFD wire requests, including DEVICE_COMMIT_EXT')
    r.add('display-wfd-fe','display-wfd-be',[(1140,1190),(1010,1190),(1010,485),(900,485)],kind='storage',flow='buffers',label='HAB · export ID / image metadata',at=(1010,905),note='dma-buf / GEM / FB identity becomes HAB export ID; QNX imports the mapped image')
    r.add('display-wfd-be','display-wfd-fe',[(900,506),(970,506),(970,1214),(1140,1214)],kind='status',flow='events',label='HAB · COMMIT_COMPLETE / VSYNC / HPD',at=(970,1005),note='Android waits acquire fences locally before commit and signals local fences on completion')
    r.add('display-wfd-be','display-buffers',[(660,485),(640,485),(640,1450),(790,1450),(790,1480)],kind='storage',flow='buffers',label='PMEM mapping',at=(640,1370))
    r.add('display-vm-notify','display-vm-memory',[(1240,1376),(1140,1376)],kind='status',flow='events',note='Peer notification wakes the receiver of the HAB communication pipe')
    # Paired HAB ports show control RPC; queue submission remains a HGSL capability.
    gpu_note='Matched HAB ports: KHAB / msm_hab communicates with QNX UHAB / HAB on MM_GFX for GSL RPC and buffer sharing'
    r.add('display-khab','display-qnx-hab',[(1740,1260),(1696,1260)],flow='control',both=True,note=gpu_note)
    r.port('display-khab','display-qnx-hab',1670,1260,'HAB','control',gpu_note)
    r.port('display-khab','display-qnx-hab',780,570,'HAB','control',gpu_note)
    r.add('display-khab','display-qnx-hab',[(780,585),(780,615)],flow='control',both=True,note=gpu_note)
    r.add('display-gsl-be','display-qnx-hab',[(780,735),(780,685)],flow='control',both=True,label='habmm_*',at=(780,714),note='GSL HAB Server uses libuhab.so; UHAB calls the QNX HAB resource manager')
    r.add('display-gsl-be','display-qnx-gsl',[(780,815),(780,855)],flow='control',label='gsl_*',at=(780,840),note='The server imports GSL context, memory and command APIs from libGSLUser.so')
    r.add('display-qnx-gsl','display-qnx-gpu',[(780,925),(780,975)],flow='control',label='GPU driver IPC',at=(780,952),note='QNX libGSLUser.so opens /dev/kgsl-3D and calls the KGSL driver through QNX IPC')
    r.add('display-qnx-gpu','display-gpu',[(660,1010),(650,1010),(650,1310),(505,1310),(505,1470),(180,1470),(180,1480)],flow='control',label='GPU HW control',at=(505,1340),note='QNX KGSL controls the GPU hardware; internal queue scheduling is not expanded')
    r.add('display-mdss','display-dpu',[(350,1010),(335,1010),(335,1420),(1265,1420),(1265,1480)],flow='control',label='Display HW programming',at=(335,1340))
    r.add('display-interface-driver','display-output',[(620,1250),(925,1250),(925,1318),(1795,1318),(1795,1480)],flow='control',label='Link / PHY configuration',at=(1560,1318),note='DSI / DP drivers configure the output controller, link timing, PHY and clocks through HAL')
    # The physical pixel path is confined to the shared hardware/output region.
    r.add('display-gpu','display-buffers',[(290,1515),(640,1515)],kind='install',flow='pixels',label='Rendered pixels',at=(460,1515))
    r.add('display-buffers','display-dpu',[(940,1515),(1140,1515)],kind='install',flow='pixels',label='Memory fetch',at=(1040,1515))
    r.add('display-dpu','display-output',[(1390,1515),(1650,1515)],kind='install',flow='pixels',label='Scanout pixels',at=(1515,1515))
    r.add('display-output','display-link',[(1795,1550),(1795,1605),(1265,1605),(1265,1640)],kind='install',flow='pixels',label='DSI / DP',at=(1460,1605))
    r.add('display-link','display-panel',[(1390,1672),(1650,1672)],kind='install',flow='pixels',label='Panel interface',at=(1520,1672))
    return r


def validate(modules, routes):
    by_id={m['id']:m for m in modules}
    if set(NODES)!=set(by_id): raise ValueError(f'Display node mismatch: {set(NODES)^set(by_id)}')
    for mid,(x,y,w,h) in NODES.items():
        domain=by_id[mid]['domain']
        if domain in LAYERS and sum(ly<y and y+h<=ly+lh for ly,lh,_ in LAYERS[domain])!=1:
            raise ValueError(f'Display node outside its software layer: {mid}')
    for item in routes.items:
        for key in ('source','target'):
            if item[key] not in by_id: raise ValueError(f'Unknown Display edge endpoint: {item[key]}')
        # No route may cut through an unrelated component.
        for (ax,ay),(bx,by) in zip(item['points'],item['points'][1:]):
            for mid,(x,y,w,h) in NODES.items():
                if mid in (item['source'],item['target']): continue
                hit=(ax==bx and x<ax<x+w and max(min(ay,by),y)<min(max(ay,by),y+h)) or (ay==by and y<ay<y+h and max(min(ax,bx),x)<min(max(ax,bx),x+w))
                if hit: raise ValueError(f'{item["source"]} → {item["target"]} crosses {mid}')


def render_graph(modules):
    routes=make_routes()
    validate(modules,routes)
    by_id={m['id']:m for m in modules}
    frame=[_rect(15,60,2010,1520,'#fbfcff','#e0e5ed',20),
           _text(34,88,'SoC Platform',17,'#202124',700),
           _text(175,88,'QNX host + Android guest',11,'#738092'),
           _rect(30,110,900,1205,'#eaf1fe','#bfd3f8',17),
           _rect(1100,110,910,1205,'#eaf6ed','#c8e5cf',17),
           _text(50,140,'QNX Cluster',19,'#1d4e9e',700),
           _text(1120,140,'AAOS IVI',19,'#176c3b',700),
           _text(1015,160,'CROSS-DOMAIN',10,'#526179',700,'middle'),
           _text(1015,180,'DISPLAY',10,'#526179',700,'middle')]
    for domain,layers in LAYERS.items():
        x,w,palette={'qnx':(42,876,('#ffffffd9','#d6e1f0')),'aaos':(1112,886,('#ffffffd9','#d6e8d9'))}[domain]
        for y,h,title in layers: frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([_layer(30,1325,1980,85,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
                  _text(50,1380,'QVM · VM isolation',12,'#675b84'),
                  _layer(30,1435,1980,132,'SoC Hardware & Shared Image Memory',('#f7f8f9','#dce1e8')),
                  _layer(30,1595,1980,120,'Display Output',('#fff','#dce1e8')),
                  _text(50,1673,'Physical links and display assignments follow the deployed board configuration.',12,'#647184')])
    nodes=[]
    for mid,(x,y,w,h) in NODES.items():
        m=by_id[mid]
        name,short=DISPLAY_NAMES[mid]
        if mid in HARDWARE: fill,stroke='#eceff1','#9aa0a6'
        elif m['domain']=='platform': fill,stroke='#f1edfb','#b8a5dc'
        elif mid in NATIVE: fill,stroke='#e6f4ea','#81b991'
        elif m.get('kind')=='config': fill,stroke='#fff','#a9b3bf'
        else: fill,stroke='#fef7e0','#d7b353'
        ny,sy=(18,33) if h<50 else (27,49)
        shape=_rect(x,y,w,h,fill,stroke,8,1.3)
        if m.get('kind')=='memory':
            shape=_rect(x+8,y-8,w,h,fill,stroke,0)+_rect(x+4,y-4,w,h,fill,stroke,0)+_rect(x,y,w,h,fill,stroke,0)
        if m.get('kind')=='config':
            shape+=f'<path d="M{x+w-18},{y} V{y+18} H{x+w}" fill="none" stroke="{stroke}"/>'
        nodes.append(f'<g class="ota-node" data-sw-module="{mid}" role="button" tabindex="0" aria-pressed="false" aria-label="{escape(m["name"],quote=True)}"><title>{escape(m["name"])}</title>'+shape+_text(x+12,y+ny,name,12.5,'#20312a',700)+_text(x+12,y+sy,short,10.2,'#596579')+'</g>')
    defs=['<defs>']
    for kind,color in PALETTE.items():
        defs.append(f'<marker id="display-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(1010,'Control / IPC','call'),(1230,'Buffer / config references','storage'),(1560,'Pixel data','install'),(1780,'Events / fences','status')]:
        dash=' stroke-dasharray="5 4"' if kind in ('storage','status') else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{PALETTE[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,11,PALETTE[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-display-diagram" id="sw-display-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, sans-serif" role="group" aria-label="Display software component interactions">'
            '<title>Display software component interactions</title><desc>QNX native display clients and Android WFD frontend meet at OpenWFD. Guest rendering uses GSL Client, HGSL and KHAB; paired HAB ports connect to the QNX GSL HAB Server stack. Shared command queues are an HGSL capability. Separate routes show control, shared buffer references, physical pixels and completion events.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'DISPLAY SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+routes.render()+'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
