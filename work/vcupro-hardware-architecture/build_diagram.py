"""Page-4 hardware reconstruction. Run only to rebuild this generated artifact."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from native_builder import Builder, cell

OUT = Path(__file__).resolve().parent
SOURCE = '/home/ethen/Documents/TechnologyDocuments/private/vcs/Arch/VCUpro--sysAD--overview (-S-N--A1--v1.4).pdf'
b = Builder(source=SOURCE + ' · page 4', purpose='VCUpro -N / -ROW hardware connectivity',
            unknowns=['Repeated connector references do not define a pinout',
                      'GNSS / game / roof configuration is TBD and mutually exclusive',
                      'FCC reserved status is visually ambiguous in the source',
                      'GYRO to GNSS signal type is not specified',
                      'TCP is named without a separate source wire'])
b.page('vcupro-hardware', 'VCUpro — Hardware Architecture',
       '-N / -ROW  ·  Source: system architecture overview v1.4, page 4  ·  Native editable components',
       3520, 4096)
C = b.tokens['signalColors']
M = b.tokens['colors']['muted']

def text(id, s, x, y, w, h=20, parent='1', size=13, bold=False, **kw):
    return b.text(id,s,x,y,w,h,parent,size,bold,**kw)

def card(id, kind, name, desc, x, y, w=296, parent='1', status='', **kw):
    return b.card(id,kind,name,desc,x,y,w,parent,status=status,**kw)

def frame(id, name, x,y,w,h,parent='dhu',kind='functional-group',sub=''):
    return b.container(id,name,x,y,w,h,parent,kind,subtitle=sub)

def edge(id, s, t, family='communication', label='', f=(1,.5), to=(0,.5), points=(), arrow=True, both=False, dash=False, pos=0, off=(0,-14)):
    return b.edge(id,s,t,family,label,from_=f,to=to,points=points,
                  arrow=arrow,both=both,dash=dash,label_pos=pos,label_offset=off)

def port(id, side, y, label, family='communication', processor='soc'):
    x,py,w,h=b.rects[processor]
    text(id,label,x+12 if side=='left' else x+w-184,y-9,172,18,processor,12,
         color=C[family],align='left' if side=='left' else 'right')
    return (0 if side=='left' else 1,(y-py)/h)

def soclink(id, other, y, name, family='communication', side='left', direction='in', endpoint=(1,.5), points=(), label='', both=False, dash=False, pos=0, off=(0,-14)):
    p=port(id+'-port',side,y,name,family)
    if direction=='in':
        return edge(id,other,'soc',family,label,endpoint,p,points,True,both,dash,pos,off)
    return edge(id,'soc',other,family,label,p,endpoint,points,True,both,dash,pos,off)

# Native sample + label entries; never substitute colored text for a line.
for i,(family,title) in enumerate([('video','Video'),('audio','Audio'),('communication','Communication'),('control','Discrete control'),('rf','RF')]):
    b.legend_entry('legend-'+family,title,40+i*232,120,220,family=family)
for id,title,x,w,typ,val in [
    ('single','Signal direction',1344,256,'direction','single'),
    ('both','Bidirectional',1632,240,'direction','bidirectional'),
    ('physical','Physical connection',1904,280,'direction','physical'),
    ('reserved','Reserved link',2216,256,'linestyle','dashed')]:
    b.legend_entry('legend-'+id,title,x,120,w,legend_type=typ,value=val)
text('legend-status','TBD = unresolved configuration',2504,120,944,24,size=13,color=M)
text('connector-convention','J identifiers on links are source connector references; repeated labels are not additional connector instances.',40,160,2500,24,size=14,color=M)

b.container('dhu','DHU',408,216,2328,3472,kind='physical-enclosure',subtitle='Physical system boundary; dashed areas below are functional groups, not additional boards')
text('external-left','EXTERNAL AUDIO / RF / VIDEO',56,248,320,24,size=14,bold=True,color=M)
text('external-right','EXTERNAL NETWORKS / I/O / DISPLAYS',2824,248,656,24,size=14,bold=True,color=M)

# QAM8255P is a module, not a second processor. Contents follow the source.
frame('qam','QAM8255P',1264,280,448,3368,kind='physical-enclosure',sub='Module contents shown in source')
card('soc','soc','SA8255P','Application SoC',1296,344,384,'qam',h=3040)
text('soc-left-heading','AUDIO / RF / VIDEO IN',1308,428,170,18,'soc',11,bold=True,color=M)
text('soc-right-heading','NETWORK / I/O / VIDEO OUT',1480,428,186,18,'soc',11,bold=True,color=M,align='right')
card('pmic','power','PMIC ×4','PMM8650',1320,3424,336,'qam')
card('dram','dram','LPDDR5','18 GB',1320,3528,336,'qam')
text('qam-contents','Power and memory interfaces are not expanded in the source.',1296,3616,392,16,'qam',11,color=M)

# Audio is arranged around its direct converters / A2B devices, with correct directions.
frame('audio','Audio interfaces',448,280,784,760,sub='Analog conversion and A2B links')
card('anc','mic','ANC microphones ×4','Analog inputs',56,416,312)
card('adc','adc','Audio ADC','PCM6240',856,416,312,'audio')
edge('anc-adc','anc','adc','audio','Analog · via J2')
soclink('adc-soc','adc',456,'LPI-TDM2','audio')
card('speakers4','speaker','Audio outputs · 4 ch','External audio outputs',56,528,312)
card('tas6424','amp','Audio output IC','TAS6424 · 4 channels',856,528,312,'audio')
soclink('soc-tas6424','tas6424',568,'LPI-TDM2','audio',direction='out')
edge('tas6424-outs','tas6424','speakers4','audio','Via J2',f=(0,.5),to=(1,.5))
card('speakers2','speaker','Audio outputs · 2 ch','AVAS 10 W / VES 25 W',56,640,312)
card('tas6422','amp','Audio output IC','TAS6422 · 2 channels',856,640,312,'audio')
soclink('soc-tas6422','tas6422',680,'LPI-TDM2','audio',direction='out')
edge('tas6422-outs','tas6422','speakers2','audio','Via J2',f=(0,.5),to=(1,.5))
card('exta2b1','amp','External AMP / MIC','A2B peripheral equipment',56,752,312)
card('a2b1','a2b','A2B transceiver 1','AD2428',856,752,312,'audio')
edge('a2b1-external','exta2b1','a2b1','audio','A2B · via J3',both=True)
soclink('a2b1-i2s','a2b1',776,'I2S2','audio',endpoint=(1,.3))
soclink('a2b1-tdm','a2b1',808,'LPI-TDM0','audio',endpoint=(1,.7),both=True)
card('exta2b2','amp','External AMP / MIC','Reserved',56,864,312,status='Reserved')
card('a2b2','a2b','A2B transceiver 2','AD2428 · Reserved',856,864,312,'audio',status='Reserved')
edge('a2b2-external','exta2b2','a2b2','audio','A2B · via J3',both=True,dash=True)
soclink('a2b2-tdm','a2b2',904,'TDM1','audio',both=True,dash=True)
text('audio-source-note','TAS devices retain the source part numbers; no amplifier-to-speaker wiring is expanded.',472,984,736,20,'audio',12,color=M)

# Two mutually exclusive tuner BOMs, kept inside the identified sub-board.
frame('radio','Tuner sub-board',448,1072,784,344,kind='board',sub='Alternative BOMs: ROW = Merlin + Mercury; N = SXM + Dirana5')
card('radio-rf','antenna','FM / AM / CDR','Radio input · via J1',56,1152,312)
card('merlin','rfmodule','Merlin','TEF7100 · ROW',480,1152,264,'radio')
card('mercury','dsp','Mercury','SAF4000EL · ROW',920,1152,280,'radio')
card('sxm','rfmodule','SXM','N configuration',480,1272,264,'radio')
card('dirana5','dsp','Dirana5','SAF7771EL · N',920,1272,280,'radio')
edge('radio-j1','radio-rf','radio','rf','Via J1',to=(0,120/344),arrow=False)
edge('merlin-mercury','merlin','mercury','audio','ROW',arrow=True)
edge('sxm-dirana','sxm','dirana5','audio','N',arrow=True)
soclink('mercury-soc','mercury',1192,'LPI-TDM4 · ROW','audio')
soclink('dirana-soc','dirana5',1312,'LPI-TDM4 · N','audio')
text('tuner-alternatives','Mercury / Dirana5: pin-to-pin alternatives. J1 internal RF mapping is not expanded.',472,1376,736,20,'radio',12,color=M)

frame('wireless','Wi-Fi / Bluetooth',448,1448,784,392,sub='On-board and external antenna paths')
card('external-ant','antenna','External antenna','Via J8',56,1536,312)
card('wifi-board-ant','antenna','On-board antenna','BT / Wi-Fi',480,1520,280,'wireless')
card('wifi','rfmodule','BT + Wi-Fi module','AF66T',856,1536,312,'wireless')
card('j8','connector','J8','',496,1624,80,'wireless')
edge('ant-j8','external-ant','j8','rf','',f=(1,.5),to=(0,.5),points=[(400,1576),(400,1648)],arrow=False)
edge('j8-wifi','j8','wifi','rf','External RF',f=(1,.5),to=(0,.7),points=[(808,1648),(808,1592)],arrow=False,pos=-.45)
edge('board-ant-wifi','wifi-board-ant','wifi','rf','',f=(1,.45),to=(0,.25),arrow=False)
soclink('wifi-tdm','wifi',1556,'LPI-TDM3','audio',direction='out',endpoint=(1,.25))
soclink('wifi-uart','wifi',1576,'UART','communication',endpoint=(1,.5),both=True)
soclink('wifi-pcie','wifi',1596,'PCIe','communication',endpoint=(1,.75),both=True)
card('bt-board-ant','antenna','On-board antenna','Rear-row Bluetooth',480,1720,280,'wireless')
card('bt2','rfmodule','Bluetooth module 2','AH20C · Rear row',856,1720,312,'wireless')
edge('ant-bt2','bt-board-ant','bt2','rf',arrow=False)
soclink('bt2-uart','bt2',1760,'UART','communication',both=True)

# Native camera / display pictograms are used, not photographs or bitmap blocks.
frame('video-in','Video ingress',448,1872,784,1256,sub='Independent streams; connector references are not pin assignments')
frame('game-board','Game input sub-board · TBD',480,1936,720,184,'video-in',kind='board',sub='Mutually exclusive with GNSS')
card('game','ic','Game source','Switch game 1',56,1904,312)
card('dp-hub','serdes','DP hub 1','MAX96745 / MAX96753',56,2024,312)
edge('game-hub','game','dp-hub','video','',f=(.5,1),to=(.5,0))
card('max96756','serdes','Deserializer','MAX96756 · TBD',856,2016,312,'game-board')
edge('hub-max96756','dp-hub','max96756','video','Via J11',f=(1,.5),to=(0,.5),points=[(760,2064),(760,2056)])
soclink('game-hsi2s','max96756',2040,'HS-I2S1','audio',endpoint=(1,.3))
soclink('game-csi','max96756',2072,'CSI1','video',endpoint=(1,.7))

frame('trailer-board','Camera sub-board',480,2152,720,456,'video-in',kind='board',sub='Reserved source inputs')
for i,(id,name) in enumerate([('rear-trailer','Rear trailer camera'),('aux-trailer','Aux trailer camera'),('ar-camera','AR camera'),('night-camera','Night-vision camera')]):
    yy=2176+i*104
    card(id,'camera',name,'Reserved',56,yy,312,status='Reserved')
card('j10','connector','J10','',544,2368,88,'trailer-board')
card('ub9702-trailer','serdes','Deserializer','DS90UB9702 · FPD-Link IV',856,2352,312,'trailer-board')
for i,id in enumerate(['rear-trailer','aux-trailer','ar-camera','night-camera']):
    yy=2216+i*104; jp=(6+12*i)/48; cp=(22+12*i)/80
    # Per-channel routes remain distinct and ordered, without a junction.
    lane=[472,448,448,472][i]
    edge(id+'-j10',id,'j10','video','',to=(0,jp),points=[(lane,yy),(lane,2374+12*i)],dash=True)
    edge('j10-deser-'+str(i),'j10','ub9702-trailer','video','',f=(1,jp),to=(0,cp),dash=True)
soclink('trailer-csi','ub9702-trailer',2392,'CSI2','video')
text('trailer-note','HS-I2S2 is labeled on the source, but no connecting wire is drawn.',504,2544,672,20,'trailer-board',12,color=M)

card('cargo','camera','Cargo-bed camera','Future PoC accommodation',56,2656,312)
card('interior','camera','Interior camera','Future PoC accommodation',56,2776,312)
card('j7','connector','J7','',544,2728,80,'video-in')
card('ub9722','serdes','Deserializer','DS90UB9722',856,2712,312,'video-in')
edge('cargo-j7','cargo','j7','video','',to=(0,.25),points=[(440,2696),(440,2740)])
edge('interior-j7','interior','j7','video','',to=(0,.75),points=[(464,2816),(464,2764)])
edge('j7-deser1','j7','ub9722','video','',f=(1,.25),to=(0,.35))
edge('j7-deser2','j7','ub9722','video','',f=(1,.75),to=(0,.65))
soclink('interior-csi','ub9722',2752,'CSI3','video')

frame('avm-board','AVM input sub-board',480,2872,720,208,'video-in',kind='board',sub='Four video inputs from ADM; not PoC')
card('adm','ic','ADM','AVM: left / front / right / rear',56,2960,312)
card('j9','connector','J9','',544,2976,80,'avm-board')
card('ub9702-avm','serdes','Deserializer','DS90UB9702 · FPD-Link IV',856,2960,312,'avm-board')
for i,side in enumerate(['Left','Front','Right','Rear']):
    cp=(22+12*i)/80; jp=(6+12*i)/48
    edge('adm-j9-'+str(i),'adm','j9','video','',f=(1,cp),to=(0,jp))
    b.objects['adm-j9-'+str(i)].set('channel',side)
    edge('j9-deser-'+str(i),'j9','ub9702-avm','video','',f=(1,jp),to=(0,cp))
soclink('avm-csi','ub9702-avm',3000,'CSI0','video')

# Ethernet is a triangle, not a cascaded single chain.
frame('ethernet','Ethernet',1752,280,944,360,sub='SoC ↔ PHY and SoC ↔ Switch; PHY ↔ Switch via RGMII')
card('phy','phy','Ethernet PHY','88Q2122',2048,416,296,'ethernet')
card('switch','ic','Ethernet switch','88Q5054',2048,536,296,'ethernet')
soclink('soc-phy-hs','phy',456,'HSGMII_0 + MDIO','communication',side='right',direction='out',endpoint=(0,.5),both=True)
soclink('soc-switch-hs','switch',576,'HSGMII_1 + MDIO','communication',side='right',direction='out',endpoint=(0,.5),both=True)
edge('phy-switch','phy','switch','communication','RGMII',f=(.5,1),to=(.5,0),off=(52,0),both=True)
card('vxm','ic','VXM','1000BASE-T1 endpoint',2832,416,312)
text('tcp-note','TCP is also named in the source; no separate link is drawn.',2832,504,632,18,size=12,color=M)
card('cgm','ic','CGM','100BASE-T1 endpoint',2832,568,312)
card('rsi','ic','RSI / PDR','100BASE-T1 endpoint',2832,680,312)
edge('phy-vxm','phy','vxm','communication','1000BASE-T1 · via J3',both=True)
edge('switch-cgm','switch','cgm','communication','100BASE-T1 · via J3',f=(1,.3),to=(0,.5),points=[(2784,560),(2784,608)],both=True,pos=-.2)
edge('switch-rsi','switch','rsi','communication','100BASE-T1 · via J3',f=(1,.7),to=(0,.5),points=[(2752,592),(2752,720)],both=True,pos=-.4,off=(0,14))

# Vehicle MCU is independent of the application processor, but within DHU.
frame('vehicle','Vehicle control & sensing',1752,672,944,1136,sub='RH850 interfaces; unspecified external endpoints are not invented')
card('mcu','mcu','RH850 F1KH-D8','Vehicle MCU · 324 pin',1792,744,272,'vehicle',h=728)
soclink('soc-mcu-spi2','mcu',872,'SPI ×2','communication',side='right',direction='out',endpoint=(0,(872-744)/728),both=True)
soclink('soc-mcu-sail','mcu',912,'SAIL · SPI','communication',side='right',direction='out',endpoint=(0,(912-744)/728),both=True)
port('mcu-spi2','left',872,'SPI ×2','communication','mcu')
port('mcu-spi','left',912,'SPI','communication','mcu')
card('keys','ic','ICC keys ×2','Interrupt inputs',2832,816,312)
mp=port('mcu-irq','right',856,'GPIO (INT) ×2','control','mcu')
edge('keys-mcu','keys','mcu','control','×2 · via J2',f=(0,.5),to=mp)

for id,name,part,yy,portname,outid,outname,outdesc,res in [
    ('can1','CAN FD interface','1145',928,'CAN1','gateway','CAN gateway','Via J2',False),
    ('can2','CAN FD interface','1044',1032,'CAN2','tcan','Tcan','Reserved',True),
    ('lin1','LIN interface 1','LIN1',1136,'LIN1','swc','SWC','Reserved',True),
    ('lin2','LIN interface 2','LIN2 · Added',1240,'LIN2',None,None,None,False),
    ('lin3','LIN interface 3','LIN3',1344,'LIN3','lin3-end','Reserved endpoint','No named device',True),
]:
    card(id,'can',name,part,2336,yy,280,'vehicle')
    p=port('mcu-port-'+id,'right',yy+40,portname,'communication','mcu')
    edge('mcu-'+id,'mcu',id,'communication','',f=p,both=True)
    if outid:
        card(outid,'ic',outname,outdesc,2832,yy,312,status='Reserved' if res else '')
        edge(id+'-external',id,outid,'communication','Via J2',both=True,dash=res)
    else:
        text('lin2-unknown','Added in source; endpoint not specified.',2832,yy+28,620,24,size=13,color=M)

for i,(id,kind,name,desc,pname,family) in enumerate([
    ('power-ctl','power','Power control','GPIO control','GPIO','control'),
    ('temp','ic','Temperature sensing','Analog measurement','ADC','control'),
    ('fan','ic','Fan control','GPIO control','GPIO','control'),
]):
    xx=[1792,2112,2432][i]
    card(id,kind,name,desc,xx,1544,240,'vehicle')
    fx=[.2,.5,.8][i]; cy=[1504,1492,1480][i]
    edge('mcu-'+id,'mcu',id,family,pname,f=(fx,1),to=(.5,0),points=[(1792+272*fx,cy),(xx+120,cy)],off=(0,14) if id=='temp' else (0,-12),both=True)

card('gyro','ic','GYRO','SMI230',2112,1696,296,'vehicle')
mp=port('mcu-gyro-port','left',1432,'SPI','communication','mcu')
edge('mcu-gyro','mcu','gyro','communication','SPI',f=mp,to=(0,.5),points=[(1772,1432),(1772,1736)],pos=.6,both=True)
text('uss-note','USS ×12 / J13 is not connected here: its Elmos ×3 bridge is marked removed in v1.4.',1776,1776,896,20,'vehicle',12,color=M)

# Storage / authentication and conditional GNSS.
frame('utilities','Storage, authentication & positioning',1752,1840,944,488)
card('nor','flash','NOR flash','Capacity not specified',1808,1904,280,'utilities')
card('ufs','flash','UFS storage','256 GB',1808,2032,280,'utilities')
card('auth','ic','Apple authentication','MFI343500177',1808,2160,280,'utilities')
soclink('soc-nor','nor',1944,'SAIL · SPI',side='right',direction='out',endpoint=(0,.5),both=True)
soclink('soc-ufs','ufs',2072,'UFS',side='right',direction='out',endpoint=(0,.5),both=True)
soclink('soc-auth','auth',2200,'I2C',side='right',direction='out',endpoint=(0,.5),both=True)
frame('gnss-board','GNSS sub-board · TBD',2184,1888,464,216,'utilities',kind='board',sub='Added; exclusive with Game / Roof')
card('gnss','rfmodule','GNSS receiver','uBlox M9 · Added / TBD',2272,1976,336,'gnss-board')
soclink('soc-gnss','gnss',2000,'UART',side='right',direction='out',endpoint=(0,.3),both=True,
        points=[(2160,2000)],label='UART',off=(0,14))
edge('gyro-gnss','gyro','gnss','control','Signal unspecified',f=(1,.5),to=(1,.7),
     points=[(2680,1736),(2680,2032)],pos=.45,off=(72,0))
text('gnss-j1','J1 is referenced for GNSS in the source.',2208,2076,416,18,'gnss-board',12,color=M)

# USB interface endpoints, not invented intermediate USB controller chips.
frame('usb','USB ports',1752,2352,944,240)
card('j6','connector','J6 (USB0 / USB1)','',2240,2424,160,'usb')
card('j14','connector','J14 (USB2)','',2480,2512,128,'usb')
soclink('usb0','j6',2400,'USB0 · USB 3.0',side='right',direction='out',endpoint=(0,.25),both=True,
        points=[(2160,2400),(2160,2436)],label='USB 3.0',pos=-.2)
soclink('usb1','j6',2460,'USB1 · USB 2.0',side='right',direction='out',endpoint=(0,.75),both=True,
        label='USB 2.0',pos=-.2)
soclink('usb2','j14',2536,'USB2 · USB 2.0',side='right',direction='out',endpoint=(0,.5),both=True,
        label='USB 2.0',pos=-.2)
text('usb0-use','USB0 / J6: SW update / DVR / Qfile / adb',2832,2400,624,24,size=14)
text('usb1-use','USB1 / J6: QNX debug',2832,2460,624,24,size=14)
text('usb2-use','USB2 / J14: CarPlay / KTV · TBD',2832,2520,624,24,size=14)
text('usb-form-note','Housing types not inferred from USB version.',1776,2564,896,18,'usb',12,color=M)

# Output groups express source-defined daisy-chain groups, without inventing
# the cable order or panel-to-panel internal wiring.
frame('video-out','Display serialization',1752,2592,944,976,sub='Output group membership follows the source; internal cable order is not specified')

def output_group(id,name,y,h=144,sub=''):
    return frame(id,name,2800,y,680,h,'1',sub=sub)

card('ub981','serdes','Display serializer','DS90UB981',2024,2664,312,'video-out')
soclink('dsi0','ub981',2688,'DSI0 · 4 lanes','video',side='right',direction='out',endpoint=(0,.3))
soclink('dsi1','ub981',2720,'DSI1 · 4 lanes','video',side='right',direction='out',endpoint=(0,.7))
output_group('display1','Daisy chain 1',2616)
card('ipd','display','IPD · Cluster','1920 × 720',2824,2672,288,'display1')
card('hud1','hud','HUD','800 × 480',3144,2672,304,'display1')
edge('display1-link','ub981','display1','video','Dual-link STP · via J4',to=(0,.61))

card('ub983-hud','serdes','Display serializer','DS90UB983',2024,2832,312,'video-out')
soclink('edp1','ub983-hud',2872,'eDP1 · 4 lanes','video',side='right',direction='out',endpoint=(0,.5))
output_group('display2','Daisy chain 2',2784)
card('hud2','hud','HUD','2048 × 2048',2984,2840,304,'display2')
edge('display2-link','ub983-hud','display2','video','Dual-link STP · via J5',to=(0,.61))

frame('roof-board','Roof / RSD sub-board · TBD',1944,2968,704,184,'video-out',kind='board',sub='Mutually exclusive with GNSS')
card('max96781','serdes','Display serializer','MAX96781 · TBD',2024,3048,312,'roof-board')
soclink('edp0','max96781',3088,'eDP0 · 4 lanes','video',side='right',direction='out',endpoint=(0,.5))
output_group('display-roof','Roof or rear-seat displays',2960,240,sub='Alternative output configurations')
card('roof','display','Roof display','3840 × 1648',2824,3024,288,'display-roof')
card('rsd','display','RSD · Left + Right','1920 × 1080 each',3144,3112,304,'display-roof')
text('roof-or','OR',3152,3056,48,24,'display-roof',14,bold=True,color=M)
edge('roof-link','max96781','display-roof','video','Dual-link coax · via J11',to=(0,.55))

card('ub983-fcc','serdes','Display serializer','DS90UB983',2024,3240,312,'video-out')
soclink('edp2','ub983-fcc',3280,'eDP2 · 4 lanes','video',side='right',direction='out',endpoint=(0,.5))
output_group('display3','Daisy chain 3',3240,152)
card('fcc','display','FCC · Front control','1350 × 810 · Status unclear',2824,3304,288,'display3')
card('rcc','display','RCC · Rear control','1350 × 810',3144,3304,304,'display3')
edge('display3-link','ub983-fcc','display3','video','Dual-link STP · via J5',to=(0,.7),points=[(2696,3280),(2696,3346.4)])

card('ub983-ics','serdes','Display serializer','DS90UB983',2024,3408,312,'video-out')
soclink('edp3','ub983-ics',3352,'eDP3 · 4 lanes','video',side='right',direction='out',endpoint=(0,.5),
        points=[(1864,3352),(1864,3448)])
output_group('display4','Daisy chain 4 · Alternative panel configurations',3432,248)
card('ics','display','ICS · Center','3000 × 1300',2824,3488,288,'display4')
card('fpd','display','FPD · Passenger','3000 × 1300',3144,3488,304,'display4')
text('ics-vcd-or','OR',2936,3600,48,20,'display4',13,bold=True,color=M)
card('vcd','display','VCD · ICS + IPD','8960 × 1320',3000,3584,336,'display4')
edge('display4-link','ub983-ics','display4','video','Dual-link STP · via J4',to=(0,.39),points=[(2664,3448),(2664,3528.72)])

# Source changes and uncertainties stay visible but are not wired into active paths.
frame('notes','Configuration & source constraints',448,3160,784,472,sub='Read these with the conditional and reserved paths above')
for i,s in enumerate([
    'GNSS, Game input and Roof/RSD are scenario-dependent; GNSS is exclusive with the other two.',
    'ROW radio uses Merlin + Mercury. N radio uses SXM + Dirana5.',
    'Reserved: A2B 2; Tcan; SWC; LIN3 endpoint; J10 camera inputs.',
    'Removed: VR mic ×4 + Mono ×1, J12, PCM6260 ADC; third AH20C BT module.',
    'Removed: Elmos ×3. The remaining USS ×12 / J13 branch is not treated as operational.',
    'TBD: GNSS placement/configuration; Game and Roof scenarios; USB2 CarPlay / KTV.',
    'FCC reservation status is ambiguous; TCP has no separate drawn link.',
    'The unlabeled GYRO → GNSS connection is retained without inventing its protocol.',
    'Connector form factors and pin assignments are not reconstructed from thumbnails.',
]):
    text('note-'+str(i),s,472,3232+i*40,736,34,'notes',13,color=M,whiteSpace='wrap')

text('reading-note','How to read',40,3744,280,26,size=18,bold=True)
text('reading-1','Neutral cards identify hardware. Colored links identify signal families. Dashed containers are functional groups; solid named sub-boards retain source physical grouping.',40,3784,3376,24,size=14,color=M)
text('reading-2','Panel pairs are grouped as in the source. Their internal daisy-chain ordering is not expanded. Four camera channels remain four independent edges, never a shared junction.',40,3824,3376,24,size=14,color=M)
text('reading-3','Only explicit direction is preserved; bidirectional labels indicate source-shown two-way interfaces. Unknown protocols and removed paths are not filled in by assumption.',40,3864,3376,24,size=14,color=M)
text('source-line','Source: VCUpro--sysAD--overview (-S-N--A1--v1.4).pdf · Page 4 · -N / -ROW',40,3936,3376,24,size=14)

# Metadata makes the reconstructed source traceable without publishing the PDF.
b.doc.set('modified','2026-10-13')
b.save(OUT/'vcupro-system-architecture.drawio')
(OUT/'geometry.json').write_text(json.dumps({k:v for k,v in b.rects.items() if k in b.objects and (b.objects[k].get('layoutClass') or b.objects[k].get('kind') in ['physical-enclosure','board','functional-group'])},indent=2))
print(OUT/'vcupro-system-architecture.drawio')
