"""HQX/QNX display services, Android WFD frontend and shared scanout resources."""
from html import escape
import re
from software_ota_graph import Routes, COLORS, _rect, _text, _layer

WIDTH, HEIGHT = 2040, 1850
NODES = {
    'display-cluster': (70, 195, 830, 70),
    'display-qnx-render': (70, 335, 350, 70),
    'display-screen': (70, 445, 350, 70),
    'display-wfd-be': (730, 615, 170, 70),
    'display-wfd-client': (70, 615, 350, 70),
    'display-wfd-server': (70, 735, 350, 70),
    'display-wfd-core': (70, 855, 350, 70),
    'display-mdss': (70, 975, 350, 70),
    'display-panel-driver': (70, 1095, 350, 88),
    'display-interface-driver': (70, 1235, 350, 70),
    'display-screen-config': (550, 335, 350, 70),
    'display-wfd-config': (550, 615, 150, 70),
    'display-qnx-hab': (550, 735, 350, 70),
    'display-gsl-be': (550, 855, 350, 70),
    'display-qnx-gsl': (550, 975, 350, 70),
    'display-qnx-gpu': (550, 1095, 350, 70),
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
    'display-vulkan': (1440,805,250,60),
    'display-flinger': (1740,705,250,60),
    'display-gsl-client': (1140,805,250,60),
    'display-renderengine': (1440,705,250,60),
    'display-gralloc': (1440,935,250,60),
    'display-composer': (1740,935,250,60),
    'display-sdm': (1740,1020,250,60),
    'display-drm-adapter': (1740,1105,250,60),
    'display-android-gpu': (1140,1230,250,60),
    'display-wfd-fe': (1740,1230,250,60),
    'display-khab': (1440,1330,250,60),
    'display-gpu': (70,1600,220,70),
    'display-buffers': (640,1600,300,70),
    'display-dpu': (1140,1600,250,70),
    'display-output': (1650,1600,290,70),
    'display-serializer': (640,1760,300,64),
    'display-deserializer': (1140,1760,250,64),
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
            'display-serializer','display-deserializer','display-panel'}
DISPLAY_NAMES = {
    'display-cluster': ('ClusterApp', 'Kanzi HMI'),
    'display-qnx-render': ('libESXEGL_Adreno.so\nlibESXGLESv2_Adreno.so', 'EGL / GLES rendering'),
    'display-screen': ('screen / libscreen.so.1', 'Windows / composition'),
    'display-wfd-be': ('wfd_be', 'Guest display backend'),
    'display-wfd-client': ('libopenwfd_qnx.so\nlibopenwfd.so', 'Screen client / generic client'),
    'display-wfd-server': ('openwfd_server', 'Display service'),
    'display-wfd-core': ('openwfd_core', 'Linked in server · WFD objects'),
    'display-mdss': ('qdi / qdiplatform_s8155', 'Linked in server · MDP / MDSS'),
    'display-interface-driver': ('qdidsihost / qdidphost', 'Linked in server · DSI / DP'),
    'display-screen-config': ('graphics.conf', 'Screen configuration'),
    'display-wfd-config': ('qcdisplaycfg.xml', 'OpenWFD configuration'),
    'display-panel-driver': ('libDSI_COMMON_QC_0.so\nlibDP0_COMMON_QC.so\nlibbridgechip_client.so', 'Panel adapters (examples) / bridge IPC'),
    'display-qnx-gpu': ('kgsl / GSLKernel.so', 'GPU driver'),
    'display-gsl-be': ('gsl_hab_server', 'Guest graphics backend'),
    'display-qnx-gsl': ('libGSLUser.so', 'Host GPU APIs'),
    'display-qnx-hab': ('libuhab.so / hab', 'HAB host endpoint'),
    'display-apps': ('Activity / View', 'Application UI'),
    'display-viewroot': ('ViewRootImpl', 'Traversal / layout / draw'),
    'display-threaded-renderer': ('ThreadedRenderer', 'Sync rendering'),
    'display-surfaceview': ('SurfaceView', 'Independent Surface'),
    'display-recording': ('RecordingCanvas / RenderNode', 'Record display lists'),
    'display-native-client': ('ANativeActivity', 'Native entry · example'),
    'display-surface': ('Surface / ANativeWindow', 'Dequeue / queue buffers'),
    'display-api-loader': ('libEGL.so / libGLESv2.so\nlibvulkan.so', 'Graphics APIs / driver loading'),
    'display-wms': ('WindowManagerService', 'Window / layer state'),
    'display-dms': ('DisplayManagerService', 'Logical displays / policy'),
    'display-bufferqueue': ('BLASTBufferQueue', 'Buffer transactions'),
    'display-flinger': ('SurfaceFlinger', 'Compose / present layers'),
    'display-gralloc': ('libgralloccore.so / QtiMapper', 'Allocate / import buffers'),
    'display-composer': ('IComposer / IComposerClient', 'HIDL 2.4 · Composer HAL'),
    'display-sdm': ('libsdmcore.so', 'Display composition plan'),
    'display-drm-adapter': ('libsdedrm.so / libdrmutils.so\nlibdrm.so', 'DRM objects / atomic commit'),
    'display-renderengine': ('RenderEngine', 'GPU composition'),
    'display-hwui': ('libhwui.so / RenderThread', 'Application GPU rendering'),
    'display-opengl': ('libEGL_adreno.so\nlibGLESv2_adreno.so', 'EGL / GLES rendering'),
    'display-vulkan': ('vulkan.adreno.so', 'Vulkan rendering'),
    'display-gsl-client': ('libgsl.so', 'Guest GPU APIs'),
    'display-wfd-fe': ('msm_hyp.ko', 'wfd_kms · display frontend'),
    'display-android-gpu': ('qcom_hgsl.ko', 'HGSL · guest GPU driver'),
    'display-khab': ('msm_hab / khab', 'MM_GFX / MM_DISP'),
    'display-gpu': ('GPU', 'Rendering / client composition'),
    'display-buffers': ('Shared Frame Buffers', 'Mapped image storage'),
    'display-dpu': ('Display Processing Unit', 'Fetch · mix · scale · scanout'),
    'display-output': ('DSI / DP Controller & PHY', 'Hardware · pixel link transmission'),
    'display-serializer': ('Serializer', 'DSI / DP input · serial link TX'),
    'display-deserializer': ('Deserializer', 'Serial link RX · panel output'),
    'display-panel': ('Display Panel', 'Physical pixel display'),
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
    # Two QNX columns: display submission at left, configuration and GPU at right.
    r.add('display-cluster','display-qnx-render',[(245,265),(245,335)],flow='control',label='EGL / GLES',at=(245,295))
    r.add('display-qnx-render','display-screen',[(245,405),(245,445)],flow='control,buffers',label='Screen surface / post',at=(245,428))
    r.add('display-screen','display-wfd-client',[(245,515),(245,615)],flow='control,buffers',label='WFD API / image handle',at=(245,540))
    r.add('display-wfd-be','display-wfd-client',[(815,615),(815,590),(375,590),(375,615)],flow='control,buffers',label='WFD API',at=(630,590))
    r.add('display-wfd-client','display-wfd-server',[(245,685),(245,735)],flow='control,buffers',both=True,label='QNX read / write IPC',at=(245,714))
    r.add('display-wfd-server','display-wfd-core',[(245,805),(245,855)],flow='control,buffers',label='Wire handler dispatch',at=(245,832))
    r.add('display-wfd-core','display-mdss',[(245,925),(245,975)],flow='control,buffers',label='QDI commit',at=(245,952))
    r.add('display-mdss','display-panel-driver',[(245,1045),(245,1095)],flow='control',label='Panel callbacks',at=(245,1072),note='OEM panel and bridge library calls inside OpenWFD server')
    r.add('display-panel-driver','display-interface-driver',[(245,1183),(245,1235)],flow='control',label='DSI / DP host APIs',at=(245,1210),note='OEM panel libraries call the selected DSI or DP host driver to configure its output interface')
    r.add('display-wfd-config','display-wfd-server',[(620,685),(620,695),(375,695),(375,735)],kind='storage',flow='control',note='OpenWFD Server loads qcdisplaycfg.xml for clients, devices, ports, pipelines and panel libraries')
    r.add('display-screen-config','display-screen',[(550,370),(520,370),(520,420),(375,420),(375,445)],kind='storage',flow='control',note='QNX Screen reads graphics.conf for rendering libraries, WFD drivers, display modes and window classes')
    r.add('display-qnx-render','display-qnx-gsl',[(420,370),(465,370),(465,1010),(550,1010)],flow='control',label='gsl_*',at=(465,910))
    r.add('display-wfd-server','display-wfd-be',[(420,770),(490,770),(490,705),(865,705),(865,685)],kind='status',flow='events',label='WFD events',at=(800,705))
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
    r.add('display-api-loader','display-vulkan',[(1340,655),(1340,675),(1410,675),(1410,780),(1565,780),(1565,805)],flow='control',label='Vulkan ICD',at=(1565,793))
    r.add('display-opengl','display-gsl-client',[(1265,765),(1265,805)],flow='control',label='gsl_*',at=(1265,793))
    r.add('display-vulkan','display-gsl-client',[(1440,835),(1390,835)],flow='control',note='Vulkan ICD links libgsl.so')
    r.add('display-flinger','display-renderengine',[(1740,735),(1690,735)],flow='control',note='Client composition request')
    r.add('display-renderengine','display-flinger',[(1690,750),(1740,750)],kind='storage',flow='buffers',note='Client target buffer and fence')
    r.add('display-renderengine','display-api-loader',[(1440,735),(1430,735),(1430,625),(1390,625)],flow='control',label='EGL / GLES',at=(1430,665),note='Current RenderEngine uses GLES or SkiaGL; no Vulkan backend in this source version')
    # HAL: allocator and the vendor composer implementation have their own layer.
    r.add('display-bufferqueue','display-gralloc',[(1990,625),(2030,625),(2030,905),(1565,905),(1565,935)],kind='storage',flow='buffers',both=True,label='Allocate / import',at=(1565,920))
    r.add('display-gralloc','display-flinger',[(1690,965),(1700,965),(1700,790),(1800,790),(1800,765)],kind='storage',flow='buffers',note='Mapper imports GraphicBuffer handles for composition')
    r.add('display-flinger','display-composer',[(1910,765),(1910,935)],flow='control,buffers,events',both=True,label='Validate / present · fences',at=(1900,885))
    r.add('display-composer','display-sdm',[(1865,995),(1865,1020)],flow='control,buffers',note='Composer HAL dispatches through HWCSession to the SDM implementation')
    r.add('display-sdm','display-drm-adapter',[(1865,1080),(1865,1105)],flow='control,buffers',note='Calls the DRM adapter for display submission')
    r.add('display-drm-adapter','display-composer',[(1740,1145),(1715,1145),(1715,980),(1740,980)],kind='status',flow='events',label='Fences / VSync',at=(1715,1095))
    r.add('display-drm-adapter','display-wfd-fe',[(1865,1165),(1865,1230)],flow='control,buffers,events',both=True,label='DRM / KMS · local fences',at=(1865,1195))
    r.add('display-gralloc','display-buffers',[(1440,965),(1420,965),(1420,1320),(1155,1320),(1155,1565),(900,1565),(900,1600)],kind='storage',flow='buffers',note='Gralloc allocates or imports image storage; components exchange handles')
    # Kernel frontends share HAB but use distinct graphics and display channels.
    r.add('display-gsl-client','display-android-gpu',[(1265,865),(1265,1230)],flow='control',label='ioctl /dev/hgsl',at=(1265,1195))
    r.add('display-android-gpu','display-khab',[(1390,1260),(1565,1260),(1565,1330)],flow='control',label='habmm_* · MM_GFX',at=(1565,1310),note='GSL control RPC and memory sharing; shared command queues remain an HGSL capability')
    r.add('display-wfd-fe','display-khab',[(1865,1290),(1865,1360),(1690,1360)],flow='control,buffers,events',both=True,note='MM_DISP: OpenWFD requests, imported/exported buffer IDs and completion events')
    # Separate HAB lanes connect the component boundaries through the domain gutter.
    r.add('display-khab','display-wfd-be',[(1440,1350),(1060,1350),(1060,650),(900,650)],
          flow='control,buffers,events',both=True,label='HAB · DISP',at=(1060,850),
          note='HAB MM_DISP: OpenWFD requests, buffer IDs and completion events between Guest KHAB and QNX wfd_be')
    r.add('display-khab','display-qnx-hab',[(1440,1380),(995,1380),(995,770),(900,770)],
          flow='control',both=True,label='HAB · GFX',at=(995,930),
          note='HAB MM_GFX: GSL control RPC and memory sharing between Guest KHAB and QNX UHAB/HAB')
    r.add('display-wfd-be','display-buffers',[(885,685),(885,720),(950,720),(950,1425),(610,1425),(610,1570),(790,1570),(790,1600)],kind='storage',flow='buffers',label='PMEM mapping',at=(610,1490))
    r.add('display-gsl-be','display-qnx-hab',[(725,855),(725,805)],flow='control',both=True,label='habmm_*',at=(725,832),note='GSL HAB Server uses libuhab.so; UHAB calls the QNX HAB resource manager')
    r.add('display-gsl-be','display-qnx-gsl',[(725,925),(725,975)],flow='control',label='gsl_*',at=(725,952),note='The server imports GSL context, memory and command APIs from libGSLUser.so')
    r.add('display-qnx-gsl','display-qnx-gpu',[(725,1045),(725,1095)],flow='control',label='GPU driver IPC',at=(725,1072),note='QNX libGSLUser.so opens /dev/kgsl-3D and calls the KGSL driver through QNX IPC')
    r.add('display-qnx-gpu','display-gpu',[(725,1165),(725,1340),(505,1340),(505,1590),(180,1590),(180,1600)],flow='control',label='GPU HW control',at=(505,1460),note='QNX KGSL controls the GPU hardware; internal queue scheduling is not expanded')
    r.add('display-mdss','display-dpu',[(70,1010),(55,1010),(55,1540),(1265,1540),(1265,1600)],flow='control',label='Display HW programming',at=(235,1540))
    r.add('display-interface-driver','display-output',[(245,1305),(245,1438),(1795,1438),(1795,1600)],flow='control',label='Link / PHY configuration',at=(1795,1538),note='DSI / DP drivers configure the output controller, link timing, PHY and clocks through HAL')
    # The physical pixel path is confined to the shared hardware/output region.
    r.add('display-gpu','display-buffers',[(290,1635),(640,1635)],kind='install',flow='pixels',label='Rendered pixels',at=(460,1635))
    r.add('display-buffers','display-dpu',[(940,1635),(1140,1635)],kind='install',flow='pixels',label='Memory fetch',at=(1040,1635))
    r.add('display-dpu','display-output',[(1390,1635),(1650,1635)],kind='install',flow='pixels',label='Scanout pixels',at=(1515,1635))
    r.add('display-output','display-serializer',[(1795,1670),(1795,1725),(790,1725),(790,1760)],kind='install',flow='pixels',label='DSI / DP',at=(1460,1725))
    r.add('display-serializer','display-deserializer',[(940,1792),(1140,1792)],kind='install',flow='pixels',label='Serial video link',at=(1040,1792))
    r.add('display-deserializer','display-panel',[(1390,1792),(1650,1792)],kind='install',flow='pixels',label='Panel interface',at=(1520,1792))
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
           _text(1015,180,'HAB CHANNELS',10,'#526179',700,'middle')]
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
        title_lines=name.split('\n')
        line_height=18
        text_height=len(title_lines)*line_height+17
        ny=(h-text_height)/2+13
        sy=ny+len(title_lines)*line_height+3
        if m['domain'] != 'qnx':
            if len(title_lines) == 1:
                ny,sy=(18,33) if h<50 else ((22,41) if h<=60 else (27,49))
            else:
                line_height=16
                ny=(h-(len(title_lines)*line_height+17))/2+13
                sy=ny+(len(title_lines)-1)*line_height+17
        shape=_rect(x,y,w,h,fill,stroke,8,1.3)
        if m.get('kind')=='memory':
            shape=_rect(x+8,y-8,w,h,fill,stroke,0)+_rect(x+4,y-4,w,h,fill,stroke,0)+_rect(x,y,w,h,fill,stroke,0)
        if m.get('kind')=='config':
            shape+=f'<path d="M{x+w-18},{y} V{y+18} H{x+w}" fill="none" stroke="{stroke}"/>'
        nodes.append(f'<g class="ota-node" data-sw-module="{mid}" role="button" tabindex="0" aria-pressed="false" aria-label="{escape(m["name"],quote=True)}"><title>{escape(m["name"])}</title>'+shape+''.join(_text(x+12,y+ny+i*line_height,line,13.5,'#20312a',700) for i,line in enumerate(title_lines))+_text(x+12,y+sy,short,11,'#596579')+'</g>')
    defs=['<defs>']
    for kind,color in PALETTE.items():
        defs.append(f'<marker id="display-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,title,kind in [(1010,'Control / IPC','call'),(1230,'Buffer / config references','storage'),(1560,'Pixel data','install'),(1780,'Events / fences','status')]:
        dash=' stroke-dasharray="5 4"' if kind in ('storage','status') else ''
        legend.append(f'<path d="M{x},31 h22" stroke="{PALETTE[kind]}" stroke-width="2"{dash}/>'+_text(x+30,35,title,11,PALETTE[kind],600))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-display-diagram" id="sw-display-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="Arial, sans-serif" role="group" aria-label="Display software component interactions">'
            '<title>Display software component interactions</title><desc>QNX native display clients and Android WFD frontend meet at OpenWFD. Guest rendering uses libgsl.so, qcom_hgsl.ko and msm_hab/KHAB; direct GFX and DISP connections show separate HAB channels to the QNX host. Android follows Java, Native, HAL and Linux Kernel layers. Shared command queues are an HGSL capability. Separate routes show control, shared buffer references, physical pixels and completion events.</desc>'
            +''.join(defs)+f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
            +_text(30,36,'DISPLAY SOFTWARE COMPONENT INTERACTIONS',18,'#202124',700)
            +''.join(legend)+''.join(frame)+routes.render()+'<g class="ota-nodes">'+''.join(nodes)+'</g></svg>')
