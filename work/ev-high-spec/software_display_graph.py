"""HQX/QNX display services, Android WFD frontend and shared scanout resources."""
from html import escape
import re
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 2040, 1850
NODES = {
    'display-cluster': (350,195,270,70),
    'display-qnx-render': (350,335,270,70),
    'display-screen': (350,445,270,70),
    'display-wfd-be': (660,445,240,70),
    'display-wfd-client': (350,615,270,70),
    'display-wfd-server': (350,735,270,70),
    'display-wfd-core': (350,855,270,70),
    'display-mdss': (350,975,270,70),
    'display-panel-driver': (350,1095,270,70),
    'display-interface-driver': (350,1215,270,70),
    'display-screen-config': (65,445,240,70),
    'display-wfd-config': (65,735,240,70),
    'display-qnx-hab': (660,615,240,70),
    'display-gsl-be': (660,735,240,70),
    'display-qnx-gsl': (660,855,240,70),
    'display-qnx-gpu': (660,975,240,70),
    'display-apps': (1140,195,850,50),
    'display-viewroot': (1140,275,250,50),
    'display-threaded-renderer': (1440,275,250,50),
    'display-surfaceview': (1740,275,250,50),
    'display-recording': (1140,350,250,50),
    'display-wms': (1440,350,250,50),
    'display-dms': (1740,350,250,50),
    'display-hwui': (1140,485,250,60),
    'display-native-client': (1440,485,250,60),
    'display-surface': (1740,485,250,60),
    'display-api-loader': (1140,595,250,60),
    'display-bufferqueue': (1740,595,250,60),
    'display-opengl': (1140,705,250,60),
    'display-vulkan': (1440,705,250,60),
    'display-flinger': (1740,705,250,60),
    'display-gsl-client': (1140,805,250,60),
    'display-renderengine': (1440,805,250,60),
    'display-gralloc': (1440,935,250,60),
    'display-composer': (1740,935,250,60),
    'display-sdm': (1740,1020,250,60),
    'display-drm-adapter': (1740,1105,250,60),
    'display-android-gpu': (1140,1230,250,60),
    'display-wfd-fe': (1740,1230,250,60),
    'display-khab': (1440,1330,550,60),
    'display-vm-memory': (690,1475,450,42),
    'display-vm-notify': (1240,1475,450,42),
    'display-gpu': (70,1600,220,70),
    'display-buffers': (640,1600,300,70),
    'display-dpu': (1140,1600,250,70),
    'display-output': (1650,1600,290,70),
    'display-link': (1140,1760,250,64),
    'display-panel': (1650,1760,290,64),
}
LAYERS = {
    'qnx': [(160,125,'Product Experience'), (300,250,'Platform Services'),
            (565,850,'Device Integration & BSP')],
    'aaos': [(160,270,'Java'), (445,430,'Native'),
             (890,285,'HAL'), (1190,225,'Linux Kernel')],
}
PALETTE = {'call':'#3974d9','storage':'#8364b7','install':'#23845b','status':'#d98324'}
NATIVE = {'display-screen','display-apps','display-wms','display-dms',
          'display-bufferqueue','display-flinger','display-renderengine','display-hwui',
          'display-viewroot','display-threaded-renderer','display-surfaceview',
          'display-recording','display-surface','display-api-loader'}
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
    'display-apps': ('Android UI Applications', 'View · Canvas · SurfaceView'),
    'display-viewroot': ('ViewRootImpl / ViewTree', 'UI thread · traversal · draw'),
    'display-threaded-renderer': ('ThreadedRenderer', 'syncAndDrawFrame'),
    'display-surfaceview': ('SurfaceView', 'Independent Surface'),
    'display-recording': ('RecordingCanvas / RenderNode', 'Java API · display list'),
    'display-native-client': ('Native / 3D Engine', 'GLES or Vulkan · Surface client'),
    'display-surface': ('Surface / ANativeWindow', 'Dequeue · queueBuffer'),
    'display-api-loader': ('GLES / Vulkan APIs & Loaders', 'libEGL · libGLESv2 · libvulkan'),
    'display-wms': ('WindowManagerService', 'Layout · visibility · surfaces'),
    'display-dms': ('DisplayManagerService', 'LocalDisplayAdapter · modes / power'),
    'display-bufferqueue': ('BLASTBufferQueue', 'Per-Surface queue · buffers / fences'),
    'display-flinger': ('SurfaceFlinger', 'Layer state · composition'),
    'display-gralloc': ('Gralloc / Mapper', 'Buffer allocation · native handles'),
    'display-composer': ('Composer HAL / HWCSession', 'Validate · present · fences'),
    'display-sdm': ('SDM / libsdmcore', 'Hardware composition plan'),
    'display-drm-adapter': ('DRM Adapter / libdrm', 'GEM / FB IDs · atomic properties'),
    'display-renderengine': ('RenderEngine', 'GLES / SkiaGL client composition'),
    'display-hwui': ('RenderThread / HWUI', 'libhwui · Skia GPU backend'),
    'display-opengl': ('OpenGL / EGL Subdriver', 'Adreno EGL / GLES implementation'),
    'display-vulkan': ('Vulkan Driver', 'vulkan.adreno.so · Vulkan ICD'),
    'display-gsl-client': ('GSL Client', 'libgsl.so · /dev/hgsl'),
    'display-wfd-fe': ('msm_drm_hyp / wfd_kms', 'WFD sources · commit · HAB export'),
    'display-android-gpu': ('HGSL', 'RPC · shared command queues'),
    'display-khab': ('Guest HAB / KHAB', 'msm_hab · MM_GFX / MM_DISP · QVM transport'),
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
    r.add('display-wfd-be','display-wfd-client',[(720,515),(720,580),(630,580),(630,650),(620,650)],flow='control,buffers',label='WFD API',at=(720,565))
    r.add('display-wfd-client','display-wfd-server',[(485,685),(485,735)],flow='control,buffers',both=True,label='QNX read / write IPC',at=(485,714))
    r.add('display-wfd-server','display-wfd-core',[(485,805),(485,855)],flow='control,buffers',label='Wire handler dispatch',at=(485,832))
    r.add('display-wfd-core','display-mdss',[(485,925),(485,975)],flow='control,buffers',label='QDI commit',at=(485,952))
    r.add('display-mdss','display-panel-driver',[(485,1045),(485,1095)],flow='control',label='Panel callbacks',at=(485,1072),note='OEM panel and bridge library calls inside OpenWFD server')
    r.add('display-panel-driver','display-interface-driver',[(485,1165),(485,1215)],flow='control',label='DSI / DP host APIs',at=(485,1192),note='OEM panel libraries call the selected DSI or DP host driver to configure its output interface')
    r.add('display-wfd-config','display-wfd-server',[(305,770),(350,770)],kind='storage',flow='control',note='OpenWFD Server loads qcdisplaycfg.xml for clients, devices, ports, pipelines and panel libraries')
    r.add('display-screen-config','display-screen',[(305,480),(350,480)],kind='storage',flow='control',note='QNX Screen reads graphics.conf for rendering libraries, WFD drivers, display modes and window classes')
    r.add('display-qnx-render','display-qnx-gsl',[(620,370),(650,370),(650,890),(660,890)],flow='control',label='Host GSL APIs',at=(650,710))
    r.add('display-wfd-server','display-wfd-be',[(620,750),(635,750),(635,725),(920,725),(920,506),(900,506)],kind='status',flow='events',label='WFD events',at=(860,725))
    # Java mirrors the UI traversal, recording and SurfaceView branches.
    r.add('display-apps','display-viewroot',[(1265,245),(1265,275)],flow='control')
    r.add('display-apps','display-surfaceview',[(1865,245),(1865,275)],flow='control')
    r.add('display-viewroot','display-threaded-renderer',[(1390,300),(1440,300)],flow='control')
    r.add('display-viewroot','display-recording',[(1265,325),(1265,350)],flow='control')
    r.add('display-viewroot','display-wms',[(1390,314),(1415,314),(1415,375),(1440,375)],flow='control',note='Window session and layout requests')
    r.add('display-wms','display-dms',[(1690,375),(1740,375)],flow='control',note='Window and logical display coordination')
    r.add('display-recording','display-hwui',[(1265,400),(1265,485)],flow='control',label='Display list',at=(1265,457))
    r.add('display-threaded-renderer','display-hwui',[(1565,325),(1565,338),(1428,338),(1428,465),(1350,465),(1350,485)],flow='control',label='JNI · syncAndDrawFrame',at=(1475,452))
    r.add('display-surfaceview','display-surface',[(1990,300),(2000,300),(2000,515),(1990,515)],flow='control',note='SurfaceView owns a separate Surface and BLAST queue')
    r.add('display-wms','display-flinger',[(1565,400),(1565,430),(1710,430),(1710,720),(1740,720)],flow='control',label='SurfaceControl',at=(1640,430))
    r.add('display-dms','display-flinger',[(1865,400),(1865,420),(2020,420),(2020,740),(1990,740)],flow='control',label='Display policy',at=(1940,420))
    # Native: left rendering stack, right Surface/BLAST/composition stack.
    r.add('display-hwui','display-api-loader',[(1265,545),(1265,595)],flow='control',label='GLES / Vulkan',at=(1265,576))
    r.add('display-native-client','display-api-loader',[(1565,545),(1565,575),(1340,575),(1340,595)],flow='control')
    r.add('display-native-client','display-surface',[(1690,515),(1740,515)],kind='storage',flow='buffers',note='The native renderer uses the target ANativeWindow')
    r.add('display-hwui','display-surface',[(1390,520),(1410,520),(1410,560),(1800,560),(1800,545)],kind='storage',flow='buffers',label='Dequeue / queue',at=(1640,560))
    r.add('display-surface','display-bufferqueue',[(1865,545),(1865,595)],kind='storage',flow='buffers',label='queueBuffer',at=(1865,576))
    r.add('display-bufferqueue','display-flinger',[(1865,655),(1865,705)],kind='storage',flow='buffers',label='Transaction / fences',at=(1865,687))
    r.add('display-api-loader','display-opengl',[(1265,655),(1265,705)],flow='control',label='EGL / GLES',at=(1265,687))
    r.add('display-api-loader','display-vulkan',[(1390,625),(1565,625),(1565,705)],flow='control',label='Vulkan ICD',at=(1565,687))
    r.add('display-opengl','display-gsl-client',[(1265,765),(1265,805)],flow='control',label='gsl_*',at=(1265,793))
    r.add('display-vulkan','display-gsl-client',[(1440,735),(1405,735),(1405,835),(1390,835)],flow='control',note='Vulkan ICD links libgsl.so')
    r.add('display-flinger','display-renderengine',[(1740,740),(1720,740),(1720,835),(1690,835)],flow='control',label='Client composition',at=(1766,820))
    r.add('display-renderengine','display-flinger',[(1565,805),(1565,772),(1865,772),(1865,765)],kind='storage',flow='buffers',label='Client target',at=(1575,778))
    r.add('display-renderengine','display-api-loader',[(1440,835),(1420,835),(1420,645),(1390,645)],flow='control',label='EGL / GLES',at=(1420,685),note='Current RenderEngine uses GLES or SkiaGL; no Vulkan backend in this source version')
    # HAL: allocator and the vendor composer implementation have their own layer.
    r.add('display-bufferqueue','display-gralloc',[(1990,625),(2030,625),(2030,905),(1565,905),(1565,935)],kind='storage',flow='buffers',both=True,label='Allocate / import',at=(1565,920))
    r.add('display-gralloc','display-flinger',[(1690,965),(1700,965),(1700,755),(1740,755)],kind='storage',flow='buffers',note='Mapper imports GraphicBuffer handles for composition')
    r.add('display-flinger','display-composer',[(1910,765),(1910,935)],flow='control,buffers,events',both=True,label='Validate / present · fences',at=(1900,885))
    r.add('display-composer','display-sdm',[(1865,995),(1865,1020)],flow='control,buffers',note='Calls the vendor composition and display commit implementation')
    r.add('display-sdm','display-drm-adapter',[(1865,1080),(1865,1105)],flow='control,buffers',note='Calls the DRM adapter for display submission')
    r.add('display-drm-adapter','display-composer',[(1740,1145),(1715,1145),(1715,980),(1740,980)],kind='status',flow='events',label='Fences / VSync',at=(1715,1095))
    r.add('display-drm-adapter','display-wfd-fe',[(1865,1165),(1865,1230)],flow='control,buffers,events',both=True,label='DRM / KMS · local fences',at=(1865,1195))
    r.add('display-gralloc','display-buffers',[(1440,965),(1420,965),(1420,1320),(1155,1320),(1155,1565),(900,1565),(900,1600)],kind='storage',flow='buffers',note='Gralloc allocates or imports image storage; components exchange handles')
    # Kernel frontends share HAB but use distinct graphics and display channels.
    r.add('display-gsl-client','display-android-gpu',[(1265,865),(1265,1230)],flow='control',label='ioctl /dev/hgsl',at=(1265,1195))
    r.add('display-android-gpu','display-khab',[(1390,1260),(1550,1260),(1550,1330)],flow='control',label='habmm_* · MM_GFX',at=(1550,1310),note='GSL control RPC and memory sharing; shared command queues remain an HGSL capability')
    r.add('display-wfd-fe','display-khab',[(1865,1290),(1865,1330)],flow='control,buffers,events',both=True,note='MM_DISP: OpenWFD requests, imported/exported buffer IDs and completion events')
    gfx_note='Matched GFX ports: HAB MM_GFX connects Guest KHAB with QNX UHAB/HAB for GSL control RPC and memory sharing'
    disp_note='Matched DISP ports: HAB MM_DISP carries OpenWFD requests, buffer IDs and events between the guest display frontend and QNX wfd_be'
    for target,y,name,flow,note in [('display-qnx-hab',1380,'GFX','control',gfx_note),('display-wfd-be',1350,'DISP','control,buffers,events',disp_note)]:
        r.add('display-khab',target,[(1440,y),(1406,y)],flow=flow,both=True,note=note)
        r.port('display-khab',target,1380,y,name,flow,note)
    r.port('display-khab','display-qnx-hab',780,570,'GFX','control',gfx_note)
    r.add('display-khab','display-qnx-hab',[(780,582),(780,615)],flow='control',both=True,note=gfx_note)
    r.port('display-khab','display-wfd-be',985,485,'DISP','control,buffers,events',disp_note)
    r.add('display-khab','display-wfd-be',[(959,485),(900,485)],flow='control,buffers,events',both=True,note=disp_note)
    r.add('display-wfd-be','display-buffers',[(860,515),(860,540),(950,540),(950,1425),(610,1425),(610,1570),(790,1570),(790,1600)],kind='storage',flow='buffers',label='PMEM mapping',at=(610,1490))
    r.add('display-vm-notify','display-vm-memory',[(1240,1496),(1140,1496)],kind='status',flow='events',note='Peer notification wakes the receiver of the HAB communication pipe')
    r.add('display-gsl-be','display-qnx-hab',[(780,735),(780,685)],flow='control',both=True,label='habmm_*',at=(780,714),note='GSL HAB Server uses libuhab.so; UHAB calls the QNX HAB resource manager')
    r.add('display-gsl-be','display-qnx-gsl',[(780,805),(780,855)],flow='control',label='gsl_*',at=(780,840),note='The server imports GSL context, memory and command APIs from libGSLUser.so')
    r.add('display-qnx-gsl','display-qnx-gpu',[(780,925),(780,975)],flow='control',label='GPU driver IPC',at=(780,952),note='QNX libGSLUser.so opens /dev/kgsl-3D and calls the KGSL driver through QNX IPC')
    r.add('display-qnx-gpu','display-gpu',[(660,1010),(650,1010),(650,1310),(505,1310),(505,1590),(180,1590),(180,1600)],flow='control',label='GPU HW control',at=(505,1460),note='QNX KGSL controls the GPU hardware; internal queue scheduling is not expanded')
    r.add('display-mdss','display-dpu',[(350,1010),(335,1010),(335,1540),(1265,1540),(1265,1600)],flow='control',label='Display HW programming',at=(335,1460))
    r.add('display-interface-driver','display-output',[(620,1250),(925,1250),(925,1438),(1795,1438),(1795,1600)],flow='control',label='Link / PHY configuration',at=(1795,1538),note='DSI / DP drivers configure the output controller, link timing, PHY and clocks through HAL')
    # The physical pixel path is confined to the shared hardware/output region.
    r.add('display-gpu','display-buffers',[(290,1635),(640,1635)],kind='install',flow='pixels',label='Rendered pixels',at=(460,1635))
    r.add('display-buffers','display-dpu',[(940,1635),(1140,1635)],kind='install',flow='pixels',label='Memory fetch',at=(1040,1635))
    r.add('display-dpu','display-output',[(1390,1635),(1650,1635)],kind='install',flow='pixels',label='Scanout pixels',at=(1515,1635))
    r.add('display-output','display-link',[(1795,1670),(1795,1725),(1265,1725),(1265,1760)],kind='install',flow='pixels',label='DSI / DP',at=(1460,1725))
    r.add('display-link','display-panel',[(1390,1792),(1650,1792)],kind='install',flow='pixels',label='Panel interface',at=(1520,1792))
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
    frame=[_rect(15,60,2010,1640,'#fbfcff','#e0e5ed',20),
           _text(34,88,'SoC Platform',17,'#202124',700),
           _text(175,88,'QNX host + Android guest',11,'#738092'),
           _rect(30,110,900,1320,'#eaf1fe','#bfd3f8',17),
           _rect(1100,110,910,1320,'#eaf6ed','#c8e5cf',17),
           _text(50,140,'QNX Cluster',19,'#1d4e9e',700),
           _text(1120,140,'AAOS IVI',19,'#176c3b',700),
           _text(1015,160,'CROSS-DOMAIN',10,'#526179',700,'middle'),
           _text(1015,180,'DISPLAY',10,'#526179',700,'middle')]
    for domain,layers in LAYERS.items():
        x,w,palette={'qnx':(42,876,('#ffffffd9','#d6e1f0')),'aaos':(1112,886,('#ffffffd9','#d6e8d9'))}[domain]
        for y,h,title in layers: frame.append(_layer(x,y,w,h,title,palette))
    frame.extend([_layer(30,1445,1980,85,'VIRTUALIZATION',('#f2f0fc','#ded9ef')),
                  _text(50,1500,'QVM · VM isolation',12,'#675b84'),
                  _layer(30,1555,1980,132,'SoC Hardware & Shared Image Memory',('#f7f8f9','#dce1e8')),
                  _layer(30,1715,1980,120,'Display Output',('#fff','#dce1e8')),
                  _text(50,1793,'Physical links and display assignments follow the deployed board configuration.',12,'#647184')])
    nodes=[]
    for mid,(x,y,w,h) in NODES.items():
        m=by_id[mid]
        name,short=DISPLAY_NAMES[mid]
        if mid in HARDWARE: fill,stroke='#eceff1','#9aa0a6'
        elif m['domain']=='platform': fill,stroke='#f1edfb','#b8a5dc'
        elif mid in ('display-apps','display-native-client'): fill,stroke='#e8f0fe','#7da5ed'
        elif mid in NATIVE: fill,stroke='#e6f4ea','#81b991'
        elif m.get('kind')=='config': fill,stroke='#fff','#a9b3bf'
        else: fill,stroke='#fef7e0','#d7b353'
        ny,sy=(18,33) if h<50 else ((22,41) if h<=60 else (27,49))
        shape=_rect(x,y,w,h,fill,stroke,8,1.3)
        if m.get('kind')=='memory':
            shape=_rect(x+8,y-8,w,h,fill,stroke,0)+_rect(x+4,y-4,w,h,fill,stroke,0)+_rect(x,y,w,h,fill,stroke,0)
        if m.get('kind')=='config':
            shape+=f'<path d="M{x+w-18},{y} V{y+18} H{x+w}" fill="none" stroke="{stroke}"/>'
        nodes.append(f'<g class="ota-node" data-sw-module="{mid}" role="button" tabindex="0" aria-pressed="false" aria-label="{escape(m["name"],quote=True)}"><title>{escape(m["name"])}</title>'+shape+_text(x+12,y+ny,name,13.5,'#20312a',700)+_text(x+12,y+sy,short,11,'#596579')+'</g>')
    defs=['<defs>']
    for kind,color in PALETTE.items():
        defs.append(f'<marker id="display-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(1010,'Control / IPC','call'),(1230,'Buffer / config references','storage'),(1560,'Pixel data','install'),(1780,'Events / fences','status')]:
        dash=' stroke-dasharray="5 4"' if kind in ('storage','status') else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{PALETTE[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,11,PALETTE[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-display-diagram" id="sw-display-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, sans-serif" role="group" aria-label="Display software component interactions">'
            '<title>Display software component interactions</title><desc>QNX native display clients and Android WFD frontend meet at OpenWFD. Guest rendering uses GSL Client, HGSL and KHAB; matched GFX and DISP ports identify separate HAB channels to the QNX host. Android follows Java, Native, HAL and Linux Kernel layers. Shared command queues are an HGSL capability. Separate routes show control, shared buffer references, physical pixels and completion events.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'DISPLAY SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+routes.render()+'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
