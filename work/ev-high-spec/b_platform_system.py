"""Vector redraw of the supplied B-platform system hardware drawing.

The three configuration columns, component placement, branch structure and
connection groups follow the supplied overview and enlarged crops. Project
codes and signal names at the SoC boundary are intentionally omitted.
"""
from html import escape

WIDTH, HEIGHT = 1918, 1208
INK = '#222426'
PAPER = '#ffffff'
PALE = '#eff2f9'
GREEN = '#6ba379'
DARK = '#6e7279'
YELLOW = '#d4bd75'
LIME = '#dfe776'
PINK = '#f8e7e4'
BLUE = '#617dc0'
CREAM = '#fff0ce'
LIGHT_GREEN = '#e6f2e8'
RESERVED = '#f1f2f5'


def create_b_system():
    back, traces, parts, words, nodes = [], [], [], [], []

    def t(x, y, value, size=10, anchor='middle', weight=400, color=INK, rotate=None):
        transform = f' transform="rotate({rotate} {x} {y})"' if rotate else ''
        return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
                f'font-weight="{weight}" fill="{color}"{transform}>{escape(str(value))}</text>')

    def label(x, y, value, size=10, anchor='middle', weight=400, color=INK, rotate=None):
        words.append(t(x, y, value, size, anchor, weight, color, rotate))

    def rect(x, y, w, h, fill='none', stroke=INK, sw=1, rx=0, dash=None, where=back):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        where.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def path(points, color=INK, sw=1.2, arrow=False, both=False, dash=None, note=None):
        d = 'M' + ' L'.join(f'{x},{y}' for x, y in points)
        m = f' marker-end="url(#bp-arrow-{color[1:]})"' if arrow else ''
        n = f' marker-start="url(#bp-arrow-{color[1:]})"' if both else ''
        ds = f' stroke-dasharray="{dash}"' if dash else ''
        title = f'<title>{escape(note)}</title>' if note else ''
        traces.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" '
                      f'stroke-linecap="round" stroke-linejoin="round"{m}{n}{ds}>{title}</path>')

    def card(name, x, y, w, h, lines=None, fill=RESERVED, note='', size=9, vertical=False,
             stroke=INK, sw=1.2, dashed=False, interactive=True, id_=None, kind=None):
        lines = [name] if lines is None else list(lines)
        id_ = id_ or f'bp-{len(nodes)+1}'
        if interactive:
            node_kind = kind or ('reserved' if dashed else
                                 'config' if x < 600 else 'load' if x >= 1660 else 'base')
            nodes.append(dict(id=id_, name=name, x=x, y=y, w=w, h=h,
                              kind=node_kind, lines=lines,
                              note=note or '原图中的硬件模块或接口。'))
        dat = (f' class="hardware-module" data-hw-node="{id_}" role="button" tabindex="0" '
               f'aria-label="{escape(name, quote=True)}"' if interactive else '')
        dd = ' stroke-dasharray="4 3"' if dashed else ''
        text_color = '#ffffff' if fill in (DARK, BLUE, GREEN, '#5869a5') else INK
        shape = (f'<g id="{id_}"{dat}><title>{escape(name)}'
                 f'{(" — " + escape(note)) if note else ""}</title>'
                 f'<rect class="hw-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="4" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dd}/>')
        if vertical:
            shape += t(x+w/2, y+h/2+4, name, size, weight=600, color=text_color, rotate=-90)
        else:
            step = min(size*1.3, max(10, (h-9)/max(1, len(lines))))
            start = y+h/2 - step*(len(lines)-1)/2 + size*.34
            for i, line in enumerate(lines):
                shape += t(x+w/2, start+i*step, line, size, weight=500, color=text_color)
        parts.append(shape+'</g>')
        return id_

    def connector(title, x, y, dark=False, face=None, label_pos='left', label_size=22):
        fill = face or ('#1f2425' if dark else '#f4f6f7')
        rect(x, y, 33, 43, fill, INK, 1.8, 6, where=parts)
        for xx in (x+10, x+23):
            for yy in (y+12, y+31):
                parts.append(f'<circle cx="{xx}" cy="{yy}" r="3.5" fill="#d0ae52" stroke="{INK}"/>')
        if label_pos == 'above':
            label(x+16.5, y-12, title, label_size, weight=700)
        elif label_pos == 'right':
            label(x+43, y+27, title, label_size, 'start', 700)
        else:
            label(x-8, y+26, title, label_size, 'end', 700)
        return (x+33, y+21.5)

    def antenna(x, y, title):
        label(x, y-12, title, 9, weight=600)
        back.append(f'<path d="M{x-12},{y} L{x+12},{y} L{x},{y+16} Z" fill="none" stroke="{INK}" stroke-width="3"/>')
        back.append(f'<circle cx="{x}" cy="{y+20}" r="2.5" fill="{INK}"/>')

    def thin_group(y1, y2, caption=None):
        path([(1670, y1), (1663, y1+8), (1663, y2-8), (1670, y2)], sw=1)
        if caption:
            label(1677, (y1+y2)/2, caption, 9, 'start')

    def load(name, x, y, w=50, h=29, fill=DARK, size=8, note=''):
        return card(name, x, y, w, h, name.split('|'), fill,
                    note=note or '平台规划负载；颜色和位置按参考图保留。', size=size)

    # The left side reproduces the three configuration matrices. Only their
    # project-code headings are replaced by neutral configuration labels.
    columns = [(8, 154, '参考配置'), (224, 154, '平台配置'),
               (438, 154, '平台规划负载')]
    rows = [(86, 192), (192, 287), (287, 422), (422, 530), (530, 752),
            (752, 870), (870, 998), (998, 1111), (1111, 1196)]
    for x, w, title in columns:
        label(x+17, 64, title, 21, 'start', 700)
        rect(x, 86, w, 1110, PAPER, '#6383c8', 1.8, dash='3 3')
        for _, yy in rows[:-1]:
            path([(x, yy), (x+w, yy)], sw=1)
    # Radio and projection.
    configs = [
        [('预留FM/AM', 60, RESERVED), ('FM&DAB', 68, YELLOW)],
        [('FM/AM', 59, GREEN), ('预留DAB', 65, DARK), ('FM&DAB', 65, DARK)],
        [('预留FM/AM', 60, RESERVED), ('预留DAB', 65, RESERVED), ('FM&DAB', 68, YELLOW)]
    ]
    for c, (x, w, _) in enumerate(columns):
        for i, (name, bw, fill) in enumerate(configs[c]):
            xx = x+50 if i == 0 else (x+50 if len(configs[c]) == 2 else x+86)
            yy = (105, 148)[i] if len(configs[c]) == 2 else (101, 101, 146)[i]
            if c == 1 and i == 0: xx=x+10
            if c == 1 and i == 1: xx=x+85
            if c == 1 and i == 2: xx=x+85
            if c == 2 and i == 1: xx=x+103
            card(name, xx, yy, bw, 38 if i!=2 else 39, fill=fill, size=8)
        card('DP In 投屏盒子', x+45, 231, 74, 23,
             fill=DARK if c==1 else RESERVED, size=8)
    # Dual display and armrest rows.
    for c, (x, w, _) in enumerate(columns):
        if c != 1:
            rect(x+16, 314, 137, 71, PALE, INK, 1.2, 5)
            label(x+83, 307, '双联屏', 8)
        card('中控LCD', x+19, 328, 58, 42,
             ['中控LCD'] if c!=1 else ['中控LCD', '29.6(LINKO)'],
             GREEN if c==1 else PINK, size=8)
        card('副驾LCD', x+91, 328, 57, 42, fill=DARK if c==1 else PINK, size=8)
        card('扶手屏1', x+18, 454, 51, 41, fill=DARK if c==1 else LIGHT_GREEN, size=8)
        card('扶手屏2/DLP', x+91, 454, 51, 41, ['扶手屏2/', 'DLP'],
             DARK if c==1 else RESERVED, size=8)
        for i, title in enumerate(('吸顶屏1', '吸顶屏2')):
            card(title, x+20+i*75, 560, 57, 40,
                 [title, '2880×1620'] if c!=1 else [title],
                 DARK if c==1 else PINK, size=7.4, dashed=c==0 and i==0)
        card('仪表', x+19, 655, 58, 42,
             ['8.88寸仪表'] if c==1 else ['10.25寸仪表', '1920×720'],
             GREEN if c==1 else PINK, size=7.7)
        card('HUD', x+92, 655, 52, 42, fill=GREEN if c==1 else PINK, size=8)
        video = [('DVR 3M', '预留3M'), ('DMS 2M', 'DMS 2M'),
                 ('OMS 8M', 'OMS 8M'), ('预留3M', '预留3M')]
        for i,(real,res) in enumerate(video):
            col=i%2;row=i//2
            name=real if c==1 else res if i==0 else real
            fill=GREEN if c==1 and i<3 else DARK if c==1 else RESERVED
            card(name, x+19+col*75, 780+row*48, 55, 31, fill=fill, size=8)
        for i,name in enumerate(('AVM1 3M','AVM2 3M')):
            card(name, x+20+i*76, 891, 57, 30, fill=GREEN if c==1 else RESERVED, size=8)
        card('SWITCH拓展坞', x+19, 951, 91, 27,
             fill=DARK if c==1 else RESERVED, size=8)
        for i in range(4):
            name = ('OMS2','OMS3','预留3M','预留3M')[i] if c==1 else '预留3M'
            fill = (LIME if i<2 else DARK) if c==1 else RESERVED
            card(name, x+19+(i%2)*76, 1020+(i//2)*42, 56, 27, fill=fill, size=8)
        card('算力卡', x+53, 1140, 60, 26, fill=DARK, size=8)
    label(289, 879, 'for ADCD', 8)
    # The source places the comparison columns below a large clear header area.
    # Keep their proportions while aligning their top and bottom to the source.
    left_counts = (len(back), len(traces), len(parts), len(words), len(nodes))
    for n in nodes:
        n['y'] = round(n['y']*.88 + 143, 2)
        n['h'] = round(n['h']*.88, 2)

    # Central IVI motherboard, with the same long vertical SoC silhouette.
    rect(903, 184, 223, 961, PALE, '#404449', 1.3, 3)
    card('SA8397 Elite-A', 910, 510, 210, 143,
         ['SA8397', 'Elite-A', '64GB', '512G'], PALE,
         note='参考图中央主计算平台；保留芯片与容量标识，省略 SoC 引脚和信号名。', size=17,
         stroke='none', sw=0)
    card('DPU', 904, 393, 38, 208, ['DPU'], '#d9dfef',
         note='图中上方显示处理单元。', vertical=True, size=10)
    card('DPU', 904, 654, 38, 194, ['DPU'], '#d9dfef',
         note='图中下方显示处理单元。', vertical=True, size=10)
    card('ADSP', 1050, 206, 40, 40, fill=LIGHT_GREEN,
         note='音频数字信号处理。', size=9)
    card('Video Input', 910, 315, 75, 28, fill=LIGHT_GREEN, size=8)
    for i in range(5):
        card('Camera input', 906, 892+i*38, 44, 32,
             ['Camera', str(i+1)], LIGHT_GREEN if i<4 else CREAM,
             note='摄像头输入通道；SoC 端口号已省略。', size=7.4)
    for i in range(3):
        card('USB controller', 1087, 966+i*49, 36, 42,
             ['USB', str(i+1)], LIGHT_GREEN,
             note='主芯片 USB 控制器；SoC 端口号已省略。', size=7.5)
    # Top-left radio and video adapter chain.
    connector('J4600(PB)', 672, 245, face=GREEN, label_pos='above', label_size=18)
    path([(705,266),(746,266),(746,201)], sw=1.2)
    path([(746,266),(746,277)], sw=1.2)
    for y, name, fill in [(188, 'TEF3200', BLUE), (226, 'TEF3100', BLUE),
                          (264, 'SAF4000EL', BLUE)]:
        card(name, 774, y, 70, 27, fill=fill, note='参考图中的广播接收/调谐器件。', size=8)
        path([(746,y+13),(769,y+13)], arrow=True)
        path([(844,y+13),(965,y+13),(965,231),(1046,231)], arrow=True)
    # J7's narrow projection connector is distinct from the four-pin plugs.
    label(668, 370, 'J7', 21, 'end', 700)
    rect(683, 349, 11, 30, PAPER, INK, 1.4, 5, where=parts)
    for py in (356,364,372):
        parts.append(f'<circle cx="688.5" cy="{py}" r="1.5" fill="{INK}"/>')
    card('GSV6155DA', 774, 351, 71, 31, fill=YELLOW, size=8)
    path([(694,365),(770,365)], arrow=True)
    path([(845,366),(879,366),(879,329),(906,329)], arrow=True)
    # Two display connector branches.
    connector('J2', 672, 481)
    for i,y in enumerate((394, 558)):
        card('MAX96855', 776, y, 71, 42,
             ['MAX96855', '(U6200)' if i==0 else '(U6250)'], BLUE,
             note='图中 J2 的显示链路转换器，共两组。', size=9)
        path([(706,502),(745,502),(745,y+21),(771,y+21)], arrow=True)
        path([(847,y+21),(873,y+21),(873,415+i*137),(899,415+i*137)], arrow=True)
    connector('J3', 672, 693, True)
    for i,y in enumerate((617, 768)):
        card('DS90UB983', 776, y, 71, 41,
             ['DS90UB983'], BLUE,
             note='图中 J3 的两路 FPD-Link 显示链路。', size=9)
        path([(706,714),(745,714),(745,y+20),(771,y+20)], arrow=True)
        path([(847,y+20),(878,y+20),(878,690+i*95),(899,690+i*95)], arrow=True)
    # Camera inputs, preserving each original deserializer and connector.
    camera_rows = [
        ('J9', 887, [('MAX96712', 776, 882, GREEN, 0)]),
        ('J5', 1003, [('MAX96792A', 776, 969, GREEN, 2),
                      ('MAX96756', 776, 1013, LIME, 3)]),
        ('J6', 1114, [('MAX96724', 776, 1090, CREAM, 4)]),
    ]
    for title, cy, adapters in camera_rows:
        connector(title, 672, cy)
        for name,x,y,fill,index in adapters:
            card(name, x, y, 77, 34, fill=fill,
                 note='参考图中的摄像头解串/输入器件。', size=8.7)
            path([(706,cy+21),(744,cy+21),(744,y+17),(772,y+17)], arrow=True)
            path([(853,y+17),(880,y+17),(880,909+index*38),(901,909+index*38)], arrow=True)
    # Reserved PCIe expansion card.
    card('PCIe Gen5', 776, 1152, 77, 31, fill='#5869a5',
         note='原图底部预留的扩展卡通道。', size=8)
    label(731, 1168, '预留', 8)
    path([(742,1167),(772,1167)], arrow=True)
    path([(853,1167),(883,1167),(883,1124),(899,1124)], arrow=True)

    # Antenna enclosure and wireless modules at the upper right.
    rect(1147, 31, 288, 69, PALE, INK, 1.3, 3)
    label(1291, 23, '天线在IVI总成体现，在IVI发包范围', 12)
    for x, title in ((1195,'2.4G BT ANT'),(1291,'5G WIFI ANT'),(1390,'2.4G BT ANT')):
        antenna(x, 64, title)
    card('BLE4.2+BT5.3+WIFI6.0', 1218, 184, 139, 46,
         ['BLE4.2+BT5.3+WIFI6.0', 'MODULE-AF67EAAMD'], CREAM,
         note='原图无线模块及两路内部天线。', size=8.7)
    card('BT5.2', 1218, 267, 139, 43,
         ['BT5.2','MODULE-AH20CAAMD'], CREAM,
         note='原图独立蓝牙模块及独立天线。', size=8.7)
    path([(1195,84),(1195,141),(1248,180)], sw=1.25)
    path([(1291,84),(1291,180)], sw=1.25)
    path([(1390,84),(1390,235),(1330,265)], sw=1.25)
    path([(1127,218),(1174,218),(1174,205),(1214,205)], arrow=True)
    path([(1127,239),(1174,239),(1174,288),(1214,288)], arrow=True)
    path([(1358,207),(1414,207),(1414,229),(1094,229)], arrow=True)

    # Audio front end, external A2B and microphone fan-out.
    card('AD2433', 1212, 350, 146, 40, fill=PINK,
         note='第一条 A2B 音频总线收发链路。', size=9)
    card('AD2433', 1212, 409, 146, 40, fill=PINK,
         note='第二条 A2B 音频总线收发链路。', size=9)
    card('PCM6360', 1212, 468, 146, 40, fill=PINK,
         note='麦克风采集 ADC。', size=9)
    for yy in (370,429,488):
        path([(1094,237),(1160,237),(1160,yy),(1208,yy)], arrow=True)
        path([(1358,yy),(1411,yy),(1411,yy+3),(1488,yy+3)], arrow=True)
    card('IVI主电源连接器', 1494, 250, 66, 383,
         ['IVI主电源连接器'], PALE,
         note='原图 J1(PB)：承载外部电源、A2B、显示使能和静音等连接。', vertical=True, size=16)
    label(1566, 466, 'J1(PB)', 19, 'start', 700)
    label(1513, 227, '×6 MIC', 14, weight=600)
    for i in range(6):
        x=1497+(i%3)*12
        back.append(f'<circle cx="{x}" cy="{201+(i//3)*11}" r="3" fill="none" stroke="{INK}"/>')
    path([(1470,216),(1470,477),(1489,477)], arrow=True)
    card('AMPLIFIERS', 1479, 93, 107, 36, fill=CREAM,
         note='平台规划的外置放大器负载。', size=9)
    label(1480, 77, '平台规划负载', 16, 'start', 700)

    # Storage and local peripherals.
    card('UFS 512GB', 1209, 525, 145, 36,
         ['UFS 512GB', '(256GB TBD)'], LIME,
         note='原图标注 UFS 512GB；256GB 为待确认。', size=9)
    path([(1127,542),(1205,542)], both=True)
    card('IMU', 1209, 633, 145, 40, fill=PINK,
         note='惯性测量单元。', size=9)
    card('MFI', 1209, 696, 145, 40, fill=PINK,
         note='MFi 认证器件。', size=9)
    path([(1127,653),(1205,653)], both=True)
    path([(1127,716),(1205,716)], both=True)

    # Power and signal connectors, control MCU and vehicle buses.
    card('IVI主信号连接器', 1494, 673, 66, 141,
         ['IVI主信号连接器'], PALE,
         note='原图 J7501(PB) 信号连接器。', vertical=True, size=13)
    label(1567, 752, 'J7501 (PB)', 18, 'start', 700)
    card('S32K324', 1212, 781, 112, 217, fill=PALE,
         note='IVI 控制 MCU：车载总线、显示使能、电源和静音控制。', size=14)
    path([(1127,798),(1208,798)], both=True)
    path([(1127,841),(1208,841)], both=True)
    path([(1127,887),(1208,887)], both=True)
    for i,(name,y) in enumerate((('TPT1043',797),('TPT1445',836),
                                 ('TPT1445',875),('TPT1021',914),('TPT1021',953))):
        card(name, 1361, y, 91, 31, fill=RESERVED, size=9,
             note=('车载 CAN 收发器。' if i<3 else '车载 LIN 收发器。'))
        path([(1328,y+15),(1357,y+15)], both=True)
        path([(1452,y+15),(1472,y+15),(1472,720+i*19),(1490,720+i*19)], arrow=True)
    label(1468, 806, 'CAN2', 8, 'end')
    label(1468, 844, 'CAN1', 8, 'end')
    label(1468, 883, 'CAN0', 8, 'end')
    label(1468, 921, 'LIN #1', 8, 'end')
    label(1468, 960, 'LIN #2', 8, 'end')
    card('16M晶体', 1156, 965, 49, 28, fill=RESERVED,
         note='MCU 时钟晶体。', size=7.5)
    path([(1205,978),(1209,978)], arrow=True)
    # Three thick load control traces are a distinctive feature of the source.
    for start_y, turn_x, end_y, title in (
        (814,1430,571,'Display EN ×8'),
        (836,1455,591,'AMP MUTE IN'),
        (858,1478,610,'TBOX MUTE IN')):
        path([(1324,start_y),(turn_x,start_y),(turn_x,end_y),(1490,end_y)],
             sw=2.4, arrow=True, note=title)
        label(turn_x-8, end_y-8, title, 9, 'end')
    path([(1560,786),(1590,786),(1590,986),(1328,986)], '#c76962', 1.8, arrow=True)
    label(1402, 1000, 'KL15 (ACC)', 8, color='#b35c55')

    # Ethernet PHY, two live gigabit lines, crossed-out reserved 2.5G part.
    card('RTL9071CP', 1225, 1020, 89, 37, fill=BLUE,
         note='原图中的千兆车载以太网 PHY。', size=9)
    path([(1127,1039),(1221,1039)], both=True)
    card('RTL9021ASA', 1346, 1080, 90, 34, fill=DARK,
         note='原图中划掉的预留 2.5G-T1 方案。', size=8, kind='reserved')
    path([(1351,1108),(1432,1084)], '#c8645e', 2.2)
    label(1379, 1123, '预留', 8)
    connector('J1(MB)', 1513, 1014, label_pos='right', label_size=18)
    # J8 is the distinct USB 3.0 board connector between Ethernet and USB 2.0.
    rect(1520, 1074, 13, 27, PAPER, INK, 1.5, 6, where=parts)
    for py in (1081, 1088, 1095):
        parts.append(f'<circle cx="1526.5" cy="{py}" r="1.5" fill="{INK}"/>')
    label(1545, 1092, 'J8(MB)', 16, 'start', 700)
    for yy in (1026,1047):
        path([(1314,1039),(1445,1039),(1445,yy),(1508,yy)], arrow=True)
    path([(1314,1044),(1343,1044),(1343,1096)], arrow=True)
    path([(1127,1083),(1481,1083),(1481,1087),(1515,1087)], '#ddb765', 1.25, arrow=True)
    path([(1436,1096),(1473,1096),(1473,1063),(1508,1063)], dash='3 3')
    # USB branch and the charger, using the source's pale gold line treatment.
    usb='#ddb765'
    card('BC1.2 Charger', 1233, 1110, 78, 46,
         ['BC1.2','Charger'], BLUE,
         note='USB 充电控制。', size=9)
    path([(1127,1090),(1170,1090),(1170,1128),(1229,1128)], usb, 1.25, arrow=True)
    path([(1127,1137),(1274,1137),(1274,1180),(1511,1180)], usb, 1.25, arrow=True)
    path([(1311,1135),(1511,1135)], usb, 1.25, arrow=True)
    connector('J6(PB)', 1514, 1111, label_pos='right', label_size=18)
    connector('J5(PB)', 1514, 1160, label_pos='right', label_size=18)
    label(1382, 1130, 'USB 2.0', 8)
    label(1382, 1180, 'USB 2.0', 8)
    label(1450, 1069, 'USB 3.0', 8, color='#b39348')

    # Rightmost load matrix. The column reflects the source's placement,
    # state colors, and individual endpoints, without its project identifier.
    rect(1660, 139, 152, 1055, PAPER, '#6283c8', 1.6, dash='3 3')
    load('BLE4.2',1670,151,53,30,GREEN)
    load('WIFI6.0',1747,151,53,30,GREEN)
    load('BLE5.2',1670,186,53,30,GREEN)
    path([(1660,226),(1812,226)], sw=1)
    load('AMP',1670,237,53,30,GREEN)
    load('数字MIC',1747,237,53,30,GREEN)
    for i,(name,x,y) in enumerate((
        ('主驾MIC',1670,274),('副驾MIC',1747,274),
        ('左后MIC',1670,311),('右后MIC',1747,311),
        ('三排左MIC',1670,348),('三排右MIC',1747,348))):
        load(name,x,y,53,30,DARK,7.3)
    path([(1660,387),(1812,387)], sw=1)
    load('IMU',1670,395,53,29,GREEN)
    load('MFI',1747,395,53,29,DARK)
    path([(1660,431),(1812,431)], sw=1)
    displays = [
        ('屏幕1（仪表屏）','EXT_DISPLAY_EN1',GREEN),
        ('屏幕2（中控屏）','EXT_DISPLAY_EN2',GREEN),
        ('屏幕3（副驾屏）','EXT_DISPLAY_EN3',DARK),
        ('屏幕4（抬头显示器）','EXT_DISPLAY_EN4',GREEN),
        ('屏幕5（扶手屏1）','EXT_DISPLAY_EN5',DARK),
        ('屏幕6（扶手屏2/DLP）','EXT_DISPLAY_EN6',DARK),
        ('屏幕7（吸顶屏）','EXT_DISPLAY_EN7',DARK),
        ('屏幕8（预留屏）','EXT_DISPLAY_EN8',DARK),
    ]
    for i,(title,signal,fill) in enumerate(displays):
        load(title+'|'+signal,1672,441+i*42,127,35,fill,7.6)
    load('AMP MUTE IN',1672,779,127,32,DARK,8)
    load('TBOX MUTE IN',1672,816,127,32,DARK,8)
    path([(1660,855),(1812,855)], sw=1)
    load('CAN0(INFO)|带终端电阻',1671,863,59,39,GREEN,7)
    load('CAN1|BACKBONE',1743,863,58,39,DARK,7)
    load('CAN2',1671,912,59,36,DARK,8)
    load('LIN #1',1671,957,59,35,DARK,8)
    load('LIN #2',1743,957,58,35,DARK,8)
    path([(1660,1000),(1812,1000)], sw=1)
    load('千兆以太网|1G-T1',1670,1009,62,40,GREEN,7)
    load('千兆以太网|2.5G',1743,1009,59,40,DARK,7)
    path([(1660,1057),(1812,1057)], sw=1)
    rect(1669, 1071, 110, 73, 'none', INK, 1, dash='3 3')
    label(1724, 1068, '前排USB', 8)
    load('Type-C|带数据传输',1677,1081,94,28,GREEN,7)
    load('Type-A|带数据传输',1677,1114,94,28,GREEN,7)
    load('USB2.0(J5)',1677,1154,94,29,DARK,8)
    # Small directional callouts into the load matrix.
    path([(1560,362),(1612,362),(1612,266),(1656,266)], sw=.9)
    path([(1560,520),(1613,520),(1613,475),(1656,475)], sw=.9)
    path([(1560,742),(1613,742),(1613,881),(1656,881)], sw=.9)
    path([(1547,1036),(1604,1036),(1604,1030),(1656,1030)], sw=.9)
    path([(1547,1132),(1608,1132),(1608,1100),(1656,1100)], usb, .9)

    # The original's restrained black-line visual vocabulary is intentional.
    marker_colors = [INK, '#c76962', '#ddb765']
    defs = '<defs>'
    for color in marker_colors:
        defs += (f'<marker id="bp-arrow-{color[1:]}" viewBox="0 0 8 8" '
                 f'refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                 f'<path d="M0 0 L7 4 L0 8" fill="none" stroke="{color}" stroke-width="1.2"/></marker>')
    defs += '</defs>'
    style = '''<style>
      #b-system-drawing text{font-family:Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif;pointer-events:none}
      #b-system-drawing .hardware-module{cursor:pointer}
      #b-system-drawing .hardware-module:hover .hw-box,
      #b-system-drawing .hardware-module:focus .hw-box{stroke:#2467c7;stroke-width:2.5}
      #b-system-drawing .hardware-module.found .hw-box{stroke:#d98809;stroke-width:3}
      #b-system-drawing .hardware-module.selected .hw-box{stroke:#1554af;stroke-width:3}
    </style>'''
    svg = (f'<svg id="b-system-drawing" xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {WIDTH} {HEIGHT}" role="group" '
           f'aria-labelledby="bSystemTitle bSystemDesc">'
           '<title id="bSystemTitle">B平台系统架构图</title>'
           '<desc id="bSystemDesc">依参考图重绘的三列配置对照、IVI主板、收音、显示、摄像头、音频、MCU、车载网络与外部负载。'
           '省略项目编号与SoC端口信号标注。</desc>'
           + defs + style + f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>'
           + '<g transform="matrix(1 0 0 .88 0 143)">'
           + ''.join(back[:left_counts[0]] + traces[:left_counts[1]]
                     + parts[:left_counts[2]] + words[:left_counts[3]]) + '</g>'
           + ''.join(back[left_counts[0]:] + traces[left_counts[1]:]
                     + parts[left_counts[2]:] + words[left_counts[3]:]) + '</svg>')
    return svg, dict(width=WIDTH, height=HEIGHT, nodes=nodes)
