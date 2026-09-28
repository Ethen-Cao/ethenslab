"""Functional B-platform system view derived from the supplied hardware drawings.

This view intentionally omits project variant IDs and SoC pin/signal names. Device
part numbers live in module notes only where the source drawings identify them.
"""
from html import escape

WIDTH, HEIGHT = 1880, 1120
COLORS = {
    "rf": "#d89a12",
    "video": "#4285f4",
    "audio": "#9a63d2",
    "vehicle": "#34a853",
    "power": "#e26355",
    "connect": "#45879a",
    "internal": "#9aa9bb",
}


def create_b_system():
    panels, links, cards, labels, nodes = [], [], [], [], []

    def text(x, y, value, size=14, color="#253345", weight=400, anchor="start", extra=""):
        return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
                f'font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>')

    def panel(x, y, w, h, title, color="#dbe4ed", fill="#fff"):
        panels.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" '
                      f'fill="{fill}" stroke="{color}" stroke-width="1.5"/>')
        labels.append(text(x + 22, y + 31, title, 13, "#526276", 750,
                           extra='letter-spacing="1.4"'))

    def section(x, y, w, h, title, fill="#f8fafc"):
        panels.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="13" '
                      f'fill="{fill}" stroke="#e4eaf0"/>')
        labels.append(text(x + 15, y + 22, title, 11, "#66778b", 750,
                           extra='letter-spacing="1"'))

    def link(points, kind="internal", dashed=False, title=None):
        d = "M" + " L".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        links.append(f'<path d="{d}" fill="none" stroke="{COLORS[kind]}" '
                     f'stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"{dash}>'
                     + (f'<title>{escape(title)}</title>' if title else "") + '</path>')

    def card(id_, name, x, y, w, h, subtitle, note, kind="base", accent=None):
        lines = subtitle if isinstance(subtitle, list) else [subtitle]
        nodes.append(dict(id=id_, name=name, x=x, y=y, w=w, h=h, kind=kind,
                          lines=[name, *lines], note=note))
        stroke = accent or {"base": "#a9bfdc", "external": "#c6d9ec",
                            "reserved": "#b8c2cd", "power": "#e7a99d"}[kind]
        fill = {"base": "#fff", "external": "#f9fcff", "reserved": "#f4f6f8",
                "power": "#fff5f2"}[kind]
        dash = ' stroke-dasharray="6 4"' if kind == "reserved" else ""
        text_color = "#526070" if kind == "reserved" else "#253345"
        title_y = y + (19 if h <= 52 else 30)
        sub_y = title_y + (15 if h <= 52 else 22)
        part = (f'<g id="{id_}" class="hardware-module" data-hw-node="{id_}" '
                f'role="button" tabindex="0" aria-label="{escape(name, quote=True)}">'
                f'<title>{escape(name)} — {escape(note)}</title>'
                f'<rect class="hw-box" x="{x}" y="{y}" width="{w}" height="{h}" '
                f'rx="11" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>')
        part += text(x + 15, title_y, name, 15 if h > 60 else 13.5,
                     text_color, 700)
        for i, line in enumerate(lines):
            if line:
                part += text(x + 15, sub_y + i * 16, line, 11.5 if h > 60 else 10.5,
                             "#69798b")
        cards.append(part + '</g>')

    panel(40, 126, 370, 930, "EXTERNAL INPUTS", "#d7e2ec")
    panel(442, 126, 996, 930, "IVI UNIT", "#c9d9f1", "#f8fbff")
    panel(1470, 126, 370, 930, "CABIN & VEHICLE OUTPUTS", "#d7e2ec")

    section(57, 184, 336, 132, "RADIO & ANTENNAS")
    section(57, 343, 336, 207, "CAMERA SOURCES")
    section(57, 580, 336, 132, "AUDIO INPUTS")
    section(57, 744, 336, 215, "VEHICLE INTERFACE", "#f8fcf9")
    section(1487, 184, 336, 305, "DISPLAY ENDPOINTS")
    section(1487, 515, 336, 132, "AUDIO OUTPUTS")
    section(1487, 678, 336, 270, "EXTERNAL CONNECTIVITY")

    # Functional links are deliberately not annotated with SoC port names.
    link([(393, 232), (425, 232), (425, 178), (935, 178), (935, 206)], "rf", title="Antennas to wireless connectivity")
    link([(393, 285), (427, 285), (427, 256), (472, 256)], "rf", title="Radio antenna to tuners")
    for y in (392, 444, 496):
        link([(393, y), (431, y), (431, 463)], "video")
    link([(431, 463), (472, 463)], "video", title="Camera sources to aggregation")
    for y in (630, 682):
        link([(393, y), (430, y), (430, 707)], "audio")
    link([(430, 707), (472, 707)], "audio", title="Audio input to front end")
    link([(393, 796), (425, 796), (425, 792), (930, 792), (930, 759)], "vehicle", title="Vehicle network to MCU")
    link([(393, 848), (419, 848), (419, 1006), (472, 1006)], "power", title="Vehicle power to IVI unit")
    link([(393, 900), (436, 900), (436, 1018), (472, 1018)], "power", title="Main harness to IVI unit")

    link([(719, 463), (735, 463)], "video", title="Camera front end to compute")
    link([(1123, 463), (1139, 463)], "video", title="Compute to display interfaces")
    link([(618, 306), (618, 332), (819, 332), (819, 350)], "internal")
    link([(935, 306), (935, 350)], "internal")
    link([(1257, 306), (1257, 332), (1046, 332), (1046, 350)], "audio")
    link([(618, 655), (618, 628), (816, 628), (816, 594)], "audio")
    link([(935, 594), (935, 655)], "vehicle")
    link([(1257, 655), (1257, 628), (1040, 628), (1040, 594)], "internal")

    link([(1408, 463), (1450, 463), (1450, 232), (1487, 232)], "video", title="Display interfaces to cabin displays")
    link([(1408, 256), (1460, 256), (1460, 565), (1487, 565)], "audio", title="Audio processing to amplification")
    link([(618, 930), (618, 952), (1448, 952), (1448, 728), (1487, 728)], "connect", title="Ethernet PHY to external network")
    link([(935, 930), (935, 961), (1458, 961), (1458, 832), (1487, 832)], "connect", title="USB interface to cabin ports")

    card("bp-antennas", "Wireless Antennas", 73, 210, 304, 42,
         "2.4 GHz BT ×2 · 5 GHz Wi-Fi", "天线在 IVI 总成内实现，属于 IVI 发包范围。", "external")
    card("bp-radio-ant", "Broadcast Antenna", 73, 263, 304, 42,
         "FM / AM / DAB", "向广播收音链路提供射频输入。", "external")
    card("bp-cameras", "Driving & Cabin Cameras", 73, 370, 304, 42,
         "DVR · DMS · OMS", "驾驶记录、驾驶员监测和乘员监测摄像头；具体装配按配置确定。", "external")
    card("bp-avm", "Surround-View Cameras", 73, 422, 304, 42,
         "AVM inputs", "全景影像摄像头经视频前端接入主计算平台。", "external")
    card("bp-expansion-camera", "Expansion Video Source", 73, 474, 304, 42,
         "Configuration-dependent", "扩展坞视频输入能力，是否装配由车型配置决定。", "reserved")
    card("bp-mics", "Microphone Array", 73, 608, 304, 42,
         "Up to six inputs", "图示规划六路麦克风输入能力；实际装配数量按配置确认。", "external")
    card("bp-a2b-source", "A2B Audio Network", 73, 660, 304, 42,
         "Cabin audio peripherals", "连接座舱音频外设与音频前端。", "external")
    card("bp-vehicle-net", "Vehicle Networks", 73, 774, 304, 42,
         "CAN FD · CAN · LIN", "MCU 侧接入车载通信网络，完成收发与网关相关控制。", "external")
    card("bp-battery", "Vehicle Power", 73, 826, 304, 42,
         "Battery / wake", "经主电源连接进入 IVI 总成，供电状态由板级电源与 MCU 协调。", "power")
    card("bp-harness", "Vehicle Harness", 73, 878, 304, 42,
         "Power & main signal connectors", "主线束连接电源、车载网络及外围控制接口；系统图省略连接器针脚。", "external")

    card("bp-radio", "Broadcast Radio", 472, 206, 292, 100,
         ["FM / AM / DAB tuners", "RF reception and demodulation"],
         "广播收音前端；原图标注 TEF3200、TEF3100 和 SAF4000EL。")
    card("bp-wireless", "Wireless Connectivity", 780, 206, 310, 100,
         ["Bluetooth · Wi-Fi", "Integrated antenna paths"],
         "原图标注 BLE4.2+BT5.3+Wi-Fi 6.0 模块 AF67EAAMD，以及 BT5.2 模块 AH20CAAMD。")
    card("bp-adsp", "Audio DSP", 1106, 206, 302, 100,
         ["Digital audio processing", "Playback and capture"],
         "音频处理域连接无线音频、A2B、麦克风和放大器链路。")
    card("bp-camera-front", "Camera Aggregation", 472, 380, 247, 166,
         ["Video input front end", "Deserializer family"],
         "汇聚 DVR、DMS、OMS、AVM 与扩展视频源。原图标注 MAX96712、MAX96792A、MAX96756 和 MAX96724。")
    card("bp-soc", "SA8397 Compute SoC", 735, 350, 388, 244,
         ["Central IVI compute", "Display · media · connectivity", "64 GB memory (drawing label)"],
         "IVI 主计算芯片，统筹图形、视频、音频和连接功能。本系统图刻意不列出 SoC 端口信号。")
    card("bp-display-front", "Display Interfaces", 1139, 380, 269, 166,
         ["Display bridge family", "Multiple cabin screens"],
         "将主计算平台的视频输出接至座舱屏幕。原图标注 MAX96855 与 DS90UB983 等桥接器件。")
    card("bp-audio-front", "A2B & Microphone Front End", 472, 655, 292, 104,
         ["A2B transceivers · ADC", "Microphone and amplifier I/O"],
         "原图标注两颗 AD2433 与 PCM6360，向音频处理域提供座舱音频输入输出。")
    card("bp-mcu", "S32K324 Control MCU", 780, 655, 310, 104,
         ["Vehicle I/O · power control", "Supervision and wake"],
         "负责车载总线、供电与唤醒、显示使能及静音控制；系统图不展开 SoC—MCU 针脚信号。")
    card("bp-storage", "UFS Storage", 1106, 655, 302, 104,
         ["Persistent system storage", "512 GB shown; 256 GB TBD"],
         "主机持久存储。容量文字按原图保留，待定配置不视为已确定装配。")
    card("bp-ethernet", "Automotive Ethernet PHY", 472, 830, 292, 100,
         ["1G-T1 vehicle connection", "2.5G-T1 reserved"],
         "原图标注已采用的 RTL9071CP；RTL9021ASA 对应被划掉的预留 2.5G-T1 路径，不计入当前装配。")
    card("bp-usb", "USB & Charging", 780, 830, 310, 100,
         ["Type-C · Type-A · USB 2.0", "BC1.2 charging"],
         "提供座舱 USB 数据端口和充电能力，图中另有 USB 3.0 外部连接。")
    card("bp-sensors", "Sensors & Accessory ICs", 1106, 830, 302, 100,
         ["IMU · MFi", "Board-level peripherals"],
         "包括惯性传感器和配件认证相关器件；详细引脚和总线连接在系统级视图中省略。")
    card("bp-power", "Power & Control Distribution", 472, 978, 936, 56,
         "Vehicle supply · wake · load control", "板级电源与控制分配路径，连通主机、MCU 及外部负载。", "power")

    card("bp-center-display", "Center Display", 1503, 210, 304, 42,
         "Primary HMI screen", "中控显示终端；屏幕规格和数量按具体配置选择。", "external")
    card("bp-cluster", "Instrument Cluster", 1503, 262, 304, 42,
         "Driver information", "仪表显示终端，与 IVI 主机和 MCU 控制链路协同。", "external")
    card("bp-hud", "Head-Up Display", 1503, 314, 304, 42,
         "Driver projection", "抬头显示终端，具体规格依装配配置。", "external")
    card("bp-passenger", "Passenger Display", 1503, 366, 304, 42,
         "Configuration-dependent", "副驾显示属于平台规划的可配置终端。", "reserved")
    card("bp-other-displays", "Roof & Rear Displays", 1503, 418, 304, 42,
         "Configuration-dependent", "吸顶与后排显示属于平台规划的可配置终端，不默认视为全部装配。", "reserved")
    card("bp-amplifiers", "Amplifiers & Speakers", 1503, 543, 304, 42,
         "Cabin playback", "音频处理与 A2B 前端连接外部放大器及扬声器负载。", "external")
    card("bp-audio-accessory", "Audio Accessories", 1503, 595, 304, 42,
         "A2B peripheral devices", "座舱音频外设经音频链路接入；实际设备列表由配置确定。", "external")
    card("bp-1gt1", "1G-T1 Ethernet", 1503, 706, 304, 42,
         "Vehicle Ethernet", "原图标注千兆车载以太网连接与 RTL9071CP。", "external")
    card("bp-25gt1", "2.5G-T1 Ethernet", 1503, 758, 304, 42,
         "Reserved path", "原图中 RTL9021ASA 路径被划掉，仅作为预留记录。", "reserved")
    card("bp-usb-main", "USB Type-C & Type-A", 1503, 810, 304, 42,
         "Cabin data / charging", "面向乘员的数据与充电端口，按配置接入。", "external")
    card("bp-usb-service", "USB Service Ports", 1503, 862, 304, 42,
         "USB 2.0 connections", "图中另列 USB 2.0 外部端口；系统图不保留连接器编号与引脚。", "external")

    labels.append(text(54, 53, "B PLATFORM SYSTEM ARCHITECTURE", 25, "#202d3b", 750))
    labels.append(text(55, 78, "Functional hardware view", 12, "#718093"))
    labels.append('<line x1="40" y1="96" x2="1840" y2="96" stroke="#dce5ef"/>')
    labels.append('<rect x="1534" y="40" width="17" height="14" rx="3" fill="#f4f6f8" stroke="#b8c2cd" stroke-dasharray="4 3"/>')
    labels.append(text(1559, 52, "Optional / reserved", 12, "#66778b"))
    labels.append('<line x1="1718" y1="47" x2="1748" y2="47" stroke="#4285f4" stroke-width="2.3"/>')
    labels.append(text(1755, 52, "Link", 12, "#66778b"))
    labels.append(text(57, 1083, "Endpoint availability depends on vehicle configuration; reserved paths are shown with dashed outlines.", 12, "#78879a"))
    for i, (kind, title) in enumerate((('rf', 'RF'), ('video', 'Video'), ('audio', 'Audio'),
                                       ('vehicle', 'Vehicle'), ('power', 'Power'), ('connect', 'Connectivity'))):
        x = 1020 + i * 132
        labels.append(f'<line x1="{x}" y1="1079" x2="{x+24}" y2="1079" stroke="{COLORS[kind]}" stroke-width="3"/>')
        labels.append(text(x + 31, 1083, title, 11, "#66778b"))

    style = '''<style>
      #b-system-drawing text{font-family:Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif;pointer-events:none}
      #b-system-drawing .hardware-module{cursor:pointer}
      #b-system-drawing .hardware-module:hover .hw-box,#b-system-drawing .hardware-module:focus .hw-box{stroke:#2469d8;stroke-width:2.5}
      #b-system-drawing .hardware-module.found .hw-box{stroke:#da8409;stroke-width:3}
      #b-system-drawing .hardware-module.selected .hw-box{stroke:#1454b8;stroke-width:3}
    </style>'''
    svg = (f'<svg id="b-system-drawing" xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {WIDTH} {HEIGHT}" role="group" '
           f'aria-labelledby="bSystemTitle bSystemDesc">'
           '<title id="bSystemTitle">B平台系统架构图</title>'
           '<desc id="bSystemDesc">系统级硬件架构，展示外部输入、IVI 主机及座舱输出；省略 SoC 信号名与项目编号。</desc>'
           + style + f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
           + ''.join(panels + links + cards + labels) + '</svg>')
    return svg, dict(width=WIDTH, height=HEIGHT, nodes=nodes)
