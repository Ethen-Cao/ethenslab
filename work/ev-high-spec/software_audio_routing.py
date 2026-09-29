"""Source-grounded audio route resolution and physical slot evidence."""
import json
from pathlib import Path
from html import escape

DATA = json.loads(Path(__file__).with_name('audio-routing-data.json').read_text())

def source_links(keys):
    return ' '.join(f'<a href="file:///home/ethen/workspace/HBEZ/{escape(DATA["sources"][k]["path"],quote=True)}">[{k}]</a>' for k in keys)

def table(headers, rows, cls=''):
    return '<div class="sw-flow-table-wrap"><table class="sw-flow-table '+cls+'"><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def route_fields(route):
    return dict(bus=route['address'],stream='STREAMRX = '+route['streamKey'],pp='DEVICEPP_RX = '+route['ppKey'],device=route['device'],devicekey='DEVICERX = '+route['deviceKey'],backend=route['backend'],format=route['format'])

def render_resolution_graph():
    f=route_fields(DATA['routes'][0])
    parts=['<svg xmlns="http://www.w3.org/2000/svg" id="audio-route-graph" viewBox="0 0 1760 450" role="img" aria-label="Selected bus to backend route resolution" font-family="Arial, sans-serif">',
           '<defs><marker id="audio-route-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L7 4 L0 8" fill="none" stroke="#3974d9" stroke-width="1.3"/></marker></defs>',
           '<rect x="1" y="1" width="1758" height="448" rx="14" fill="#fbfcff" stroke="#dce3ed"/>']
    def text(x,y,t,sz=13,color='#1f2e40',weight=400,id=None):
        parts.append(f'<text x="{x}" y="{y}" font-size="{sz}" fill="{color}" font-weight="{weight}"'+(f' id="audio-route-{id}"' if id else '')+'>'+escape(t)+'</text>')
    def box(x,y,w,title,lines,fill='#edf5ee'):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="90" rx="8" fill="{fill}" stroke="#b5c9bc"/>')
        text(x+14,y+23,title,14,weight=700)
        for i,(s,key) in enumerate(lines):text(x+14,y+47+i*22,s,12,id=key)
    def edge(d):parts.append(f'<path d="{d}" fill="none" stroke="#3974d9" stroke-width="1.5" marker-end="url(#audio-route-arrow)"/>')
    text(22,30,'ROUTE RESOLUTION',16,weight=700)
    text(255,30,'Arrows show configuration dependencies, not PCM sample flow.',12,'#647184')
    box(25,125,330,'Android bus',[(f['bus'],'bus'),('PAL_STREAM_PLAYBACK_BUS',None)])
    box(410,55,330,'Stream / processing keys',[(f['stream'],'stream'),(f['pp'],'pp')])
    box(410,225,330,'AudioDevice / PAL device',[(f['device'],'device'),(f['devicekey'],'devicekey')])
    box(800,225,370,'ResourceManager / BE interface',[(f['backend'],'backend'),(f['format'],'format')])
    box(800,55,370,'AGM session + AIF metadata',[('Stream + session-AIF + device keys',None),('FE Connect selects the BE interface',None)])
    box(1230,55,500,'GSL / HAB / QNX audio_service',[('Graph open / configuration commands',None),('ACDB graph + calibration lookup',None)],'#eaf1fe')
    box(1230,225,500,'ADSP graph / hardware endpoint',[('Mixing / channel routing / TDM configuration',None),('Bus-to-slot matrix: unknown',None)],'#fff7e4')
    edge('M355 170 H380 V100 H410');edge('M355 170 H380 V270 H410')
    edge('M740 100 H800');edge('M740 270 H800');edge('M985 225 V145')
    edge('M1170 100 H1230');edge('M1480 145 V225')
    text(30,365,'Separate identities:',13,weight=700)
    text(170,365,'bus address / PAL device / graph key / BE interface / TDM slot',13)
    text(30,394,'A shared BE does not imply an identical DSP graph. No fixed bus-to-slot correspondence is inferred.',13,'#647184')
    text(30,422,'RX / TX in BE names follow the audio backend convention: playback / capture.',12,'#647184')
    parts.append('</svg>')
    return ''.join(parts)

def render_slot_graph():
    p=['<svg xmlns="http://www.w3.org/2000/svg" id="audio-slot-graph" viewBox="0 0 1760 560" role="img" aria-label="Verified ADC and A2B slot allocation" font-family="Arial, sans-serif"><rect x="1" y="1" width="1758" height="558" rx="14" fill="white" stroke="#dce3ed"/>']
    def text(x,y,t,size=13):p.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="#24364a">{escape(t)}</text>')
    text(24,32,'TDM / A2B SLOT ALLOCATION',17)
    text(24,60,'Source configuration; slot indices are zero-based. Playback bus-to-slot mapping remains unknown.')
    text(24,101,'MIC ADC: SLOT_MAPPING = 0x542310 | CHANNEL_SWITCH = 0x3F | 32-bit slots',14)
    for slot,mic in enumerate([1,2,4,3,5,6]):
        x=24+slot*281
        p.append(f'<rect x="{x}" y="118" width="265" height="65" rx="7" fill="#eaf1fe" stroke="#bfd3f8"/>')
        text(x+13,142,f'Slot {slot}',14);text(x+13,165,f'Hardware MIC{mic}')
    text(24,210,'ADC channel mapping is verified. DSP capture extraction and application channel order need graph confirmation.')
    text(24,252,'A2B downstream: 16 slots | 48 kHz | 32-bit | bus start index 0',14)
    for slot in range(16):
        x=24+slot*107
        p.append(f'<rect x="{x}" y="269" width="99" height="63" rx="6" fill="#fff7e4" stroke="#dfca91"/>')
        text(x+12,293,f'Slot {slot}');text(x+12,315,'unknown',12)
    text(24,357,'Signal / speaker assignment is unknown. These slots are not labeled as unused.')
    text(24,396,'A2B upstream: 4 slots | 48 kHz | 32-bit | bus start index 0',14)
    for slot in range(4):
        x=24+slot*250
        p.append(f'<rect x="{x}" y="413" width="232" height="63" rx="6" fill="#f0ecfa" stroke="#cfc0e3"/>')
        text(x+13,437,f'Slot {slot}');text(x+13,461,'Signal purpose: unknown',12)
    text(24,510,'16-slot x 32-bit x 48 kHz = 24.576 MHz serial bit clock, if one lane carries the full frame. Not a measured value.')
    text(24,538,'ADSP slot_mask / lane configuration / bus mixing matrix are not established by the peripheral slot settings.')
    p.append('</svg>');return ''.join(p)

def render_routing():
    opts=''.join(f'<option value="{escape(r["address"])}">{escape(r["address"])} - {escape(r["name"])}</option>' for r in DATA['routes'])
    rows=[]
    for r in DATA['routes']:
        active=r==DATA['routes'][0]
        rows.append('<tr data-route-row="'+escape(r['address'])+'"'+(' class="is-selected"' if active else '')+'><td><button type="button" class="audio-route-choice" data-audio-route="'+escape(r['address'])+'" aria-pressed="'+str(active).lower()+'">'+escape(r['address'])+'</button><small>'+escape(r['zone'])+'</small></td><td>'+escape(', '.join(r['contexts']) or 'No context in selected car config')+'</td><td><code>'+escape(r['device'])+'</code></td><td><code>'+r['streamKey']+'<br>'+r['deviceKey']+'<br>'+r['ppKey']+'</code></td><td><code>'+escape(r['backend'])+'</code><small>'+escape(r['format'])+'</small></td><td>unknown</td></tr>')
    bus_table='<div class="sw-flow-table-wrap"><table class="sw-flow-table audio-bus-table"><thead><tr>'+''.join('<th>'+t+'</th>' for t in ['Android bus / zone','Audio contexts','PAL device','STREAMRX / DEVICERX / DEVICEPP_RX','BE interface / profile','Business → slot'])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    capture=table(['Entry / stream','PAL device(s)','BE interface(s)','Mapping / limitation'],[
      ['BUS04_INPUT<br>BUS09_INPUT_FRONT_PASSENGER','PAL_DEVICE_IN_HANDSET_MIC','TDM-LPAIF_AUD-TX-PRIMARY','AUDIO_DEVICE_IN_BUS 的默认映射；48 kHz / 32-bit / 16 channels。应用实际通道抽取、参考信号位置：unknown。'],
      ['AUDIO_DEVICE_IN_ECHO_REFERENCE','PAL_DEVICE_IN_ASR_MIC','TDM-LPAIF_AUD-TX-PRIMARY','与 handset mic 共用 BE 名称，设备 graph key 不同；不能由 BE 名推断相同录音数据。'],
      ['HFP RX loopback','PAL_DEVICE_IN_HFP_DOWNLINK → PAL_DEVICE_OUT_SPEAKER','TDM-LPAIF_WSA-TX-PRIMARY → TDM-LPAIF_RXTX-RX-PRIMARY','Hfp.cpp 直接建立 loopback；BT 收到的通话音频送扬声器。不是 BUS03_PHONE 的普通应用 PCM 播放。'],
      ['HFP TX loopback','PAL_DEVICE_IN_HANDSET_MIC → PAL_DEVICE_OUT_HFP_UPLINK','TDM-LPAIF_AUD-TX-PRIMARY → TDM-LPAIF_WSA-RX-PRIMARY','麦克风送 BT 通话上行。HFP 采样率按 8/16 kHz 模式配置；实际 BT slot 编号：unknown。']])
    strategy=table(['Decision point','Implementation','Responsibility / limits'],[
      ['Business routing','CarAudioService / AudioPolicyService','context、zone、volume group 选择 bus；焦点与应用仲裁属于上层策略。HBEZ 的 call_ring 在 Car 配置中归 BUS03_PHONE，不能直接沿用文档的简写 bus 编号。'],
      ['Stream / device resolution','AudioDevice + PayloadBuilder + ResourceManager','GetPalDeviceIds(address) 选择 PAL device；bus_addr 选择 STREAMRX 和 DEVICEPP_RX；资源配置提供 BE 名。三种 graph key 的键分别为 0xA1000000、0xA2000000、0xAC000000。'],
      ['FE / BE binding','SessionAlsaPcm → tinyalsa AGM plugin → AGM','普通 PLAYBACK_BUS 使用 SessionAlsaPcm；设置 stream/device metadata 和 FE Connect。SessionAgm 仅用于 NON_TUNNEL，不能作为所有 bus 的会话实现。'],
      ['DSP graph selection','AGM metadata merge → GSL → QNX backend → ADSP','合并 session、session-AIF、device 元数据，按 graph key 和校准配置打开/连接图。文档描述 mixing/demux、参考信号与 HFP loopback；具体图实例、混音系数、矩阵与每个 slot 的业务用途仍需 ACDB 导出。'],
      ['Runtime speaker routing','VendorAudioExtn::SyncSpeakerMode','CustomVersion == V3 时启用 ALS 分支；导航、语音、电话等下发 SPEAKER_MODE / TAG_SPEAKER_MODE，媒体同步 EQ、Fader/Balance、音效等参数。通过 PAL_PARAM_ID_UIEFFECT 下发 TKV；存在接口不代表当前车机已启用该条件。'],
      ['Runtime MIC / reference routing','SyncMicMode / SyncRefMode','micMode != 0 时通过 DEVICE_MUX_DEMUX + CHANNELS 选择 MIC 模式；值不是 TDM slot 位图。V3 下语音识别同步 reference 模式；HFP reference 分支已被注释。ECNS 的运行状态不能从库文件存在推出。'],
      ['Physical slot assignment','ADSP endpoint config + PCM6xx0 registers + A2B BCF','TDM 的 slot_mask、nslots_per_frame、slot_width 和 lane 配置需与外设匹配。Android bus 编号、PAL device ID、QNX clk_id 都不是物理 slot 编号。']])
    gaps=table(['Unresolved item','Current evidence','Required evidence'],[
      ['BUS08 / BUS16 BE binding','HAL 和 KV 文件有 A2B/A2B2 设备；本次核对的 gvmauto8295_adp_star profile 未定义这两个设备，默认后端名为空。','确认运行时选择的 resource profile、覆盖配置及已加载 AIF 列表；此处保留 unknown。'],
      ['Playback bus → slot → speaker','主从默认 TDM16，A2B 下行 16、上行 4 个 slot；没有可读业务分配表。','设计文档引用的 A2B input/output ChannelMap，以及匹配版本的 ACDB 图/通道矩阵导出。'],
      ['ADSP endpoint slot_mask / lanes','SPF API 定义了参数字段；项目 ACDB 和 delta 为二进制，本次未解析其有效图。','当前图的 PARAM_ID_TDM_INTF_CFG / PARAM_ID_TDM_LANE_CFG 与运行日志。不能用 API 默认值冒充项目配置。'],
      ['Flashed configuration','本页依据源码、配置和设计文档，非实车路由快照。','运行时 resource profile、graph key/tag dump、固件/ACDB 版本与 A2B/ADC 寄存器读数。']])
    return f'''<section id="sw-audio-routing" class="audio-routing" hidden aria-labelledby="audio-routing-title">
<div class="sw-section-heading"><h3 id="audio-routing-title">Bus / BE / TDM routing</h3><p lang="zh-CN">按项目源码核对逻辑 bus、PAL 设备、后端接口及物理时隙。未知项明确标记为 unknown，不从 bus 编号推断 slot。</p></div>
<div class="audio-route-picker"><label for="audio-route-select">Playback bus</label><select id="audio-route-select">{opts}</select><span id="audio-route-status" role="status">{escape(DATA['routes'][0]['status'])}</span></div>
<div class="audio-routing-scroll">{render_resolution_graph()}</div>
<p class="audio-routing-note" lang="zh-CN">图中箭头表示配置依赖。后端名称采用源码原名，RX 表示播放方向，TX 表示采集方向；不是芯片引脚命名。资源 profile 为 <code>resourcemanager_gvmauto8295_adp_star.xml</code>，其运行时加载情况尚未确认。{source_links(['hal','kv','rm'])}</p>
<h4>Playback bus → PAL device → BE</h4>{bus_table}
<p class="audio-routing-note" lang="zh-CN">表中 bus 来自策略 devicePort，context/zone 来自 HBEZ Car 配置；设备映射描述默认打开流路径，运行时外部设备/AG SCO 等重路由可能覆盖它。BUS2001_VENDOR_CALL_RING 虽在策略与 KV 文件中定义，但未分配到所选 Car 配置；不等同当前活跃业务。两条分区 bus 缺少本 profile 的设备定义，不能补造后端。{source_links(['build','policy','car'])}</p>
<h4>Capture &amp; HFP device pairs</h4>{capture}<p class="audio-routing-note">{source_links(['hal','hfp','rm'])}</p>
<h4>Qualcomm ADSP routing decisions</h4>{strategy}<p class="audio-routing-note">{source_links(['session','pcm','utils','plugin','payload','agm','graph','vendor'])}</p>
<h4>TDM slot allocation</h4><div class="audio-routing-scroll">{render_slot_graph()}</div>
<p class="audio-routing-note" lang="zh-CN">MIC 映射来自板级 devcfg_audio.xml 与 ADC 驱动：硬件 MIC1–6 → slot 0、1、3、2、4、5；它与文档中的二排 MIC3/MIC4 顺序交换一致。A2B 默认选择函数当前固定返回 0x3，对应已核对的 TDM16 主从配置；下行 stream 从 slot 0 起使用 16 个 slot，上行从 slot 0 起使用 4 个 slot。上行信号的业务含义仍是 unknown。{source_links(['board','adc','a2b_select','a2b','tdm_api'])}</p>
<p class="audio-routing-note" lang="zh-CN">audio_oem.cfg 的启动项为 clk_id 4/7/17，均配置 48 kHz、32-bit、16 channels；这是设备启动/时钟配置，不是 slot 4、7、17，也不构成 bus-to-slot 映射。{source_links(['oem'])}</p>
<h4>Evidence gaps</h4>{gaps}
<p class="audio-routing-note" lang="zh-CN">核对日期：{DATA['audited']}。证据文件路径及 SHA-256 保存在 <a href="audio-routing-data.json">routing data snapshot</a>；完整说明见 <a href="audio-evidence.md">Audio evidence notes</a>。</p>
</section>'''
