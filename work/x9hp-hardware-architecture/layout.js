// Hardware connection view: confirmed board boundaries, no inferred OS or VM deployment.
const sourceImage='source-reference.png';
const p=begin('x9hp-hardware','X9HP Cockpit Hardware Architecture','Compute Board  /  Interface & Audio Board',2850);
const objects=new Map([['1',{id:'1',x:0,y:0,w:3100,h:2850,parent:null}]]);
const relations=[];
function local(parent,x,y){const a=objects.get(parent);return [x-a.x,y-a.y];}
function register(id,x,y,w,h,parent,extra={}){objects.set(id,{id,x,y,w,h,parent,...extra});}
function region(id,title,x,y,w,h,parent='1',kind='board'){
  const [a,b]=local(parent,x,y);
  frame(id,title,a,b,w,h,parent,{fillColor:kind==='enclosure'?'#FFFFFF':'#FAFBFC',strokeColor:kind==='enclosure'?'#AAB7C4':C.border,strokeWidth:kind==='enclosure'?1.6:1.3},kind);
  register(id,x,y,w,h,parent,{kind,title,evidence:kind==='board'?'user-board-confirmation':'source-image'});
}
function part(id,type,title,subtitle,x,y,w,h,parent='1',opts={}){
  const [a,b]=local(parent,x,y),{reserved=false,large=false,vertical=false,...style}=opts;
  box(id,'',a,b,w,h,parent,{container:1,recursiveResize:0,collapsible:0,fillColor:large?'#EDF2F6':'#FFFFFF',strokeColor:large?'#8599AD':C.border,...(reserved?{dashed:1,dashPattern:'6 5',fillColor:'#F5F6F7'}:{}),...style},{entityType:'hardware',canonicalName:title,symbolType:type,status:reserved?'reserved':'included',evidence:'source-image'});
  register(id,x,y,w,h,parent,{kind:'component',type,title,subtitle,status:reserved?'reserved':'included',evidence:'source-image'});
  if(large){
    glyph(id,type,w/2,h/2-49);
    txt(id+'-name',title,12,h/2-4,w-24,36,id,24,true,C.ink,'center');
    txt(id+'-subtitle',subtitle,12,h/2+36,w-24,38,id,16,false,C.muted,'center');
  }else if(vertical){
    glyph(id,type,w/2,34);
    txt(id+'-name',title,8,70,w-16,24,id,16,true,C.ink,'center');
    txt(id+'-subtitle',subtitle,8,98,w-16,h-102,id,12,false,C.muted,'center');
  }else{
    glyph(id,type,49,h/2);
    txt(id+'-name',title,101,15,w-111,42,id,16,true,C.ink,'left');
    txt(id+'-subtitle',subtitle,101,58,w-111,h-66,id,12,false,C.muted,'left');
  }
}
function connector(id,title,type,x,y,w=150,h=116,parent='compute',subtitle=''){
  part(id,type,title,subtitle,x,y,w,h,parent,{vertical:true});
}
function connectorStrip(id,title,subtitle,x,y,w,h,parent){
  const [a,b]=local(parent,x,y);
  box(id,'',a,b,w,h,parent,{container:1,recursiveResize:0,collapsible:0,fillColor:'#EDF2F6',strokeColor:'#91A2B3',strokeWidth:1.5},{entityType:'hardware',canonicalName:title,symbolType:'connector',evidence:'source-image'});
  register(id,x,y,w,h,parent,{kind:'connector',title,subtitle,evidence:'source-image'});
  glyph(id,'connector',66,h/2);
  txt(id+'-name',title,125,22,190,30,id,18,true);
  txt(id+'-subtitle',subtitle,125,56,190,26,id,12,false,C.muted);
}
function terminal(id,title,cx,y,w,parent,reserved=false){
  const x=cx-w/2,[a,b]=local(parent,x,y);
  box(id,title,a,b,w,48,parent,{fontSize:13,align:'center',fillColor:'#FFFFFF',arcSize:8,...(reserved?{dashed:1,dashPattern:'6 5',fontColor:C.muted}:{})},{kind:'connector-port',evidence:'source-image'});
  register(id,x,y,w,48,parent,{kind:'port',title,reserved,evidence:'source-image'});
}
function ancestor(id){const chain=[];let n=objects.get(id);while(n){chain.push(n.id);n=objects.get(n.parent);}return chain;}
function anchor(id,spec){
  const n=objects.get(id),[side,z]=spec;
  if(side==='L'||side==='R'){const y=z??n.y+n.h/2;return {p:[side==='L'?n.x:n.x+n.w,y],uv:[side==='L'?0:1,(y-n.y)/n.h]};}
  const x=z??n.x+n.w/2;return {p:[x,side==='T'?n.y:n.y+n.h],uv:[(x-n.x)/n.w,side==='T'?0:1]};
}
function link(id,from,to,family,options={}){
  const {start=['R'],end=['L'],via=[],label='',labelAt=null,both=false,arrow=true,reserved=false}=options;
  const aa=anchor(from,start),bb=anchor(to,end),chain=ancestor(to);
  const parent=ancestor(from).slice(1).find(k=>chain.includes(k))??'1';
  const origin=objects.get(parent),route=[aa.p,...via,bb.p];
  let pos=0,offset=[0,-15];
  if(labelAt){
    const lengths=route.slice(1).map((b,i)=>Math.hypot(b[0]-route[i][0],b[1]-route[i][1]));
    const total=lengths.reduce((s,n)=>s+n,0);let prior=0,best=null;
    lengths.forEach((len,i)=>{const a=route[i],b=route[i+1];const t=len?Math.max(0,Math.min(1,((labelAt[0]-a[0])*(b[0]-a[0])+(labelAt[1]-a[1])*(b[1]-a[1]))/(len*len))):0;const q=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])],d=Math.hypot(labelAt[0]-q[0],labelAt[1]-q[1]);if(!best||d<best.d)best={d,along:prior+t*len,q};prior+=len;});
    pos=total?2*best.along/total-1:0;offset=[labelAt[0]-best.q[0],labelAt[1]-best.q[1]];
  }
  edge(id,from,to,parent,C[family],{from:aa.uv,to:bb.uv,points:via.map(([x,y])=>[x-origin.x,y-origin.y]),label,labelOffset:offset,position:pos,both,arrow,dash:reserved,width:['video','audio'].includes(family)?2.6:1.8});
  relations.push({id,from,to,parent,family,label,both,arrow,reserved,route,source:'source-image'});
}

// Legend: neutral device fills, signal-family edge colors, and explicit reservation state.
const legend=[['Video','video'],['Audio','audio'],['Communication','comm'],['Discrete control','control'],['Power','power'],['RF','rf']];
legend.forEach(([name,fam],i)=>{
  const x=40+i*290;line('1',x,131,x+54,131,C[fam],fam==='video'||fam==='audio'?2.6:1.8);
  txt('legend-'+fam,name,x+68,118,208,26,'1',14,false,C.muted);
});
box('legend-reserved','Reserved',1820,114,128,30,'1',{dashed:1,dashPattern:'6 5',fontSize:13,align:'center',fillColor:'#F5F6F7'});
txt('legend-arrows','Arrows: primary signal direction',1990,116,450,28,'1',14,false,C.muted);

region('ecu','Cockpit ECU',410,188,2200,2424,'1','enclosure');
region('compute','Compute Board',440,260,2140,1050,'ecu');
region('interface','Interface & Audio Board',440,1510,2140,1080,'ecu');

// Compute board support devices and radio interfaces.
part('bt-ant','antenna','BT Antenna','',40,290,260,116,'1');
part('wifi-ant','antenna','Wi-Fi Antenna','2.4 / 5 GHz',40,430,260,116,'1');
part('wifi','rfmodule','NF3205PQ','Wi-Fi / Bluetooth · nFore',580,330,300,116,'compute');
part('emmc','flash','eMMC · 64 GB','MTFC64GAZAQHD-AAT',945,330,290,116,'compute');
part('dram','dram','LPDDR · 8 GB','MT53E2G32D4DT-046 AAT',1285,330,340,116,'compute');
part('mfi','ic','Apple MFi','mfi343s00177',1720,330,270,116,'compute');
part('soc','soc','X9HP','Cockpit SoC',1120,540,340,610,'compute',{large:true});
link('bt-feed','bt-ant','wifi','rf',{start:['R',348],end:['L',360],via:[[500,348],[500,360]],arrow:false});
link('wifi-feed','wifi-ant','wifi','rf',{start:['R',488],end:['L',412],via:[[520,488],[520,412]],arrow:false});
link('wifi-control','wifi','soc','comm',{start:['B',850],end:['L',567],via:[[850,470],[1040,470],[1040,567]],both:true,label:'SDIO / UART',labelAt:[920,454]});
link('wifi-audio','wifi','soc','audio',{start:['B',800],end:['L',598],via:[[800,500],[1015,500],[1015,598]],both:true,label:'I2S',labelAt:[930,485]});
link('emmc-bus','emmc','soc','comm',{start:['B',1090],end:['T',1200],via:[[1090,486],[1200,486]],both:true,label:'SDIO1',labelAt:[1150,470]});
link('dram-bus','dram','soc','comm',{start:['B',1370],end:['T',1370],both:true,label:'D / A',labelAt:[1400,491]});
link('mfi-link','mfi','soc','comm',{start:['B',1855],end:['T',1425],via:[[1855,494],[1425,494]],both:true});

// Camera chains: connectors follow the actual receiving deserializer.
part('avm','camera','AVM Cameras ×4','360° / 540° surround view',40,600,285,132,'1');
connector('j11','J11','coax-connector',455,616,150,116,'compute','FAKRA ×4');
part('des-avm','serdes','MAX9286','GMSL deserializer · 4 inputs',680,608,220,132,'compute');
link('avm-j11','avm','j11','video',{start:['R',666],end:['L',674],via:[[380,666],[380,674]]});
link('j11-des','j11','des-avm','video',{label:'GMSL ×4',labelAt:[642,655]});
link('avm-csi','des-avm','soc','video',{end:['L',674],label:'CSI-2',labelAt:[1010,656]});

const cameras=[['apa','APA Camera',814],['dms','DMS Camera',952],['oms','OMS Camera',1090],['dvr','DVR Camera',1228]];
part('des-cabin','serdes','MAX96722','GMSL deserializer<br>4 camera inputs',680,760,220,502,'compute',{large:true});
cameras.forEach(([id,title,cy])=>{
  part(id,'camera',title,'',40,cy-55,285,110,'1');
  connector('conn-'+id,'Coax','coax-connector',455,cy-58,150,116,'compute','Connector');
  link(id+'-coax',id,'conn-'+id,'video');
  link(id+'-gmsl','conn-'+id,'des-cabin','video',{end:['L',cy],label:id==='apa'?'GMSL':'',labelAt:id==='apa'?[642,796]:null});
});
link('cabin-csi','des-cabin','soc','video',{end:['L',1011],label:'CSI-2',labelAt:[1010,993]});

// Display chains retain the two independent links and actual connector IDs.
part('ser-cluster','serdes','DS90UB947','Serializer · 2 lanes',1740,575,310,132,'compute');
part('ser-center','serdes','DS90UB947','Serializer · 2 lanes',1740,795,310,132,'compute');
connector('j8','J8','shielded-connector',2400,583,150,116,'compute','Display connector');
connector('j9','J9','shielded-connector',2400,803,150,116,'compute','Display connector');
part('cluster','display','Cluster Display','1920 × 384 @ 60 Hz',2730,575,310,132,'1');
part('center','display','Center Display','1920 × 1080 @ 60 Hz',2730,795,310,132,'1');
link('soc-cluster','soc','ser-cluster','video',{start:['R',641],label:'LVDS12 · 2.62 Gb/s',labelAt:[1600,623]});
link('soc-center','soc','ser-center','video',{start:['R',861],label:'LVDS34 · 3.9 Gb/s',labelAt:[1600,843]});
link('cluster-fpd','ser-cluster','j8','video',{label:'FPD-Link · 2 lanes · <3 Gb/s/lane',labelAt:[2225,623]});
link('center-fpd','ser-center','j9','video',{label:'FPD-Link · 2 lanes · <3 Gb/s/lane',labelAt:[2225,843]});
link('j8-panel','j8','cluster','video');link('j9-panel','j9','center','video');

part('pmic','power','LP87565VRNFRQ1','PMIC',1740,990,300,120,'compute');
link('soc-pmic','soc','pmic','comm',{start:['R',1050],both:true,label:'I2C',labelAt:[1600,1034]});
part('usb-charger','power','USB Charger','CDP · 5 V / 1.5 A',2020,1160,285,118,'compute');
connector('j15','J15','connector',2400,1160,150,118,'compute','Media USB');
part('usb-media','ic','Media / USB DVR','USB 2.0 host port',2730,1160,310,118,'1');
part('vbat-12','power','VBAT','12 V',2110,1010,220,116,'compute');
link('soc-media-usb','soc','usb-charger','comm',{start:['R',1120],end:['L',1219],via:[[1660,1120],[1660,1219]],both:true,label:'USB 2.0 · D+ / D−',labelAt:[1780,1201]});
link('vbat-charger','vbat-12','usb-charger','power',{start:['B',2220],end:['T',2220]});
link('charger-j15','usb-charger','j15','comm',{both:true});
link('j15-media','j15','usb-media','comm',{both:true});

// One physical board-to-board connector with separate signal groups.
connectorStrip('b2b','B2B Connector','SnP > 5 GHz',440,1370,2140,112,'ecu');
const b2bPorts=[['usb','USB 2.0',915],['vbus','VBUS',1055],['esai','ESAI',1195],['i2c','I2C',1335],['ctrl','SPI / UART',1505],['reset','Reset / Power-on',1690],['power','Power / Sense',1890]];
b2bPorts.forEach(([id,name,x])=>terminal('b2b-'+id,name,x,1402,id==='reset'?156:120,'b2b'));
const upperRoutes=[['usb','comm',1150,1186],['vbus','power',1200,1210],['esai','audio',1250,1234],['i2c','comm',1310,1258],['ctrl','comm',1370,1306],['reset','control',1425,1282]];
upperRoutes.forEach(([id,fam,x,y])=>{const target=objects.get('b2b-'+id);link('soc-b2b-'+id,'soc','b2b-'+id,fam,{start:['B',x],end:['T'],via:[[x,y],[target.x+target.w/2,y]],both:['usb','esai','i2c','ctrl'].includes(id),arrow:id!=='reset'});});
link('b2b-pmic','b2b-power','pmic','power',{start:['T'],end:['B']});

// Interface board: MCU dependencies and audio paths are independent local chains.
part('mcu','mcu','CYT2B','Vehicle MCU',1360,1650,250,770,'interface',{large:true});
part('usb-protection','ic','TPD2S701-Q1','USB protection',710,1640,270,128,'interface');
connector('tbox-connector','TBox','connector',455,1646,150,116,'interface','Connector');
part('tbox','ic','TBox','USB 2.0 host',40,1646,285,116,'1');
link('b2b-usb-protection','b2b-usb','usb-protection','comm',{start:['B'],end:['T',820],via:[[915,1570],[820,1570]],both:true});
link('b2b-vbus-protection','b2b-vbus','usb-protection','power',{start:['B'],end:['R',1738],via:[[1055,1738]],label:'5 V / 10 mA',labelAt:[1088,1630]});
link('protection-tbox-data','usb-protection','tbox-connector','comm',{start:['L',1677],end:['R',1677],both:true,label:'D+ / D−',labelAt:[658,1659]});
link('protection-tbox-vbus','usb-protection','tbox-connector','power',{start:['L',1737],end:['R',1737],label:'VBUS',labelAt:[658,1719]});
link('tbox-connector-host','tbox-connector','tbox','comm',{start:['L'],end:['R'],both:true});
link('b2b-mcu-serial','b2b-ctrl','mcu','comm',{start:['B'],end:['T',1505],both:true});
link('b2b-mcu-discrete','b2b-reset','mcu','control',{start:['B'],end:['T',1570],via:[[1690,1590],[1570,1590]],arrow:false});

connector('j4','J4 · GNSS','coax-connector',455,1830,200,140,'interface','FAKRA');
part('gyro','ic','SMI230','Gyroscope',1050,1850,220,120,'interface');
link('gyro-mcu','gyro','mcu','comm',{end:['L',1910],both:true,label:'I2C / SPI',labelAt:[1315,1892]});
part('radio-ant','antenna','AM / FM Antenna','PoC supply',40,2080,285,132,'1');
connector('j6','J6','coax-connector',455,2088,150,116,'interface','FAKRA');
part('dsp','dsp','SAF775D','Audio DSP / tuner',750,2060,250,162,'interface');
part('amp','amp','TDF8532 /<br>TAS6424L-Q1','Amplifier · 4 channels',750,2270,300,134,'interface');
link('radio-j6','radio-ant','j6','rf',{arrow:false});
link('j6-dsp','j6','dsp','rf',{end:['L',2146],arrow:false,label:'AM / FM',labelAt:[678,2128]});
link('b2b-esai-dsp','b2b-esai','dsp','audio',{start:['B'],end:['T',835],via:[[1195,1792],[1006,1792],[1006,2008],[835,2008]],both:true});
link('b2b-i2c-dsp','b2b-i2c','dsp','comm',{start:['B'],end:['T',935],via:[[1335,1816],[1030,1816],[1030,2032],[935,2032]],both:true});
link('dsp-amp','dsp','amp','audio',{start:['B',875],end:['T',875],label:'I2S',labelAt:[908,2246]});

part('eeprom','flash','CAT24C16WI-GT3','EEPROM',1050,2120,220,132,'interface');
part('watchdog','ic','TPS3828-Q1','Watchdog',1080,2300,210,114,'interface');
link('mcu-eeprom-gpio','mcu','eeprom','control',{start:['L',2152],end:['R',2152],arrow:false,label:'GPIO',labelAt:[1315,2136]});
link('mcu-eeprom-i2c','mcu','eeprom','comm',{start:['L',2210],end:['R',2210],both:true,label:'I2C',labelAt:[1315,2194]});
link('mcu-watchdog','mcu','watchdog','control',{start:['L',2357],end:['R',2357],both:true});

part('power-sense','power','Power Sense','Vehicle power interface',1740,1660,300,128,'interface');
part('can1','can','JA1043T','CAN FD · channel 1',1740,1840,300,120,'interface');
part('can2','can','JA1043T','CAN FD · channel 2 · Reserved',1740,2010,300,120,'interface',{reserved:true});
part('control-io','ic','Control I/O','ACC / IGN / CRANK',1740,2180,300,112,'interface');
part('switch-adc','ic','Switch / ADC','Switch[0:4] · ADC[0:3]<br>Reserved',1740,2340,300,116,'interface',{reserved:true});
link('power-sense-mcu','power-sense','mcu','control',{start:['L',1724],end:['R',1724],arrow:false});
link('sense-b2b','power-sense','b2b-power','power',{start:['T'],end:['B'],arrow:false});
link('mcu-can1','mcu','can1','comm',{start:['R',1900],both:true});
link('mcu-can2','mcu','can2','comm',{start:['R',2070],both:true,reserved:true});
link('mcu-control','mcu','control-io','control',{start:['R',2236],both:true});
link('mcu-switch-adc','mcu','switch-adc','control',{start:['R',2398],arrow:false,reserved:true});

// J1 occurs once. The microphone, speaker, power, bus and I/O groups remain distinct terminals.
connectorStrip('j1','J1 · Main Connector','Audio / vehicle harness',455,2480,2100,100,'interface');
const j1ports=[['mic','MIC ×2',850],['speaker','Speaker ×4',1130],['switch','Switch / ADC',1800],['control','Discrete I/O',1980],['can2','CAN2',2160],['can1','CAN1',2340],['power','Power',2490]];
j1ports.forEach(([id,name,x])=>terminal('j1-'+id,name,x,2506,id==='power'?90:130,'j1',['switch','can2'].includes(id)));
link('j1-mic-dsp','j1-mic','dsp','audio',{start:['T'],end:['L',2190],via:[[850,2440],[680,2440],[680,2190]],label:'External MIC IN ×2',labelAt:[590,2360]});
link('amp-j1','amp','j1-speaker','audio',{start:['B'],end:['T'],via:[[900,2432],[1130,2432]]});
link('j1-power-sense','j1-power','power-sense','power',{start:['T'],end:['R',1724],via:[[2490,1724]],both:true});
link('can1-j1','can1','j1-can1','comm',{end:['T'],via:[[2340,1900]],both:true});
link('can2-j1','can2','j1-can2','comm',{end:['T'],via:[[2160,2070]],both:true,reserved:true});
link('control-j1','control-io','j1-control','control',{start:['R'],end:['T'],via:[[2090,2236],[2090,2472],[1980,2472]],both:true});
link('switch-j1','switch-adc','j1-switch','control',{start:['B',1800],end:['T'],arrow:false,reserved:true});

part('microphones','mic','Microphones ×2','Powered microphone inputs',700,2660,300,128,'1');
part('speakers','speaker','Speakers ×4','20 W ×4 · max. 25 W ×4',1050,2660,320,128,'1');
part('vehicle-switch','ic','Vehicle Inputs','Brake fluid / parking brake',1530,2660,330,128,'1');
part('vehicle-control','ic','Vehicle Control','ACC / IGN ON / CRANK',1870,2660,310,128,'1');
part('vehicle-can','can','Vehicle CAN','CAN1 / CAN2 provision',2210,2660,310,128,'1');
part('vehicle-power','power','Vehicle Power','6–16 V',2670,2660,300,128,'1');
link('mic-j1','microphones','j1-mic','audio',{start:['T',850],end:['B']});
link('j1-speakers','j1-speaker','speakers','audio',{start:['B'],end:['T',1130]});
link('vehicle-switch-j1','vehicle-switch','j1-switch','control',{start:['T',1800],end:['B'],arrow:false,reserved:true});
link('vehicle-control-j1','vehicle-control','j1-control','control',{start:['T',1980],end:['B'],both:true});
link('vehicle-can1-j1','vehicle-can','j1-can1','comm',{start:['T',2340],end:['B'],both:true});
link('vehicle-can2-j1','vehicle-can','j1-can2','comm',{start:['T',2270],end:['B'],via:[[2270,2600],[2160,2600]],both:true,reserved:true});
link('vehicle-power-j1','vehicle-power','j1-power','power',{start:['T',2820],end:['B'],via:[[2820,2618],[2490,2618]]});

// Preserve source interfaces with no established receiver, without fabricating a route.
part('rear-camera','camera','Rear Camera','AHD / LVDS',2730,1700,310,128,'1');
txt('lin-source-note','LIN: implementation not shown',2730,1900,310,42,'1',16,false,C.muted);
txt('unrouted-label','Unrouted in source',2730,1638,310,28,'1',18,true,C.muted);

// Finish with the shared theme and native symbols; geometry reflects the hardware view.
finish(p);
const diagram=pages[0].replace('dx="1408"','dx="3100"').replace('pageWidth="1408"','pageWidth="3100"');
const evidence={sourceImage,userConfirmations:['Compute Board and Interface & Audio Board are distinct physical boards connected through B2B.','CAN2 and Switch/ADC are reserved.','GNSS and SMI230 are separate; omit the unconfirmed connection.'],scope:'Hardware connectivity, not a software or virtualization deployment view'};
const notes=[
  'J1 is one physical connector. Its source parts 1 and 2 are represented by distinct terminals of the same native container.',
  'J4 GNSS is retained without an inferred receiver. No GNSS-to-SMI230 connection is drawn.',
  'The rear-camera AHD/LVDS and LIN references have no established receiver/implementation in the source and remain unrouted.',
  'Source part spellings are retained, including JA1043T, LP87565VRNFRQ1 and the alternative amplifier parts. No BOM validation is claimed.',
  'Source rates: MAX9286 GMSL channels <1.5 Gb/s; CSI-2 D-PHY links <2.5G as written. Exact lane/rate interpretation is not independently established.',
  'The SMI230 source link lists I2C/SPI/UART together. I2C/SPI is retained; UART endpoint remains unassigned after separating GNSS.',
  'The source USB charger block lies on the depicted media USB route; exact switch/power-path implementation is not expanded.',
  'VBAT 12 V is retained as a local rail without inventing its upstream conversion path from the 6–16 V vehicle supply.',
  'Power/sense connectivity is retained, without inventing individual supply rails or regulator-to-load connections.',
  'Main video arrows indicate the primary video direction; reverse control channels are not expanded into extra physical cables.',
  'Connector artwork is symbolic, not a mechanical drawing or pin-count specification. USB connector form factors are not inferred from the source.'
];
const model={schema:'cockpit-hardware-view-1',title:p.title,canvas:{width:3100,height:2850},evidence,notes,objects:[...objects.values()].filter(n=>n.id!=='1'),relations};
const output=path.join(here,'x9hp-cockpit-hardware.drawio');
const xml=`<?xml version="1.0" encoding="UTF-8"?>\n<mxfile ${A({host:'Electron',compressed:false,vars:JSON.stringify({evidence,notes,fontLicense:license,fontVersions:manifest.fonts})})}>${diagram}</mxfile>\n`;
const overwrite=process.argv.includes('--overwrite');
fs.writeFileSync(output,xml,{flag:overwrite?'w':'wx'});
fs.writeFileSync(path.join(here,'x9hp-cockpit-hardware.model.json'),JSON.stringify(model,null,2)+'\n',{flag:overwrite?'w':'wx'});
console.log(JSON.stringify({output,components:model.objects.filter(n=>n.kind==='component').length,relations:relations.length,bytes:Buffer.byteLength(xml)}));
