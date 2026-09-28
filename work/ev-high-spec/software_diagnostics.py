"""Source-checked diagnostic components plus the supplied MCU reference view."""
from html import escape
from software_diagnostics_graph import render_graph

MODULES = [
    # QNX image and SLM configuration; binary strings corroborate rpcif and DTC interfaces.
    dict(id='diag-qnx-dtc', name='dtcagent', domain='qnx', short='DTC collection', duty='QNX 故障码代理。已打包并由 SLM 启动；预置二进制包含板级状态读取、rpcif 客户端和 DTC 发布接口。'),
    dict(id='diag-qnx-did', name='ecuinfobe', domain='qnx', short='DID backend', duty='按 ecu_info_be.json 管理诊断数据标识符；配置包含 UDS 请求/响应主题，二进制中可核实 rpcif 与 VSOCK 端点。'),
    dict(id='diag-qnx-log', name='vlogmanager', domain='qnx', short='QNX log files', duty='收集 QNX 系统日志并按配置轮转、压缩及保存；预置配置指定 /log/qlog/syslog。'),
    dict(id='diag-qnx-rpcif', name='librpcif', domain='qnx', short='Local RPC client', duty='为 dtcagent 和 ecuinfobe 提供到 rpcd 的 RPC 客户端接口；两者的二进制均引用该库。'),
    dict(id='diag-qnx-rpcd', name='rpcd', domain='qnx', short='SoC–MCU bridge', duty='接收 QNX 侧本地 RPC 请求并通过板级 SPI 与 MCU 交换消息；镜像 SLM 配置确认该服务。'),
    dict(id='diag-qnx-status', name='Device Status I/O', domain='qnx', short='Thermal · display · camera', duty='dtcagent 读取多个板级 /dev 状态节点（温度、显示、摄像头、音频等），形成故障状态输入。'),
    dict(id='diag-qnx-spi', name='SPI I/O', domain='qnx', short='Board-level link', duty='为 rpcd 提供 SoC 与 MCU 间的物理 SPI 接口；对端消息语义由 RPC 与 MCU 任务处理。'),
    dict(id='diag-qnx-slog', name='Slog2 I/O', domain='qnx', short='System log source', duty='向 vlogmanager 提供 QNX slog2 日志记录；预置二进制引用 slog2_parse_all。'),
    dict(id='diag-qnx-os', name='QNX Neutrino', domain='qnx', short='Processes · I/O', duty='承载诊断进程、资源管理器、设备节点及本地 IPC。'),
    # Android vendor diagnostic sources; no generic AOSP/QTI diagnostics are conflated with this feature.
    dict(id='diag-aaos-service', name='DiagService', domain='aaos', short='Android service', duty='启动 Android 侧诊断管理器，初始化 MCU 事件订阅与 DTC 状态采集。'),
    dict(id='diag-aaos-dtc', name='DtcEventHandler', domain='aaos', short='Wi-Fi · BT · USB DTC', duty='周期读取 Wi-Fi/蓝牙与 USB 充电故障节点，汇总状态并交由 VehicleManager 上报。'),
    dict(id='diag-aaos-mcu', name='McuDiagEventHandler', domain='aaos', short='MCU property events', duty='订阅 MCU 例程控制、PKI 状态和工厂模式车辆属性，并通过 VehicleManager 返回相应结果。'),
    dict(id='diag-aaos-vehicle', name='VehicleManager', domain='aaos', short='Vehicle property API', duty='通过 IVehicle/Vehicle HAL 订阅、读取与设置诊断车辆属性，包括 TOPIC_DTC_UPDATE 和 MCU 例程控制。'),
    dict(id='diag-aaos-doip', name='doip_server', domain='aaos', short='Ethernet diagnostics', duty='Android vendor 原生诊断进程，面向外部测试仪开放 DoIP/UDS 入口。'),
    dict(id='diag-aaos-dcm', name='DcmManager', domain='aaos', short='UDS service dispatch', duty='注册 DID、例程、安全、编程和 I/O 控制回调，并启动 UDS 服务；该组件属于 Android DoIP 实现。'),
    dict(id='diag-aaos-binder', name='DoipServiceImpl', domain='aaos', short='AIDL callbacks', duty='注册 IDoipService/default，向订阅客户端发送诊断命令回调并接收操作结果。'),
    dict(id='diag-aaos-uds', name='UDS / DoIP Stack', domain='aaos', short='Transport · sessions', duty='Android doip_server 引用的 UDS 与 DoIP 库，负责传输连接和诊断服务协议；与 MCU 的 Dcm 是不同实现。'),
    dict(id='diag-aaos-doipvehicle', name='DoipVehicleManager', domain='aaos', short='Vehicle context', duty='DoIP 服务通过它访问 Vehicle HAL 中的 VIN、车辆状态、车速等上下文。'),
    dict(id='diag-aaos-vhal', name='Vehicle HAL', domain='aaos', short='IVehicle properties', duty='承载 Android 诊断组件读写 MCU 与 QNX 相关车辆属性；具体底层桥接路径需按 HAL 实现进一步核实。'),
    dict(id='diag-aaos-devices', name='DTC Device Nodes', domain='aaos', short='Wi-Fi · BT · USB', duty='Android 侧故障状态节点，为 DtcEventHandler 的周期性采样提供原始输入。'),
    # MCU internal structure is the user-supplied reference, not validated MCU firmware source.
    dict(id='diag-mcu-factory', name='FactoryDiag', domain='mcu', short='Factory diagnosis', duty='参考图中的工厂诊断应用入口；与 MCU Dcm 的请求映射需固件源码核实。', reference=True),
    dict(id='diag-mcu-mfg', name='MFG Diag Task', domain='mcu', short='Manufacturing task', duty='参考图中的制造诊断任务，处理生产测试相关命令。', reference=True),
    dict(id='diag-mcu-spi-ivi', name='SPI IVI Task', domain='mcu', short='IVI messages', duty='参考图中的 IVI 侧 SPI 消息任务；图中实际绑定的 SoC 软件端点尚未核实。', reference=True),
    dict(id='diag-mcu-spi-ic', name='SPI IC Task', domain='mcu', short='Cluster messages', duty='参考图中的仪表侧 SPI 消息任务；图中实际绑定的 SoC 软件端点尚未核实。', reference=True),
    dict(id='diag-mcu-dcm', name='Dcm', domain='mcu', short='Diagnostic sessions', duty='参考图中的 MCU 诊断通信管理，处理 UDS 会话及服务请求。', reference=True),
    dict(id='diag-mcu-dem', name='Dem', domain='mcu', short='DTC events', duty='参考图中的故障事件管理，维护 MCU 故障状态。', reference=True),
    dict(id='diag-mcu-cantp', name='CanTp', domain='mcu', short='ISO 15765-2', duty='参考图中的 CAN 诊断分段与重组传输层。', reference=True),
    dict(id='diag-mcu-canif', name='CanIf', domain='mcu', short='CAN abstraction', duty='参考图中的 CAN 报文接口，连接上层通信服务和 CAN FD 驱动。', reference=True),
    dict(id='diag-mcu-nvm', name='NvM', domain='mcu', short='Persistent data', duty='参考图中的非易失性数据管理，为故障数据保存提供接口。', reference=True),
    dict(id='diag-mcu-rtos', name='FreeRTOS', domain='mcu', short='Task runtime', duty='参考图中的 MCU 任务调度与同步运行环境。', reference=True),
    dict(id='diag-mcu-cdd', name='CDD', domain='mcu', short='Custom device logic', duty='参考图中的复杂驱动集成层；诊断关联接口未在固件源码中核实。', reference=True),
    dict(id='diag-mcu-canfd', name='CAN FD Driver', domain='mcu', short='Tester bus', duty='参考图中接收诊断仪经 CAN FD 发送的诊断报文。', reference=True),
    dict(id='diag-mcu-spi', name='SPI Driver', domain='mcu', short='SoC link', duty='参考图中接收来自 SoC 的 SPI 消息，供 IVI/仪表 SPI 任务处理。', reference=True),
    dict(id='diag-mcu-flash', name='Flash Driver', domain='mcu', short='Persistent write', duty='参考图中为 MCU 存储操作提供 Flash 驱动接口。', reference=True),
    dict(id='diag-mcu-boot', name='Bootloader', domain='mcu', short='Startup', duty='参考图中的 MCU 启动程序；诊断模式与升级切换细节需固件源码确认。', reference=True),
    dict(id='diag-mcu-hw', name='Automotive MCU', domain='mcu', short='CAN FD · SPI · Flash', duty='参考图中的 MCU 硬件资源；具体供应商与型号已脱敏。', reference=True),
    dict(id='diag-vm-isolation', name='VM Isolation', domain='platform', short='QNX host · Android guest', duty='通过 QNX Hypervisor 隔离 QNX 主机与 Android 来宾。'),
    dict(id='diag-vdev-net', name='VirtIO Network', domain='platform', short='Android network I/O', duty='Android 来宾的虚拟网卡基础能力；DoIP 使用 Android 网络栈，具体外部接口路径需按网络配置核对。'),
]

FLOWS = [
    ('Diagnostic Tester ↔ CAN FD Driver ↔ CanIf ↔ CanTp ↔ Dcm', 'UDS request / response', 'CAN FD · ISO 15765-2', 'MCU 路径依据参考图；具体固件实现待核实。'),
    ('Diagnostic Tester ↔ doip_server ↔ DcmManager', 'DoIP / UDS request and response', 'Ethernet TCP/IP · DoIP', 'Android vendor 源码中的 DcmManager 注册 UDS 回调并启动服务。'),
    ('DcmManager ↔ DoipServiceImpl', 'Routine command / result', 'AIDL callback', 'DoIP 原生服务向注册客户端发送回调，客户端返回操作结果。'),
    ('DiagService → DtcEventHandler → VehicleManager → Vehicle HAL', 'Device DTC status', 'Android local call · IVehicle', 'Wi-Fi/蓝牙与 USB 节点每 3 秒读取；车辆属性 TOPIC_DTC_UPDATE 承载状态。'),
    ('DiagService → McuDiagEventHandler ↔ VehicleManager', 'MCU routine / PKI / factory events', 'Vehicle HAL property callback', '订阅 MCU 例程控制、证书状态与工厂模式属性，并返回处理结果。'),
    ('Vehicle HAL ⇢ QNX dtcagent', 'DTC delivery to QNX', 'Vehicle property; peer mapping unverified', 'Android 上报车辆属性与 QNX dtcagent 接收 DTC 均可核实；HAL 到 QNX 代理的完整映射仍需核实。'),
    ('dtcagent / ecuinfobe ↔ librpcif ↔ rpcd ↔ MCU SPI Driver', 'Board DTC / DID data', 'QNX RPC client · local IPC · SPI', 'QNX 服务依赖与二进制接口可核实；MCU 内部任务和数据语义来自参考图。'),
    ('MCU SPI Tasks ↔ SPI Driver', 'IVI / cluster messages', 'MCU internal SPI task path', '参考图显示两条任务链；具体消息映射待 MCU 固件验证。'),
    ('Dem ↔ NvM → Flash Driver', 'DTC persistence', 'MCU BSW · Flash I/O', '参考图表达的 MCU 存储链路，持久化策略待固件源码验证。'),
    ('Slog2 I/O → vlogmanager', 'Diagnostic logs', 'QNX slog2 · file rotation', '预置二进制和配置确认 vlogmanager 从 slog2 收集日志并保存。'),
]


def render_diagnostics():
    groups = [('QNX Cluster','qnx'), ('AAOS IVI','aaos'), ('MCU','mcu'), ('Virtualization','platform')]
    index = ''.join(
        '<section class="sw-index-group"><h4>' + title + '</h4><ul class="sw-index-list">' +
        ''.join('<li><button class="sw-index-entry" id="sw-index-' + escape(m['id']) +
                '" type="button" data-sw-module="' + escape(m['id']) + '" aria-pressed="false">' +
                '<span class="sw-index-name">' + escape(m['name']) + '</span>' +
                '<span class="sw-index-duty" lang="zh-CN">' + escape(m['duty']) + '</span></button></li>'
                for m in MODULES if m['domain']==domain) + '</ul></section>'
        for title,domain in groups)
    rows = ''.join('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>' for row in FLOWS)
    graph = render_graph(MODULES)
    html = f'''
<div class="sw-page sw-diag-page" id="sw-diag-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-diag-back" type="button">← High-Level software architecture</button><span>Diagnostic software architecture</span></div>
  <div class="sw-ota-controls" role="group" aria-label="Highlight diagnostic interaction path">
    <span>Interaction paths</span>
    <button type="button" data-diag-focus="all" aria-pressed="true">All</button>
    <button type="button" data-diag-focus="can" aria-pressed="false">CAN FD / UDS</button>
    <button type="button" data-diag-focus="doip" aria-pressed="false">DoIP / UDS</button>
    <button type="button" data-diag-focus="dtc" aria-pressed="false">DTC reporting</button>
    <button type="button" data-diag-focus="spi" aria-pressed="false">SoC ↔ MCU</button>
    <button type="button" data-diag-focus="logs" aria-pressed="false">Logs</button>
  </div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="Diagnostic component interaction architecture; scroll horizontally if needed">{graph}</div>
  <div class="sw-ota-inspector" id="sw-diag-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  <section class="sw-index" aria-labelledby="sw-diag-index-title">
    <div class="sw-section-heading"><div><h3 id="sw-diag-index-title">Module responsibilities</h3></div><p lang="zh-CN">点击组件可高亮交互；MCU 内部模块依据参考图，供应商及型号已脱敏。</p></div>
    {index}
  </section>
  <section class="sw-interfaces" aria-labelledby="sw-diag-flows-title">
    <div class="sw-section-heading"><div><h3 id="sw-diag-flows-title">Interface &amp; data-flow register</h3></div><p lang="zh-CN">请求、响应和状态链路按实际证据范围标注。</p></div>
    <div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Components</th><th>Data flow</th><th>Transport</th><th>Implementation note</th></tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <div class="sw-provenance" lang="zh-CN">QNX 进程与依赖依据 HBEZ 预置镜像和 SLM 配置；Android 诊断组件依据 vendor 源码。MCU 软件分层和任务来自所附参考图，当前工作区没有对应 MCU 固件源码。Vehicle HAL 到 QNX dtcagent 的完整映射及 MCU 两个 SPI 任务的 SoC 端点未被当前源码确认；图中以虚线表示。</div>
</div>'''
    return html, {'modules':MODULES, 'flows':FLOWS}
