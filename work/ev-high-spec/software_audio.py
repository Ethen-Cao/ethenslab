"""Audio design v1.5 mapped to the current QNX and Android source tree."""
from html import escape
from software_audio_graph import render_graph
from software_audio_routing import render_routing, DATA as ROUTING_DATA

MODULES = [
    dict(id='audio-client', name='libaudiomgr_if', domain='qnx', short='Cluster audio client API', duty='仪表业务使用的音频客户端库，通过项目本地 IPC 请求 audiomgr 播放、停止或调整提示音，并接收播放状态；客户端库与服务进程分别构建。'),
    dict(id='audio-manager', name='audiomgr', domain='qnx', short='Chime scheduling · priority', duty='项目实际的仪表提示音服务；管理播放队列、优先级、互斥及音量。QNX 构建默认选择 csd2pcm_player 后端，HBEZ 预置 SLM 启动该进程。对应文档中的 chime_play 能力，不将示例名另画为项目服务。'),
    dict(id='audio-avas', name='avas_service', domain='qnx', short='Document reference', reference=True, duty='设计文档描述的低速提示音接口，向外部扬声器输出 AVAS 音频。本次未定位到项目服务实现和启动证据；以文档参考模块及虚线接口展示，不声明已集成算法。'),
    dict(id='audio-csd-client', name='libcsd2IpcClient', domain='qnx', short='CSD2 session API', duty='audiomgr 的 QNX CSD2 后端所链接的客户端库；通过 csd2_open、csd2_ioctl 等接口配置音频会话、格式、缓冲及读写，与服务端进行本地 IPC 和回调交互。'),
    dict(id='audio-service', name='audio_service', domain='qnx', short='CSD2 · audio graph runtime', duty='QNX 音频服务运行时。coreinit 初始化 CSD2 和 GSL 后端，处理本地及来宾音频会话、图配置、设备资源与 DSP 交互。相邻 GSL HAB Backend 是该运行时内的组件，不表示另一个独立进程。'),
    dict(id='audio-gsl-be', name='GSL HAB Backend', domain='qnx', short='gsl_be · gsl_vm_be', duty='处理 Android 来宾图命令、响应和异步事件；源码使用 habmm_socket_open/send/recv，并通过 habmm_import/export 映射跨域音频缓冲。属于 audio_service 初始化的后端。'),
    dict(id='audio-acdb', name='ACDB / OEM Config', domain='qnx', short='Graphs · calibration · devices', duty='图键值、校准及设备启动配置；镜像打包 ACDB 数据，audio_oem.cfg 配置采样率、位宽和通道。具体输出通道以项目配置为准。'),
    dict(id='audio-codec', name='codec_service', domain='qnx', short='Plugin loading · STR lifecycle', duty='根据板级配置装载音频 Codec 插件，监控初始化动作并注册低功耗回调。已在项目镜像清单中打包；设备管理与音频样本传输分开表示。'),
    dict(id='audio-a2b-driver', name='A2B Driver / Stack', domain='qnx', short='liba2b_amp · liba2b_common', duty='负责 A2B 主从发现、时隙和采样配置、链路故障检测与恢复；通过 I2C/GPIO 访问器件，并提供 /dev/a2b 状态接口。codec_service 加载的插件与 A2B 音频线上的 PCM 数据不是同一条通路。'),
    dict(id='audio-pcm-driver', name='PCM6xx0 Driver', domain='qnx', short='libpcm6xx0 · MIC ADC', duty='配置麦克风 ADC 格式及通道，读取故障状态并处理挂起/恢复。源码含 I2C 访问和低功耗检查；文档写作 PCM60xx/PCM6260，按器件族表达以避免误用其他平台型号。'),
    dict(id='audio-gpr', name='DSP Transport / GPR', domain='qnx', short='Graph commands · buffers', duty='QNX 音频驱动内的 DSP 命令与应答传输。CSD2 公共实现提供 GPR/SPF 命令封装；不把 HAB 跨域链路与主处理器到 ADSP 的传输混为一条接口。'),
    dict(id='audio-apps', name='Media / Voice Clients', domain='aaos', short='Examples: Music · Video · Navigation · Voice Assistant · Recorder', duty='典型调用方包括音乐、视频、导航、语音助手及录音应用（示例，不代表项目已部署应用清单）。业务应用通过 AudioTrack、AudioRecord 等音频接口播放或录制数据，通过音频管理 API 请求焦点和路由；此块为调用方集合，不表示一个同名进程。'),
    dict(id='audio-bt-hfp', name='Bluetooth HFP Client', domain='aaos', short='HeadsetClientService', duty='Android 蓝牙免提客户端系统服务，源码对应继承 ProfileService 的 HeadsetClientService 及其状态机；处理拨号、接听、拒接、挂断和通话状态。状态机通过 AudioManager 的 setHfpEnabled、setHfpSamplingRate、setHfpVolume 配置通话音频，经 AudioSystem、AudioFlinger 传递至 Audio HAL；另一分支经 NativeInterface/JNI 调用蓝牙协议栈，并接收连接和通话状态回调。通话 PCM 按文档在蓝牙芯片与 ADSP 之间通过 I2S 双向传输。'),
    dict(id='audio-audio-manager', name='AudioManager', domain='aaos', short='HFP enable · rate · volume', duty='HFP Client 调用的 Java 音频 API。当前源码的 setHfpEnabled、setHfpSamplingRate、setHfpVolume 将参数交给 AudioSystem.setParameters；不是由 Bluetooth HCI HAL 转发到音频 HAL。'),
    dict(id='audio-framework-system', name='AudioSystem', domain='aaos', short='Native audio client API', duty='Android 原生音频客户端接口。AudioManager 通过 JNI 进入 AudioSystem，后者以 AUDIO_IO_HANDLE_NONE 向 AudioFlinger 发起全局 setParameters Binder 调用。'),
    dict(id='audio-bt-jni', name='HFP Client JNI / Profile API', domain='aaos', short='bthf_client_interface_t', duty='HeadsetClientService 的 NativeInterface/JNI 适配层，通过 BT_PROFILE_HANDSFREE_CLIENT_ID 获取 bthf_client_interface_t，调用连接、通话操作和音频连接接口；连接、音频及通话状态通过 JNI 回调返回。该 Profile API 不是独立的厂商 HFP HAL 服务。'),
    dict(id='audio-bt-stack', name='Bluetooth Stack', domain='aaos', short='BTIF / BTA HFP Client', duty='原生蓝牙协议栈的 HFP Client 实现，负责 AT 命令、RFCOMM 通话控制及 SCO/eSCO 音频连接管理。btif_hf_client 的 connect_audio/disconnect_audio 调用 BTA_HfClientAudioOpen/Close，并把状态事件返回 Profile API。'),
    dict(id='audio-bt-hal', name='Bluetooth HCI HAL', domain='aaos', short='IBluetoothHci · vendor transport', duty='蓝牙协议栈与控制器的硬件抽象边界，传递 HCI 命令、事件及相关数据。工作区 HCI 适配源码使用 IBluetoothHci；图中不指定未经板级配置确认的 UART/USB 绑定或部署接口版本。该模块服务经典蓝牙等控制器通信，不命名为 BLE HAL，也不直接调用 Audio HAL 配置本项目 HFP 回路。'),
    dict(id='audio-hfp-ext', name='HFP Extension', domain='aaos', short='libhfp_pal · Hfp.cpp', duty='Audio HAL 内部通过 AudioExtn 加载的 libhfp_pal 插件；接收 hfp_enable、hfp_set_sampling_rate 和 hfp_volume，创建、启动、停止 PAL_STREAM_LOOPBACK_HFP_RX/TX 两条通话回路，并设置音量。它属于 Audio HAL 实现，不是另一个独立 HAL 服务；通过 PAL 进入音频后端。'),
    dict(id='audio-car', name='CarAudioService', domain='aaos', short='Zones · groups · focus', duty='AAOS 车载音频区域、音量组、焦点及动态路由管理；通过音频策略接口配置框架，通过 AudioControl 接口发送静音与降音信息。'),
    dict(id='audio-flinger', name='AudioFlinger', domain='aaos', short='Stream I/O · parameter dispatch', duty='Android 音频混音、播放与录制线程，连接应用音频缓冲和 Audio HAL 输入输出流。同时把 AudioSystem 的全局 setParameters 请求转交硬件设备接口；图中将 HFP 参数控制与 PCM 流分别连线。'),
    dict(id='audio-policy', name='AudioPolicyService', domain='aaos', short='Device routing · port gain', duty='Android 原生策略服务；依据策略配置和动态策略选择输入输出设备、路由及端口增益，经 AudioFlinger/HAL 执行。CarAudioService 不承担所有 Android 基础音频框架职责。'),
    dict(id='audio-hal', name='AudioDevice', domain='aaos', short='Stream I/O · AudioExtn dispatch', duty='实现输出/输入流打开关闭、端口增益与参数接口，转换为 PAL 流和设备操作；HFP 参数经 AudioExtn 分发至 libhfp_pal 插件。AudioExtn 注册 AudioControl 客户端，静音回调按设备地址定位输出流并调用 SetOutputMute。'),
    dict(id='audio-control', name='AudioControl HAL', domain='aaos', short='AIDL · mute callback', duty='AAOS 音频控制 AIDL 服务。当前 onDevicesToMuteChange 确实向已注册 Audio HAL 回调发送静音；onDevicesToDuckChange 在核对文件中仅记录日志，不能据此声称已执行降音。'),
    dict(id='audio-pal', name='PAL', domain='aaos', short='SessionAlsaPcm · device routing', duty='Platform Abstraction Layer 管理流、设备和会话。普通 PLAYBACK_BUS 使用 SessionAlsaPcm，经 tinyalsa AGM 插件设置 stream/device metadata 与 FE Connect；NON_TUNNEL 才使用 SessionAgm。bus_addr、PAL device 和 resource profile 共同决定 graph key 与后端接口，详见 Bus / BE / TDM routing。'),
    dict(id='audio-agm', name='AGM', domain='aaos', short='FE / BE · graph metadata', duty='Audio Graph Manager 将音频会话映射为图和设备对象；graph.c 调用 gsl_open、gsl_ioctl 及读写接口。平台构建可通过 AGM IPC 客户端封装访问服务。'),
    dict(id='audio-gsl-fe', name='GSL / MMHAB Frontend', domain='aaos', short='Guest audio graph endpoint', duty='AGM 的 GSL 接口后续跨域端点；文档称 MMHAB，QNX 后端源码明确实现对应 HAB 命令和共享缓冲机制。前端内部实现未完全展开，不额外假设跨域套接字地址或端口。'),
    dict(id='audio-hypervisor', name='QNX Hypervisor', domain='platform', short='Host / guest isolation', duty='维持 QNX 主机与 Android 来宾的执行和内存边界。HAB 是音频跨域通信方案；此处只展示相关虚拟化基础，不重复画成一个业务服务。'),
    dict(id='audio-shmem', name='Shared Memory / Events', domain='platform', short='HAB transport foundation', duty='支撑跨域缓冲映射和事件通知；gsl_be 的 habmm_import/export 可核实共享缓冲使用。不据此宣称存在一个独立部署的 Doorbell 进程或设备。'),
    dict(id='audio-dsp', name='ADSP Audio Graphs', domain='dsp', short='Mixing · routing · capture · HFP loopback', duty='按 session、session-AIF 与 device 元数据和 ACDB 配置构建播放、采集及 HFP 图；通过端点配置连接 LPASS。bus 到 BE 映射、条件化路由参数与已证实 slot 配置见路由视图；播放混音矩阵和具体 bus 到 slot 的关系仍为 unknown。文档表示 ECNS 当时处于 bypass，当前镜像虽打包 capi_ecns.so，也不足以证明算法在运行时启用。'),
    dict(id='audio-a2b-hw', name='A2B Transceiver', domain='hardware', short='TDM / A2B audio link', duty='通过 TDM 与 ADSP 交换音频，通过 A2B 连接功放端节点。软件驱动使用 I2C/GPIO 配置与读取状态；不把配置线等同音频数据线。'),
    dict(id='audio-amp', name='Amplifier / Speakers', domain='hardware', short='A2B endpoint', duty='消费 A2B 下行播放音频；文档中媒体音量由外部功放调节。当前未核实媒体音量命令完整的车辆总线和 MCU 映射，因此不绘制臆测的 MCU 或 CAN 控制链。'),
    dict(id='audio-mic', name='Microphones / PCM6xx0', domain='hardware', short='Analog capture → TDM', duty='模拟麦克风经 ADC 数字化，再以 TDM 向 ADSP 提供采集音频；按实际产品配置决定通道顺序和使用范围。图中不强制采用其他平台的麦克风数量。'),
    dict(id='audio-bt-chip', name='Bluetooth Controller', domain='hardware', short='HCI control · I2S call audio', duty='按照设计文档，通过 I2S 与 ADSP 双向交换蓝牙通话上下行音频。HCI 命令/事件来自 Android 蓝牙栈与 HCI HAL，I2S 音频数据与该控制路径分别绘制。'),
    dict(id='audio-radio', name='FM / DAB USB Audio', domain='hardware', short='Document reference', reference=True, duty='文档中的广播音源通过 USB 向 Android 音频框架提供数据；本次未完成项目广播 HAL 和 USB 运行配置核验，使用配对 RADIO 端口及虚线标为文档参考。'),
]

FLOWS = [
    ('libaudiomgr_if ↔ audiomgr → libcsd2IpcClient ↔ audio_service', 'Chime request / PCM / completion', 'Project IPC · CSD2 IPC', '项目源码及 SLM 确认；audiomgr 内部优先级队列与 csd2pcm_player 是实际实现。'),
    ('Media / Voice Clients ↔ AudioFlinger ↔ AudioDevice ↔ PAL ↔ AGM', 'Playback and capture buffers', 'AudioTrack / AudioRecord · HAL stream I/O · PAL / AGM API', '双向箭头概括播放下行和采集上行，不表示每条硬件链路都双向。'),
    ('CarAudioService → AudioPolicyService → AudioFlinger', 'Zone / routing policy', 'Android audio policy API', '将车载策略与通用 Android 音频框架分开。'),
    ('CarAudioService → AudioControl HAL → AudioDevice', 'Mute request / callback', 'AIDL · onAudioMuteChanged · SetOutputMute', 'mute 回调已实现；当前 duck 回调仅日志。'),
    ('Bluetooth HFP Client ↔ HFP Client JNI / Profile API ↔ Bluetooth Stack', 'Call commands / connection state / callbacks', 'NativeInterface · JNI · bthf_client_interface_t', 'HeadsetClientService 与原生 HFP Client 协议实现之间的接口；包括拨号、接听、挂断和音频连接管理。'),
    ('Bluetooth Stack ↔ Bluetooth HCI HAL ↔ Bluetooth Controller', 'HCI commands / events', 'IBluetoothHci · vendor transport', '承载蓝牙控制器通信；UART/USB 等具体板级传输绑定未在本图展开。没有 HCI HAL → Audio HAL 控制连线。'),
    ('Bluetooth HFP Client → AudioManager → AudioSystem → AudioFlinger → AudioDevice', 'HFP enable / sampling rate / volume', 'Java API · JNI · Binder setParameters · HAL parameters', '当前源码 AudioManager 直接转交 AudioSystem；AudioFlinger 将全局参数送至 Audio HAL 设备实现。'),
    ('AudioDevice → HFP Extension → PAL', 'Start / stop HFP RX and TX loops', 'AudioExtn dispatch · libhfp_pal · pal_stream_*', 'HFP Extension 置于 Audio HAL Implementation 容器内，构建蓝牙下行到扬声器、麦克风到蓝牙上行两条 PAL 回路。'),
    ('AGM ↔ GSL / MMHAB Frontend ↔ GSL HAB Backend', 'Graph commands / buffers / events', 'GSL API · HAB · shared-memory import/export', 'QNX 后端源码确认命令通道、事件通道和带外缓冲；不虚构固定端口。'),
    ('audio_service ↔ DSP Transport / GPR ↔ ADSP Audio Graphs', 'Graph control and stream data', 'GPR / SPF · audio buffers', 'CSD2/GSL 运行时及 DSP 传输封装；并非 QNX ↔ Android 的 HAB 通道。'),
    ('codec_service → A2B Driver / Stack, PCM6xx0 Driver', 'Plugin initialization / suspend / resume', 'Board configuration · driver plugin API', '对应项目打包的 liba2b_amp、liba2b_common、libpcm6xx0。'),
    ('A2B Driver / Stack ↔ A2B Transceiver; PCM6xx0 Driver ↔ MIC ADC', 'Configuration / fault status', 'I2C · GPIO · device registers', '配对 A2B / MIC 端口表示同一控制链路的两个端点。'),
    ('ADSP Audio Graphs → A2B Transceiver → Amplifier / Speakers', 'Playback PCM', 'TDM · A2B', '包括媒体与仪表提示音；媒体功放音量的 MCU/CAN 控制映射尚未核实。'),
    ('Microphones / PCM6xx0 → ADSP Audio Graphs', 'Capture PCM', 'TDM', '采集可继续经 QNX/Android 音频通路送往 AudioRecord。'),
    ('Bluetooth Controller ↔ ADSP Audio Graphs', 'Call uplink / downlink', 'I2S', '文档中的 ADSP 通话回路；不声称当前 ECNS 已启用。'),
    ('avas_service ⇢ libcsd2IpcClient; FM / DAB USB Audio ⇢ AudioFlinger', 'Documented AVAS / radio paths', 'CSD2 API / USB audio', '虚线是文档参考，项目完整实现尚未核实。'),
]


def render_audio():
    groups = [('QNX Cluster','qnx'), ('AAOS IVI','aaos'), ('Virtualization','platform'), ('ADSP Firmware','dsp'), ('Audio Devices','hardware')]
    index = ''.join('<section class="sw-index-group"><h4>'+title+'</h4><ul class="sw-index-list">'+''.join(
        '<li><button class="sw-index-entry" id="sw-index-'+m['id']+'" type="button" data-sw-module="'+m['id']+'" aria-pressed="false"><span class="sw-index-name">'+escape(m['name'])+'</span><span class="sw-index-duty" lang="zh-CN">'+escape(m['duty'])+'</span></button></li>' for m in MODULES if m['domain']==domain)+'</ul></section>' for title,domain in groups)
    rows=''.join('<tr>'+''.join('<td>'+escape(cell)+'</td>' for cell in row)+'</tr>' for row in FLOWS)
    controls=''.join('<button type="button" data-audio-focus="'+key+'" aria-pressed="'+str(key=='all').lower()+'">'+title+'</button>' for key,title in [('all','All'),('media','Playback / Capture'),('chime','Cluster / AVAS'),('policy','Policy / Mute'),('phone','Bluetooth Call'),('device','Device Control'),('radio','Radio')])
    return f'''
<div class="sw-page sw-audio-page" id="sw-audio-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-audio-back" type="button">← High-Level software architecture</button><span>Audio software architecture</span></div>
  <div class="audio-panel-tabs" role="group" aria-label="Audio architecture view"><button type="button" data-audio-panel="components" aria-pressed="true" aria-controls="sw-audio-components">Component interactions</button><button type="button" data-audio-panel="routing" aria-pressed="false" aria-controls="sw-audio-routing">Bus / BE / TDM routing</button></div>
  <div id="sw-audio-components">
  <div class="sw-ota-controls" role="group" aria-label="Highlight audio interaction path"><span>Interaction paths</span>{controls}</div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="Audio component interactions; scroll horizontally if needed">{render_graph(MODULES)}</div>
  <div class="sw-ota-inspector" id="sw-audio-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  </div>
  {render_routing()}
  <section class="sw-index" aria-labelledby="sw-audio-index-title"><div class="sw-section-heading"><h3 id="sw-audio-index-title">Module responsibilities</h3><p lang="zh-CN">实线表示已核对的接口或文档明确的设备通路；棕色虚线表示仅文档确认、实现待核实。</p></div>{index}</section>
  <section class="sw-interfaces" aria-labelledby="sw-audio-flows-title"><div class="sw-section-heading"><h3 id="sw-audio-flows-title">Interface &amp; data-flow register</h3></div><div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Components</th><th>Data flow</th><th>Transport</th><th>Implementation note</th></tr></thead><tbody>{rows}</tbody></table></div></section>
  <div class="sw-provenance" lang="zh-CN">依据 Audio 设计文档 v1.5 与当前 QNX/Android 源码、镜像清单整理。图中 GSL 后端是 audio_service 内的组件，框图不等同进程划分。AVAS、广播完整实现、功放音量的 MCU 映射与 ECNS 运行启用状态尚未核实；不绘制空 MCU 域。详细证据见 <a href="audio-evidence.md">Audio evidence notes</a>。</div>
</div>''', {'modules':MODULES, 'flows':FLOWS, 'routing':ROUTING_DATA}
