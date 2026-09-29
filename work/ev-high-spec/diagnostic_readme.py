"""Offline diagnostic guide, with SVG sequence diagrams and explicit evidence limits."""
from html import escape
import textwrap


def sequence(key, actors, rows, title, description):
    width = 1160
    xs = [100 + i * (width - 200) / (len(actors) - 1) for i in range(len(actors))]
    parts, y = [], 102
    for row in rows:
        kind = row[0]
        if kind in ('phase', 'note'):
            color = '#eaf1fc' if kind == 'phase' else '#fff7e8'
            parts.append(f'<rect x="20" y="{y}" width="1120" height="32" rx="6" fill="{color}"/>')
            parts.append(f'<text x="36" y="{y + 21}" font-size="13" font-weight="600">{escape(row[1])}</text>')
            y += 54
            continue
        _, start, end, label = row
        a, b = xs[start], xs[end]
        self_call = start == end
        available = 210 if self_call else abs(b - a) - 20
        lines = textwrap.wrap(label, max(16, int(available / 6.8)), break_long_words=False, break_on_hyphens=False)
        line_y = y + len(lines) * 17 + 8
        color = '#a36c24' if kind == 'unverified' else '#368262' if kind == 'reply' else '#436dcc'
        dash = ' stroke-dasharray="6 4"' if kind in ('reply', 'unverified') else ''
        marker = f'{key}-{kind}'
        if self_call:
            direction = -1 if start == len(actors) - 1 else 1
            outer = a + direction * 40
            d = f'M {a} {line_y} H {outer} V {line_y + 22} H {a}'
            label_x = a + direction * 52
            anchor = 'end' if direction < 0 else 'start'
        else:
            d = f'M {a} {line_y} H {b}'
            label_x = (a + b) / 2
            anchor = 'middle'
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{dash} marker-end="url(#{marker})"/>')
        for i, line in enumerate(lines):
            parts.append(f'<text class="diag-seq-label" x="{label_x}" y="{y + 15 + i * 17}" text-anchor="{anchor}" font-size="13" fill="{color}">{escape(line)}</text>')
        y = line_y + (52 if self_call else 32)
    height = y + 25
    defs = ''.join(f'<marker id="{key}-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="{color}" stroke-width="1.5"/></marker>' for kind, color in [('msg', '#436dcc'), ('reply', '#368262'), ('unverified', '#a36c24')])
    lanes = []
    palette = ['#eaf1fc', '#eef5f1', '#fff4e5', '#f1effa', '#eef5f1', '#fff4e5']
    for i, (x, actor) in enumerate(zip(xs, actors)):
        lanes.append(f'<line x1="{x}" y1="76" x2="{x}" y2="{height - 15}" stroke="#c9d2df" stroke-dasharray="4 5"/>')
        lanes.append(f'<rect x="{x - 82}" y="16" width="164" height="60" rx="8" fill="{palette[i % len(palette)]}" stroke="#cdd8e6"/>')
        labels = actor.split('\n')
        for j, line in enumerate(labels):
            lanes.append(f'<text x="{x}" y="{43 - (len(labels)-1)*8 + j*17}" text-anchor="middle" font-size="13" font-weight="600">{escape(line)}</text>')
    return f'<div class="diag-readme-sequence" tabindex="0" role="region" aria-label="{escape(title)}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{key}-title {key}-desc"><title id="{key}-title">{escape(title)}</title><desc id="{key}-desc">{escape(description)}</desc><defs>{defs}</defs>{"".join(lanes)}{"".join(parts)}</svg></div>'


def render_readme():
    uds = sequence('diag-readme-uds', ['Diagnostic\nTester / VCI', 'VCM\nGateway', 'MCU Transport\nCAN / ISO-TP', 'MCU\nDcm', 'MCU\nDem'], [
        ('note', 'Reference sequence: project CAN IDs and VCM routing rules are not verified.'),
        ('msg', 0, 1, 'UDS 19 02 08 over Diagnostic CAN'),
        ('msg', 1, 2, 'Route request to INFO CAN FD'),
        ('msg', 2, 3, 'Deliver complete UDS payload'),
        ('msg', 3, 3, 'Validate service, subfunction, length and access'),
        ('msg', 3, 4, 'Get supported status mask'),
        ('reply', 4, 3, 'DTCStatusAvailabilityMask'),
        ('msg', 3, 4, 'Set filter: confirmedDTC (0x08)'),
        ('msg', 3, 4, 'Iterate matching DTCs'),
        ('reply', 4, 3, 'DTC + status records'),
        ('msg', 3, 3, 'Build 59 02 response'),
        ('reply', 3, 2, 'Positive response / NRC'),
        ('reply', 2, 1, 'ISO-TP response over INFO CAN FD'),
        ('reply', 1, 0, 'Routed diagnostic response'),
    ], 'UDS request dispatch and DTC query', '通用参考时序：诊断仪经 VCM 路由到 MCU。通信栈把完整 UDS 请求交给 Dcm；Dcm 校验后向 Dem 设置过滤条件、读取 DTC 和状态，再沿通信链路返回。实际 CAN ID 和网关路由尚未核实。')
    reporting = sequence('diag-readme-report', ['AAOS\nDTC Collector', 'Vehicle HAL', 'QNX\ndtcagent', 'librpcif / rpcd', 'MCU\nSPI Endpoint', 'MCU\nDem'], [
        ('phase', 'Background reporting runs independently of an external UDS read request.'),
        ('msg', 0, 0, 'Read Wi-Fi / BT / USB state; sleep 3 s after each round'),
        ('msg', 0, 1, 'TOPIC_DTC_UPDATE: status[8] + DTC[24]'),
        ('unverified', 1, 2, 'Bridge mapping unverified; QNX subscribes to dtc/Update/Set'),
        ('msg', 2, 2, 'Repack Android DTC / status values'),
        ('msg', 2, 3, 'RPC 0x4345: DTC[3 bytes] + status[1 byte]'),
        ('msg', 3, 4, 'SPI transfer; QNX endpoint /dev/spi9'),
        ('unverified', 4, 5, 'Firmware adapter / EventId mapping unverified'),
        ('phase', 'QNX board monitoring uses the same outbound RPC / SPI path.'),
        ('msg', 2, 2, 'Read BSP status / thermal state; batch interval at least 3 s'),
        ('msg', 2, 3, 'RPC 0x4345: DTC[3 bytes] + status[1 byte]'),
        ('msg', 3, 4, 'SPI transfer'),
        ('unverified', 4, 5, 'Event ingestion and storage policy require MCU source'),
    ], 'QNX and Android background fault reporting', '源码确认 Android 采集状态后写 Vehicle HAL 属性；QNX 订阅 DTC 主题并将状态转换为内部 0x4345 消息，通过 rpcd 的 SPI 路径发送到 MCU。Vehicle HAL 中间映射和 MCU 接入 Dem 的具体代码尚未确认。QNX 板级采集同样主动上报，不等待 0x19 请求。')
    storage = sequence('diag-readme-storage', ['MCU\nDcm', 'Dem\nRAM State', 'NvM', 'Memory Stack\nAbstraction / Driver', 'Flash / EEPROM'], [
        ('note', 'Typical persistence lifecycle; the MCU reference diagram selects a Flash path.'),
        ('phase', 'Startup: restore valid persisted diagnostic data'),
        ('msg', 2, 3, 'Read configured diagnostic blocks'),
        ('msg', 3, 4, 'Read nonvolatile data'),
        ('reply', 4, 3, 'Stored records'),
        ('reply', 3, 2, 'Data + read / integrity result'),
        ('reply', 2, 1, 'Restore valid state; initialize defaults on failure'),
        ('phase', 'Runtime: monitors update event state in RAM'),
        ('msg', 1, 1, 'Process reported events; update status / configured records'),
        ('phase', 'Persistence: triggered by the configured policy, not by every diagnostic read'),
        ('msg', 1, 2, 'Persist changed diagnostic blocks'),
        ('msg', 2, 3, 'Schedule block write'),
        ('msg', 3, 4, 'Write nonvolatile data'),
        ('reply', 4, 3, 'Write result'),
        ('reply', 3, 2, 'Job completion'),
        ('reply', 2, 1, 'Persistence result'),
        ('phase', 'Diagnostic query: read managed records'),
        ('msg', 0, 1, 'Read matching DTC records'),
        ('reply', 1, 0, 'DTC + status / requested record data'),
    ], 'Dem RAM and nonvolatile storage lifecycle', '典型存储时序：上电时通过 NvM 和存储栈恢复有效数据，运行时在 RAM 更新事件和记录，按配置触发持久化写入，Dcm 查询由 Dem 管理的数据。具体 Flash 区域、数据块和写入策略尚未核实。')
    return '''
<dialog class="diag-readme" id="sw-diag-readme" aria-labelledby="diag-readme-title" aria-describedby="diag-readme-description">
  <div class="diag-readme-shell">
    <div class="diag-readme-header"><div><h2 id="diag-readme-title">Diagnostic README</h2><p id="diag-readme-description">UDS 基本协议 → 项目代码实现 → 交互时序</p></div><button type="button" id="sw-diag-readme-close" autofocus aria-label="关闭诊断介绍，返回架构图">关闭 ×</button></div>
    <div class="diag-readme-layout">
      <nav class="diag-readme-toc" aria-label="诊断介绍目录">
        <a href="#diag-guide-protocol">UDS 基本协议</a><a href="#diag-guide-overview">软件组件</a><a href="#diag-guide-routing">项目拓扑与寻址</a><a href="#diag-guide-request">MCU 请求处理</a><a href="#diag-guide-reporting">项目代码实现</a><a href="#diag-guide-storage">DTC 存储</a><a href="#diag-guide-sequences">交互时序</a><a href="#diag-guide-evidence">证据与待确认项</a>
      </nav>
      <article class="diag-readme-body" lang="zh-CN">

        <section id="diag-guide-protocol"><h3>UDS 基本协议</h3>
          <p>UDS（ISO 14229）规定诊断仪（客户端）向 ECU（服务端）请求的服务及响应，不限定物理连接器。经 CAN 传输时，ISO-TP（ISO 15765-2）提供分段、流控与重组；经以太网传输时可使用 DoIP。OBD 在本项目拓扑中是诊断连接器，不等同于 UDS 协议。</p>
          <div class="diag-readme-table"><table><thead><tr><th>字段</th><th>用途</th><th>所在层</th></tr></thead><tbody>
            <tr><td>CAN ID</td><td>识别该总线上的报文及诊断通道；跨网关后可能映射成另一 ID。</td><td>CAN 帧</td></tr>
            <tr><td>PCI</td><td>单帧 / 首帧 / 连续帧 / 流控帧标记及长度、序号。</td><td>ISO-TP</td></tr>
            <tr><td>SID、可选子功能、请求参数</td><td>服务操作及其对象，例如 DID、DTC 或状态掩码。</td><td>UDS 有效载荷</td></tr>
            <tr><td>Padding</td><td>按链路配置填充数据区；不是诊断业务参数。</td><td>传输封装</td></tr>
          </tbody></table></div>
          <p><strong>读数据：</strong><code>22 F1 90</code> 中，<code>22</code> 是 ReadDataByIdentifier，<code>F190</code> 是 VIN 的两字节 DID；<code>0x22</code> 没有子功能。经典 CAN 普通寻址、填充为零时，单帧数据区可写作 <code>03 22 F1 90 00 00 00 00</code>，开头的 <code>03</code> 是 ISO-TP 长度，不属于 UDS。肯定响应以 <code>62 F1 90</code> 开始，后接 VIN；否定响应为 <code>7F 22 NRC</code>。VIN 回复较长，可由 ISO-TP 的首帧、流控帧和连续帧传输。示例不代表本项目 CAN ID 或填充配置。</p>
          <p><strong>读故障：</strong><code>19 02 08</code> 中，<code>19</code> 是 ReadDTCInformation，<code>02</code> 是按状态筛选的子功能，<code>08</code> 是 confirmedDTC 状态掩码。DTC 编号通常为三字节，查询结果中的后一字节是状态位。状态位是八个可组合的标志：当前测试失败 <code>01</code>、本运行周期失败 <code>02</code>、待确认 <code>04</code>、已确认 <code>08</code>、清除后尚未完成测试 <code>10</code>、清除后曾失败 <code>20</code>、本周期尚未完成测试 <code>40</code>、请求故障指示 <code>80</code>。筛选条件是 <code>(status &amp; mask) != 0</code>，因此 <code>09</code> 表示 01 或 08 任意一位匹配，不要求同时成立；<code>FF</code> 还可能返回尚未完成测试的 DTC。<code>19 0A</code> 用于列出 ECU 支持的 DTC；已配置的快照和扩展数据可用 <code>19 04</code> / <code>19 06</code> 查询。</p>
          <p><strong>其他常用服务：</strong><code>10</code> 切换会话、<code>14</code> 清故障、<code>22</code> 读 DID、<code>27</code> 访问授权、<code>31</code> 执行例程、<code>3E</code> 维持诊断会话。某些操作受会话、权限和执行条件限制。DID、DTC、返回字段与解释必须由 ECU 诊断描述和项目配置约定，不能仅凭服务号推断。本文的概念顺序参考 <a href="https://www.csselectronics.com/pages/uds-protocol-tutorial-unified-diagnostic-services" target="_blank" rel="noopener noreferrer">CSS Electronics 的 UDS 入门文章</a>；以下再区分本项目源码证据与尚待确认的 MCU 实现。</p>
        </section>
        <section id="diag-guide-overview"><h3>项目软件组件及职责</h3>
          <p><strong>后台监测与记录</strong>在设备运行期间采集故障状态；<strong>诊断请求与响应</strong>由诊断仪发起，读取数据、查询故障或执行指定动作。读取 DTC 通常查询已经维护的记录，不要求重新检查所有设备。</p>
          <div class="diag-readme-callout">本文使用三类证据：<strong>源码确认</strong>表示已核对本项目代码；<strong>通用机制</strong>表示标准或典型实现；<strong>参考 / 待确认</strong>表示只有所附架构图或证据尚不完整。时序图中的棕色虚线表示未确认的实现映射，绿色虚线表示返回数据。</div>
          <div class="diag-readme-table"><table><thead><tr><th>组件 / 数据</th><th>职责</th></tr></thead><tbody>
            <tr><td>Fault Monitor</td><td>驱动或业务模块中的检测逻辑，报告检测通过、失败或待判定状态。</td></tr>
            <tr><td>Dcm — Diagnostic Communication Manager</td><td>解析 UDS 请求，检查会话和执行条件，分派服务并组织响应。</td></tr>
            <tr><td>Dem — Diagnostic Event Manager</td><td>维护诊断事件及 DTC 状态，按配置处理去抖、确认、恢复、现场数据和事件存储。</td></tr>
            <tr><td>NvM — NVRAM Manager</td><td>管理非易失存储数据块及读写任务；它是软件，不是存储芯片。</td></tr>
            <tr><td>Data Provider / Routine Handler</td><td>提供 DID 数据或执行 RID 对应的业务。请求可能由 MCU 本地处理，也可能按项目映射转给 QNX / Android。</td></tr>
            <tr><td>SID / DID / RID / DTC / Event ID</td><td>分别标识诊断服务、数据项、例程、对外故障码和内部诊断事件。它们与通信寻址所用的 CAN ID / DoIP 逻辑地址不同。</td></tr>
          </tbody></table></div>
          <p>UDS（ISO 14229）定义诊断服务；ISO-TP（ISO 15765-2）负责 CAN / CAN FD 上的分段、重组与流控；DoIP（ISO 13400）承载 IP 网络诊断；AUTOSAR 定义 Dcm / Dem 等软件职责；ODX 描述 ECU 的诊断接口。具体 DID、DTC、阈值、权限和时序由项目规范定义，模块名称相同不代表已验证完整标准符合性。</p>
          <div class="diag-readme-table"><table><thead><tr><th>业务需求</th><th>常见 UDS 服务</th></tr></thead><tbody>
            <tr><td>读版本、序列号、状态</td><td><code>0x22</code> ReadDataByIdentifier</td></tr><tr><td>读 / 清故障</td><td><code>0x19</code> ReadDTCInformation / <code>0x14</code> ClearDiagnosticInformation</td></tr><tr><td>执行自检、产线操作</td><td><code>0x31</code> RoutineControl；部分输出控制使用 <code>0x2F</code></td></tr><tr><td>写数据 / 下载软件</td><td><code>0x2E</code>；下载流程常用 <code>0x34 / 0x36 / 0x37</code> 等</td></tr>
          </tbody></table></div>
        </section>
        <section id="diag-guide-routing"><h3>诊断数据如何到达 MCU</h3>
          <p><strong>A 平台拓扑参考：</strong>诊断仪通过 VCI（车辆通信接口）接入 OBD 连接器，经 Diagnostic CAN（500 kbit/s）到达 VCM，再由网关按配置路由至 INFO CAN FD 侧的座舱控制器。图纸能说明网络连接；实际请求 / 响应 CAN ID、VCM 转发规则及 MCU 接收过滤配置尚未核实。</p>
          <pre>Tester / VCI ↔ OBD ↔ Diagnostic CAN ↔ VCM ↔ INFO CAN FD ↔ IVI MCU</pre>
          <p>OBD 在这里指车辆诊断连接器。诊断仪根据 ECU 诊断描述组装 UDS 请求，再由通信栈封装发送；不能根据 MCU 的芯片名称寻址。CAN 诊断通常按配置的接收 / 发送 CAN ID 寻址，扩展寻址还可能使用额外地址字节。物理寻址用于指定目标，功能寻址用于一组目标。网关可以做地址和网络映射，不应假定 CAN ID 原样透传。</p>
          <div class="diag-readme-table"><table><thead><tr><th>路径</th><th>诊断请求的封装</th><th>项目范围</th></tr></thead><tbody>
            <tr><td>UDS over CAN</td><td>UDS → ISO-TP → CAN / CAN FD</td><td>MCU 参考图给出 CAN FD → CanIf → CanTp → Dcm 路径。</td></tr>
            <tr><td>UDS over DoIP</td><td>UDS → DoIP → TCP/IP → Ethernet；发现等功能可使用 UDP</td><td>源码存在 Android doip_server / DcmManager 入口；这不证明请求自动转发到 MCU。</td></tr>
          </tbody></table></div>
          <p>DoIP 网关可以把请求路由到 CAN ECU，但本项目是否采用这条桥接路径及其逻辑地址映射，需要另外核实。普通 TCP 或 SPI 消息也不能仅凭传输方式就称为 DoIP 或 UDS。</p>
        </section>
        <section id="diag-guide-request"><h3>MCU 侧典型请求处理</h3>
          <p><span class="diag-readme-tag">通用机制</span>采用典型 AUTOSAR CAN 诊断栈时，请求经过 <code>CAN Driver → CanIf → CanTp → PduR → Dcm</code>。CanTp 将分段重组为完整 UDS 消息；PduR 是典型路由组件，所附 MCU 图未单列它，因此不宣称项目已有该模块。</p>
          <ol><li><strong>校验：</strong>Dcm 检查服务、子功能、长度、参数和配置要求的会话 / 访问条件。</li><li><strong>派发：</strong><code>0x19</code> 查询 Dem；<code>0x14</code> 请求清除；<code>0x22</code> 调用 DID 数据提供者；<code>0x31</code> 调用 RID 对应例程。Dcm 通过配置和回调映射识别业务。</li><li><strong>执行：</strong>本地数据可直接获取；跨处理器数据按业务接口请求 QNX / Android。服务编号本身不决定必须访问哪个域。</li><li><strong>响应：</strong>返回肯定响应或 <code>7F + SID + NRC</code> 否定响应；异步处理遵循配置时序，必要时可发送 <code>7F 19 78</code> 表示处理中。</li></ol>
          <p>以下以 <code>19 02 08</code> 为例：服务 <code>0x19</code> 读取 DTC，子功能 <code>0x02</code> 按状态筛选，掩码 <code>0x08</code> 选择 confirmedDTC。已确认不等于当前仍然失败。</p>
          <div class="diag-readme-table"><table><thead><tr><th>报文 / 操作</th><th>解释</th></tr></thead><tbody>
            <tr><td><code>19 02 08</code></td><td>UDS 请求有效载荷。经典 CAN 普通寻址、填充为 00 的示例数据区：<code>03 19 02 08 00 00 00 00</code>；03 是 ISO-TP 单帧长度，不是 UDS 服务。</td></tr>
            <tr><td>Dem 查询</td><td>典型接口：<code>Dem_GetDTCStatusAvailabilityMask</code> → <code>Dem_SetDTCFilter</code> → 循环 <code>Dem_GetNextFilteredDTC</code>；版本不同接口可能变化。</td></tr>
            <tr><td><code>59 02 FF 12 34 56 09</code></td><td>示例肯定响应：59 为响应服务，02 为子功能，FF 为支持的状态位掩码，123456 为虚构 DTC，09 表示 testFailed 与 confirmedDTC。不是项目真实故障码或支持掩码。</td></tr>
            <tr><td><code>59 02 FF</code></td><td>假设支持掩码为 FF，未匹配到 DTC 时也可肯定响应，记录列表为空。</td></tr>
            <tr><td><code>7F 19 13</code> / <code>7F 19 12</code></td><td>长度 / 格式错误，或不支持子功能。报文较长时由传输栈分段，不由 Dem 处理 CAN 帧。</td></tr>
          </tbody></table></div>
          <p><code>19 02 FF</code> 表示按所有支持的状态位筛选；只要匹配任一位即可，并不等价于“列出所有当前故障”。<code>19 0A</code> 用于报告支持的 DTC；<code>19 04</code> / <code>19 06</code> 可读取快照 / 扩展数据，支持范围以 ECU 配置为准。</p>
        </section>
        <section id="diag-guide-reporting"><h3>QNX / Android 故障上报的代码实现</h3>
          <p><span class="diag-readme-tag">源码确认</span>这条链路独立于诊断仪读取：QNX 的 <code>dtcagent</code> 主动读取板级设备状态并检查 SoC 温度；其发送批次设置至少 3000 ms 的间隔控制，每条再间隔 3 ms，因此不能理解为严格每 3 秒一次。Android 的 <code>DtcEventHandler</code> 读取 Wi-Fi / 蓝牙和 USB 充电状态，分发本轮维护的数据后休眠 3000 ms。两者都不只在诊断仪发送 0x19 时才采集。</p>

          <div class="diag-readme-table"><table><thead><tr><th>源码位置 / 函数</th><th>已确认的处理</th></tr></thead><tbody>
            <tr><td>Android <code>DtcEventHandler</code> → <code>VehicleManager.sendDtc</code></td><td>采集 Wi-Fi / 蓝牙、USB 充电状态；把内部状态放到高 8 位、DTC 编号放到低 24 位，再写 <code>TOPIC_DTC_UPDATE</code>。</td></tr>
            <tr><td>QNX <code>convert_qnxVipc2todtc</code></td><td>解析 <code>dtc/Update/Set</code> 的值数组，将每个 32 位值重排为 <code>[DTC 高、中、低字节, status]</code> 的独立 4 字节内部帧。</td></tr>
            <tr><td>QNX <code>convert_qnxBsp2dtc</code></td><td>将板级监测结果转换为 <code>bus_id=1</code>、<code>frame_dlc=4</code> 的内部 RPC 帧。</td></tr>
            <tr><td><code>dtc_clientRpcd</code> → <code>rpcd_mcu_spi</code></td><td>调用 <code>rpcif_update_clusterstate</code>；QNX rpcd 通过 SPI 路径发送。源码未证明 MCU 接收后如何进入 Dem。</td></tr>
          </tbody></table></div>
          <p>Android 通过 <code>VehicleManager</code> 写 <code>TOPIC_DTC_UPDATE</code>，每个值打包为 <code>(status &lt;&lt; 24) | DTC</code>。QNX 订阅 <code>dtc/Update/Set</code> 并重排字段，通过 <code>librpcif → rpcd → SPI</code> 向 MCU 发送内部消息：</p>
          <pre>RPC message ID: 0x4345     bus_id: 1     payload length: 4
Payload: [DTC high byte] [DTC middle byte] [DTC low byte] [status]</pre>
          <p><strong>0x4345 是内部 RPC 消息 ID，不是诊断请求的 CAN ID，也不是 UDS 服务编号。</strong>此处的单字节状态是项目内部上报值，不能直接解释为完整 UDS DTC 状态字节；MCU 如何映射为事件和 Dem 状态仍待固件确认。</p>
          <p><span class="diag-readme-tag is-reference">待确认</span>Android Vehicle HAL 与 QNX 主题之间的完整桥接映射尚未确认；MCU 收到 SPI 消息后由哪一个 SPI Task 解析、如何映射 Event ID、是否调用 Dem，仍需固件源码。示意图没有替这些缺口指定 HAB / VSOCK 等传输方式。</p>
          <p>若 MCU 已在 Dem 中维护这些上报状态，收到 0x19 后可以直接查询。只有项目另外设计了代理查询或按需刷新，才需要再次请求 QNX。读取实时 DID 或执行例程可能产生跨域请求，应与后台 DTC 上报区分。</p>
        </section>
        <section id="diag-guide-storage"><h3>Dem 将 DTC 数据存放在哪里</h3>
          <p><strong>运行时在 RAM 管理，需要掉电保留的数据通过 NvM 保存到非易失存储。</strong>DTC 编号及事件映射通常属于软件配置；运行时记录保存的是发生情况、状态、快照及配置的扩展数据。清除记录不会删除软件中对 DTC 的定义。</p>
          <div class="diag-readme-table"><table><thead><tr><th>位置 / 模块</th><th>保存或管理的内容</th><th>掉电行为</th></tr></thead><tbody>
            <tr><td>Dem RAM / Event Memory</td><td>运行中的事件状态、计数和故障记录。Event Memory 是逻辑管理概念，不是一颗芯片。</td><td>RAM 通常丢失；下次启动恢复配置要求保留的数据。</td></tr>
            <tr><td>NvM</td><td>管理诊断数据块、读写请求和完成状态；下层可能有 MemIf、Fee / Ea 等抽象组件。</td><td>自身是软件模块，不是存储介质。</td></tr>
            <tr><td>Flash / EEPROM</td><td>持久化的诊断数据块，布局和内容依配置与实现而定。</td><td>已经成功写入的数据可保留。</td></tr>
          </tbody></table></div>
          <p>保存可在首次记录、相关数据更新或正常关机等配置时机触发，并非每次接收状态或读取 0x19 都写 Flash。掉电前尚未完成写入的数据不保证保留。故障恢复后，当前状态和历史记录按规则更新；历史记录可能等待老化或 0x14 清除。清除时也要保持 RAM 与持久化记录一致，响应完成时机由配置决定。</p>
          <p><span class="diag-readme-tag is-reference">MCU 参考图</span>所附图明确画出 <code>Dem → NvM → Flash Driver</code>。这支持 Flash 存储路径的设计意图，但还不能确定使用哪块 Flash、地址范围、块大小、容量或写入策略；也不能把它等同于 QNX / Android 的 UFS 分区。</p>
        </section>

        <section id="diag-guide-sequences"><h3>交互时序</h3>
          <p>先看外部诊断仪主动读取：示例使用 <code>19 02 08</code> 查询已确认 DTC。图中的 VCM 路由与 MCU Dem 行为按通用机制和参考架构表达，实际 CAN ID、服务配置及网关实现仍待核实。</p>
          <!-- UDS_SEQUENCE -->
          <p>再看项目源码确认的后台上报：Android 和 QNX 监测任务在诊断仪未接入时也会运行。棕色虚线表示缺少 Vehicle HAL 中间映射或 MCU 固件证据，不能将它解释为已确认的 Dem 写入。</p>
          <!-- REPORTING_SEQUENCE -->
          <p>最后是典型持久化生命周期：事件状态在运行时由 Dem 管理，配置要求保留的记录经 NvM 存入非易失介质。具体存储布局与写入策略需要 MCU 配置证据。</p>
          <!-- STORAGE_SEQUENCE -->
        </section>
        <section id="diag-guide-evidence"><h3>实现证据与待确认项</h3>
          <div class="diag-readme-table"><table><thead><tr><th>证据</th><th>可以确认的范围</th></tr></thead><tbody>
            <tr><td>A 平台电子电器架构、所附 MCU 图</td><td>OBD / VCM / INFO CAN FD 拓扑，以及 Dcm、Dem、NvM、SPI、Flash 的参考关系；不提供实际路由和存储配置。</td></tr>
            <tr><td><code>cluster_source_code/platforms/dtcagent/</code></td><td><code>src/dtc_clientQnxBsp.cpp</code> 的 threadFun；<code>inc/dtc_clientQnxBsp.h</code> 的 WAIT_TIME；<code>src/dtc_convertMsg.cpp</code> 的 convert_qnxBsp2dtc / convert_qnxVipc2todtc；<code>inc/dtc_common.h</code> 的 0x4345；<code>src/dtc_clientRpcd.cpp</code> 的 rpcif_update_clusterstate。</td></tr>
            <tr><td><code>cluster_source_code/platforms/rpcd/src/rpcd_mcu_spi.c</code></td><td>QNX 分支使用 /dev/spi9 和 spi_xchange；MCU 内部接收任务绑定未被此文件证明。</td></tr>
            <tr><td>Android vendor 诊断源码</td><td><code>diagService/.../dtcEvent/DtcEventHandler.java</code> 的采集循环；<code>vehicle/VehicleManager.java</code> 的属性打包；<code>doipserver/dcm/DcmManager.cpp</code> 的 UDS 回调注册。此处省略供应商目录名。</td></tr>
          </tbody></table></div>
          <p><strong>待补齐：</strong>诊断请求 / 响应 CAN ID、VCM 路由表、MCU 服务与 DID / RID 配置、0x4345 到 Dem Event ID 的映射、DTC 判定 / 老化 / 清除规则、NvM 数据块与 Flash 地址配置、Android Vehicle HAL 到 QNX 的完整桥接。</p>
          <p>验收应覆盖请求正常返回、错误参数、访问条件、长报文、故障注入与恢复、掉电重启和清除后再次检测。没有配置和测试证据，不能仅凭架构图认定满足某个标准版本。</p>
          <ul class="diag-readme-sources">
            <li><a href="https://www.csselectronics.com/pages/uds-protocol-tutorial-unified-diagnostic-services" target="_blank" rel="noopener noreferrer">CSS Electronics — UDS Explained</a>：基本协议、报文、响应及 ISO-TP 入门示例。</li>
            <li><a href="https://www.iso.org/standard/87962.html" target="_blank" rel="noopener noreferrer">ISO 14229-1 — UDS</a>：诊断服务；具体采用版本以项目基线为准。</li>
            <li><a href="https://docs.kernel.org/networking/iso15765-2.html" target="_blank" rel="noopener noreferrer">Linux Kernel — ISO-TP</a>：CAN 诊断寻址、分段与重组。</li>
            <li><a href="https://www.iso.org/standard/13400-2" target="_blank" rel="noopener noreferrer">ISO 13400-2 — DoIP</a>：IP 网络上的诊断传输与路由。</li>
            <li><a href="https://www.autosar.org/fileadmin/standards/R22-11/CP/AUTOSAR_SWS_DiagnosticCommunicationManager.pdf" target="_blank" rel="noopener noreferrer">AUTOSAR Dcm, R22-11</a>：请求校验、服务派发和 DTC 查询响应。</li>
            <li><a href="https://www.autosar.org/fileadmin/standards/R22-11/CP/AUTOSAR_SWS_DiagnosticEventManager.pdf" target="_blank" rel="noopener noreferrer">AUTOSAR Dem, R22-11</a>：事件、故障记录和持久化接口。</li>
            <li><a href="https://www.autosar.org/fileadmin/standards/R22-11/CP/AUTOSAR_SWS_NVRAMManager.pdf" target="_blank" rel="noopener noreferrer">AUTOSAR NvM, R22-11</a>：非易失存储数据块管理。</li>
            <li><a href="https://www.asam.net/standards/detail/mcd-2-d/" target="_blank" rel="noopener noreferrer">ASAM MCD-2 D — ODX</a>：诊断服务、数据及工具配置描述。</li>
          </ul>
        </section>
      </article>
    </div>
  </div>
</dialog>'''.replace('<!-- UDS_SEQUENCE -->', uds).replace('<!-- REPORTING_SEQUENCE -->', reporting).replace('<!-- STORAGE_SEQUENCE -->', storage)
