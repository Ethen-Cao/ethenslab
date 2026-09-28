"""Vector transcription of the user-supplied IVI hardware diagram."""
from html import escape

WIDTH, HEIGHT = 1827, 1344
SIGNALS = {'comm':'#65c750','video':'#5683ff','audio':'#9660f5','rf':'#24292f','power':'#f36a66','reserved':'#b7bbc0'}
FILLS = {'base':'#ffecd7','external':'#dfe7fb','reserved':'#bdc1c6','power':'#f56566'}

def create_hardware():
    shapes=[]; wires=[]; labels=[]; node_parts=[]; nodes=[]
    def text(x,y,value,size=10,anchor='middle',color='#30343a',weight=400,rotate=None):
        extra=f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ''
        return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}"{extra}>{escape(str(value))}</text>'
    def label(x,y,value,size=10,anchor='middle',color='#30343a',weight=400):
        labels.append(text(x,y,value,size,anchor,color,weight))
    def box(name,x,y,w,h,lines=None,kind='base',size=10,note='',searchable=True):
        id=f'hw-{len(nodes)+1}'
        lines=lines or name.split('\n')
        if searchable:
            nodes.append(dict(id=id,name=name.replace('\n',' · '),x=x,y=y,w=w,h=h,kind=kind,lines=lines,note=note))
        group=f'<g class="hardware-module" id="{id}" data-hw-node="{id}" role="button" tabindex="0" aria-label="{escape(name.replace(chr(10),'，'))}"><title>{escape(" / ".join(lines))}</title>' if searchable else '<g>'
        group+=f'<rect class="hw-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{FILLS[kind]}" stroke="#6b95fb" stroke-width="1"/>'
        for i,line in enumerate(lines):
            group+=text(x+w/2,y+h/2+(i-(len(lines)-1)/2)*(size*1.4)+size*.34,line,size)
        group+='</g>'
        node_parts.append(group)
        return id
    def flow(x1,y,x2,kind='comm',name='',both=False,reverse=False,lx=None,size=10):
        a,b=(x2,x1) if reverse else (x1,x2)
        color=SIGNALS[kind]
        wires.append(f'<path d="M{a} {y}H{b}" fill="none" stroke="{color}" stroke-width="1.45" marker-end="url(#hw-arrow-{kind})"'+(f' marker-start="url(#hw-arrow-{kind})"' if both else '')+'/>')
        if name:label((x1+x2)/2 if lx is None else lx,y-5,name,size)
    def route(pts,kind='comm',both=False):
        d='M'+' L'.join(f'{x} {y}' for x,y in pts)
        wires.append(f'<path d="{d}" fill="none" stroke="{SIGNALS[kind]}" stroke-width="1.45" marker-end="url(#hw-arrow-{kind})"'+(f' marker-start="url(#hw-arrow-{kind})"' if both else '')+'/>')
    def connector(name,x,y,h,tag_y=None,kind='external'):
        # The narrow connector shape crosses the signal lines, as in the source.
        labels.append(f'<rect x="{x}" y="{y}" width="10" height="{h}" rx="4" fill="#e5eaff" stroke="#648cff" stroke-width="1.7"/><path d="M{x+1} {y+2}L{x+9} {y+h-2}M{x+9} {y+2}L{x+1} {y+h-2}" fill="none" stroke="#b1bac8" stroke-width="1.2"/>')
        box(name,x-28,tag_y if tag_y is not None else y+h+5,67,23,kind=kind,size=10,note='连接器标识，按原图保留。')
    def region(x,y,w,h):
        shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#f5a442" stroke-width="2.5" stroke-dasharray="4 4"/>')
    def note(x,y,rows,kind='base',size=10):
        for i,t in enumerate(rows):
            w=sum(1 if ord(c)>255 else .54 for c in t)*size+4
            labels.append(f'<rect x="{x}" y="{y+i*14-10}" width="{w}" height="14" fill="{"#bdc1c6" if kind=="reserved" else "#facb9e"}"/>')
            label(x+2,y+i*14,t,size,'start')
    def brace(x,y1,y2,title,right=False):
        mid=(y1+y2)/2;d=1 if right else -1
        path=f'M{x} {y1} q{d*12} 0 {d*12} 18 V{mid-16} q0 12 {d*8} 16 q{-d*8} 4 {-d*8} 16 V{y2-18} q0 18 {-d*12} 18'
        shapes.append(f'<path d="{path}" fill="none" stroke="#353a40" stroke-width="1.15"/>')
        for i,t in enumerate(title.split('\n')):label(x+(24 if right else -30),mid+i*14,t,10,'start' if right else 'end')
    def antenna(x,y,title):
        label(x-16,y+4,title,10,'end')
        shapes.append(f'<path d="M{x} {y-10}L{x+16} {y}L{x} {y+10}Z" fill="#f2f4f5" stroke="#6b737c" stroke-width="1.8"/>')

    # Central system-on-module and its internal resources.
    nodes.append(dict(id='hw-soc',name='QAM 8295P',x=843,y=18,w=219,h=815,kind='base',lines=['QAM 8295P','SOC: SA8295P','LPDDR4X: 32GB','PMIC: PMM8295AU ×4'],note='主计算模块；内部资源按所附图纸列出。'))
    shapes.append('<g class="hardware-module" id="hw-soc" data-hw-node="hw-soc" role="button" tabindex="0" aria-label="QAM 8295P 主计算模块"><rect class="hw-box" x="843" y="18" width="219" height="815" fill="#ffead2" stroke="#608bff" stroke-width="1.5"/></g>')
    for i,t in enumerate(['QAM 8295P','包含：','SOC: SA8295P','LPDDR4X: 32GB','PMIC: PMM8295AU ×4']):
        label(952.5,187+i*20,t,14,weight=650)
    resources=[('CPU',863,317,66,41,['CPU','Kryo 695','8核心 64位'],8),('GPU',958,317,67,41,['GPU','Adreno 695'],8),('VPU',863,403,66,42,['VPU','Adreno','VPU 665'],8),('DPU',958,403,67,42,['DPU','Adreno','DPU 1199'],8),('ADSP',863,473,66,65,['ADSP','Hexagon','DSP@1.5G'],9),('Hexagon Tensor',958,473,67,65,['Hexagon','Tensor'],9),('Video In',863,560,66,60,['Video In','MIPI CSI ×4'],9),('Video Out',958,556,67,65,['Video Out','MIPI DSI ×2','eDP ×4','DP ×3'],9)]
    for name,x,y,w,h,ss,size in resources:box(name,x,y,w,h,ss,size=size,note='QAM 8295P 内部资源，参数按所附图纸标注。')
    for name,x,y in [('USB 2.0 ×2',863,639),('USB 3.1 ×4',958,639),('RGMII/RMII ×2',863,679),('GPIO ×228',958,679),('PCIe ×7',863,721),('TDM ×10',958,721),('SPI/UART/I2C',863,762)]:box(name,x,y,67,22,size=9)

    # Video inputs, left side.
    region(145,44,686,272);brace(146,46,311,'Video Input')
    note(149,60,['1.合并CSI0输入配置','AVM无需供电'])
    cams=box('DVR / DMS / OMS / AVM',242,47,134,62,['DVR: 2MP@30fps','DMS: 2MP@30fps','OMS: 2MP@30fps','AVM: 3MP@25fps'],'external',9)
    box('GMSL Deserializer #0',644,57,85,49,['GMSL','Deserializer #0','MAX96712'],size=9)
    for i,t in enumerate(['GMSL2+POC','GMSL2+POC','GMSL2+POC','GMSL2']):flow(379,64+i*10,637,'video',t,lx=550,size=8)
    connector('D8480J',479,54,49,106)
    flow(732,75,836,'video','MIPI CSI 1');flow(732,92,836,'comm','CSI_I2C',both=True)
    note(149,149,['2.预留CSI1，维持','供电设计（后期','兼容国内需实贴）'])
    box('Reserve CAM1–4',242,140,134,62,[f'Reserve CAM{i} 3MP@30fps' for i in range(1,5)],'reserved',8.7)
    box('GMSL Deserializer #1',644,134,85,64,['GMSL','Deserializer #1','MAX96712'],'reserved',9)
    for i in range(4):flow(379,151+i*10,637,'reserved','GMSL2+POC',lx=550,size=8)
    connector('D8480I',479,142,48,194,'reserved')
    flow(732,155,836,'reserved','MIPI CSI 0');flow(732,172,836,'reserved','CSI_I2C',both=True)
    note(149,283,['3.扩展坞输出至车机','端视频流为1路'])
    box('SWITCH 扩展坞',242,250,134,56,['SWITCH 扩展坞','2MP@60fps'],'external',10)
    box('GMSL Deserializer #3',644,247,85,64,['GMSL','Deserializer #3','MAX96756'],size=9)
    flow(379,276,637,'video','GMSL2',lx=550,size=9)
    flow(732,263,836,'audio','I2S');flow(732,280,836,'video','MIPI_CSI3');flow(732,298,836,'comm','I2C',both=True)

    # Broadcast radio shares connector G with the expansion video path.
    brace(146,324,437,'Tuner & DAB+')
    for title,y in [('Tuner ANT',342),('DAB ANT',409)]:antenna(359,y,title)
    box('Tuner FM/AM',644,321,85,50,['Tuner','FM/AM','TDA7708LX52'],size=9)
    box('DAB',644,389,85,45,['DAB','TDA7707'],size=9)
    flow(379,342,637,'rf','POC',lx=529,size=8);flow(379,409,637,'rf','POC',lx=529,size=8)
    flow(732,337,836,'comm','Tuner_I2C',both=True);flow(732,356,836,'audio','I2S')
    flow(732,404,836,'comm','DAB_I2C',both=True);flow(732,422,836,'audio','HS_I2S')
    connector('D8480G',479,258,179,441)

    # Audio, ADC and reserve paths.
    brace(146,477,667,'Audio In &\nOut')
    label(344,511,'A2B AMP',10,'end');label(367,567,'A2B（设计预留）',10,'end')
    box('A2B TRANS #1',628,493,100,41,['A2B TRANS #1','AD2428'],size=9)
    box('A2B TRANS #2',628,550,100,40,['A2B TRANS #2','AD2428'],'reserved',9)
    flow(360,507,625,'audio','A2B_Data',True,lx=548,size=9);flow(360,562,625,'reserved','A2B_Data',True,lx=548,size=9)
    flow(732,504,836,'comm','A2B#1_I2C',True);flow(732,520,836,'audio','TDM',True)
    flow(732,561,836,'reserved','A2B#2_I2C',True);flow(732,578,836,'reserved','TDM',True)
    region(148,596,692,77);note(152,613,['1.硬件保留6路MIC输入能力','当前实贴4路的型号'])
    label(354,625,'模拟MIC ×4',10,'end');box('ADC PCM6340',628,606,100,40,['ADC','PCM6340'],size=9)
    box('PCM6360',628,647,100,21,kind='reserved',size=9,note='原图中作为 ADC 下方预留型号标记。')
    flow(360,620,625,'audio','Anlog Audio',True,lx=549,size=9)
    flow(732,617,836,'comm','ADC_I2C',True);flow(732,634,836,'audio','TDM')
    connector('D8480B',479,482,167,652)

    # Wireless front end.
    brace(146,672,766,'前排 BT & WIFI')
    for title,y in [('BT ANT',697),('WIFI ANT',714),('BT ANT',753)]:antenna(359,y,title)
    box('BT & WIFI i1568-sp',628,682,100,46,['BT & WIFI','i1568-sp'],size=10)
    box('BT i1572-s',628,740,100,37,['BT','i1572-s'],size=10)
    flow(379,697,622,'rf');flow(379,714,622,'rf','Inside WIFI ANT',lx=551,size=9);flow(379,753,622,'rf','Inside WIFI ANT',lx=551,size=9)
    flow(732,692,836,'audio','BT1_PCM');flow(732,706,836,'comm','BT1_UART',True);flow(732,721,836,'comm','BT1_PCIe',True)
    flow(732,752,836,'audio','BT2_PCM');flow(732,767,836,'comm','BT2_UART',True)

    # Display output.
    region(1065,28,604,280);brace(1708,25,304,'Video Output',True)
    box('Serializer #3 MAX96855',1161,53,83,55,['Serializer #3','MAX96855'],size=9)
    box('中控屏',1417,44,108,32,['中控屏','2560×1440@60fps'],'external',9)
    box('副驾屏',1417,80,108,32,['副驾屏','2560×1440@60fps'],'external',9)
    flow(1067,74,1157,'comm','DP_I2C',True);flow(1067,92,1157,'video','DP2')
    for y in [64,95]:flow(1247,y,1411,'video','GMSL 3',lx=1284,size=6.5)
    connector('D8480H',1336,54,18,103);labels.append('<rect x="1336" y="85" width="10" height="18" rx="4" fill="#e5eaff" stroke="#648cff"/><path d="M1337 86L1345 102M1345 86L1337 102" stroke="#b1bac8"/>')
    note(1543,60,['1.中控及副驾屏纵向分辨率','由1600改为1440'])
    box('Serializer #2 DS90UB983',1161,131,83,58,['Serializer #2','DS90UB983'],size=9)
    box('吸顶屏',1417,127,108,67,['吸顶屏','3036×1708@60fps'],'external',10)
    flow(1067,149,1157,'comm','eDP_I2C',True);flow(1067,169,1157,'video','eDP0')
    for y in [142,176]:flow(1247,y,1411,'video','FPD LINK IV',lx=1291,size=6)
    connector('D8480K',1336,130,21,190);labels.append('<rect x="1336" y="166" width="10" height="21" rx="4" fill="#e5eaff" stroke="#648cff"/><path d="M1337 167L1345 186M1345 167L1337 186" stroke="#b1bac8"/>')
    box('Serializer #1 DS90UB981',1161,225,83,70,['Serializer #1','DS90UB981'],size=9)
    box('HUD',1417,215,108,34,['HUD','1280×640@60fps,24bit'],'external',9)
    box('仪表屏',1417,253,108,34,['仪表屏','1920×480@60fps,8bit'],'external',9)
    flow(1067,238,1157,'comm','DSI_I2C',True);flow(1067,257,1157,'video','DSI0_HUD');flow(1067,277,1157,'video','DSI1_IPC')
    flow(1247,235,1411,'video','FPD LINK III',lx=1291,size=6);flow(1247,269,1411,'video','FPD LINK IV',lx=1291,size=6)
    connector('D8480K',1336,225,21,282);labels.append('<rect x="1336" y="259" width="10" height="21" rx="4" fill="#e5eaff" stroke="#648cff"/><path d="M1337 260L1345 279M1345 260L1337 279" stroke="#b1bac8"/>')
    note(1583,253,['2.仪表纵向分辨率','由720改为480'])

    # Storage, ethernet and USB.
    brace(1710,321,377,'Mfi & Storage',True)
    box('256GB UFS',1161,307,113,37,['256GB UFS','HN8T15DJHVX109'],size=9)
    box('Apple Mfi Chip',1161,356,83,21,size=9)
    flow(1067,327,1157,'comm','UFS 0',True);flow(1067,367,1157,'comm','Mfi_I2C_1',True)
    brace(1710,392,462,'ETH Interface',True)
    box('ETH PHY RTL9010ARG',1161,398,83,46,['ETH PHY','RTL9010ARG'],size=9)
    box('外部以太网',1417,400,108,34,kind='external',size=10)
    flow(1067,408,1157,'comm','RGMII',True);flow(1067,434,1157,'comm','I2C',True)
    flow(1248,418,1411,'comm','1000BASE-T1',True,lx=1289,size=6);connector('D8480F',1336,397,41,440)
    brace(1710,479,741,'USB接口',True)
    box('USB CHG RTQ2117A',1162,469,82,36,['USB CHG','RTQ2117A'],size=9)
    box('TYPE-A 多媒体/手机投射',1415,467,108,33,['TYPE-A','多媒体/手机投射'],'external',9)
    flow(1067,491,1157,'comm','USB2.0_HS',True)
    flow(1248,482,1410,'comm','USB 2.0',lx=1290,size=6);flow(1248,494,1410,'power','vbus',lx=1280,size=6)
    connector('D8480C',1335,472,31,506)
    box('USB 充电模块',1415,527,108,57,kind='external',size=10)
    for y,title,label_ in [(537,'USB3.0_HS','USB 3.0'),(553,'USB3.0_SS','USB 3.0'),(572,'USB2.0','')]:
        flow(1067,y,1410,'comm','',True);label(1083,y-5,title,10,'start')
        if label_:label(1290,y-3,label_,6)
    connector('D8480E',1335,532,63,601)
    route([(1522,609),(1469,609),(1469,587)],'power');label(1475,604,'Vehicle BATT',6,'start')
    region(1065,654,604,75);note(1593,687,['1.客户确认预留'],'reserved')
    box('TYPE-A 预留',1415,670,108,33,['TYPE-A'],'reserved',10)
    flow(1067,690,1410,'reserved','USB2.0',True,lx=1107);connector('D8480D',1335,671,29,702,'reserved')

    # Debug and IMU.
    brace(1710,742,793,'IMU',True)
    box('Internal Debug · SoC',1161,743,89,25,['Internal Debug'],size=9)
    box('IMU IAM-20680HV',1161,775,89,43,['IMU','IAM-20680HV'],size=9)
    flow(1067,757,1157,'comm','Debug_UART',True)
    flow(1067,788,1157,'comm','SPI',True);flow(1067,808,1157,'comm','INT',True)
    route([(1112,808),(1112,968),(1064,968)],'comm')

    # MCU and hardware interfaces.
    nodes.append(dict(id='hw-mcu',name='MCU S32K312NHT0MPBST',x=842,y=940,w=219,h=319,kind='base',lines=['MCU','S32K312NHT0MPBST','ARM CORTEX M7','@120MHz'],note='微控制器；连接 CAN、LIN、供电管理、EEPROM、RTC 与监测接口。'))
    shapes.append('<g class="hardware-module" id="hw-mcu" data-hw-node="hw-mcu" role="button" tabindex="0" aria-label="MCU S32K312NHT0MPBST"><rect class="hw-box" x="842" y="940" width="219" height="319" fill="#fff0de" stroke="#608bff" stroke-width="1.5"/></g>')
    for i,t in enumerate(['MCU','S32K312NHT0MPBST','ARM CORTEX M7','@120MHz']):label(951.5,956+i*15,t,10)
    for name,x,y in [('2MB PFlash',859,1029),('SPI ×4',971,1029),('128KB SRAM',859,1059),('CAN ×6',971,1059),('LPUART ×8',859,1089),('I2C ×2',971,1089),('ADC ×2',859,1120)]:box(name,x,y,74,21,size=10)
    for x,title in [(911,'Reset'),(930,'SPI ×1'),(951,'UART'),(972,'硬线')]:
        route([(x,839),(x,936)],both=True)
        labels.append(text(x-5,889,title,9,rotate=-90))
    box('SWC/TBOX/MUTE/CLUSTER',646,961,85,44,['SWC/TBOX/MUTE/','CLUSTER'],size=9)
    flow(339,982,642,'comm','外部输入待定',True,lx=390)
    flow(735,986,837,'comm','A/D signal ×N',lx=785,size=9)
    region(149,1011,691,158)
    note(152,1027,['1.公CAN 需支持局部唤醒'])
    note(152,1101,['2.预留私CAN支持CAN-FD'],'reserved')
    note(152,1147,['3.客户要求预留LIN'],'reserved')
    box('CAN1 TRANS SIT 1145',646,1018,85,38,['CAN1 TRANS','SIT 1145'],size=9)
    box('CAN2 TRANS SIT 1043',646,1071,85,38,['CAN2 TRANS','SIT 1043'],'reserved',9)
    box('LIN TRANS TLIN1021',646,1122,85,39,['LIN TRANS','TLIN1021'],'reserved',9)
    for y,k,cap,typ in [(1036,'comm','CAN FD-公','CAN TX/RX 0'),(1094,'reserved','CAN FD-私','CAN TX/RX 1'),(1145,'reserved','','LIN')]:
        flow(339,y,642,k,cap,True,lx=365);flow(735,y,837,k,typ,True,lx=785,size=9)
    box('Main Power',646,1174,85,53,kind='power',size=10)
    flow(339,1196,642,'power','Vehicle BATT',lx=390)
    for y,title in [(1223,'EXT_MCU0_WAKE ×2'),(1243,'EXT_DSP_EN ×4')]:flow(339,y,475,'power','',reverse=True);label(346,y-5,title,10,'start',SIGNALS['power'])
    flow(735,1187,837,'comm','SPI',True,lx=764);flow(735,1203,837,'comm','Reset',lx=776);flow(735,1223,837,'power','5V/3.3V',lx=787)
    connector('D8480A',479,966,286,1254)
    for name,y,ss in [('EEPROM',982,['EEPROM','GT24C32B']),('RTC',1027,['RTC','INS5A8804']),('Internal Debug · MCU',1076,['Internal Debug']),('Temp Sensor',1118,['Temp Sensor']),('Watch Dog',1171,['Watch Dog'])]:
        box(name,1147,y,89,33,ss,size=9)
    for y,title in [(999,'MCU_I2C'),(1040,'MCU_I2C'),(1090,'Debug_UART')]:flow(1066,y,1143,'comm',title,True,lx=1103,size=9)
    flow(1066,1135,1143,'comm','A/D',reverse=True,lx=1090)
    flow(1066,1188,1143,'comm',reverse=True)

    # Legend follows the attached diagram.
    label(1564,1090,'图示说明',10,'start')
    for title,yy,kind in [('基础配置',1107,'base'),('外部设备',1148,'external'),('预留功能',1185,'reserved')]:box(title,1564,yy,70,24,kind=kind,size=10,searchable=False)
    for i,(k,title) in enumerate([('comm','通信信号'),('video','视频信号'),('audio','音频信号'),('rf','射频信号'),('power','供电电源')]):
        yy=1229+i*23
        labels.append(f'<path d="M1564 {yy}H1630" stroke="{SIGNALS[k]}" stroke-width="1.5"/>')
        label(1642,yy+4,title,10,'start')

    defs='<defs>'
    for k,c in SIGNALS.items():
        defs+=f'<marker id="hw-arrow-{k}" viewBox="0 0 8 10" refX="7" refY="5" markerWidth="6" markerHeight="7" orient="auto-start-reverse"><path d="M1 1L7 5L1 9" fill="none" stroke="{c}" stroke-width="1.3"/></marker>'
    defs+='</defs>'
    svg='<svg id="hardware-drawing" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1827 1344" role="group" aria-labelledby="hardwareTitle hardwareDesc"><title id="hardwareTitle">A平台IVI硬件架构图</title><desc id="hardwareDesc">根据所附图纸重绘，展示 QAM 8295P 与 MCU，以及视频、音频、无线通信、以太网、USB 和电源接口。灰色表示预留功能。</desc>'+defs
    svg+='<style>#hardware-drawing text{pointer-events:none;font-family:Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif}#hardware-drawing .hardware-module{cursor:pointer}#hardware-drawing .hardware-module:hover .hw-box,#hardware-drawing .hardware-module:focus .hw-box{stroke:#2454af;stroke-width:2}#hardware-drawing .hardware-module.found .hw-box{stroke:#da8409;stroke-width:2.5}#hardware-drawing .hardware-module.selected .hw-box{stroke:#1454b8;stroke-width:2.5}</style><rect width="1827" height="1344" fill="white"/>'
    svg+=''.join(shapes+wires+node_parts+labels)+'</svg>'
    return svg,dict(width=WIDTH,height=HEIGHT,nodes=nodes)
