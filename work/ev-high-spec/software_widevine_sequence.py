"""Numbered, responsive Widevine playback sequence diagrams.

Four views expand different parts of the same logical playback process. The
numbers locate operations; they are not timestamps from one captured session.
The security subroutine is reusable, and output policy runs alongside rendering.
"""
from html import escape
import unicodedata

WIDTH = 1600
COLORS = {
    'control': '#3974d9', 'data': '#23845b',
    'buffer': '#8364b7', 'output': '#d98324',
}
PALETTES = {
    'app': ('#f1f7f2', '#b8d7c2'), 'qnx': ('#edf4ff', '#bdd0ee'),
    'tee': ('#fff8e7', '#e5cb86'), 'cloud': ('#f2f5fc', '#c7d4eb'),
    'hardware': ('#eaf6ef', '#9fcab1'), 'mixed': ('#f7f4fd', '#d0c4e8'),
}


def msg(n, source, target, label, kind='control', reply=False, ref=False, note=''):
    return dict(n=n, source=source, target=target, label=label, kind=kind,
                reply=reply, ref=ref, note=note)


PHASES = [
    dict(
        key='a', title='A · 会话与许可证',
        subtitle='App 通过 MediaDrm 管理 DRM 会话，网页通过 EME 和 Chrome 调用对应的 Android 接口。',
        actors=[
            ('p', 'App / Chrome bridge', 'app'),
            ('d', 'MediaDrm /\nDrmHalAidl', 'app'),
            ('w', 'WVDrmPlugin /\nWVCdm', 'app'),
            ('l', 'License Proxy /\nService', 'cloud'),
        ],
        before=[('Web 入口', [
            'requestMediaKeySystemAccess → createMediaKeys；setMediaKeys 绑定 video，createSession 创建 JS 会话。',
            'generateRequest 提交 initData，Chrome 在内部创建 DRM 会话并生成许可证请求。',
            'setMediaKeys 绑定媒体元素，createSession 创建网页会话。底层调用时点由浏览器实现决定。',
            'initData 可来自 encrypted 事件或清单 / 容器；CENC 通常使用 PSSH。',
        ])],
        groups=[],
        messages=[
            msg(1,'p','d','openSession()\nWeb: generateRequest 内部触发'),
            msg(2,'d','w','AIDL openSession\n创建原生 DRM 会话'),
            msg(3,'w','w','ref 图 B\n必要的 L1 安全调用',ref=True),
            msg(4,'w','d','返回 session ID\n关联 DRM 会话',reply=True),
            msg(5,'d','p','原生会话标识\nWeb 由浏览器关联',reply=True),
            msg(6,'p','d','getKeyRequest(sessionId, initData, …)\n同次 generateRequest 的后续步骤'),
            msg(7,'d','w','AIDL getKeyRequest\n生成 DRM 消息'),
            msg(8,'w','d','challenge\n不透明请求字节',reply=True),
            msg(9,'d','p','KeyRequest / message 事件\n交由 App / 网页处理',reply=True),
            msg(10,'p','l','HTTPS 发送 challenge\n附站点所需身份信息'),
            msg(11,'l','p','许可证响应\n或拒绝授权',reply=True),
            msg(12,'p','d','provideKeyResponse(sessionId, response)\nWeb: session.update(response)'),
            msg(13,'d','w','AIDL provideKeyResponse\n交回 Widevine'),
            msg(14,'w','w','ref 图 B\n必要的密钥加载安全操作',ref=True),
            msg(15,'w','d','许可证加载操作结果\nstreaming: 无 keySetId',reply=True),
            msg(16,'d','p','许可证响应处理完成\n密钥状态异步通知',reply=True),
        ],
        after=[('opt · 仅在需要时进行 Provisioning', [
            'NotProvisioned / 需要配置 → getProvisionRequest → App / 浏览器访问 Provisioning Server → provideProvisionResponse → 重试原操作。',
            'Provisioning Server 提供设备配置服务。服务证书与许可证消息可分多轮交换，内容密钥状态通过事件通知。',
            'MediaDrm keys-change / EME keystatuseschange 通知密钥状态。所需密钥进入 usable 状态后可执行解密。',
        ])],
        caption='许可证端点包括站点代理及许可证后端。图中按职责组织参与者，Prime Video 的服务端部署待确认。',
    ),
    dict(
        key='b', title='B · 可复用的安全调用子过程',
        subtitle='展开会话、密钥加载和安全解密中复用的 TEE 调用过程。编号用于定位接口步骤。',
        actors=[
            ('o','liboemcrypto.so\n普通侧调用入口','app'),
            ('b','QSEECom / Mink\n库 + guest driver','app'),
            ('s','qcom_scm /\nqcom_scm_hab','app'),
            ('q','qcpe_service\nQNX host','qnx'),
            ('e','Secure monitor /\nTEE entry','tee'),
            ('t','Widevine TA','tee'),
        ],
        before=[('调用边界', [
            'QSEECom 与 TA Loader/Mink 是两种调用分支，各自经对应 guest 驱动进入 SCM。',
        ])],
        groups=[dict(start=17,end=20,title='alt · QSEECom（源码默认）',split=19,
                     split_title='else · TA Loader / Mink（可用路径）')],
        messages=[
            msg(17,'o','b','QSEECom_send_cmd /\nmodified_cmd\n/dev/qseecom + ioctl'),
            msg(18,'b','s','qcom_scm_qseecom_call\nSCM 安全调用'),
            msg(19,'o','b','TA Loader / Mink invoke\n/dev/smcinvoke + ioctl'),
            msg(20,'b','s','qcom_scm_invoke_smc\n或 legacy 入口'),
            msg(21,'s','q','HAB · MM_QCPE_VM1\n安全调用消息'),
            msg(22,'q','e','qcpe_send_smc\n安全监控调用'),
            msg(23,'e','t','分派可信应用操作\n会话 / 密钥 / crypto 策略'),
            msg(24,'t','e','返回操作结果\n及状态信息',reply=True),
            msg(25,'e','q','SMC 返回',reply=True),
            msg(26,'q','s','HAB 回复',reply=True),
            msg(27,'s','b','驱动调用返回',reply=True),
            msg(28,'b','o','OEMCrypto 操作结果',reply=True),
        ],
        after=[('源码选择与运行观察', [
            '源码默认 WIDEVINE_USES_SMCINVOKE=false，预编译库同时提供 Mink 分支。状态：实际运行分支及库版本待确认。',
        ])],
        caption='HAB 传递安全调用参数和结果。QNX qcpe_service 执行安全监控调用，TEE 入口分派可信服务操作。',
    ),
    dict(
        key='c', title='C · 安全解密与视频解码',
        subtitle='加密样本经安全解密形成受保护压缩码流，再由 VPU 解码为受保护像素。',
        actors=[
            ('p','App / Chrome\nmedia pipeline','app'),
            ('m','MediaCodec /\nCCodecBufferChannel','app'),
            ('c','CryptoHalAidl /\nWVCryptoPlugin','app'),
            ('o','OEMCrypto 调用 /\n可信解密路径','mixed'),
            ('v','Codec2 / Video FE','app'),
            ('h','hyp_video_be /\nvideoCore (QNX)','qnx'),
            ('b','受保护缓冲 /\nVPU','hardware'),
        ],
        before=[('会话绑定与就绪条件', [
            'MediaCrypto(uuid, sessionId) / setMediaDrmSession 关联 DRM 会话。Codec 配置与许可证准备可交叠执行。',
            '所需内容密钥可用后执行安全解密，OEMCrypto 提供普通侧调用接口。参与者按职责分组。',
        ])],
        groups=[],
        messages=[
            msg(29,'p','m','configure(…)\nSurface + MediaCrypto',note='MediaCodec.configure(format, surface, crypto, flags) associates the output Surface and MediaCrypto object'),
            msg(30,'p','m','queueSecureInputBuffer(…)\n密文 + key ID / IV / subsamples'),
            msg(31,'m','c','decrypt(source,\nNATIVE_HANDLE target)\n密文源与安全目标分开'),
            msg(32,'c','o','请求安全解密\n必要调用 ref 图 B'),
            msg(33,'o','b','安全实现写入目标\n输出受保护的压缩码流','data',
                note='The secure implementation decrypts encrypted samples into the protected compressed-video buffer.'),
            msg(34,'o','c','返回解密结果\n及状态信息',reply=True),
            msg(35,'c','m','decrypt 返回写入字节数\n保留受保护 block 引用',reply=True),
            msg(36,'m','v','queueInputBufferInternal\nC2 work / block handle','buffer'),
            msg(37,'v','h','video_fe_ioctl\nHAB · MM_VID\n命令 + buffer export ID','buffer',note='Video FE sends control commands and exported buffer IDs over HAB.'),
            msg(38,'h','b','VIDC 安全 SMMU 映射\nCP_B_VIDEO /\nCP_P_VIDEO'),
            msg(39,'b','b','VPU 读受保护压缩码流\n写入受保护解码像素','data'),
            msg(40,'h','v','解码完成\nbuffer 引用','buffer',reply=True),
            msg(41,'v','m','输出 graphic block\n与完成状态','buffer',reply=True),
        ],
        after=[('硬件与缓冲语义', [
            'CP_B_VIDEO / CP_P_VIDEO 分别提供压缩码流和像素的 SMMU 安全访问上下文。状态：具体解密硬件 IP 待确认。',
            'Codec2 / Video FE 包含 libqcodec2_v4l2codec 和 libhyp_video_intercept / FE。安全实现写入受保护缓冲，VPU 完成解码。',
        ])],
        caption='第 36–41 步依次传递 C2 block、buffer export ID、输出 graphic block 和解码完成状态。',
    ),
    dict(
        key='d', title='D · 显示提交与并行输出保护',
        subtitle='显示提交与 OPS 输出保护协同可并行执行。HDCP 按内容保护要求及链路状态启用。',
        actors=[
            ('m','MediaCodec /\nSurface','app'),
            ('s','SurfaceFlinger /\nHWC','app'),
            ('k','msm-hyp /\nwfd_kms','app'),
            ('h','wfd_be / OpenWFD /\nMDSS (QNX)','qnx'),
            ('t','Widevine TA /\nOPS (TEE)','tee'),
            ('o','qseecom_daemon\nOPS Listener (QNX)','qnx'),
            ('d','Display HW /\nHDCP','hardware'),
        ],
        before=[],
        groups=[
            dict(start=42,end=53,title='par · 显示提交支路',split=47,
                 split_title='并行支路 · 输出保护要求、拓扑与状态'),
            dict(start=54,end=54,title='允许输出 · 保护要求满足'),
            dict(start=55,end=57,title='状态变化 / 保护不足 · 限制受保护输出'),
        ],
        messages=[
            msg(42,'m','m','收到 releaseOutputBuffer(index, true)\n内部 queueToOutputSurface',note='The player triggers releaseOutputBuffer(index, true); the MediaCodec / Surface group then runs the internal output-surface operation'),
            msg(43,'m','s','graphic block + fence\n提交受保护图层','buffer'),
            msg(44,'s','k','Linux DRM framebuffer /\natomic 提交\nsecure layer 标志','buffer'),
            msg(45,'k','h','HAB export ID +\nsecured WFD source\n导入已有 buffer','buffer'),
            msg(46,'h','d','PMEM handle → 显示 SMMU\n配置待扫描缓冲'),
            msg(47,'t','o','内容所需输出保护\n最低保护等级','output'),
            msg(48,'o','h','查询拓扑 / 配置输出保护\nOPS ↔ OpenWFD / MDSS','output'),
            msg(49,'h','d','需要时认证并启用 HDCP\n连接建立或状态变化','output'),
            msg(50,'d','h','链路能力 / 认证 / 加密状态','output',reply=True),
            msg(51,'h','o','当前显示状态','output',reply=True),
            msg(52,'o','t','输出保护状态反馈','output',reply=True),
            msg(53,'t','t','比较许可证要求\n与实际输出状态','output'),
            msg(54,'d','d','保护要求满足时扫描输出\n读取受保护 scanout buffer','data'),
            msg(55,'t','o','限制受保护输出','output'),
            msg(56,'o','h','更新输出限制','output'),
            msg(57,'h','d','停止不满足要求的受保护输出','output'),
        ],
        after=[('实际显示路径', [
            'SurfaceFlinger/HWC 按需要采用硬件图层或受保护 GPU 合成。HAB 传递显示缓冲引用，QNX 配置扫描输出。',
            '输出保护根据端口能力、认证及加密状态判断。状态：本次播放的实际 HDCP 状态待验证。',
        ])],
        caption='42–46 为显示提交，47–53 为输出保护协同。满足保护要求后输出画面，状态变化导致保护不足时限制输出。',
    ),
]


def _measure(text, size):
    return sum(1 if unicodedata.east_asian_width(c) in ('F','W') else .53 for c in text) * size


def _wrap(text, width, size):
    """Wrap readable copy at whitespace; keep API identifiers intact."""
    result=[]
    for explicit in text.split('\n'):
        if _measure(explicit,size)<=width:
            result.append(explicit);continue
        words=explicit.split(' ')
        if len(words)==1:
            # CJK copy can break between characters; API names stay intact.
            if all(ord(c)<128 or c=='…' for c in explicit):
                result.append(explicit);continue
            chunks=[];chunk=''
            for c in explicit:
                if chunk and _measure(chunk+c,size)>width:
                    chunks.append(chunk);chunk=''
                chunk+=c
            if chunk:chunks.append(chunk)
            result.extend(chunks);continue
        line=''
        for word in words:
            trial=word if not line else line+' '+word
            if line and _measure(trial,size)>width:
                result.append(line);line=word
            else:line=trial
        if line:result.append(line)
    return result


def _text(x,y,text,size=17,color='#253242',weight=500,anchor='start'):
    return (f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{color}">{escape(text)}</text>')


def _rect(x,y,w,h,fill='#fff',stroke='#dce3ed',rx=10,sw=1):
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}"/>'


def _note_layout(blocks, y):
    laid=[]
    for title,paragraphs in blocks:
        lines=[]
        for p in paragraphs:lines.extend(_wrap(p,WIDTH-100,17))
        h=54+len(lines)*25
        laid.append(dict(y=y,h=h,title=title,lines=lines))
        y+=h+16
    return laid,y


def _message_lines(item, xs):
    source,target=xs[item['source']],xs[item['target']]
    available=340 if source==target else max(224,abs(target-source)-25)
    lines = _wrap(item['label'],available,17)
    lines[0] = f"{item['n']:02d} · {lines[0]}"
    return lines,available


def layout_phase(phase):
    n=len(phase['actors'])
    before,cursor=_note_layout(phase['before'],94)
    actor_y=cursor+9
    card_w=min(300,(WIDTH-260)/(n-1)-14)
    side=max(130,card_w/2+26)
    xs={actor[0]:side+i*(WIDTH-2*side)/(n-1) for i,actor in enumerate(phase['actors'])}
    actor_lines={a[0]:_wrap(a[1],card_w-24,18) for a in phase['actors']}
    actor_h=max(76,28+max(map(len,actor_lines.values()))*23)
    cursor=actor_y+actor_h+38
    starts={g['start']:g for g in phase['groups']}
    splits={g['split']:g for g in phase['groups'] if g.get('split')}
    ends={g['end']:g for g in phase['groups']}
    rows=[];groups=[];active=None
    for item in phase['messages']:
        if item['n'] in starts:
            active=dict(starts[item['n']]);active['y']=cursor-7;active['split_y']=None
            cursor+=40
        if item['n'] in splits:
            if active:active['split_y']=cursor
            cursor+=43
        lines,label_width=_message_lines(item,xs)
        arrow_y=cursor+len(lines)*23+12
        self_call=item['source']==item['target'] and not item['ref']
        bottom=arrow_y+(36 if self_call else 0)+25
        rows.append(dict(item=item,lines=lines,label_width=label_width,arrow_y=arrow_y,bottom=bottom))
        cursor=bottom+12
        if item['n'] in ends:
            if active:
                active['h']=cursor-active['y']
                groups.append(active);active=None
            cursor+=19
    line_end=cursor+8
    after,cursor=_note_layout(phase['after'],line_end+30)
    return dict(xs=xs,before=before,after=after,actor_y=actor_y,actor_h=actor_h,
                actor_lines=actor_lines,card_w=card_w,rows=rows,groups=groups,
                line_end=line_end,height=cursor+15)


def _notes(blocks):
    out=[]
    for b in blocks:
        out.append(_rect(24,b['y'],WIDTH-48,b['h'],'#f7f9fd','#dce4ef',12))
        out.append(_text(42,b['y']+29,b['title'],18,'#355785',700))
        for i,line in enumerate(b['lines']):out.append(_text(42,b['y']+57+i*25,line,17,'#526179'))
    return ''.join(out)


def render_phase(phase):
    layout=layout_phase(phase);xs=layout['xs'];prefix='wv-seq-'+phase['key']
    height=layout['height']
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" id="{prefix}-diagram" class="wv-sequence-diagram" '
         f'viewBox="0 0 {WIDTH} {height:g}" width="{WIDTH}" height="{height:g}" '
         f'font-family="Noto Sans CJK SC, Arial, sans-serif" role="img" aria-label="{escape(phase["title"],quote=True)}">',
         '<title>'+escape(phase['title'])+'</title>',
         '<desc>Widevine 播放逻辑时序，包含会话、许可证、安全解密、视频解码及输出保护。参与者按职责分组，编号用于定位步骤。</desc>',
         '<defs>']
    for kind,color in COLORS.items():
        out.append(f'<marker id="{prefix}-{kind}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                   f'<path d="M0,0 L10,5 L0,10 Z" fill="{color}"/></marker>')
    out += ['</defs>',_rect(0,0,WIDTH,height,'#fff','none',0),
            _text(26,37,phase['title'],26,'#202124',700),
            _text(26,70,phase['subtitle'],17,'#526179'),_notes(layout['before'])]
    # Conditional frames sit behind lifelines and message labels.
    for g in layout['groups']:
        out.append(_rect(61,g['y'],WIDTH-85,g['h'],'#f9fbfe','#c8d5e7',8,1.2))
        out.append(_text(78,g['y']+28,g['title'],18,'#355785',700))
        if g['split_y'] is not None:
            sy=g['split_y']
            out.append(f'<path d="M61,{sy:g} H{WIDTH-24}" stroke="#b9c9df" stroke-dasharray="7 5" fill="none"/>')
            out.append(_text(78,sy+28,g['split_title'],18,'#355785',700))
    for aid,title,palette in phase['actors']:
        x=xs[aid];fill,stroke=PALETTES[palette]
        out.append(f'<path d="M{x:g},{layout["actor_y"]+layout["actor_h"]:g} V{layout["line_end"]:g}" '
                   'stroke="#c5cdd8" stroke-width="1.2" stroke-dasharray="5 6"/>')
        out.append(_rect(x-layout['card_w']/2,layout['actor_y'],layout['card_w'],layout['actor_h'],fill,stroke,10,1.3))
        lines=layout['actor_lines'][aid]
        top=layout['actor_y']+(layout['actor_h']-len(lines)*23)/2+18
        for i,line in enumerate(lines):out.append(_text(x,top+i*23,line,18,'#243348',700,'middle'))
    for row in layout['rows']:
        item=row['item'];sy=row['arrow_y'];sx=xs[item['source']];tx=xs[item['target']]
        color=COLORS[item['kind']]
        out.append(f'<g class="wv-sequence-message" data-sequence-step="{item["n"]}" data-sequence-kind="{item["kind"]}">')
        if item['note']:out.append('<title>'+escape(item['note'])+'</title>')
        if item['ref']:
            w=min(330,row['label_width'])
            y=sy-len(row['lines'])*23-3
            h=len(row['lines'])*23+16
            out.append(_rect(sx-w/2,y,w,h,'#f5f1fd','#c9bae4',8,1.2))
            for i,line in enumerate(row['lines']):out.append(_text(sx,y+24+i*23,line,17,'#715397',600,'middle'))
        else:
            self_call=sx==tx
            if self_call:
                direction=-1 if sx>WIDTH-380 else 1
                bend=sx+direction*88
                label_x=sx+direction*174
                d=f'M{sx:g},{sy:g} H{bend:g} V{sy+36:g} H{sx:g}'
            else:
                label_x=(sx+tx)/2;d=f'M{sx:g},{sy:g} H{tx:g}'
            dash=' stroke-dasharray="7 5"' if item['reply'] or item['kind']=='buffer' else ''
            width=2.6 if item['kind']=='data' else 1.8
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
                       f'marker-end="url(#{prefix}-{item["kind"]}-arrow)"/>')
            # White label backing keeps the labels legible where other lifelines pass.
            widest=max(_measure(line,17) for line in row['lines'])
            label_top=sy-len(row['lines'])*23-3
            out.append(_rect(label_x-widest/2-8,label_top,widest+16,len(row['lines'])*23,'#fff','none',4))
            for i,line in enumerate(row['lines']):
                out.append(_text(label_x,label_top+19+i*23,line,17,color,500,'middle'))
        out.append('</g>')
    out.append(_notes(layout['after']))
    out.append('</svg>')
    return ''.join(out)


def render_sequence():
    """Return four responsive, self-contained figures with unique SVG ids."""
    figures=[]
    for phase in PHASES:
        figures.append('<figure class="wv-sequence-panel" data-sequence-phase="'+phase['key']+'">'
                       +render_phase(phase)+'<figcaption>'+escape(phase['caption'])+'</figcaption></figure>')
    return '<div id="wv-playback-sequence">'+''.join(figures)+'</div>'
