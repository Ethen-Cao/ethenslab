from pathlib import Path
from html import escape as esc
import json, re
from ivi_hardware import create_hardware
from b_platform_system import create_b_system
from software_high_level import render_software
from software_ota import render_ota
from software_diagnostics import render_diagnostics
from software_audio import render_audio
from software_widevine import render_widevine
from storage_partitions import render_storage

ROOT = Path(__file__).parent
glossary = []
for line in (ROOT/'glossary.tsv').read_text().splitlines():
    abbr, en, cn = line.split('\t')
    glossary.append(dict(abbr=abbr, en=en, cn=cn))
COLORS = dict(energy='#f5d875', chassis='#52b1e2', cockpit='#e0eef2', body='#c9c2d5', thermal='#a4ce65', adas='#f5d8bc', central='#e9edf4')
DOMAINS = dict(energy='新能源', chassis='底盘控制', cockpit='智能座舱', body='车身控制', thermal='动力 / 空调 / 热管理', adas='智能驾驶', central='中央 / 区域控制器')
BC = dict(CANFD='#27ac49', CAN='#ff4338', LIN='#efb517', Ethernet='#287ad5', LVDS='#834cb4', DSI='#e8b52d', Signal='#555555')
nodes=[]; nets={}; lines=[]; annotations=[]; decorations=[]

def text(x,y,s,size=5.2,anchor='start',fill='#283444',extra=''):
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" {extra}>{esc(str(s))}</text>'

def label(x,y,s,size=5.2,anchor='start',fill='#283444'):
    annotations.append(text(x,y,s,size,anchor,fill))

def node(name,x,y,w=34,h=18,domain='body',key=None,removed=False,optional=False,sub='',note='',nm=False,marks=''):
    id='n'+str(len(nodes)+1)
    n=dict(id=id,name=name,x=x,y=y,w=w,h=h,domain=domain,key=key or name.replace('\n',' '),removed=removed,optional=optional,sub=sub,note=note,nm=nm,marks=marks,nets=[])
    nodes.append(n)
    return n

def net(id,kind,title):
    nets[id]=dict(id=id,kind=kind,title=title,members=[])
    return id

def wire(netid,pts):
    lines.append((netid,pts))

def join(n,netid):
    if netid not in n['nets']: n['nets'].append(netid)
    if n['id'] not in nets[netid]['members']: nets[netid]['members'].append(n['id'])

def tap(n,netid,x=None,y=None,side='left'):
    join(n,netid)
    if side in ['left','right']:
        end=(n['x'] if side=='left' else n['x']+n['w'],n['y']+n['h']/2)
        wire(netid,[(x,end[1]),end])
    else:
        end=(n['x']+n['w']/2,n['y'] if side=='top' else n['y']+n['h'])
        wire(netid,[(end[0],y),end])

def row(netid,items,x,y,trunkY,startX,domain='body',w=34,h=18,gap=4):
    rownodes=[]
    for i,item in enumerate(items):
        o=dict(item) if isinstance(item,dict) else dict(name=item)
        xx=o.pop('x',x+i*(w+gap))
        yy=o.pop('y',y)
        n=node(x=xx,y=yy,w=o.pop('w',w),h=h,domain=domain,**o)
        tap(n,netid,y=trunkY,side='top' if yy>trunkY else 'bottom')
        rownodes.append(n)
    centers=[startX]+[n['x']+n['w']/2 for n in rownodes]
    wire(netid,[(min(centers),trunkY),(max(centers),trunkY)])
    return rownodes

def note(x,y,w,h,s):
    annotations.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="white" stroke="#fb655b" stroke-width=".65"/>')
    ss=s.split('\n')
    for i,t in enumerate(ss): label(x+3,y+7+i*6,t,5,fill='#eb625a')

def term(x,y,ohm=120):
    decorations.append(f'<rect x="{x-3.5}" y="{y-1.8}" width="7" height="3.6" fill="{"#277ad0" if ohm==66 else "#666"}"/>')

ivi=node('IVI-8295',87,71,39,209,'cockpit',key='IVI',marks='*#')
vcm=node('VCM',355,75,1132,43,'central',marks='*')
ml=node('VIU_ML',818,317,52,447,'central',marks='*',note='原图区域控制器标识。所附缩写表未列出 VIU_ML 的全称；ML 的准确含义待项目缩写表核对。')
mr=node('VIU_MR',1317,317,50,447,'central',marks='*',note='原图区域控制器标识。所附缩写表未列出 VIU_MR 的全称；MR 的准确含义待项目缩写表核对。')
adcu=node('ADCU',1780,66,43,516,'adas',sub='J6E',note='原图标注：自研智驾系统。')

# Backbone and diagnostic links.
bb=net('backbone','CANFD','Backbone CAN FD · 2M')
wire(bb,[(390,118),(390,785),(1801,785),(1801,582)])
wire(bb,[(844,764),(844,785)])
wire(bb,[(1342,764),(1342,785)])
for n in [vcm,ml,mr,adcu]:join(n,bb)
label(396,128,'Backbone CANFD · 2M',4.4)
for a,b in [(390,118),(844,764),(1342,764),(1801,582)]:term(a,b)
ethivi=net('eth-ivi','Ethernet','IVI ↔ VCM · Ethernet')
wire(ethivi,[(126,96),(355,96)])
join(ivi,ethivi);join(vcm,ethivi);label(286,92,'IVI_ETH · 1000BASE-T1',4)
info=net('info','CANFD','INFO CAN FD · 2M')
wire(info,[(126,109),(355,109)]);wire(info,[(228,109),(228,275)])
join(ivi,info);join(vcm,info);label(257,116,'INFO CANFD · 2M',4)
obd=node('OBD',457,32,30,22,marks='*')
tbox=node('T_BOX',526,32,29,22,nm=True,marks='*')
for n,xx in [(obd,466),(tbox,535)]:
    b=net('diag-'+n['id'],'CAN','Diagnostic CAN · 500K' if n==obd else 'Terminal CAN · 500K')
    wire(b,[(xx,54),(xx,75)]);join(n,b);join(vcm,b)
    e=net('eth-'+n['id'],'Ethernet','Ethernet · '+n['name'])
    wire(e,[(xx+13,54),(xx+13,75)]);join(n,e);join(vcm,e)
    label(xx-2,65,'CAN 500K',3.8,'end');label(xx+16,67,'Ethernet',3.6)
term(466,75,66)
adeth=net('eth-adas','Ethernet','VCM ↔ ADCU · Ethernet · 1000BASE-T1')
wire(adeth,[(1487,88),(1780,88)]);join(vcm,adeth);join(adcu,adeth);label(1495,84,'Ethernet · 1000BASE-T1',4)
e=net('eth-reserved','Ethernet','VCM 以太网接口（原图开放端）');wire(e,[(1487,109),(1557,109)]);join(vcm,e);label(1495,104,'Ethernet · 100BASE-T1',4)
for n,xx in [(ml,853),(mr,1350)]:
    e=net('eth-'+n['id'],'Ethernet','VCM ↔ '+n['name']+' · Ethernet')
    wire(e,[(xx,118),(xx,317)]);join(vcm,e);join(n,e);label(xx+5,128,'ZCU_ETH',4);label(xx+5,134,'100BASE-T1',3.7)

# Cockpit.
dms=node('DMS',24,126,34,18,'cockpit')
e=net('lvds-dms','LVDS','DMS ↔ IVI · LVDS');wire(e,[(58,135),(87,135)]);join(dms,e);join(ivi,e)
cab=[('PS',126,'PassengerScreen'),('CS',148,'CentralScreen'),('AR_HUD',182,'AR_HUD'),('IC',216,'IC'),('CMCS',250,'CMCS')]
for name,yy,key in cab:
    n=node(name,155,yy,34,18,'cockpit',key=key,marks='*')
    e=net('lvds-'+name,'LVDS',name+' ↔ IVI · LVDS');wire(e,[(126,yy+9),(155,yy+9)]);join(ivi,e);join(n,e)
    tap(n,info,x=228,side='right')
decorations.append('<rect x="151" y="122" width="43" height="47" fill="none" stroke="#ff6860" stroke-width=".7" stroke-dasharray="3 2"/>')
label(198,148,'双联屏',5,fill='#ef6a60')
c=node('To VIU_ML',262,232,34,18,'cockpit',note='原图跨区域网络引用端口；该处未画出物理线束走向。');tap(c,info,x=228)
n=node('EIRM',262,266,34,18,note='原图批注：电子内后视镜。所附缩写表未列出英文全称。',marks='*',nm=True);tap(n,info,x=228)
note(263,293,33,16,'电子内后视\n镜')
note(259,143,67,43,'二排扶手屏改为无线扶\n手屏方案；延迟、发热、\nWi-Fi 稳定性等批注\n（细小文字待核对）')
for i,t in enumerate(['DVR（原图接口）','AVM bypass1','AVM bypass2']):
    e=net('ivi-port-'+str(i),'LVDS',t);wire(e,[(31,207+i*8),(87,207+i*8)]);join(ivi,e);label(80,204+i*8,t,3.7,'end')

# Energy and front thermal domain.
dc=net('dc-charging','CAN','DC Charging CAN · 250K')
wire(dc,[(466,118),(466,196)]);join(vcm,dc);n=node('EVCC',453,164,26,17,'energy',note='原图标识 EVCC；所附缩写表未列出全称。');join(n,dc)
label(473,138,'DC Charging CAN',4);label(473,144,'250K',4);label(476,188,'To Body CAN',4)
en=net('energy','CANFD','Energy CAN FD · 2M');wire(en,[(640,118),(640,368)]);join(vcm,en);label(646,128,'Energy CANFD · 2M',4.3)
for name,y,domain,w,h in [('BMS',164,'energy',34,18),('OBC',190,'energy',34,18),('LBMS',241,'body',34,18),('TMCF',279,'thermal',34,27),('HSG',325,'thermal',34,18),('MCUF',351,'energy',34,18)]:
    n=node(name,593,y,w,h,domain,nm=name in ['BMS','OBC','LBMS','MCUF'],marks='' if name in ['TMCF','HSG'] else '*');tap(n,en,x=640,side='right')
    if name=='TMCF':tm=n
    if name=='MCUF':mcu=n
for name,y,removed in [('PNG',202,True),('SWM',229,False)]:
    n=node(name,653,y,34,18,removed=removed,nm=True,marks='*');tap(n,en,x=640)
n=node('To VIU_MR',653,339,34,18,'cockpit',note='原图 Energy CAN FD 跨区域引用端口。');tap(n,en,x=640)
for name,yy,trunk in [('APTC',258,284),('AGS1',309,302)]:
    n=node(name,525,yy,26,18,'thermal',sub='下' if name=='AGS1' else '',note='原图标识 APTC；所附缩写表列出 CPTC，二者未自动等同。' if name=='APTC' else '')
    b=net('thermal-'+name,'LIN','Thermal LIN · 19.2K · '+name);wire(b,[(538,yy+18 if name=='APTC' else yy),(538,trunk),(593,trunk)]);join(n,b);join(tm,b);label(583,trunk-3,'Thermal LIN 19.2K',3.9,'end')
n=node('EOFF',547,351,30,18,'energy');b=net('private-front-motor','CAN','前电机私有 CAN');wire(b,[(577,360),(593,360)]);join(n,b);join(mcu,b);label(584,349,'私有',4,'middle');label(584,355,'CAN',4,'middle')

# Chassis and motion.
cc=net('chassis','CANFD','Chassis CAN FD · 2M');wire(cc,[(1028,118),(1028,326),(870,326)]);join(vcm,cc);join(ml,cc);label(1034,129,'Chassis CANFD · 2M',4.1);label(881,322,'To Chassis CANFD',4.6)
motion=net('motion','CANFD','Motion CAN FD · 2M');wire(motion,[(1180,118),(1180,343),(1317,343)]);join(vcm,motion);join(mr,motion);label(1187,129,'Motion CANFD · 2M',4.1);label(1312,339,'To Motion CANFD',4.4,'end')
for name,x,y,d,side in [('ACU',984,151,'body','right'),('RWS',984,194,'chassis','right'),('To ADCU',984,237,'adas','right'),('IPB',1036,164,'chassis','left'),('EPS',1036,215,'chassis','left')]:
    n=node(name,x,y,34,18,d,marks='' if name.startswith('To') else '*#',nm=name in ['ACU','IPB']);tap(n,cc,x=1028,side=side)
    if name=='IPB':tap(n,motion,x=1180,side='right')
n=node('MCUR',1194,151,37,18,'energy',marks='*#',nm=True);tap(n,motion,x=1180);rearMcu=n
n=node('EOFR',1248,151,31,18,'energy',note='原图标识 EOFR；所附缩写表未列出全称。');b=net('private-rear-motor','CAN','后电机私有 CAN');wire(b,[(1231,160),(1248,160)]);join(rearMcu,b);join(n,b);label(1240,147,'私有 CAN',4,'middle')
iccl=node('ICC_L',1053,296,26,18,'chassis',key='ICC',marks='*#',nm=True,note='左侧 ICC；原图标注集成悬架相关控制功能。')
iccr=node('ICC_R',1079,296,26,18,'chassis',key='ICC',marks='*#',nm=True)
tap(iccl,cc,x=1028);tap(iccr,motion,x=1180,side='right');wire(motion,[(1066,296),(1066,288),(1180,288)]);join(iccl,motion)
note(943,288,75,25,'底盘集成控制器 ICC\n集成悬架相关控制功能')
asu=node('ASU',1082,347,31,14,'chassis',nm=True,marks='*#');b=net('icc-asu','CANFD','ICC ↔ ASU · CAN FD');wire(b,[(1069,314),(1069,354),(1082,354)]);join(iccl,b);join(asu,b)
ef=net('energy-ml','CANFD','VCM ↔ VIU_ML · CAN FD');wire(ef,[(837,118),(837,317)]);join(vcm,ef);join(ml,ef);label(813,129,'ZCU_L CANFD',4)
ef=net('energy-mr','CANFD','VCM ↔ VIU_MR · CAN FD');wire(ef,[(1334,118),(1334,317)]);join(vcm,ef);join(mr,ef);label(1301,129,'ZCU_R CANFD',4)
for name,y in [('To INFO CANFD',325),('To Energy CANFD',325)]:
    xx=818 if name=='To INFO CANFD' else 1317
    b=net('port-'+str(xx),'CANFD',name+'（跨区域网络引用）');wire(b,[(xx-41,y),(xx,y)]);join(ml if xx==818 else mr,b);label(xx-3,y-5,name,4.5,'end')

# Left zone LIN nodes.
for id,ty,items,x,y in [('body-lin-left-1',347,['HOD','SWS'],747,355),('body-lin-left-2',398,['SSM_F','WSM_FL','ITL'],713,406),('body-lin-left-3',450,['FEW','RLS'],747,458),('body-lin-left-4',500,['AR_IBC'],768,508)]:
    b=net(id,'LIN','Body LIN · 19.2K · '+' / '.join(items));join(ml,b)
    ns=row(b,items,x,y,ty,818,w=26 if len(items)>1 else 34,gap=8)
    for n in ns:n['marks']='*' if n['name'] in ['RLS','AR_IBC'] else ''
    label(813,ty-4,'Body LIN 19.2K',4,'end')
note(705,433,34,21,'前排天窗遮\n阳帘二合一')
note(768,536,34,17,'投影脚踏')

# Left zone Body CAN 1 and private digital key CAN.
body1=net('body-can-left-1','CAN','VIU_ML · Body CAN · 500K');join(ml,body1)
ns=row(body1,[dict(name='EVCC',note='原图 Body CAN 上的 EVCC 标识。'),dict(name='CRF',nm=True,marks='*'),dict(name='WCM_FL',key='WCM_F',nm=True),dict(name='WCM_RL',key='WCM_F')],883,406,393,870,w=26,gap=8)
ns[0]['domain']='energy';ns[1]['domain']='thermal';ns[2]['x']=994;ns[3]['x']=1036
# Rebuild their drops after changing the sparse positions.
lines[:]=[(b,p) for b,p in lines if b!=body1]
wire(body1,[(870,393),(1096,393)])
for n in ns:tap(n,body1,y=393,side='top')
dkc=node('DKC',1096,381,94,26,marks='*',nm=True);tap(dkc,body1,x=870);label(876,389,'Body CAN 500K',4)
note(1201,381,35,27,'遥控钥匙\n蓝牙钥匙\nNFC 钥匙')
pk=net('private-nfc','CANFD','Private NFC CAN FD · 2M');join(dkc,pk);wire(pk,[(1143,407),(1143,462),(1007,462),(1007,424)]);join(ns[2],pk)
label(1150,417,'Private NFC CANFD 2M',3.8)
for name,yy in [('BLE Slave FR',420),('BLE Slave FL',433),('BLE Slave R',446)]:
    n=node(name,1088,yy,43,9,marks='*');tap(n,pk,x=1143,side='right')
n=node('NFC_OUT',1156,420,46,17,marks='*',nm=True);tap(n,pk,x=1143)
body2=net('body-can-left-2','CAN','VIU_ML · Body CAN · 500K（车门）');join(ml,body2)
row(body2,[dict(name='POT',marks='*',nm=True),dict(name='DCU_FR',marks='*',nm=True),dict(name='DCU_FL',marks='*',nm=True),dict(name='DCU_RR',marks='*',nm=True),dict(name='DCU_RL',marks='*',nm=True),dict(name='PSD_L',marks='*',nm=True,note='原图 PSD_L；缩写表未列出全称。'),dict(name='PSD_R',marks='*',nm=True,note='原图 PSD_R；缩写表未列出全称。'),dict(name='POD_FL',marks='*',nm=True),dict(name='POD_FR',marks='*',nm=True)],879,488,475,870,w=29,h=26,gap=5)
label(876,471,'Body CAN 500K',4);note(1113,518,64,18,'一排左 / 右电动门\n（只电动关门）')

# Lower Body CAN connects to right zone.
br=net('body-can-right','CAN','VIU_MR · Body CAN · 500K');join(mr,br)
ns=row(br,[dict(name='AMP',nm=True,marks='*',sub='24EQ',w=34),dict(name='ETC',removed=True,optional=True),dict(name='WCM_FR',key='WCM_F'),dict(name='WCM_RR',key='WCM_F'),dict(name='SCU_TR',x=1114,nm=True,marks='*'),dict(name='SCU_RR',x=1178,nm=True,marks='*'),dict(name='SCU_RL',x=1242,nm=True,marks='*')],925,556,543,1317,w=34,h=26,gap=9)
ns[0]['domain']='cockpit';label(1312,539,'Body CAN 500K',4,'end');note(968,587,34,17,'ETC 接口')
for parent,xx,items in [(ns[4],1114,['SS_TRL','SS_TRR']),(ns[5],1178,['WSM_RR','WSM2_RR']),(ns[6],1242,['WSM_RL','WSM2_RL'])]:
    b=net('seating-'+parent['id'],'LIN','Seating LIN · 19.2K · '+parent['name']);join(parent,b)
    trunk=xx+17 if parent==ns[4] else xx+40
    wire(b,[(xx+17,582),(trunk,582),(trunk,629)])
    for i,name in enumerate(items):
        n=node(name,xx-43 if parent==ns[4] else xx-6,598+i*22,34,17,sub='座椅开关' if name.startswith('SS_') else ('座垫' if '2' in name else '腰托'))
        tap(n,b,x=trunk,side='right')
    label(xx+13,589,'Seating LIN',3.8,'end');label(xx+13,594,'19.2K',3.8,'end')

# Exterior lighting.
ext=net('exterior-lighting','CANFD','Lighting CAN FD · 2M');join(mr,ext)
wire(ext,[(1078,703),(1317,703)])
lights=[]
for name,xx,ww in [('HCM_L',1061,30),('HCM_R',1095,30),('RRLM_Fix',1129,39),('RLLM_Fix',1172,35),('RLM_Move',1211,43)]:
    n=node(name,xx,717,ww,18,marks='*');lights.append(n)
    if name in ['HCM_L','HCM_R','RLM_Move']:tap(n,ext,y=703,side='top')
p=net('private-lights','CAN','尾灯私有 CAN');wire(p,[(1149,735),(1149,747),(1232,747),(1232,735)]);wire(p,[(1189,735),(1189,747)])
for n in lights[2:]:join(n,p)
label(1310,699,'Lighting CANFD · 2M',4,'end');label(1190,758,'尾灯私有 CAN',4,'middle')

# Cabin lighting, original labels retained even when absent from glossary.
leftLight=net('lighting-left-1','LIN','VIU_ML · Lighting LIN · 19.2K（门板 / 照脚灯）');join(ml,leftLight)
top=['IAL_FL_Door1','IAL_FL_Door2','IAL_FL_Door3','IAL_FL_Door4','IAL_FL_Door5','IAL_DB1','IAL_DB2','IAL_DB3']
row(leftLight,[dict(name=t,removed=i in [1,2,7],key=t) for i,t in enumerate(top)],470,649,675,818,'cockpit',w=34,gap=4)
row(leftLight,['IAL_TRL_Door1','IAL_RL_Door2','IAL_RL_Door2','IAL_RL_Door1','IAL_SkyLight','IAL_DB4'],513,683,675,818,'cockpit',w=41,gap=4)
label(813,672,'Lighting LIN 19.2K',3.8,'end')
leftLight2=net('lighting-left-2','LIN','VIU_ML · Lighting LIN · 19.2K（仪表板）');join(ml,leftLight2)
row(leftLight2,['IAL_IPL1','IAL_IPL2','IAL_DI','IAL_Console1','IAL_IPM1','IAL_IS'],556,714,738,818,'cockpit',w=34,gap=4)
row(leftLight2,['IAL_IPL3','IAL_IPR2','IAL_IPR1','IAL_P1'],632,748,738,818,'cockpit',w=34,gap=4)
label(813,735,'Lighting LIN 19.2K',3.8,'end')

# Right zone climate LIN branches.
c1=net('climate-1','LIN','VIU_MR · Climate LIN · 19.2K（前排风门）');join(mr,c1)
row(c1,['AQS','IntkActr','MixAct_FL','MixAct_FR','DefrostAct_F','BlowFeet_Act_FL','BlowFace_Act_FL'],1393,338,330,1367,'thermal',w=34,h=14,gap=3)
row(c1,['BlowFeet_Act_FR','BlowFace_Act_FR'],1580,308,330,1367,'thermal',w=39,h=14,gap=4)
label(1372,324,'Climate LIN 19.2K',4)
c2=net('climate-2','LIN','VIU_MR · Climate LIN · 19.2K（后排风门）');join(mr,c2)
row(c2,[dict(name='FCM',optional=True),dict(name='PM2.5'),dict(name='MixAct_RL',removed=True,note='原图标识；所附表仅列出 MixAct_R，未自动等同。'),dict(name='MixAct_RR',note='原图标识；所附表仅列出 MixAct_R，未自动等同。'),dict(name='DefrostAct_R'),dict(name='ModeActr_R'),dict(name='BlowFeet_Act_RL'),dict(name='BlowFace_Act_RL')],1393,389,382,1367,'thermal',w=34,h=14,gap=3)
row(c2,[dict(name='BlowFeet_Act_RR',removed=True),dict(name='BlowFace_Act_RR',removed=True)],1614,359,382,1367,'thermal',w=34,h=14,gap=3)
label(1372,377,'Climate LIN 19.2K',4)
c3=net('climate-3','LIN','VIU_MR · Climate LIN · 19.2K（出风口电机）');join(mr,c3)
row(c3,['EAO_FR Motor1','EAO_FR Motor2','EAO_MR Motor1','EAO_MR Motor2','EAO_ML Motor1','EAO_FL Motor1','EAO_ML Motor2','EAO_FL Motor2'],1393,457,446,1367,'thermal',w=34,h=18,gap=4)
row(c3,[dict(name=t,removed=True) for t in ['EAO_RL Motor1','EAO_RL Motor2','EAO_RR Motor1','EAO_RR Motor2']],1393,415,446,1367,'thermal',w=34,h=18,gap=4)
label(1372,441,'Climate LIN 19.2K',4)
rr=net('lighting-right','LIN','VIU_MR · Lighting LIN · 19.2K（门板 / 照脚灯）');join(mr,rr)
row(rr,[dict(name=t,removed=i in [1,2]) for i,t in enumerate(['IAL_FR_Door1','IAL_FR_Door2','IAL_FR_Door3','IAL_FR_Door4','IAL_FR_Door5','IAL_RR_Door1','IAL_RR_Door2'])],1405,492,518,1367,'cockpit',w=34,gap=4)
row(rr,[dict(name='IAL_PB4'),dict(name='IAL_PB3',removed=True),dict(name='IAL_PB2'),dict(name='IAL_PB1'),dict(name='IAL_TRR_Door1',x=1597),dict(name='IAL_RR_Door2',x=1640)],1393,526,518,1367,'cockpit',w=39,gap=4)
label(1372,514,'Lighting LIN 19.2K',4)
rb=net('body-lin-right','LIN','VIU_MR · Body LIN · 19.2K');join(mr,rb)
row(rb,['WSM_FR','SSM_R'],1393,577,565,1367,w=34,gap=13);label(1372,561,'Body LIN 19.2K',4)
note(1440,602,34,18,'后排分区\n遮阳帘')
logo=net('logo','LIN','VIU_MR · Lighting LIN · 19.2K（LOGO 灯）');join(mr,logo)
row(logo,['EIL_Logo'],1393,649,637,1367,w=34);label(1372,634,'Lighting LIN 19.2K',4);note(1393,676,34,13,'Logo 灯')

# ADAS sensors.
label(1814,51,'自研智驾系统',12,fill='#f16c62')
chAd=net('adas-chassis-port','CANFD','ADCU · Chassis CAN FD · 2M（引用端口）');wire(chAd,[(1724,131),(1780,131)]);join(adcu,chAd);label(1725,127,'Chassis CANFD 2M',4)
for i,s in enumerate(['DVR（原图接口）','AVM bypass1','AVM bypass2']):
    b=net('adas-input-'+str(i),'LVDS',s);wire(b,[(1724,152+i*8),(1780,152+i*8)]);join(adcu,b);label(1775,149+i*8,s,3.7,'end')
pb=node('P-BOX',1848,122,51,18,'adas',key='PBOX',sub='IMU / GNSS / RTK',marks='*')
for kind,yy in [('Ethernet',126),('CANFD',137)]:
    b=net('pbox-'+kind,kind,'ADCU ↔ P-BOX · '+kind);wire(b,[(1823,yy),(1848,yy)]);join(pb,b);join(adcu,b)
us=node('USC',1848,148,22,18,'adas');uss=node('USS',1883,148,17,18,'adas',sub='× 12')
b=net('ultrasonic','CANFD','ADCU ↔ USC · CAN FD');wire(b,[(1823,157),(1848,157)]);join(adcu,b);join(us,b)
b=net('uss','Signal','USC ↔ USS × 12');wire(b,[(1870,157),(1883,157)]);join(us,b);join(uss,b)
lrr=node('LRR_F',1848,245,51,18,'adas');rcl=node('RCR_L',1848,271,51,18,'adas');rcr=node('RCR_R',1848,293,51,18,'adas')
b=net('radar-front','CANFD','ADCU ↔ LRR_F · CAN FD');wire(b,[(1823,254),(1848,254)]);join(adcu,b);join(lrr,b)
b=net('radar-rear','CANFD','ADCU ↔ RCR_L / RCR_R · CAN FD');wire(b,[(1823,280),(1848,280)]);wire(b,[(1835,280),(1835,302),(1848,302)]);join(adcu,b);join(rcl,b);join(rcr,b)
cams=[('AVM Front',317,'AVM Front'),('AVM Left',334,'AVM Left'),('AVM Right',351,'AVM Right'),('AVM Back',368,'AVM Rear'),('FNCamera',389,'FrontNarrowCamera'),('FWCamera',408,'FrontWideCamera'),('RearCamera',425,'RearCamera')]
for name,y,key in cams:
    n=node(name,1848,y,51,14,'adas',key=key)
    b=net('camera-'+n['id'],'LVDS','ADCU ↔ '+name+' · LVDS');wire(b,[(1823,y+7),(1848,y+7)]);join(adcu,b);join(n,b)
    decorations.append(f'<rect x="1817" y="{y}" width="6" height="14" fill="#8950b4" stroke="#57515f" stroke-width=".5"/>')

# Network and supply markers visible in the source.
for xx,yy in [(837,317),(1334,317),(1028,118),(1180,118),(1334,118),(466,118),(1317,703)]:term(xx,yy)
for n in [ivi,ml,mr]:n['nm']=True

# Original-style legend, deliberately kept inside the drawing.
legend=['<rect x="2" y="437" width="133" height="356" fill="white" stroke="#666" stroke-width=".8"/>',text(68,453,'图例',14,'middle')]
for i,d in enumerate(['energy','chassis','cockpit','body','thermal','adas']):
    yy=467+i*21
    legend.append(f'<rect x="15" y="{yy}" width="43" height="17" fill="{COLORS[d]}" stroke="#555" stroke-width=".6"/>')
    legend.append(text(36.5,yy+10,DOMAINS[d] if d!='thermal' else '动力 / 热管理',5.5,'middle'))
for i,k in enumerate(['LVDS','DSI','CANFD','CAN','LIN','Ethernet']):
    yy=603+i*13
    legend.append(f'<path d="M15 {yy}H42" stroke="{BC[k]}" stroke-width="1.2" {"stroke-dasharray='2 2'" if k=='LIN' else ""}/>')
    legend.append(text(51,yy+2,k if k!='DSI' else 'DSI Bus',5.4))
for yy,col,s in [(681,'#666','Termination 120 Ω'),(694,'#287ad5','Termination 66 Ω')]:
    legend.append(f'<rect x="24" y="{yy-3}" width="8" height="4" fill="{col}"/>');legend.append(text(51,yy,s,5.2))
legend.extend(['<rect x="15" y="705" width="25" height="12" fill="none" stroke="#555" stroke-dasharray="2 2"/>',text(51,713,'选配',5.6),'<rect x="15" y="725" width="25" height="12" fill="none" stroke="#555"/><path d="M15 725L40 737" stroke="#fa6b60" stroke-width=".8"/>',text(51,733,'该控制器在本车型不装',5),text(16,754,'NM',5),text(51,754,'Network Management',5),text(28,770,'*',7,'middle'),text(51,770,'KL30 常电供电',5),text(28,783,'#',6,'middle'),text(51,783,'KL15 受控供电',5)])

def node_svg(n):
    x,y,w,h=n['x'],n['y'],n['w'],n['h']
    desc=next((g['cn'] for g in glossary if g['abbr']==n['key']),n['note'] or '原图标识；缩写表未列出对应释义')
    a=[f'<g class="module" id="{n["id"]}" data-node="{n["id"]}" role="button" tabindex="0" aria-label="{esc(n["name"]+"，"+desc)}"><title>{esc(n["name"]+" · "+desc)}</title>',f'<rect class="node-box" x="{x}" y="{y}" width="{w}" height="{h}" fill="{COLORS[n["domain"]]}" stroke="#62666b" stroke-width=".8" {"stroke-dasharray='3 2'" if n['optional'] else ""}/>']
    raw=n['name']
    if h>100:
        ss=[raw]+(['—',n['sub']] if n['sub'] else [])
        for i,s in enumerate(ss):a.append(text(x+w/2,y+h/2+(i-(len(ss)-1)/2)*12,s+(n['marks'] if i==0 else ''),7.3 if n['domain']=='adas' else 6,'middle'))
    else:
        if len(raw)>13:
            split=raw.rfind('_') if '_' in raw else raw.rfind(' ')
            if 'Motor' in raw:split=raw.index(' ')
            ss=[raw[:split],raw[split+1:]] if split>0 else [raw]
        else:ss=[raw]
        if n['sub']:ss.append(n['sub'])
        for i,s in enumerate(ss):
            sz=min(5.9 if w>=50 else 5.2,(w-3)/max(len(s)*.55,1))
            if len(ss)>1:sz=min(sz,4.8)
            a.append(text(x+w/2,y+h/2+1.7+(i-(len(ss)-1)/2)*5.7,s+(n['marks'] if i==0 else ''),round(sz,2),'middle'))
    if n['nm']:
        ny=y+1 if h<80 else y+34
        a.append(f'<rect x="{x+2}" y="{ny}" width="11" height="3.3" fill="#f4f1db" stroke="#4c535c" stroke-width=".6"/>')
        a.append(text(x+7.5,ny+2.7,'NM',2.9,'middle'))
    if n['removed']:a.append(f'<path class="removed-mark" d="M{x} {y}L{x+w} {y+h}" stroke="#ee766b" stroke-width="1.1"/>')
    a.append('</g>')
    return ''.join(a)

svg=['<svg id="drawing" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1946 800" role="img" aria-labelledby="diagramTitle diagramDesc"><title id="diagramTitle">电子电气架构</title><desc id="diagramDesc">根据所附架构图重绘。包含 VCM、IVI、VIU_ML、VIU_MR、ADCU 及其网络和下挂节点。可点击模块查看中英文释义。</desc><style>text{font-family:Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif}.module{cursor:pointer;outline:none}.module:hover .node-box,.module:focus .node-box{stroke:#0b5fba;stroke-width:1.8}.module.selected .node-box{stroke:#075cbb;stroke-width:2.4}.module.found .node-box{stroke:#d97300;stroke-width:2}.wire{fill:none;stroke-width:1.15;stroke-linejoin:round}.wire.active{stroke-width:2.4}.wire.dim{opacity:.22}</style><rect width="1946" height="800" fill="white"/><rect x="2" y="7" width="1928" height="786" fill="none" stroke="#666" stroke-width=".9"/>']
for b,pts in lines:
    p='M'+' L'.join(f'{x},{y}' for x,y in pts)
    nn=nets[b]
    svg.append(f'<path class="wire" data-net="{b}" d="{p}" stroke="{BC[nn["kind"]]}" {"stroke-dasharray='2.5 2'" if nn['kind']=='LIN' else ""}><title>{esc(nn["title"])}</title></path>')
svg += [node_svg(n) for n in nodes]+decorations+annotations+legend+['</svg>']
hardware_svg,hardware_data=create_hardware()
b_system_svg,b_system_data=create_b_system()
software_html,software_data=render_software()
ota_html,ota_data=render_ota()
diag_html,diag_data=render_diagnostics()
audio_html,audio_data=render_audio()
widevine_html,widevine_data=render_widevine()
software_data["ota"]=ota_data
software_data["diagnostics"]=diag_data
software_data["audio"]=audio_data
software_data["widevine"]=widevine_data
data=dict(nodes=nodes,nets=nets,glossary=glossary,domains=DOMAINS,colors=COLORS,hardware=hardware_data,bSystem=b_system_data,software=software_data)
template=(ROOT/'template.html').read_text()
svg[0]=svg[0].replace('role="img"','role="group"').replace('<title id="diagramTitle">电子电气架构</title>','<title id="diagramTitle">A平台电子电器架构图</title>').replace('.wire{','.module.selected.found .node-box{stroke:#075cbb;stroke-width:2.4}.wire{')
template=template.replace('<!-- DRAWING -->',''.join(svg)).replace('<!-- HARDWARE_DRAWING -->',hardware_svg).replace('<!-- B_SYSTEM_DRAWING -->',b_system_svg).replace('<!-- SOFTWARE_CONTENT -->',software_html+ota_html+diag_html+audio_html+widevine_html).replace('/* SOFTWARE_STYLE */',(ROOT/'software_high_level.css').read_text()).replace('/* DIAGRAM_DATA */ null',json.dumps(data,ensure_ascii=False).replace('</',r'<\/'))
template=template.replace('/* APP_SCRIPT */',(ROOT/'app.js').read_text()).replace('/* SOFTWARE_SCRIPT */',(ROOT/'software_high_level.js').read_text())
(ROOT/'index.html').write_text(template)
(ROOT/'storage-partitions.html').write_text(render_storage())
(ROOT/'architecture.svg').write_text(''.join(svg))
(ROOT/'ivi-hardware.svg').write_text(hardware_svg)
(ROOT/'b-platform-system.svg').write_text(b_system_svg)
print(json.dumps(dict(nodes=len(nodes),nets=len(nets),segments=len(lines),b_system_nodes=len(b_system_data["nodes"]),glossary=len(glossary),html_bytes=len(template.encode())),ensure_ascii=False))
