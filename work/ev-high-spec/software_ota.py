"""Source-grounded OTA child view using the high-level software board layout."""
from html import escape
from software_ota_graph import render_graph

MODULES = [
    dict(id='ota-aaos-ui', name='UsbUpdateActivity', domain='aaos', short='User entry', duty='提供本地升级的用户入口，并调用 OTA 服务；界面不直接写入系统分区。'),
    dict(id='ota-aaos-doip', name='DoipOtaManager', domain='aaos', short='DoIP ingress', duty='接收 DoIP 升级指令，校验约定包路径的签名，并通过 UpdateBinder 触发安装。'),
    dict(id='ota-aaos-sdk', name='VoyahOtaUpdateImpl', domain='aaos', short='Client SDK', duty='向升级界面暴露触发与回调接口，通过 Binder 访问 UpdateService。'),
    dict(id='ota-aaos-recovery', name='icupdater', domain='aaos', short='Recovery-only REQ', duty='Recovery 环境中的独立 ZeroMQ 客户端，绕过 Android UpdateService 直接与 QNX updater 通信。'),
    dict(id='ota-aaos-notifier', name='UpdateNotifier', domain='aaos', short='Client callbacks', duty='将 TaskScheduler 的任务状态转成客户端通知，最终经 UpdateBinder 回传给 SDK/界面。'),
    dict(id='ota-aaos-device', name='DeviceManager', domain='aaos', short='Target routing', duty='按 manifest.json 中的设备目标路由到 QNX、Android、MCU 升级协议；目标执行次序由清单的 order 字段决定。'),
    dict(id='ota-aaos-service', name='UpdateService / UpdateBinder', domain='aaos', short='Service API', duty='承接应用请求，向客户端提供升级服务接口和状态回调。'),
    dict(id='ota-aaos-scheduler', name='TaskScheduler', domain='aaos', short='Task lifecycle', duty='调度加载、刷写与激活任务；启动恢复时会将未完成任务标记失败，重启激活阶段有特殊成功处理，不能理解为自动续传。'),
    dict(id='ota-aaos-load', name='LoadTask', domain='aaos', short='Manifest · staging', duty='解析升级包顶层 manifest.json，准备各目标组件所需的升级文件与任务。'),
    dict(id='ota-aaos-flash', name='FlashTask', domain='aaos', short='Flash dispatch', duty='按任务目标调度 Android、QNX 与 MCU 的刷写处理并汇总执行状态。'),
    dict(id='ota-aaos-activate', name='ActivateTask', domain='aaos', short='Activation', duty='执行升级后的激活和重启阶段处理。'),
    dict(id='ota-aaos-impl', name='UpdateImpl', domain='aaos', short='Target coordination', duty='协调 QNX、MCU 与 Android 升级协议和进度查询；MCU 进度达到 100 不必然代表最终结果已验证。'),
    dict(id='ota-aaos-protocol', name='Target Protocols', domain='aaos', short='QNX · MCU · Android', duty='QnxUpdateProtocol、McuUpdateProtocol、AndroidUpdateProtocol 封装各目标的请求与响应。'),
    dict(id='ota-aaos-jmq', name='JMQClient', domain='aaos', short='ZeroMQ REQ', duty='通过 TCP/IP 上的 ZeroMQ 请求/应答与 QNX updater 交换升级控制消息。'),
    dict(id='ota-aaos-engine', name='Android UpdateEngine', domain='aaos', short='A/B payload', duty='执行 Android 自身 A/B payload 的写入与激活，受上层 OTA 服务协调。'),
    dict(id='ota-aaos-storage', name='OTA Package Staging', domain='aaos', short='Manifest · payloads', duty='存放顶层 manifest.json 与目标升级包；Android payload 的 URL、偏移、大小和属性由 UpgradeConfig 解析，不能一概视作解压后的独立文件。'),
    dict(id='ota-aaos-slot', name='Android A/B Slot', domain='aaos', short='Inactive target', duty='承接 Android UpdateEngine 对非活动槽位的 payload 写入和后续激活。'),
    dict(id='ota-qnx-updater', name='updater', domain='qnx', short='ZeroMQ REP · orchestration', duty='接收 Android 跨域升级命令，启动 QNX、仪表屏、DMS 和 MCU 的对应更新处理，并返回请求结果。'),
    dict(id='ota-qnx-ipc', name='IPC Update Job', domain='qnx', short='QNX image', duty='对应 updater 内的 update_job_ipc 任务：准备包目录并调用 update_ic.sh 写入非活动 QNX 分区；bank 激活是后续独立请求。'),
    dict(id='ota-qnx-lcd', name='IPC LCD Update Job', domain='qnx', short='Display firmware', duty='由 updater 与 IPC 更新并行发起，处理仪表显示相关固件的升级。'),
    dict(id='ota-qnx-dms', name='DMS Update Job', domain='qnx', short='DMS firmware', duty='由 updater 与 IPC 更新并行发起，处理 DMS 组件升级。'),
    dict(id='ota-qnx-script', name='update_ic.sh', domain='qnx', short='Image installation', duty='执行 QNX system、ifs2、hyp 镜像补丁并写入对应非活动分区；不负责选择下次启动 bank。'),
    dict(id='ota-qnx-slot', name='swdl_utils', domain='qnx', short='Bank query · selection', duty='BSP 层的板级启动槽位工具，查询当前启动 bank，并按请求 slot 选择目标 bank；不会仅凭当前 bank 自动选择对侧。'),
    dict(id='ota-qnx-mcu', name='upgrademcu', domain='qnx', short='MCU transfer', duty='读取 MCU 固件数据，构造升级传输请求，经 RPC 通路发送至 MCU；重发路径沿用预先计算的数据 CRC。'),
    dict(id='ota-qnx-rpcif', name='librpcif', domain='qnx', short='RPC client API', duty='Platform Services 层的 RPC 客户端库，为 upgrademcu 提供 MCU 消息发送和应答接口，经本地 IPC 向 rpcd 提交消息。'),
    dict(id='ota-qnx-rpcd', name='rpcd', domain='qnx', short='SPI bridge', duty='Platform Services 层的 RPC 通信服务，接收 QNX 本地 IPC 通知，并通过板级 SPI 与 MCU 交换消息帧；此处才是物理 SPI 链路。'),
    dict(id='ota-qnx-fifo', name='fifo_progress', domain='qnx', short='QNX progress file', duty='QNX 镜像更新脚本写入进度，updater 读取后通过 ZeroMQ 请求应答提供给 Android。'),
    dict(id='ota-qnx-mcu-progress', name='mcu_update_process', domain='qnx', short='MCU progress file', duty='upgrademcu 写入 MCU 固件传输进度，updater 读取并响应 Android 轮询。'),
    dict(id='ota-qnx-banks', name='System Image Banks (A/B)', domain='qnx', kind='storage', short='system · ifs2 · hyp', duty='存储对象，表示两组可切换的系统镜像分区（system、ifs2、hyp）。update_ic.sh 写入非活动侧；BSP 工具 swdl_utils 按请求 slot 选择下次启动 bank。'),
    dict(id='ota-qnx-network', name='TCP/IP & Block I/O', domain='qnx', short='Network · storage', duty='为 ZeroMQ 服务和升级文件访问提供 QNX 网络、文件系统与块设备接口。'),
    dict(id='ota-qnx-os', name='QNX Neutrino', domain='qnx', short='Processes · I/O', duty='为 updater、升级任务和设备接口提供进程、线程、文件系统与设备 I/O 运行环境。'),
    dict(id='ota-mcu-task', name='OTA Task', domain='mcu', short='Firmware session', duty='参考图中的 MCU 应用任务，负责接收升级会话、管理固件传输状态；当前工作区没有 MCU 固件源码可验证细节。', reference=True),
    dict(id='ota-mcu-rtos', name='FreeRTOS', domain='mcu', short='Task runtime', duty='参考图中的 MCU 任务调度与同步环境；当前 OTA 运行行为未从 MCU 源码验证。', reference=True),
    dict(id='ota-mcu-spi', name='SPI Driver', domain='mcu', short='SoC link', duty='参考图中的 SPI 设备驱动，用于 SoC–MCU 消息传输；具体帧协议待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-flash', name='Flash Driver', domain='mcu', short='Firmware write', duty='参考图中的片内 Flash 访问接口；写入与校验细节待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-boot', name='Bootloader', domain='mcu', short='Image startup', duty='参考图中的启动程序，承接固件启动与升级切换；回滚策略待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-hw', name='Automotive MCU', domain='mcu', short='Flash · SPI', duty='提供 MCU 处理器、Flash 与 SPI 硬件资源；供应商与型号已脱敏。', reference=True),
]


FLOWS = [
    ('USB UI → VoyahOtaUpdateImpl → UpdateBinder', 'Trigger / callback', 'SDK + Binder', 'USB package is copied to /ota/usb/; UI receives task status through the service callback path.'),
    ('DoIP → DoipOtaManager → UpdateBinder', 'Signature check / install request', 'DoIP + service call', 'DoIP ingress verifies /ota/doip/update.zip before submitting the install action.'),
    ('UpdateBinder → TaskScheduler → tasks', 'LOAD → FLASH → ACTIVATE', 'In-process task scheduling', 'FlashTask visits targets in manifest.json order; no fixed QNX→Android→MCU order is assumed.'),
    ('FlashTask → DeviceManager → protocols → UpdateImpl', 'Per-target update operation', 'In-process calls / callbacks', 'DeviceManager routes QNX, Android and MCU targets; progress returns through the task callback chain.'),
    ('JMQClient ↔ QNX updater', 'Commands, progress and result', 'ZeroMQ REQ/REP over TCP/IP', '10.10.200.1:5030; requests are answered, including polled status and final result.'),
    ('updater → IPC / LCD / DMS jobs', 'QNX and display updates', 'QNX threads / processes', 'REQ_START_UPDATE_IPC (0xA1) starts all three jobs in the checked source.'),
    ('update_ic.sh → QNX bank → fifo_progress → updater', 'Image write / progress', 'Block I/O + progress file', 'Bank selection uses the requested slot; progress is read back by updater.'),
    ('updater → upgrademcu → librpcif → rpcd ↔ MCU', 'Firmware chunks / responses', 'Process + API + local IPC + SPI', 'Only rpcd↔MCU is the physical SPI exchange; MCU internal flow is reference-only.'),
    ('UpdateImpl ↔ UpdateEngine → Android A/B slot', 'Payload install / callback', 'Android UpdateEngine API', 'Callback returns progress and completion to UpdateImpl.'),
    ('Progress files / engine → client', 'Progress / final status', 'ZeroMQ replies + callbacks', 'updater → JMQClient → UpdateImpl → protocol → FlashTask → TaskScheduler → UpdateNotifier → UpdateBinder → SDK/UI.'),
]


def render_ota():
    groups = [('QNX Cluster', 'qnx'), ('AAOS IVI', 'aaos'), ('MCU', 'mcu')]
    index = ''.join(
        f'<section class="sw-index-group"><h4>{title}</h4><ul class="sw-index-list">'
        + ''.join(
            f'<li><button class="sw-index-entry" id="sw-index-{escape(m["id"])}" type="button" '
            f'data-sw-module="{escape(m["id"])}" aria-pressed="false">'
            f'<span class="sw-index-name">{escape(m["name"])}</span>'
            f'<span class="sw-index-duty" lang="zh-CN">{escape(m["duty"])}</span>'
            '</button></li>'
            for m in MODULES if m['domain'] == domain
        ) + '</ul></section>'
        for title, domain in groups
    )
    rows = ''.join('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>' for row in FLOWS)
    graph = render_graph(MODULES)
    html = f'''
<div class="sw-page sw-ota-page" id="sw-ota-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-ota-back" type="button">← High-Level software architecture</button><span>OTA software architecture</span></div>
  <div class="sw-ota-controls" role="group" aria-label="Highlight OTA interaction path">
    <span>Interaction paths</span>
    <button type="button" data-ota-focus="all" aria-pressed="true">All</button>
    <button type="button" data-ota-focus="qnx" aria-pressed="false">QNX &amp; displays</button>
    <button type="button" data-ota-focus="android" aria-pressed="false">Android A/B</button>
    <button type="button" data-ota-focus="mcu" aria-pressed="false">MCU firmware</button>
    <button type="button" data-ota-focus="feedback" aria-pressed="false">Status return</button>
  </div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="OTA component interaction architecture; scroll horizontally if needed">{graph}</div>
  <div class="sw-ota-inspector" id="sw-ota-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  <section class="sw-index" aria-labelledby="sw-ota-index-title">
    <div class="sw-section-heading"><div><h3 id="sw-ota-index-title">Module responsibilities</h3></div><p lang="zh-CN">点击图中组件可高亮其连线；下方按域列出职责。MCU 内部模块为参考结构。</p></div>
    {index}
  </section>
  <section class="sw-interfaces" aria-labelledby="sw-ota-flows-title">
    <div class="sw-section-heading"><div><h3 id="sw-ota-flows-title">Interface & data-flow register</h3></div><p lang="zh-CN">方向、传输方式和状态返回均按已核实的 Android/QNX 源码标注。</p></div>
    <div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Components</th><th>Data flow</th><th>Transport</th><th>Implementation note</th></tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <div class="sw-provenance" lang="zh-CN">Android 与 QNX 的组件和交互依据当前源码绘制。MCU 侧内部模块依据已提供的参考架构推断，当前工作区缺少 MCU 固件源码。任务目标顺序来自 manifest.json；进行中的任务重启后会标为失败（激活重启阶段有例外）。MCU 进度达到 100 并不保证最终结果已核验。</div>
</div>'''
    return html, {'modules': MODULES, 'flows': FLOWS}
