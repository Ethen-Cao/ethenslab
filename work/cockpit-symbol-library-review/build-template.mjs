#!/usr/bin/env node
// Review specimen: native primitives, not a factual platform deployment model.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const arch = path.resolve(here, '../skills/architecture-diagram');
const theme = JSON.parse(fs.readFileSync(path.join(arch, 'assets/theme.json'), 'utf8'));
const manifest = JSON.parse(fs.readFileSync(path.join(arch, 'assets/fonts/manifest.json'), 'utf8'));
const license = fs.readFileSync(path.join(arch, 'assets/fonts/OFL.txt'), 'utf8');
const fonts = {};
for (const f of manifest.fonts) {
  const bytes = fs.readFileSync(path.join(arch, 'assets/fonts', f.file));
  if (createHash('sha256').update(bytes).digest('hex') !== f.sha256) throw Error('Font hash mismatch');
  fonts[f.family] = 'data:font/woff2;base64,' + bytes.toString('base64');
}
const C = {ink:'#263445', muted:'#647286', border:'#CDD6DF', panel:'#F7F9FB', fill:'#EDF2F6', glyph:'#52667A',
  video:'#356DC9', audio:'#8055B5', comm:'#087F83', control:'#5F6368', power:'#BE532E', rf:'#846342'};
const E = s => String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const A = o => Object.entries(o).filter(([,v])=>v!==undefined).map(([k,v])=>`${k}="${E(v)}"`).join(' ');
const S = o => Object.entries(o).map(([k,v])=>`${k}=${v}`).join(';')+';';
const base = {html:1,whiteSpace:'wrap',fontFamily:'Roboto',fontSize:theme.type.node,fontColor:C.ink,shadow:0,glass:0};
const pages=[];
let cells, count, pageId;
function begin(id,title,subtitle,h) {
  pageId=id; count=0; cells=['<mxCell id="0"/>','<mxCell id="1" parent="0"/>'];
  txt('title',title,40,28,1260,38,'1',theme.type.title,true,C.ink,'left',{
    fontFamily:'Roboto',fontSource:encodeURIComponent(fonts.Roboto)});
  txt('subtitle',subtitle,40,72,1328,24,'1',theme.type.body,false,C.muted);
  v('font-mono','',40,100,1,1,'1',{shape:'text',strokeColor:'none',fillColor:'none',fontFamily:'Roboto Mono',fontSource:encodeURIComponent(fonts['Roboto Mono']),fontSize:1},{connectable:0});
  return {id,title,h};
}
function finish(p) {
  const attr={dx:1408,dy:p.h,grid:0,gridSize:8,guides:1,tooltips:1,connect:1,arrows:1,fold:0,page:1,pageScale:1,pageWidth:1408,pageHeight:p.h,math:0,shadow:0,background:'#FFFFFF',extFonts:Object.entries(fonts).map(([f,u])=>f+'^'+u).join('|')};
  pages.push(`<diagram ${A({id:p.id,name:p.title})}><mxGraphModel ${A(attr)}><root>\n${cells.join('\n')}\n</root></mxGraphModel></diagram>`);
}
function v(id,label,x,y,w,h,parent='1',style={},meta={},connectable=undefined) {
  if (!(w>0&&h>0)) throw Error('Invalid geometry: '+id);
  const native=`<mxCell ${A({style:S({...base,...style}),vertex:1,parent,connectable})}><mxGeometry ${A({x,y,width:w,height:h,as:'geometry'})}/></mxCell>`;
  cells.push(`<object ${A({id,label,...meta})}>${native}</object>`);
  return id;
}
function txt(id,label,x,y,w,h,parent='1',size=16,bold=false,color=C.ink,align='left',style={}) {
  return v(id,label,x,y,w,h,parent,{shape:'text',strokeColor:'none',fillColor:'none',fontSize:size,fontStyle:bold?1:0,fontColor:color,align,verticalAlign:'middle',spacing:0,...style},{},0);
}
function box(id,label,x,y,w,h,parent='1',style={},meta={}) {
  return v(id,label,x,y,w,h,parent,{rounded:1,absoluteArcSize:1,arcSize:2*theme.radii.node,strokeColor:C.border,strokeWidth:theme.strokes.node,fillColor:'#FFFFFF',...style},meta);
}
function frame(id,title,x,y,w,h,parent='1',style={},kind='specimen') {
  box(id,'',x,y,w,h,parent,{container:1,recursiveResize:0,collapsible:0,fillColor:C.panel,...style},{kind});
  txt(id+'-heading',title,20,14,w-40,28,id,18,true);
  return id;
}
function badge(id,text,x,y,w,parent) {
  box(id,text,x,y,w,22,parent,{arcSize:8,fontSize:11,fillColor:'#F1F4F7',strokeColor:C.border,fontColor:C.muted,align:'center'});
}
function primitive(parent,shape,x,y,w,h,style={},label='') {
  return v(parent+'-part-'+(++count),label,x,y,w,h,parent,{shape,strokeColor:C.glyph,strokeWidth:1.8,fillColor:'none',align:'center',verticalAlign:'middle',spacing:0,...style},{},0);
}
function line(parent,x1,y1,x2,y2,color=C.glyph,width=1.8) {
  const id='legend-glyph-'+pageId+'-'+(++count);
  cells.push(`<mxCell ${A({id,style:S({edgeStyle:'none',strokeColor:color,strokeWidth:width,startArrow:'none',endArrow:'none',rounded:0}),edge:1,parent,connectable:0})}><mxGeometry relative="1" as="geometry"><mxPoint ${A({x:x1,y:y1,as:'sourcePoint'})}/><mxPoint ${A({x:x2,y:y2,as:'targetPoint'})}/></mxGeometry></mxCell>`);
}
function glyph(parent,type,cx,cy) {
  const r=(x,y,w,h,s={},label='')=>primitive(parent,'rectangle',cx+x,cy+y,w,h,{rounded:1,absoluteArcSize:1,arcSize:8,...s},label);
  const e=(x,y,w,h,s={})=>primitive(parent,'ellipse',cx+x,cy+y,w,h,s);
  const l=(a,b,c,d)=>line(parent,cx+a,cy+b,cx+c,cy+d);
  if (['soc','mcu','dsp','ic','adc','serdes','phy','can','rfmodule'].includes(type)) {
    r(-28,-24,56,48,{fillColor:C.fill}, {soc:'SoC',mcu:'MCU',dsp:'DSP',ic:'IC',adc:'ADC',serdes:'SER',phy:'PHY',can:'TRX',rfmodule:'RF'}[type]);
    for(const q of [-14,0,14]) {l(q,-31,q,-24);l(q,24,q,31);}
    for(const q of [-12,0,12]) {l(-35,q,-28,q);l(28,q,35,q);}
  } else if(type==='camera') {
    primitive(parent,'triangle',cx-33,cy-12,16,24,{fillColor:C.fill});
    l(-17,0,-15,0);r(-15,-17,44,34,{fillColor:C.fill,arcSize:4});
    l(7,17,7,27);l(-5,27,19,27);
  } else if(type==='mic') {
    r(-11,-30,22,40,{arcSize:22,fillColor:C.fill});
    for(const y of [-20,-13,-6])l(-5,y,5,y);
    l(-20,-6,-20,17);l(-20,17,20,17);l(20,17,20,-6);l(0,17,0,29);l(-13,29,13,29);
  } else if(type==='speaker') {
    r(-29,-11,13,22,{arcSize:0,fillColor:C.fill});
    primitive(parent,'trapezoid',cx-16,cy-25,30,50,{rotation:270,fillColor:C.fill});
    l(22,-13,29,-5);l(29,-5,29,5);l(29,5,22,13);l(31,-22,40,-9);l(40,-9,40,9);l(40,9,31,22);
  } else if(type==='amp') {
    primitive(parent,'triangle',cx-27,cy-27,54,54,{fillColor:C.fill},'');
    txt(parent+'-amp-label','AMP',cx-22,cy-10,38,20,parent,12,true,C.glyph,'center');
    l(-38,0,-27,0);l(27,0,38,0);
  } else if(type==='display'||type==='touch') {
    // A bezel-only automotive panel; no desktop stand or base.
    r(-42,-22,84,44,{fillColor:C.fill});
    r(-36,-16,72,32,{strokeColor:C.border,fillColor:'#FFFFFF',arcSize:4});
    if(type==='touch') {
      e(9,-4,18,18);
      r(19,5,8,26,{rotation:-25,arcSize:8,fillColor:'#FFFFFF'});
    }
  } else if(type==='hud') {
    // Tilted projection surface and separate projector; not a flat-panel display.
    l(-33,-21,33,-29);l(33,-29,33,-24);l(33,-24,-33,-16);l(-33,-16,-33,-21);
    line(parent,cx-8,cy+12,cx-22,cy-17,C.border,1.4);
    line(parent,cx+8,cy+12,cx+22,cy-22,C.border,1.4);
    r(-22,12,44,16,{fillColor:C.fill,arcSize:4});l(-10,17,10,17);
  } else if(type==='antenna') {
    l(0,-28,0,29);l(-15,-28,0,-9);l(15,-28,0,-9);l(-15,-28,15,-28);l(-13,29,13,29);
    l(-22,-19,-28,-10);l(-28,-10,-22,-1);l(22,-19,28,-10);l(28,-10,22,-1);
  } else if(type==='dram') {
    r(-38,-21,76,40,{fillColor:C.fill});
    for(const x of [-28,-8,12])r(x,-13,15,23,{fillColor:'#FFFFFF',arcSize:2});
    for(const x of [-29,-21,-13,-5,3,11,19,27])r(x,19,4,7,{fillColor:C.glyph,strokeColor:'none',arcSize:0});
  } else if(type==='flash') {
    r(-27,-29,54,58,{fillColor:C.fill});r(-18,-18,36,22,{fillColor:'#FFFFFF'});
    for(const x of [-18,-8,2,12])r(x,14,6,10,{fillColor:C.glyph,strokeColor:'none',arcSize:0});
  } else if(type==='buffer') {
    r(-24,-29,59,44,{fillColor:C.fill});r(-29,-24,59,44,{fillColor:C.fill});r(-34,-19,59,44,{fillColor:'#FFFFFF'});
    l(-23,-5,14,-5);l(-23,4,14,4);l(-23,13,2,13);
  } else if(type==='connector') {
    r(-37,-23,74,46,{fillColor:C.fill});
    for(const x of [-24,-8,8,24])for(const y of [-9,9])e(x-3,y-3,6,6,{fillColor:'#FFFFFF'});
    l(-44,-12,-37,-12);l(-44,12,-37,12);l(37,-12,44,-12);l(37,12,44,12);
  } else if(type==='coax-connector') {
    // Generic shielded coax front view, not a vendor-specific keyed housing.
    r(-29,-27,58,54,{fillColor:C.fill,arcSize:4});
    e(-20,-20,40,40,{fillColor:'#FFFFFF'});
    e(-14,-14,28,28);e(-4,-4,8,8,{fillColor:C.glyph});
  } else if(type==='shielded-connector') {
    // Paired contacts are symbolic; they do not declare a real pin count.
    r(-36,-23,72,46,{fillColor:C.fill});
    r(-29,-16,58,32,{fillColor:'#FFFFFF',arcSize:4});
    for(const x of [-11,11])e(x-4,-4,8,8,{fillColor:C.fill});
  } else if(type==='usb-a') {
    r(-39,-21,78,42,{fillColor:C.fill,arcSize:2});
    r(-33,-15,66,30,{fillColor:'#FFFFFF',arcSize:0});
    r(-26,3,52,8,{fillColor:C.fill,arcSize:0});
    for(const x of [-17,-6,5,16])l(x,4,x,10);
  } else if(type==='usb-c') {
    // Capsule opening and centered tongue distinguish Type-C from Type-A.
    r(-40,-19,80,38,{fillColor:C.fill,arcSize:38});
    r(-34,-13,68,26,{fillColor:'#FFFFFF',arcSize:26});
    r(-25,-4,50,8,{fillColor:C.fill,arcSize:8});
  } else if(type==='power') {
    r(-33,-27,66,54,{fillColor:C.fill});
    l(-23,0,-13,0);l(-18,-5,-18,5);l(14,0,24,0);
    l(4,-19,-6,2);l(-6,2,6,2);l(6,2,-3,20);
  }
}
function symbol(id,type,title,subtitle,x,y,w=302,h=148,parent='1',opts={}) {
  box(id,'',x,y,w,h,parent,{container:1,recursiveResize:0,collapsible:0,...opts},{entityType:type==='buffer'?'memory':'hardware',canonicalName:title,symbolType:type});
  glyph(id,type,w/2,47);
  txt(id+'-name',title,10,88,w-20,24,id,16,true,C.ink,'center');
  if(subtitle)txt(id+'-description',subtitle,10,118,w-20,20,id,12,false,C.muted,'center');
  return id;
}
function edge(id,source,target,parent,color,{from=[1,.5],to=[0,.5],points=[],label='',labelOffset=[0,-14],both=false,arrow=true,dash=false,width=theme.strokes.control,position=0}={}) {
  const style={edgeStyle:'segmentEdgeStyle',rounded:0,curved:0,html:1,jumpStyle:'arc',jumpSize:2*theme.geometry.bridgeRadius,strokeColor:color,strokeWidth:width,startArrow:both?'open':'none',endArrow:arrow?'open':'none',startFill:0,endFill:0,endSize:8,startSize:8,exitX:from[0],exitY:from[1],exitPerimeter:0,entryX:to[0],entryY:to[1],entryPerimeter:0,...(dash?{dashed:1,dashPattern:'6 5'}:{})};
  const route=points.length?`<Array as="points">${points.map(([x,y])=>`<mxPoint ${A({x,y})}/>`).join('')}</Array>`:'';
  cells.push(`<object ${A({id,label:'',signalClass:Object.keys(C).find(k=>C[k]===color)??'neutral'})}><mxCell ${A({style:S(style),edge:1,parent,source,target})}><mxGeometry relative="1" as="geometry">${route}</mxGeometry></mxCell></object>`);
  if(label)cells.push(`<mxCell ${A({id:id+'-label',value:`<span style="white-space:nowrap">${E(label)}</span>`,style:S({...base,shape:'text',edgeLabel:1,whiteSpace:'nowrap',align:'center',verticalAlign:'middle',fontSize:13,fontColor:color,fillColor:'#FFFFFF',strokeColor:'none',spacing:3}),vertex:1,parent:id,connectable:0})}><mxGeometry x="${position}" y="0" relative="1" as="geometry"><mxPoint ${A({x:labelOffset[0],y:labelOffset[1],as:'offset'})}/></mxGeometry></mxCell>`);
}
function pin(id,x,y,parent,label='') {return box(id,label,x,y,14,14,parent,{arcSize:4,fillColor:'#FFFFFF',strokeColor:C.glyph,fontSize:9},{kind:'sample-port'});}

// Page 1: copyable symbol families. Grouping and labels remain editable.
const p1=begin('symbols','Cockpit Hardware Symbols','Device library  /  Generic names  /  Native editable shapes',1660);
const rows=[
  ['Processing & interface ICs',[['soc','Cockpit SoC','Application processor'],['mcu','Vehicle MCU','Independent controller'],['dsp','Audio DSP','Audio processing'],['ic','Interface IC','Generic peripheral IC']]],
  ['Audio & video devices',[['camera','Camera','Image sensor / camera module'],['mic','Microphone','Audio input'],['speaker','Speaker','Audio output'],['amp','Amplifier','Speaker drive stage']]],
  ['Displays',[['display','Display','Cluster / Center / Passenger'],['touch','Touch Display','Display and touch interfaces'],['hud','HUD','Projector and projection surface']]],
  ['Memory, storage & connectors',[['dram','DRAM','Physical memory device'],['flash','Flash Storage','UFS / eMMC / NOR'],['buffer','Shared Buffer','Logical memory resource'],['connector','Connector','Board / harness interface']]],
  ['Bridges, networks & power',[['serdes','SerDes','Serializer / deserializer'],['phy','Ethernet PHY','Physical-layer transceiver'],['can','CAN / LIN Transceiver','Vehicle bus interface'],['power','Power Supply','Power conversion / regulation']]],
  ['Wireless & audio interfaces',[['antenna','Antenna','RF endpoint'],['rfmodule','Wireless Module','GNSS / Wi-Fi / Bluetooth'],['adc','Audio ADC','Analog input / digital audio output']]]
];
rows.forEach(([heading,items],r)=>{
  const group=frame('catalog-row-'+r,heading,40,128+r*244,1328,220);
  const start=(1328-(items.length*302+(items.length-1)*24))/2;
  items.forEach(([type,title,sub],c)=>symbol('symbol-'+type,type,title,sub,start+c*326,54,302,148,group));
});
txt('catalog-footer','Neutral device styling; no vendor or configuration meaning is assigned to the fill.',40,1606,1328,22,'1',12,false,C.muted);
finish(p1);

// Page 2: hardware-view grammar; palettes are review proposals, not standards.
const p2=begin('visual-grammar','Connections & Boundaries','Hardware-view style proposal  /  Signal colors, enclosure semantics and connection marks',1180);
const signals=[['Video','MIPI CSI-2 / DSI / DP',C.video],['Audio','I2S / TDM / analog audio',C.audio],['Communication','SPI / I2C / USB / Ethernet',C.comm],['Discrete Control','Reset / Enable / Interrupt',C.control],['Power','Supply rail / VBUS',C.power],['RF','Antenna feed',C.rf]];
signals.forEach(([title,detail,color],i)=>{
  const id=frame('signal-'+i,title,40+(i%3)*456,128+Math.floor(i/3)*168,416,144);
  txt(id+'-detail',detail,20,48,376,24,id,13,false,C.muted);
  pin(id+'-a',24,100,id);pin(id+'-b',378,100,id);
  edge(id+'-wire',id+'-a',id+'-b',id,color,{both:i===2,arrow:i!==5});
});
txt('boundary-title','Boundaries & configuration',40,484,1328,30,'1',20,true);
const enclosure=frame('enclosure-card','Physical enclosure',40,530,416,244);
box('ecu-sample','',20,60,376,158,enclosure,{container:1,recursiveResize:0,collapsible:0,strokeColor:'#8594A5',strokeWidth:1.4,fillColor:'#FFFFFF'},{kind:'physical-enclosure'});
txt('ecu-name','Cockpit ECU',16,12,344,24,'ecu-sample',16,true);
box('board-sample','',16,50,344,90,'ecu-sample',{container:1,recursiveResize:0,collapsible:0,fillColor:C.panel},{kind:'board'});
txt('board-name','Main Board',12,8,310,22,'board-sample',14,true);
box('sample-soc','SoC',16,40,130,34,'board-sample',{fillColor:C.fill},{entityType:'hardware'});
box('sample-dsp','DSP',198,40,130,34,'board-sample',{fillColor:C.fill},{entityType:'hardware'});
const functional=frame('functional-card','Functional grouping',496,530,416,244);
box('audio-group','',20,60,376,158,functional,{container:1,recursiveResize:0,collapsible:0,dashed:1,dashPattern:'6 5',fillColor:'#FFFFFF'},{kind:'functional-group'});
txt('audio-heading','Audio',16,12,344,24,'audio-group',16,true);
box('group-mic','Microphone',16,62,146,44,'audio-group',{fillColor:C.fill},{entityType:'hardware'});
box('group-dsp','DSP',212,62,146,44,'audio-group',{fillColor:C.fill},{entityType:'hardware'});
edge('group-audio', 'group-mic','group-dsp','audio-group',C.audio);
txt('group-note','Grouping does not imply a shared enclosure.',16,122,344,22,'audio-group',12,false,C.muted);
const status=frame('status-card','Configuration labels',952,530,416,244);
[['Included','In this configuration'],['Optional','Variant-dependent'],['Reserved','Future provision'],['DNP','Device not populated']].forEach(([a,b],i)=>{
  badge('state-'+i,a,20,59+i*39,91,status);
  txt('state-info-'+i,b,125,59+i*39,270,23,status,13,false,C.muted);
});
txt('marks-title','Direction, crossing & junction',40,804,1328,30,'1',20,true);
const dir=frame('direction-card','Arrow semantics',40,850,416,242);
[['Signal direction',false,true],['Bidirectional link',true,true],['Physical connection',false,false]].forEach(([label,both,arrow],i)=>{
  const y=69+i*59;
  pin('dir-a-'+i,22,y,dir);pin('dir-b-'+i,380,y,dir);
  edge('dir-edge-'+i,'dir-a-'+i,'dir-b-'+i,dir,C.control,{both,arrow,label});
});
const crossing=frame('crossing-card','Crossing: not connected',496,850,416,242);
pin('cross-left',26,132,crossing);pin('cross-right',376,132,crossing);pin('cross-top',201,62,crossing);pin('cross-bottom',201,190,crossing);
edge('cross-horizontal','cross-left','cross-right',crossing,C.video,{arrow:false});
edge('cross-vertical','cross-top','cross-bottom',crossing,C.control,{from:[.5,1],to:[.5,0],arrow:false});
const junction=frame('junction-card','Junction: connected',952,850,416,242);
pin('join-left',26,132,junction);pin('join-right',376,132,junction);pin('join-bottom',201,190,junction);
v('join-dot','',204,135,8,8,junction,{shape:'ellipse',fillColor:C.control,strokeColor:C.control},{kind:'junction'});
edge('join-in','join-left','join-dot',junction,C.control,{arrow:false});
edge('join-right-edge','join-dot','join-right',junction,C.control,{arrow:false});
edge('join-down','join-dot','join-bottom',junction,C.control,{from:[.5,1],to:[.5,0],arrow:false});
txt('grammar-footer','Line color identifies the signal family. Device and connector labels identify the interface.',40,1122,1328,24,'1',12,false,C.muted);
finish(p2);

// Page 3: a generic review topology, not a claim about the user's deployed board.
const p3=begin('audio-example','External DSP Audio Example','Reference topology  /  Microphone and speaker paths terminate at the audio subsystem',862);
const ecu=frame('audio-ecu','Cockpit ECU',320,136,800,552,'1',{fillColor:'#F7F9FB',strokeColor:'#8594A5',strokeWidth:1.4},'physical-enclosure');
const board=frame('audio-board','Main Board',24,60,752,464,ecu,{fillColor:'#FFFFFF'},'board');
symbol('example-soc','soc','Cockpit SoC','Application processor',264,56,224,140,board);
symbol('example-adc','adc','Audio ADC','Microphone interface',24,292,176,140,board);
symbol('example-dsp','dsp','Audio DSP','External to the SoC',264,292,224,140,board);
symbol('example-amp','amp','Digital Amplifier','DAC + power stage',552,292,176,140,board);
symbol('example-mic','mic','Microphone','External input',40,488,224,140);
symbol('example-speaker','speaker','Speaker','External output',1152,488,216,140);
edge('audio-mic-adc','example-mic','example-adc','1',C.audio,{label:'Analog',labelOffset:[0,-16],width:2.6});
edge('audio-adc-dsp','example-adc','example-dsp',board,C.audio,{label:'TDM',width:2.6});
edge('audio-dsp-amp','example-dsp','example-amp',board,C.audio,{label:'TDM',width:2.6});
edge('audio-amp-speaker','example-amp','example-speaker','1',C.audio,{label:'Drive',width:2.6});
edge('soc-dsp-stream','example-soc','example-dsp',board,C.audio,{from:[.35,1],to:[.35,0],both:true,label:'TDM',labelOffset:[-26,0],width:2.6});
edge('soc-dsp-control','example-soc','example-dsp',board,C.comm,{from:[.75,1],to:[.75,0],both:true,label:'I2C',labelOffset:[26,0],width:1.8});
txt('audio-legend-title','Legend',40,738,100,24,'1',14,true);
pin('audio-legend-a',150,743,'1');pin('audio-legend-b',226,743,'1');
edge('audio-legend-wire','audio-legend-a','audio-legend-b','1',C.audio,{arrow:false,width:2.6});
txt('audio-legend-label','Audio',254,736,160,26,'1',13,false,C.muted);
pin('control-legend-a',424,743,'1');pin('control-legend-b',500,743,'1');
edge('control-legend-wire','control-legend-a','control-legend-b','1',C.comm,{arrow:false});
txt('control-legend-label','Communication',528,736,250,26,'1',13,false,C.muted);
txt('audio-footer','Boundary nesting shows physical inclusion; device positions follow the connections.',40,792,1328,24,'1',12,false,C.muted);
finish(p3);

// Page 4: connector geometry is independent of the protocol carried by a link.
const p4=begin('connector-symbols','Connector Symbols','Physical connector shapes  /  Protocol names belong on links',436);
const connectorGroup=frame('connector-families','Connector families',40,128,1328,222);
const connectorSymbols=[
  ['coax-connector','Coax Connector','Shield and center contact'],
  ['shielded-connector','Shielded Connector','Shield and paired contacts'],
  ['usb-a','USB Type-A','Rectangular opening / offset tongue'],
  ['usb-c','USB Type-C','Rounded opening / centered tongue'],
  ['connector','Connector','Unspecified physical type']
];
connectorSymbols.forEach(([type,title,subtitle],i)=>symbol('connector-catalog-'+type,type,title,subtitle,16+i*264,56,240,148,connectorGroup));
txt('connector-footer','Symbolic front views; contact counts are illustrative. Use specific connector-family names only when confirmed.',40,378,1328,24,'1',12,false,C.muted);
finish(p4);

const vars={purpose:'Cockpit hardware symbol library review specimen',status:'Draft for review',fontLicense:license,fontVersions:manifest.fonts,signalPalette:Object.fromEntries(signals.map(([k,,v])=>[k,v]))};
const outputIndex=process.argv.indexOf('--output');
if(outputIndex!==-1&&!process.argv[outputIndex+1])throw Error('--output requires a path');
const output=outputIndex===-1?path.join(here,'cockpit-hardware-symbols.drawio'):path.resolve(process.argv[outputIndex+1]);
let xml=`<?xml version="1.0" encoding="UTF-8"?>\n<mxfile ${A({host:'Electron',compressed:false,vars:JSON.stringify(vars)})}>${pages.join('\n')}</mxfile>\n`;
const appendConnectors=process.argv.includes('--append-connectors');
if(appendConnectors) {
  // Preserve edited native pages verbatim; do not rebuild them from this specimen source.
  if(process.argv.includes('--overwrite'))throw Error('Append and overwrite are mutually exclusive');
  const original=fs.readFileSync(output,'utf8');
  if(!/<\/mxfile>\s*$/.test(original))throw Error('Expected an mxfile document');
  if(/<diagram\b[^>]*\bid="connector-symbols"/.test(original))throw Error('Connector page already exists; edit its native cells in place');
  xml=original.replace(/<\/mxfile>\s*$/,pages.at(-1)+'</mxfile>\n');
}
fs.writeFileSync(output,xml,{flag:appendConnectors||process.argv.includes('--overwrite')?'w':'wx'});
console.log(JSON.stringify({output,pages:pages.length,connectorSymbols:connectorSymbols.length,appended:appendConnectors,bytes:Buffer.byteLength(xml)}));
