"""Widevine in execution domains and explicit software layers.

A single responsive SVG aligns the platform's software, hypervisor, hardware,
protected memory and display. Component identities retain the evidence inspector.
"""
from html import escape
import unicodedata
from software_ota_graph import _rect, _text

WIDTH, HEIGHT = 1600, 2220
NODES = {
    'wv-cdn': (760,128,330,66), 'wv-license': (1210,128,330,66),
    'wv-ta': (58,430,240,84), 'wv-ops': (58,680,240,70),
    'wv-tee-entry': (58,1376,240,64),
    'wv-opslistener': (395,680,260,70),
    'wv-videobe': (395,932,260,66), 'wv-vidc': (395,1040,260,66),
    'wv-wfdbe': (395,1160,260,64), 'wv-mdss': (395,1270,260,64),
    'wv-qcpe': (395,1376,260,64),
    'wv-app': (780,335,250,64), 'wv-web': (1100,335,430,58),
    'wv-eme': (1100,425,430,58),
    'wv-mediacodec': (780,555,220,64), 'wv-mediacrypto': (1040,555,220,64),
    'wv-mediadrm': (1300,555,230,64),
    'wv-bufferchannel': (780,685,220,64), 'wv-cryptohal': (1040,685,220,64),
    'wv-drmhal': (1300,685,230,64),
    'wv-codec': (780,834,220,64), 'wv-cryptoplugin': (1040,834,220,64),
    'wv-plugin': (1300,834,230,64), 'wv-videofe': (780,932,220,66),
    'wv-oemcrypto': (1040,940,490,62), 'wv-cpion': (1180,1021,350,43),
    'wv-composer': (780,1040,220,64), 'wv-gralloc': (780,1120,220,60),
    'wv-qseeapi': (1040,1090,220,64), 'wv-loader': (1300,1090,230,64),
    'wv-kms': (780,1250,220,64), 'wv-qseecom': (1040,1250,220,64),
    'wv-smcinvoke': (1300,1250,230,64), 'wv-scm': (1040,1376,490,64),
    'wv-encrypted': (55,1680,175,104), 'wv-crypto-hw': (275,1680,175,104),
    'wv-bitstream': (495,1680,230,104), 'wv-video': (770,1680,170,104),
    'wv-pixels': (985,1680,235,104), 'wv-dpu': (1270,1680,250,104),
    'wv-plain-dp': (280,1960,210,84),
    'wv-plain-serializer': (620,1960,230,84),
    'wv-plain-deserializer': (1000,1960,230,84),
    'wv-plain-panel': (1380,1960,180,84),
    'wv-hdcp-dp': (280,2090,210,84),
    'wv-hdcp-serializer': (620,2090,230,84),
    'wv-hdcp-deserializer': (1000,2090,230,84),
    'wv-hdcp-panel': (1380,2090,180,84),
}
BUFFER_IDS = {'wv-encrypted', 'wv-bitstream', 'wv-pixels'}
DISPLAY_IDS = {mid for mid in NODES if mid.startswith(('wv-plain-', 'wv-hdcp-'))}
# Short on-canvas captions; source names and duties remain in each inspector.
DISPLAY = {
    'wv-license': ('License Proxy / Service', 'site endpoint / license policy'),
    'wv-cdn': ('Media CDN', 'Manifest / encrypted samples'),
    'wv-app': ('Prime Video App', 'MediaDrm / MediaCodec'),
    'wv-web': ('Web Player (JS)', 'EME · MediaKeys / MediaKeySession'),
    'wv-eme': ('Chrome / MediaDrmBridge', 'EME bridge / Android media pipeline'),
    'wv-mediacodec': ('MediaCodec', 'queueSecureInputBuffer'),
    'wv-mediacrypto': ('MediaCrypto', 'bind session to codec'),
    'wv-mediadrm': ('MediaDrm', 'session / license APIs'),
    'wv-bufferchannel': ('CCodecBufferChannel', 'decrypt / queue / render'),
    'wv-cryptohal': ('CryptoHalAidl', 'ICryptoPlugin'),
    'wv-drmhal': ('DrmHalAidl', 'IDrmPlugin'),
    'wv-codec': ('Codec2 · secure AVC', 'libqcodec2_v4l2codec'),
    'wv-videofe': ('libhyp_video_fe', 'via libhyp_video_intercept'),
    'wv-cryptoplugin': ('WVCryptoPlugin', 'decrypt into secure target'),
    'wv-plugin': ('WVDrmPlugin / WVCdm', 'license / session state'),
    'wv-oemcrypto': ('liboemcrypto.so', 'OEMCrypto session / secure decrypt commands'),
    'wv-cpion': ('libcpion.so', 'protected-memory helper'),
    'wv-composer': ('SurfaceFlinger / HWC', 'protected layer / fence'),
    'wv-gralloc': ('gralloc / DMA-BUF', 'secure-pixel / handles'),
    'wv-qseeapi': ('libQSEEComAPI.so', 'source default'),
    'wv-loader': ('TA Loader / Mink', 'available alternative'),
    'wv-kms': ('msm-hyp / wfd_kms', 'secured source / DMA-BUF'),
    'wv-qseecom': ('qseecom driver', '/dev/qseecom'),
    'wv-smcinvoke': ('smcinvoke driver', '/dev/smcinvoke'),
    'wv-scm': ('qcom_scm / qcom_scm_hab', 'secure calls via HAB · MM_QCPE_VM1'),
    'wv-qcpe': ('qcpe_service', 'HAB backend → SMC'),
    'wv-videobe': ('hyp_video_be', 'HAB · MM_VID'),
    'wv-vidc': ('videoCore / VIDC', 'PMEM / SMMU mapping'),
    'wv-wfdbe': ('wfd_be', 'HAB import / PMEM handle'),
    'wv-mdss': ('OpenWFD / MDSS', 'secure source / scanout'),
    'wv-opslistener': ('qseecom_daemon', 'OPS Listener / OpenWFD OPS'),
    'wv-ta': ('Widevine Trusted App', 'keys / secure operations'),
    'wv-ops': ('OPS', 'output-protection policy'),
    'wv-tee-entry': ('Secure monitor', 'SMC / TEE entry'),
    'wv-encrypted': ('Encrypted input', 'App / MediaCodec · CENC'),
    'wv-crypto-hw': ('Crypto HW', 'secure decryption'),
    'wv-bitstream': ('Secure compressed buffer', 'decrypt output · compressed'),
    'wv-video': ('Video HW / VPU', 'secure decoding'),
    'wv-pixels': ('Secure frame buffers', 'decode output / scanout'),
    'wv-dpu': ('Display HW / MDSS', 'Display SMMU / scanout'),
    'wv-plain-dp': ('SoC DP Output', 'DisplayPort output'),
    'wv-plain-serializer': ('Serializer', 'DP RX · GMSL TX'),
    'wv-plain-deserializer': ('Deserializer', 'GMSL RX · panel output'),
    'wv-plain-panel': ('Display Panel', 'Physical display output'),
    'wv-hdcp-dp': ('SoC DP Output', 'HDCP TX'),
    'wv-hdcp-serializer': ('Serializer', ['DP HDCP RX', 'GMSL HDCP TX']),
    'wv-hdcp-deserializer': ('Deserializer', 'GMSL HDCP RX'),
    'wv-hdcp-panel': ('Display Panel', 'Physical display output'),
}

EDGE_STYLES = {
    'control': ('#3974d9', 1.8, ''),
    'data': ('#23845b', 3.8, ''),
    'buffer': ('#8364b7', 2.1, '8 5'),
    'output': ('#d98324', 2.2, ''),
    'encrypted': ('#5f6368', 2.6, ''),
}


class DiagramRoutes:
    """Orthogonal routes and labels, with explicit content semantics."""
    def __init__(self, view):
        self.view = view
        self.items = []
        self.labels = []

    def add(self, source, target, points, kind='control', flow=None,
            label='', at=None, both=False, note=''):
        if kind not in EDGE_STYLES:
            raise ValueError(f'Unknown Widevine edge kind: {kind}')
        if len(points) < 2 or any(x1 != x2 and y1 != y2 for (x1, y1), (x2, y2) in zip(points, points[1:])):
            raise ValueError(f'Non-orthogonal Widevine route: {source} -> {target}')
        kinds = [kind] + [f for f in (flow or '').split(',') if f and f != kind]
        item = dict(source=source, target=target, points=points, kind=kind,
                    flow=','.join(kinds), both=both, note=note or label)
        self.items.append(item)
        if label:
            if at is None:
                raise ValueError(f'Label position required: {source} -> {target}')
            self.labels.append(dict(source=source, target=target, kind=kind,
                                    flow=item['flow'], label=label, at=at))

    def render(self):
        edges, labels, segments = [], [], []
        prefix = 'wv-' + self.view
        for item in self.items:
            source, target, points = item['source'], item['target'], item['points']
            color, width, dash = EDGE_STYLES[item['kind']]
            attrs = (f'data-ota-from="{source}" data-ota-to="{target}" '
                     f'data-ota-flow="{item["flow"]}" data-edge-kind="{item["kind"]}"')
            bridges = set()
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                for (a, b) in segments:
                    if x1 == x2 and a[1] == b[1] and min(a[0], b[0]) + 5 < x1 < max(a[0], b[0]) - 5 and min(y1, y2) + 5 < a[1] < max(y1, y2) - 5:
                        bridges.add((x1, a[1], 'v'))
                    if y1 == y2 and a[0] == b[0] and min(a[1], b[1]) + 5 < y1 < max(a[1], b[1]) - 5 and min(x1, x2) + 5 < a[0] < max(x1, x2) - 5:
                        bridges.add((a[0], y1, 'h'))
            for x, y, direction in sorted(bridges):
                d = f'M{x},{y-6} V{y+6}' if direction == 'v' else f'M{x-6},{y} H{x+6}'
                edges.append(f'<path class="ota-edge-label wv-crossing" {attrs} d="{d}" fill="none" stroke="#fff" stroke-width="8"/>')
            d = 'M' + ' L'.join(f'{x},{y}' for x, y in points)
            start = f' marker-start="url(#{prefix}-arrow-{item["kind"]})"' if item['both'] else ''
            dashed = f' stroke-dasharray="{dash}"' if dash else ''
            edges.append(f'<path class="ota-edge" {attrs} d="{d}" fill="none" stroke="{color}" '
                         f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" '
                         f'marker-end="url(#{prefix}-arrow-{item["kind"]})"{start}{dashed}>'
                         f'<title>{escape(item["note"] or source + " → " + target)}</title></path>')
            segments.extend(zip(points, points[1:]))
        for item in self.labels:
            x, y = item['at']
            color = EDGE_STYLES[item['kind']][0]
            label = item['label']
            w = max(56, _measure(label, 14) + 20)
            labels.append(f'<g class="ota-edge-label" data-ota-from="{item["source"]}" data-ota-to="{item["target"]}" data-ota-flow="{item["flow"]}">'
                          + _rect(x-w/2, y-17, w, 25, '#fff', color, 5, .55)
                          + _text(x, y, label, 14, color, 600, 'middle') + '</g>')
        return '<g class="ota-connections">' + ''.join(edges) + '</g><g class="ota-labels">' + ''.join(labels) + '</g>'


def _measure(text, size):
    return sum(1 if unicodedata.east_asian_width(c) in ('F', 'W') else .56 for c in text) * size


def _wrap(text, width, size, limit=2):
    """Wrap human-readable captions without shrinking their font size."""
    if _measure(text, size) <= width:
        return [text]
    words = text.split()
    lines, line = [], ''
    for word in words:
        trial = word if not line else line + ' ' + word
        if line and _measure(trial, size) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    if len(lines) > limit:
        raise ValueError(f'Widevine caption needs more than {limit} lines: {text}')
    return lines



def make_routes(view='architecture'):
    if view != 'architecture':
        raise ValueError('Widevine now uses one layered architecture view')
    r = DiagramRoutes(view)
    # Application / framework: media data is distinct from license control.
    r.add('wv-cdn','wv-app',[(925,194),(925,222),(905,222),(905,335)],kind='data')
    r.add('wv-cdn','wv-web',[(925,194),(925,222),(1315,222),(1315,335)],kind='data')
    r.add('wv-web','wv-license',[(1450,335),(1450,194)],both=True,
          label='HTTPS',at=(1450,218))
    r.add('wv-app','wv-license',[(1030,368),(1072,368),(1072,206),(1320,206),(1320,194)],both=True,
          note='App forwards the opaque license challenge and response over HTTPS')
    r.add('wv-web','wv-eme',[(1315,393),(1315,425)],both=True)
    r.add('wv-app','wv-mediadrm',[(1030,390),(1060,390),(1060,500),(1415,500),(1415,555)],
          note='Native session and license API calls')
    r.add('wv-eme','wv-mediadrm',[(1460,483),(1460,555)],
          note='MediaDrmBridge invokes Android MediaDrm')
    r.add('wv-app','wv-mediacodec',[(905,399),(905,470),(890,470),(890,555)],kind='data',
          label='CENC samples',at=(905,450))
    r.add('wv-eme','wv-mediacodec',[(1100,459),(1020,459),(1020,530),(965,530),(965,555)],kind='data')
    r.add('wv-mediadrm','wv-mediacrypto',[(1300,588),(1260,588)],kind='buffer',
          note='Associate the DRM session ID with the codec crypto context')
    r.add('wv-mediacrypto','wv-mediacodec',[(1040,588),(1000,588)],kind='buffer')
    r.add('wv-mediacodec','wv-bufferchannel',[(890,619),(890,685)],label='queue input',at=(890,654))
    r.add('wv-mediacrypto','wv-cryptohal',[(1150,619),(1150,685)])
    r.add('wv-mediadrm','wv-drmhal',[(1415,619),(1415,685)])
    r.add('wv-bufferchannel','wv-cryptohal',[(1000,717),(1040,717)],
          note='decrypt(source, NATIVE_HANDLE destination, IV, subsamples)')
    r.add('wv-cryptohal','wv-cryptoplugin',[(1150,749),(1150,834)],label='AIDL · decrypt',at=(1150,785))
    r.add('wv-drmhal','wv-plugin',[(1415,749),(1415,834)],label='AIDL · session',at=(1415,785))
    r.add('wv-cryptoplugin','wv-oemcrypto',[(1150,898),(1150,940)])
    r.add('wv-plugin','wv-oemcrypto',[(1415,898),(1415,940)])
    r.add('wv-oemcrypto','wv-cpion',[(1450,1002),(1450,1021)],kind='buffer',
          note='Protected-memory helper interfaces. Runtime mapping backend: pending confirmation.')
    # Native vendor libraries and corresponding guest-kernel drivers are parallel branches.
    r.add('wv-oemcrypto','wv-qseeapi',[(1100,1002),(1100,1090)])
    r.add('wv-oemcrypto','wv-loader',[(1530,970),(1550,970),(1550,1075),(1415,1075),(1415,1090)])
    r.add('wv-qseeapi','wv-qseecom',[(1150,1154),(1150,1250)],label='ioctl',at=(1150,1215))
    r.add('wv-loader','wv-smcinvoke',[(1415,1154),(1415,1250)],label='Mink invoke',at=(1415,1215))
    r.add('wv-qseecom','wv-scm',[(1150,1314),(1150,1376)])
    r.add('wv-smcinvoke','wv-scm',[(1415,1314),(1415,1376)])
    r.add('wv-scm','wv-qcpe',[(1040,1408),(655,1408)],both=True,
          label='HAB · MM_QCPE_VM1',at=(850,1408))
    r.add('wv-qcpe','wv-tee-entry',[(395,1408),(298,1408)],both=True,label='SMC',at=(346,1408))
    r.add('wv-tee-entry','wv-ta',[(298,1390),(313,1390),(313,472),(298,472)],both=True,
          note='Secure monitor / TEE dispatches the trusted application invocation')
    # Video and display commands cross only adjacent Android/QNX domains.
    r.add('wv-bufferchannel','wv-codec',[(890,749),(890,834)],label='C2 work',at=(890,790))
    r.add('wv-codec','wv-videofe',[(890,898),(890,932)])
    r.add('wv-videofe','wv-videobe',[(780,950),(655,950)],
          label='MM_VID',at=(716,929),note='HAB commands: video_fe_open / ioctl → hyp_video_be')
    r.add('wv-videofe','wv-videobe',[(780,980),(655,980)],kind='buffer',
          note='HAB transfers exported buffer identities to the QNX video backend')
    r.add('wv-videobe','wv-vidc',[(525,998),(525,1040)])
    r.add('wv-bufferchannel','wv-composer',[(780,717),(744,717),(744,1072),(780,1072)],kind='buffer',
          note='queueToOutputSurface passes a graphic block and fence to SurfaceFlinger / HWC')
    r.add('wv-composer','wv-gralloc',[(890,1104),(890,1120)],kind='buffer')
    r.add('wv-gralloc','wv-kms',[(890,1180),(890,1250)],kind='buffer')
    r.add('wv-composer','wv-kms',[(780,1090),(758,1090),(758,1282),(780,1282)],kind='buffer',
          note='HWC submits a protected layer and framebuffer reference')
    r.add('wv-kms','wv-wfdbe',[(780,1282),(718,1282),(718,1192),(655,1192)],kind='buffer',
          label='WFD / HAB',at=(716,1242),note='dma_buf export ID is imported as an existing PMEM handle')
    r.add('wv-wfdbe','wv-mdss',[(525,1224),(525,1270)],kind='buffer')
    # Protection policy is a separate loop, not the OEMCrypto command transport.
    r.add('wv-ta','wv-ops',[(178,514),(178,680)],kind='output',both=True,
          label='content policy',at=(178,596))
    r.add('wv-ops','wv-opslistener',[(298,715),(395,715)],kind='output',both=True,
          label='OPS',at=(347,695))
    r.add('wv-opslistener','wv-mdss',[(655,715),(682,715),(682,1302),(655,1302)],kind='output',both=True,
          note='OPS listener exchanges minimum protection requirements and actual output state with OpenWFD / MDSS')
    # Device programming is separate from DDR payloads and buffer references.
    r.add('wv-ta','wv-crypto-hw',[(58,472),(32,472),(32,1640),(362,1640),(362,1680)],
          label='secure decrypt',at=(188,1640),note='Trusted decryption control. Crypto IP: pending confirmation.')
    r.add('wv-vidc','wv-video',[(395,1073),(370,1073),(370,1607),(855,1607),(855,1680)],
          label='decode / SMMU',at=(760,1607))
    r.add('wv-mdss','wv-dpu',[(655,1320),(668,1320),(668,1634),(1395,1634),(1395,1680)],
          label='scanout / SMMU',at=(1230,1634))
    r.add('wv-bufferchannel','wv-bitstream',[(1000,738),(1010,738),(1010,1580),(610,1580),(610,1680)],kind='buffer',
          label='native_handle · secure target',at=(800,1580),
          note='CCodecBufferChannel supplies a native_handle for the protected decryption destination')
    r.add('wv-gralloc','wv-pixels',[(1000,1150),(1025,1150),(1025,1560),(1100,1560),(1100,1680)],kind='buffer',
          note='Protected gralloc pixel buffers / native handles; device mappings use secure contexts')
    # Hardware accesses the encrypted/secure memory stages below. No CPU pixel IPC is implied.
    for a,b,sx,tx in [('wv-encrypted','wv-crypto-hw',230,275),
                      ('wv-crypto-hw','wv-bitstream',450,495),
                      ('wv-bitstream','wv-video',725,770),
                      ('wv-video','wv-pixels',940,985),
                      ('wv-pixels','wv-dpu',1220,1270)]:
        r.add(a,b,[(sx,1732),(tx,1732)],kind='data',
              note='Media data read and written by the secure decrypt, video and display engines')
    # Alternative output topologies share the same display-engine source.
    r.add('wv-dpu','wv-plain-dp',[(1395,1784),(1395,1880),(250,1880),(250,2002),(280,2002)],kind='data',
          label='Display pixels',at=(810,1880))
    r.add('wv-dpu','wv-hdcp-dp',[(1395,1784),(1395,1880),(250,1880),(250,2132),(280,2132)],kind='data',
          note='Use the HDCP output configuration when required by the OTT service')
    for mode, cy in [('plain',2002),('hdcp',2132)]:
        prefix='wv-'+mode+'-'
        kind='encrypted' if mode=='hdcp' else 'data'
        r.add(prefix+'dp',prefix+'serializer',[(490,cy),(620,cy)],kind=kind,flow='data',
              label='DP + HDCP' if mode=='hdcp' else 'DP',at=(555,cy))
        r.add(prefix+'serializer',prefix+'deserializer',[(850,cy),(1000,cy)],kind=kind,flow='data',
              label='GMSL + HDCP' if mode=='hdcp' else 'GMSL',at=(925,cy))
        r.add(prefix+'deserializer',prefix+'panel',[(1230,cy),(1380,cy)],kind='data',
              label='Panel interface',at=(1305,cy))
    return r


def _node(module, box):
    x,y,w,h=box
    mid=module['id']; buffer=mid in BUFFER_IDS
    palette={'cloud':('#f8faff','#b6c8e8'),'tee':('#fffaf0','#ddc077'),
             'qnx':('#ffffff','#abc0dc'),'aaos':('#ffffff','#a9c5b1'),
             'guest-kernel':('#f7fbf8','#a9c5b1'),'hardware':('#fff','#b1bdcc'),
             'buffer':('#e9f6ee','#77ae8b')}
    fill,stroke=palette.get(module['domain'],palette['hardware'])
    if mid=='wv-encrypted':fill,stroke='#f5f7fa','#b1bdcc'
    if mid in DISPLAY_IDS:fill,stroke='#9aa0a6','none'
    if buffer:
        shape=(f'<path d="M{x+15},{y} H{x+w} L{x+w-15},{y+h} H{x} Z" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
               f'<path d="M{x+3},{y+h+6} H{x+w-12}" fill="none" stroke="{stroke}"/>')
        inset=23
    else:
        shape=_rect(x,y,w,h,fill,stroke,10,1.3);inset=12
    title,sub=DISPLAY[mid]
    names=_wrap(title,w-inset-10,17,limit=2)
    captions=[line for part in (sub if isinstance(sub,list) else [sub])
              for line in _wrap(part,w-inset-10,13,limit=2)]
    if h<=50:
        # The helper library stays a subordinate row in the OEMCrypto card.
        content=_text(x+12,y+20,title,16,'#253242',700)+_text(x+12,y+38,sub,12,'#637286')
    else:
        first=y+25
        content=''.join(_text(x+inset,first+i*21,line,17,'#253242',700) for i,line in enumerate(names))
        sy=first+(len(names)-1)*21+22
        content+=''.join(_text(x+inset,sy+i*17,line,13,'#253242' if mid in DISPLAY_IDS else '#637286') for i,line in enumerate(captions))
        if sy+(len(captions)-1)*17>y+h-5:raise ValueError(f'Text overflow: {mid}')
    return (f'<g class="ota-node" data-sw-module="{mid}" data-node-kind="{"buffer" if buffer else "component"}" '
            f'role="button" tabindex="0" aria-label="{escape(module["name"],quote=True)}" aria-pressed="false">'
            f'<title>{escape(module["name"])}</title>'+shape+content+'</g>')


def _panel(x,y,w,h,title,subtitle,fill,stroke):
    return (_rect(x,y,w,h,fill,stroke,22,1.5)+_text(x+20,y+34,title,23,'#243348',700)
            +_text(x+20,y+60,subtitle,14,'#637286'))


def _band(x,y,w,h,title,fill='#ffffffa6'):
    return ('<g class="wv-software-layer" data-layer="'+escape(title)+'">'
            +_rect(x,y,w,h,fill,'#dbe5df',10,.8)
            +_text(x+12,y+23,title,15,'#54705e',700)+'</g>')


def _frame():
    out=[
        _text(24,38,'Widevine DRM',27,'#243348',700),
        _text(24,66,'Execution domains · software layers · protected media',16,'#637286'),
        _text(24,144,'CONTENT SERVICES',14,'#637286',700),
        _text(24,174,'License exchange / encrypted media delivery',15,'#637286'),
        _panel(20,235,310,1293,'TEE','Trusted software / secure world','#fffaf0','#e5d5ac'),
        _panel(350,235,350,1223,'QNX','Host services / resource owners','#eef4fc','#c0d0e6'),
        _rect(730,235,850,1223,'#eef7f0','#bed7c5',22,1.5),
        _text(750,269,'Android',23,'#243348',700),
        _text(1100,269,'AAOS guest',14,'#637286'),
        _band(746,285,818,207,'Applications'),
        _band(746,510,818,264,'Framework'),
        _band(746,790,818,404,'Native / HAL'),
        _band(746,1200,818,248,'Linux kernel'),
        _rect(45,336,265,958,'#ffffff88','#eadfc3',12),
        _text(60,365,'Trusted applications / services',15,'#8d742d',700),
        _text(60,827,'Key management /',17,'#8d742d',700),
        _text(60,858,'secure decryption',17,'#8d742d',700),
        _text(60,883,'Trusted services in TEE',14,'#8d742d'),
        _rect(45,1315,265,194,'#ffffff88','#eadfc3',12),
        _text(60,1344,'Secure platform',15,'#8d742d',700),
        _rect(375,570,300,215,'#ffffff99','#d2deed',12),
        _text(390,598,'Output protection service',15,'#526f96',700),
        _text(390,623,'Protection requirements / output state',13,'#637286'),
        _rect(375,803,300,544,'#ffffff99','#d2deed',12),
        _text(390,833,'Video / display services',15,'#526f96',700),
        _text(390,858,'Host backends and device drivers',13,'#637286'),
        _text(390,884,'Device control / protected buffers',13,'#637286'),
        _text(395,1365,'Secure-call transport',14,'#526f96',700),
        _text(375,335,'QNX Neutrino RTOS',17,'#526f96',700),
        _text(375,367,'Video, display and secure calls',14,'#637286'),
        _text(375,391,'are handled by host services.',14,'#637286'),
        # Grouped framework families and vendor DRM library card.
        _rect(768,538,244,224,'#f5faf6','#d0dfd4',10),
        _rect(1028,538,244,224,'#f5faf6','#d0dfd4',10),
        _rect(1288,538,254,224,'#f5faf6','#d0dfd4',10),
        _rect(1028,820,514,245,'#f5faf6','#d0dfd4',10),
        _rect(768,1028,244,159,'#f5faf6','#d0dfd4',10),
        _rect(350,1474,1230,54,'#f1eef9','#cfc6e3',12,1.4),
        _text(375,1508,'QNX Hypervisor',20,'#655580',700),
        _text(1120,1507,'VM isolation / resource assignment',14,'#655580'),
        _panel(20,1550,1560,319,'Hardware','SoC engines + memory objects','#f5f7fa','#c7d0dc'),
        _text(55,1667,'Ordinary input',13,'#637286',700),
        _text(495,1667,'Protected memory',13,'#23845b',700),
        _text(985,1667,'Protected memory',13,'#23845b',700),
        _text(495,1818,'CP_B_VIDEO · VPU bitstream',14,'#54705e',700),
        _text(985,1818,'CP_P_VIDEO · VPU pixels',14,'#54705e',700),
        _text(55,1846,'GraphicBuffer / fence links decoded frames to Surface / HWC. CP_B_VIDEO and CP_P_VIDEO select video SMMU contexts.',14,'#637286'),
        _panel(20,1890,1560,310,'Display Output','Alternative configurations','#fff','#c7d0dc'),
        _text(45,2006,'Without HDCP',15,'#253242',700),
        _text(45,2136,'With HDCP',15,'#253242',700),
        _text(45,2190,'Use HDCP when required by the OTT service.',13,'#637286'),
        '<circle cx="250" cy="2002" r="3" fill="#23845b"/>',
    ]
    for top in [1938,2068]:
        out.append(f'<rect class="wv-display-module" x="978" y="{top}" width="594" height="118" rx="7" fill="#9aa0a6" fill-opacity=".04" stroke="#5f6368" stroke-width="1.2" stroke-dasharray="6 5"/>')
        out.append(_text(994,top+15,'Display Module',12,'#5f6368',600))
    return ''.join(out)


def render_graph(modules):
    by_id={m['id']:m for m in modules}
    assert set(NODES)==set(by_id), f'Module mismatch: {set(NODES)^set(by_id)}'
    defs=['<defs>']
    for kind,(color,_,_) in EDGE_STYLES.items():
        defs.append(f'<marker id="wv-architecture-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                    f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.3"/></marker>')
    defs.append('</defs>')
    legend=[]
    for x,kind,label in [(24,'control','Control / IPC'),(260,'data','Video data'),(475,'buffer','Buffer / handle'),(740,'output','Protection policy'),(1045,'encrypted','Encrypted link / HDCP')]:
        color,width,dash=EDGE_STYLES[kind];dashed=f' stroke-dasharray="{dash}"' if dash else ''
        legend.append(f'<path d="M{x},96 h34" stroke="{color}" stroke-width="{width}"{dashed}/>'+_text(x+43,101,label,15,color,600))
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" class="sw-ota-diagram sw-widevine-diagram" '
         f'id="sw-widevine-architecture-diagram" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
         f'font-family="Noto Sans CJK SC, Arial, sans-serif" role="group" aria-label="Widevine: TEE, QNX and Android software layers above Hypervisor, Hardware and Display">'
         '<title>Widevine DRM: execution domains and software layers</title>'
         '<desc>Display Output compares alternative configurations without HDCP and with HDCP. Dashed Display Module boundaries group the screen-side deserializer, panel interface and display panel.</desc>'+''.join(defs)
         +f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'+_frame()+''.join(legend)
         +make_routes().render()+'<g class="ota-nodes">'
         +''.join(_node(by_id[mid],box) for mid,box in NODES.items())+'</g></svg>')
    return '<div id="sw-widevine-diagram" class="sw-widevine-diagrams">'+svg+'</div>'
