"""Source-grounded OTA child view using the high-level software board layout."""
from html import escape

MODULES = [
    dict(id='ota-aaos-ui', name='UsbUpdateActivity', domain='aaos', short='User entry', duty='提供本地升级的用户入口，并调用 OTA 服务；界面不直接写入系统分区。'),
    dict(id='ota-aaos-doip', name='DoipOtaManager', domain='aaos', short='DoIP ingress', duty='接收 DoIP 升级指令，校验约定包路径的签名，并通过 UpdateBinder 触发安装。'),
    dict(id='ota-aaos-service', name='UpdateService / UpdateBinder', domain='aaos', short='Service API', duty='承接应用请求，向客户端提供升级服务接口和状态回调。'),
    dict(id='ota-aaos-scheduler', name='TaskScheduler', domain='aaos', short='Task lifecycle', duty='调度加载、刷写与激活任务；启动恢复时会将未完成任务标记失败，重启激活阶段有特殊成功处理，不能理解为自动续传。'),
    dict(id='ota-aaos-load', name='LoadTask', domain='aaos', short='Manifest · staging', duty='解析升级包顶层 manifest.json，准备各目标组件所需的升级文件与任务。'),
    dict(id='ota-aaos-flash', name='FlashTask', domain='aaos', short='Flash dispatch', duty='按任务目标调度 Android、QNX 与 MCU 的刷写处理并汇总执行状态。'),
    dict(id='ota-aaos-activate', name='ActivateTask', domain='aaos', short='Activation', duty='执行升级后的激活和重启阶段处理。'),
    dict(id='ota-aaos-impl', name='UpdateImpl', domain='aaos', short='Target coordination', duty='协调 QNX、MCU 与 Android 升级协议和进度查询；MCU 进度达到 100 不必然代表最终结果已验证。'),
    dict(id='ota-aaos-protocol', name='Target Protocols', domain='aaos', short='QNX · MCU · Android', duty='QnxUpdateProtocol、McuUpdateProtocol、AndroidUpdateProtocol 封装各目标的请求与响应。'),
    dict(id='ota-aaos-jmq', name='JMQClient', domain='aaos', short='ZeroMQ REQ', duty='通过 TCP/IP 上的 ZeroMQ 请求/应答与 QNX updater 交换升级控制消息。'),
    dict(id='ota-aaos-engine', name='Android UpdateEngine', domain='aaos', short='A/B payload', duty='执行 Android 自身 A/B payload 的写入与激活，受上层 OTA 服务协调。'),
    dict(id='ota-aaos-storage', name='OTA Staging & A/B Storage', domain='aaos', short='Packages · slots', duty='存放已加载的升级包，并提供 Android A/B 目标分区；目录和包格式由项目清单决定。'),
    dict(id='ota-qnx-updater', name='updater', domain='qnx', short='ZeroMQ REP · orchestration', duty='接收 Android 跨域升级命令，启动 QNX、仪表屏、DMS 和 MCU 的对应更新处理，并返回请求结果。'),
    dict(id='ota-qnx-ipc', name='IPC Update Job', domain='qnx', short='QNX image', duty='对应 updater 内的 update_job_ipc 任务：准备包目录并调用 update_ic.sh；目标槽位由请求中的 slot 参数指定。'),
    dict(id='ota-qnx-lcd', name='IPC LCD Update Job', domain='qnx', short='Display firmware', duty='由 updater 与 IPC 更新并行发起，处理仪表显示相关固件的升级。'),
    dict(id='ota-qnx-dms', name='DMS Update Job', domain='qnx', short='DMS firmware', duty='由 updater 与 IPC 更新并行发起，处理 DMS 组件升级。'),
    dict(id='ota-qnx-script', name='update_ic.sh', domain='qnx', short='Image installation', duty='执行 QNX 镜像分区刷写等安装步骤，写入请求指定的目标分区。'),
    dict(id='ota-qnx-slot', name='swdl_utils', domain='qnx', short='Bank query · selection', duty='查询当前启动 bank，并按请求 slot 选择目标 bank；不会仅凭当前 bank 自动选择对侧。'),
    dict(id='ota-qnx-mcu', name='upgrademcu', domain='qnx', short='MCU transfer', duty='读取 MCU 固件数据，构造升级传输请求，经 RPC 通路发送至 MCU；重发路径沿用预先计算的数据 CRC。'),
    dict(id='ota-qnx-rpcif', name='librpcif / rpcd', domain='qnx', short='RPC bridge', duty='提供 QNX 到 MCU 的消息接口和转发守护进程，对接板级 SPI 通道。'),
    dict(id='ota-qnx-network', name='TCP/IP & Block I/O', domain='qnx', short='Network · storage', duty='为 ZeroMQ 服务和升级文件访问提供 QNX 网络、文件系统与块设备接口。'),
    dict(id='ota-qnx-os', name='QNX Neutrino', domain='qnx', short='Processes · I/O', duty='为 updater、升级任务和设备接口提供进程、线程、文件系统与设备 I/O 运行环境。'),
    dict(id='ota-mcu-task', name='OTA Task', domain='mcu', short='Firmware session', duty='参考图中的 MCU 应用任务，负责接收升级会话、管理固件传输状态；当前工作区没有 MCU 固件源码可验证细节。', reference=True),
    dict(id='ota-mcu-rtos', name='FreeRTOS', domain='mcu', short='Task runtime', duty='参考图中的 MCU 任务调度与同步环境；当前 OTA 运行行为未从 MCU 源码验证。', reference=True),
    dict(id='ota-mcu-spi', name='SPI Driver', domain='mcu', short='SoC link', duty='参考图中的 SPI 设备驱动，用于 SoC–MCU 消息传输；具体帧协议待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-flash', name='Flash Driver', domain='mcu', short='Firmware write', duty='参考图中的片内 Flash 访问接口；写入与校验细节待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-boot', name='Bootloader', domain='mcu', short='Image startup', duty='参考图中的启动程序，承接固件启动与升级切换；回滚策略待 MCU 源码核实。', reference=True),
    dict(id='ota-mcu-hw', name='Automotive MCU', domain='mcu', short='Flash · SPI', duty='提供 MCU 处理器、Flash 与 SPI 硬件资源；供应商与型号已脱敏。', reference=True),
]

QNX = [
    ('Product Experience', []),
    ('Vehicle Domain Services', ['ota-qnx-updater', 'ota-qnx-ipc', 'ota-qnx-lcd', 'ota-qnx-dms']),
    ('Platform Services', ['ota-qnx-script', 'ota-qnx-slot', 'ota-qnx-mcu']),
    ('Device Integration & BSP', ['ota-qnx-rpcif', 'ota-qnx-network']),
    ('QNX Neutrino Core', ['ota-qnx-os']),
]
AAOS = [
    ('Applications', ['ota-aaos-ui']),
    ('Framework', ['ota-aaos-doip', 'ota-aaos-service', 'ota-aaos-scheduler', 'ota-aaos-load', 'ota-aaos-flash', 'ota-aaos-activate', 'ota-aaos-impl', 'ota-aaos-protocol', 'ota-aaos-jmq']),
    ('Native / HAL', ['ota-aaos-engine']),
    ('Android OS', ['ota-aaos-storage']),
]
MCU = [
    ('Applications', ['ota-mcu-task']),
    ('BSW & RTOS', ['ota-mcu-rtos']),
    ('Drivers', ['ota-mcu-spi', 'ota-mcu-flash']),
    ('Bootloader', ['ota-mcu-boot']),
    ('Hardware', ['ota-mcu-hw']),
]
FLOWS = [
    ('DoIP tester → AAOS OTA service', 'Signed package / install request', 'DoIP', 'DoipOtaManager verifies /ota/doip/update.zip, then calls UpdateBinder'),
    ('AAOS app → OTA service', 'Start / status', 'Binder', 'UsbUpdateActivity → UpdateBinder / UpdateService'),
    ('AAOS OTA service ↔ QNX updater', 'Commands / replies', 'ZeroMQ REQ/REP over TCP/IP', 'JMQClient ↔ updater; QNX endpoint 10.10.200.1:5030'),
    ('AAOS package → QNX updater', 'Manifest / target images', 'Staged files', 'Top-level manifest.json; optional QNX, MCU, Cluster and DMS payloads'),
    ('QNX updater → QNX target bank', 'Image install / bank selection', 'Local process + block I/O', 'update_ic.sh; swdl_utils selects the request slot'),
    ('QNX updater → MCU', 'Firmware chunks / status', 'librpcif → rpcd → SPI', 'upgrademcu is the QNX-side sender; MCU internals are reference-only'),
    ('AAOS OTA service → Android A/B', 'Payload install / activation', 'UpdateEngine', 'Android payload follows the A/B update path'),
]


def _button(module, *, index=False):
    mid, name = escape(module['id']), escape(module['name'])
    if index:
        return (f'<li><button class="sw-index-entry" id="sw-index-{mid}" type="button" data-sw-module="{mid}" aria-pressed="false">'
                f'<span class="sw-index-name">{name}</span><span class="sw-index-duty" lang="zh-CN">{escape(module["duty"])}</span>'
                '</button></li>')
    cls = ' sw-module-reference' if module.get('reference') else ''
    return (f'<button class="sw-module{cls}" type="button" data-sw-module="{mid}" aria-pressed="false" aria-label="{name}">'
            f'<span class="sw-module-name">{name}</span><span class="sw-module-short">{escape(module["short"])}</span></button>')


def _layer(title, ids, lookup, domain):
    empty = ' sw-ota-layer-empty' if not ids else ''
    return (f'<div class="sw-layer sw-layer-{domain}{empty}"><div class="sw-layer-label">{escape(title)}</div>'
            f'<div class="sw-layer-modules">{"".join(_button(lookup[mid]) for mid in ids)}</div></div>')


def render_ota():
    lookup = {module['id']: module for module in MODULES}
    qnx = ''.join(_layer(title, ids, lookup, 'qnx') for title, ids in QNX)
    aaos = ''.join(_layer(title, ids, lookup, 'aaos') for title, ids in AAOS)
    mcu = ''.join(_layer(title, ids, lookup, 'mcu') for title, ids in MCU)
    groups = [('QNX Cluster', 'qnx'), ('AAOS IVI', 'aaos'), ('MCU', 'mcu')]
    index = ''.join(f'<section class="sw-index-group"><h4>{title}</h4><ul class="sw-index-list">'
                    + ''.join(_button(m, index=True) for m in MODULES if m['domain'] == domain)
                    + '</ul></section>' for title, domain in groups)
    rows = ''.join('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>' for row in FLOWS)
    html = f'''
<div class="sw-page sw-ota-page" id="sw-ota-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-ota-back" type="button">← High-Level software architecture</button><span>OTA software architecture</span></div>
  <div class="sw-board-scroll" aria-label="OTA software architecture diagram; scroll horizontally if needed">
    <div class="sw-board sw-ota-board" lang="en" aria-label="OTA software architecture">
      <div class="sw-soc">
        <div class="sw-system-heading"><div><strong>SoC Platform</strong><small>QNX host + Android guest</small></div></div>
        <div class="sw-soc-domains">
          <section class="sw-domain sw-domain-qnx" aria-label="QNX Cluster domain">
            <div class="sw-domain-heading"><span class="sw-domain-symbol sw-qnx-symbol">Q</span><div><h3>QNX Cluster</h3><p>Real-time host domain</p></div><span class="sw-domain-os">QNX Neutrino</span></div>
            {qnx}
          </section>
          <div class="sw-cross-domain" aria-label="OTA cross-domain interface">
            <div class="sw-link-title">CROSS-DOMAIN<br>DATA FLOW</div>
            <div class="sw-link"><strong>ZeroMQ</strong><small>REQ ⇄ REP</small></div>
            <div class="sw-link"><strong>TCP/IP</strong><small>10.10.200.1:5030</small></div>
            <p>Commands · replies</p>
          </div>
          <section class="sw-domain sw-domain-aaos" aria-label="AAOS IVI domain">
            <div class="sw-domain-heading"><span class="sw-domain-symbol sw-aaos-symbol">A</span><div><h3>AAOS IVI</h3><p>Android guest domain</p></div></div>
            {aaos}
          </section>
        </div>
        <div class="sw-platform-bands">
          <div class="sw-hypervisor-band"><div class="sw-band-lead"><span>VIRTUALIZATION</span><small>VM isolation · virtual network</small></div><span class="sw-ota-band-text">Cross-domain TCP/IP path</span></div>
          <div class="sw-hardware-band"><span>SoC Hardware</span><span>CPU · storage · network I/O · SPI</span></div>
        </div>
      </div>
      <div class="sw-mcu-bridge"><div class="sw-bridge-line">↔</div><strong>SoC ⇄ MCU</strong><span>RPC → SPI</span><small>Firmware · status</small></div>
      <section class="sw-mcu" aria-label="MCU domain">
        <div class="sw-system-heading"><div><strong>MCU</strong><small>Reference modules · source unavailable</small></div></div>
        <div class="sw-mcu-layers">{mcu}</div>
        <p class="sw-mcu-legend">Dashed outline: MCU source not available</p>
      </section>
      <div class="sw-ota-paths" aria-label="OTA data flow summary">
        <div><strong>Control</strong><span>USB UI / DoIP</span><b>→</b><span>UpdateService</span><b>⇄</b><span>JMQClient</span><b>⇄</b><span>updater</span></div>
        <div><strong>QNX / MCU</strong><span>updater</span><b>→</b><span>update_ic.sh / upgrademcu</span><b>→</b><span>QNX bank / SPI → MCU</span></div>
        <div><strong>Android</strong><span>UpdateService</span><b>→</b><span>UpdateEngine</span><b>→</b><span>Android A/B slot</span></div>
      </div>
    </div>
  </div>
  <section class="sw-index" aria-labelledby="sw-ota-index-title">
    <div class="sw-section-heading"><div><h3 id="sw-ota-index-title">Module responsibilities</h3></div><p lang="zh-CN">模块名使用源码名称；点击架构块可定位职责。MCU 块为参考结构。</p></div>
    {index}
  </section>
  <section class="sw-interfaces" aria-labelledby="sw-ota-flows-title">
    <div class="sw-section-heading"><div><h3 id="sw-ota-flows-title">Interface & data-flow register</h3></div><p lang="zh-CN">只标注已核实的 Android/QNX 通路；MCU 内部行为待源码验证。</p></div>
    <div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Boundary</th><th>Data flow</th><th>Transport</th><th>Implementation note</th></tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <div class="sw-provenance" lang="zh-CN">Android 与 QNX 模块依据当前工作区源码绘制。MCU 侧仅依据已提供的参考架构及 QNX 发出的升级协议推断，当前工作区缺少 MCU 固件源码。升级进度、重试、bank 选择等行为按源码表达；图中不作自动恢复或最终校验保证。</div>
</div>'''
    return html, {'modules': MODULES, 'flows': FLOWS}
