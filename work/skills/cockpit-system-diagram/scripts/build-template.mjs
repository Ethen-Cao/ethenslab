#!/usr/bin/env node
// Canonical compact hardware template. Native editable primitives; generic reference topologies.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const skill = path.resolve(here, '..');
const theme = JSON.parse(fs.readFileSync(path.join(skill, 'assets/tokens.json'), 'utf8'));
const manifest = JSON.parse(fs.readFileSync(path.join(skill, 'assets/fonts/manifest.json'), 'utf8'));
const license = fs.readFileSync(path.join(skill, 'assets/fonts/OFL.txt'), 'utf8');
const fonts = {};
for (const f of manifest.fonts) {
  const bytes = fs.readFileSync(path.join(skill, 'assets/fonts', f.file));
  if (createHash('sha256').update(bytes).digest('hex') !== f.sha256) throw Error('Font hash mismatch');
  fonts[f.family] = 'data:font/woff2;base64,' + bytes.toString('base64');
}
const C = {...theme.colors,...theme.signalColors,comm:theme.signalColors.communication};
let glyphTransform = null;
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
  if(glyphTransform){const t=glyphTransform;x=x*t.scale+t.center;y=y*t.scale+t.center;w*=t.scale;h*=t.scale;size=Math.max(7,size*t.scale);}
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
  if(glyphTransform){const t=glyphTransform;x=x*t.scale+t.center;y=y*t.scale+t.center;w*=t.scale;h*=t.scale;style={...style,strokeWidth:t.stroke,fontSize:Math.max(7,16*t.scale),...(style.arcSize!==undefined?{arcSize:style.arcSize*t.scale}:{})};}
  return v(parent+'-part-'+(++count),label,x,y,w,h,parent,{shape,strokeColor:C.glyph,strokeWidth:1.8,fillColor:'none',align:'center',verticalAlign:'middle',spacing:0,...style},{},0);
}
function line(parent,x1,y1,x2,y2,color=C.glyph,width=1.8) {
  if(glyphTransform){const t=glyphTransform;x1=x1*t.scale+t.center;y1=y1*t.scale+t.center;x2=x2*t.scale+t.center;y2=y2*t.scale+t.center;width=t.stroke;}
  const id='legend-glyph-'+pageId+'-'+(++count);
  cells.push(`<mxCell ${A({id,style:S({edgeStyle:'none',strokeColor:color,strokeWidth:width,startArrow:'none',endArrow:'none',rounded:0}),edge:1,parent,connectable:0})}><mxGeometry relative="1" as="geometry"><mxPoint ${A({x:x1,y:y1,as:'sourcePoint'})}/><mxPoint ${A({x:x2,y:y2,as:'targetPoint'})}/></mxGeometry></mxCell>`);
}
function glyph(parent,type,cx,cy) {
  const r=(x,y,w,h,s={},label='')=>primitive(parent,'rectangle',cx+x,cy+y,w,h,{rounded:1,absoluteArcSize:1,arcSize:8,...s},label);
  const e=(x,y,w,h,s={})=>primitive(parent,'ellipse',cx+x,cy+y,w,h,s);
  const l=(a,b,c,d)=>line(parent,cx+a,cy+b,cx+c,cy+d);
  if (['soc','mcu','dsp','ic','adc','a2b','serdes','phy','can','rfmodule'].includes(type)) {
    r(-28,-24,56,48,{fillColor:C.fill}, {soc:'SoC',mcu:'MCU',dsp:'DSP',ic:'IC',adc:'ADC',a2b:'A2B',serdes:'SER',phy:'PHY',can:'TRX',rfmodule:'RF'}[type]);
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

const glyphBounds = {
 soc:[70,62],mcu:[70,62],dsp:[70,62],ic:[70,62],adc:[70,62],a2b:[70,62],serdes:[70,62],phy:[70,62],can:[70,62],rfmodule:[70,62],
 camera:[66,58],mic:[40,60],speaker:[82,62],amp:[76,54],display:[84,44],touch:[84,64],hud:[66,58],antenna:[56,58],
 dram:[76,54],flash:[54,58],buffer:[70,58],connector:[88,46],'coax-connector':[58,54],'shielded-connector':[72,46],
 'usb-a':[78,42],'usb-c':[80,38],power:[66,54]
};
function icon(parent,type,slot,max,x,y) {
  const id=parent+'-icon';
  v(id,'',x,y,slot,slot,parent,{container:1,recursiveResize:0,collapsible:0,strokeColor:'none',fillColor:'none'},{kind:'icon-group'},0);
  const bounds=glyphBounds[type];if(!bounds)throw Error('Unknown symbol: '+type);
  glyphTransform={scale:max/Math.max(...bounds),center:slot/2,stroke:slot===24?theme.strokes.connectorIcon:theme.strokes.icon};
  glyph(id,type,0,0);glyphTransform=null;
}
function symbol(id,type,title,subtitle,x,y,w=304,parent='1',opts={}) {
  const n=theme.node,h=n.height,lines=title.split('<br>').length;
  if(lines>2 || /<br>|\n/.test(subtitle))throw Error('Too many text lines: '+id);
  if(w%theme.grid)throw Error('Node width must follow the grid: '+id);
  const layoutClass=['soc','mcu'].includes(type)?'processor':'device';
  box(id,'',x,y,w,h,parent,{container:1,recursiveResize:0,collapsible:0,...opts},{entityType:type==='buffer'?'memory':'hardware',canonicalName:title.replaceAll('<br>',' '),symbolType:type,layoutClass});
  icon(id,type,n.iconSlot,n.iconMax,n.paddingX,(h-n.iconSlot)/2);
  const nameH=lines*n.nameLineHeight,total=nameH+(subtitle?n.textGap+n.descriptionLineHeight:0),top=(h-total)/2,textX=n.paddingX+n.iconSlot+n.iconGap;
  txt(id+'-name',title,textX,top,w-textX-n.paddingX,nameH,id,n.nameFont,true,C.ink,'left',{whiteSpace:'nowrap'});
  if(subtitle)txt(id+'-description',subtitle,textX,top+nameH+n.textGap,w-textX-n.paddingX,n.descriptionLineHeight,id,n.descriptionFont,false,C.muted,'left',{whiteSpace:'nowrap'});
  return id;
}
function connector(id,type,title,x,y,w=theme.connector.referenceWidths[title],parent='1',opts={}) {
  const c=theme.connector,h=c.height;
  if(/<br>|\n/.test(title))throw Error('Connector label must be one line');
  if(!Number.isFinite(w)||w<=c.paddingX*2+c.iconSlot+c.iconGap)throw Error('Provide a content-fitted connector width: '+title);
  if(w%theme.grid)throw Error('Connector width must follow the grid');
  box(id,'',x,y,w,h,parent,{container:1,recursiveResize:0,collapsible:0,arcSize:2*theme.radii.connector,...opts},{entityType:'hardware',canonicalName:title,symbolType:type,layoutClass:'connector'});
  icon(id,type,c.iconSlot,c.iconMax,c.paddingX,(h-c.iconSlot)/2);
  const textX=c.paddingX+c.iconSlot+c.iconGap;
  txt(id+'-name',title,textX,(h-c.lineHeight)/2,w-textX-c.paddingX,c.lineHeight,id,c.font,true,C.ink,'left',{whiteSpace:'nowrap'});
  return id;
}
function edge(id,source,target,parent,color,{from=[1,.5],to=[0,.5],points=[],label='',labelOffset=[0,-14],both=false,arrow=true,dash=false,width=theme.strokes.control,position=0}={}) {
  const style={edgeStyle:points.length?'segmentEdgeStyle':'orthogonalEdgeStyle',jettySize:theme.geometry.lastSegment,rounded:0,curved:0,html:1,jumpStyle:'arc',jumpSize:2*theme.geometry.bridgeRadius,strokeColor:color,strokeWidth:width,startArrow:both?'open':'none',endArrow:arrow?'open':'none',startFill:0,endFill:0,endSize:8,startSize:8,exitX:from[0],exitY:from[1],exitPerimeter:0,entryX:to[0],entryY:to[1],entryPerimeter:0,...(dash?{dashed:1,dashPattern:'6 5'}:{})};
  const route=points.length?`<Array as="points">${points.map(([x,y])=>`<mxPoint ${A({x,y})}/>`).join('')}</Array>`:'';
  cells.push(`<object ${A({id,label:'',signalClass:Object.keys(C).find(k=>C[k]===color)??'neutral'})}><mxCell ${A({style:S(style),edge:1,parent,source,target})}><mxGeometry relative="1" as="geometry">${route}</mxGeometry></mxCell></object>`);
  if(label)cells.push(`<mxCell ${A({id:id+'-label',value:`<span style="white-space:nowrap">${E(label)}</span>`,style:S({...base,shape:'text',edgeLabel:1,whiteSpace:'nowrap',align:'center',verticalAlign:'middle',fontSize:13,fontColor:color,fillColor:'#FFFFFF',strokeColor:'none',spacing:3}),vertex:1,parent:id,connectable:0})}><mxGeometry x="${position}" y="0" relative="1" as="geometry"><mxPoint ${A({x:labelOffset[0],y:labelOffset[1],as:'offset'})}/></mxGeometry></mxCell>`);
}
function pin(id,x,y,parent,label='') {return box(id,label,x,y,14,14,parent,{arcSize:4,fillColor:'#FFFFFF',strokeColor:C.glyph,fontSize:9},{kind:'sample-port'});}

// Page 1: compact copyable devices. SoC and MCU use the same compact catalog size.
const p1=begin('symbols','Cockpit Hardware Symbols','Native editable library  /  Devices: 80 px  /  Connectors: 48 px  /  Neutral hardware styling',1224);
const rows=[
 ['Processing & interface ICs', [['soc','Cockpit SoC','Application processor'],['mcu','Vehicle MCU','Independent controller'],['dsp','Audio DSP','Audio processing'],['ic','Interface IC','Generic peripheral IC']]],
 ['Audio & video devices', [['camera','Camera','Sensor / camera module'],['mic','Microphone','Powered microphone inputs'],['speaker','Speaker','Audio output'],['amp','Amplifier','Speaker drive stage']]],
 ['Displays', [['display','Display','Cluster / center / passenger'],['touch','Touch Display','Display + touch interfaces'],['hud','HUD','Projection surface + projector']]],
 ['Memory, storage & connectors', [['dram','DRAM','Physical memory'],['flash','Flash Storage','UFS / eMMC / NOR'],['buffer','Shared Buffer','Logical memory resource'],['connector','Connector','']]],
 ['Bridges, networks & power', [['serdes','SerDes','Serializer / deserializer'],['phy','Ethernet PHY','Physical-layer transceiver'],['can','CAN / LIN<br>Transceiver','Vehicle bus interface'],['power','Power Supply','Conversion / regulation']]],
 ['Wireless & audio interfaces', [['antenna','Antenna','RF endpoint'],['rfmodule','Wireless Module','GNSS / Wi-Fi / Bluetooth'],['adc','Audio ADC','Analog to digital audio'],['a2b','A2B Transceiver','Audio bus interface']]]
];
rows.forEach(([heading,items],r)=>{
 const group=frame('catalog-row-'+r,heading,40,128+r*168,1328,144);
 const start=(1328-(items.length*304+(items.length-1)*24))/2;
 items.forEach(([type,title,sub],c)=>type==='connector'
  ?connector('symbol-connector',type,title,start+c*328+48,64,undefined,group)
  :symbol('symbol-'+r+'-'+type,type,title,sub,start+c*328,48,304,group));
});
txt('catalog-footer','Part numbers may change widths, not device heights. Empty descriptions do not reserve a text row.',40,1158,1328,24,'1',12,false,C.muted);
finish(p1);

// Page 2: line semantics are independent of device identity and physical boundaries.
const p2=begin('visual-grammar','Connections & Boundaries','Hardware-view grammar  /  Signal families, physical inclusion and connection marks',1264);
const signals=[['Video','MIPI CSI-2 / DSI / DP',C.video],['Audio','I2S / TDM / analog / A2B',C.audio],['Communication','SPI / I2C / USB / Ethernet',C.comm],['Discrete Control','Reset / Enable / Interrupt',C.control],['Power','Supply rail / VBUS',C.power],['RF','Antenna feed',C.rf]];
signals.forEach(([title,detail,color],i)=>{
 const id=frame('signal-'+i,title,40+(i%3)*456,128+Math.floor(i/3)*168,416,144);
 txt(id+'-detail',detail,20,48,376,24,id,13,false,C.muted);
 pin(id+'-a',24,100,id);pin(id+'-b',378,100,id);
 edge(id+'-wire',id+'-a',id+'-b',id,color,{both:i===2,arrow:i!==5});
});
txt('boundary-title','Boundaries & configuration',40,484,1328,30,'1',20,true);
const enclosure=frame('enclosure-card','Physical enclosure',40,530,416,304);
box('ecu-sample','',20,56,376,224,enclosure,{container:1,recursiveResize:0,collapsible:0,strokeColor:'#8594A5',strokeWidth:1.4,fillColor:'#FFFFFF'},{kind:'physical-enclosure'});
txt('ecu-name','Cockpit ECU',16,12,344,24,'ecu-sample',16,true);
box('board-sample','',16,52,344,152,'ecu-sample',{container:1,recursiveResize:0,collapsible:0,fillColor:C.panel},{kind:'board'});
txt('board-name','Main Board',12,10,320,22,'board-sample',14,true);
symbol('sample-soc','soc','SoC','',12,52,144,'board-sample');
symbol('sample-dsp','dsp','DSP','',180,52,152,'board-sample');
const functional=frame('functional-card','Functional grouping',496,530,416,304);
box('audio-group','',20,56,376,224,functional,{container:1,recursiveResize:0,collapsible:0,dashed:1,dashPattern:'6 5',fillColor:'#FFFFFF'},{kind:'functional-group'});
txt('audio-heading','Audio',16,12,344,24,'audio-group',16,true);
symbol('group-mic','mic','Mic','',16,72,144,'audio-group');
symbol('group-dsp','dsp','DSP','',216,72,144,'audio-group');
edge('group-audio','group-mic','group-dsp','audio-group',C.audio);
txt('group-note','Grouping does not imply a shared enclosure.',16,184,344,20,'audio-group',12,false,C.muted);
const status=frame('status-card','Configuration labels',952,530,416,304);
symbol('state-included','ic','Interface IC','Included',20,56,376,status);
symbol('state-reserved','ic','Interface IC','Reserved',20,160,376,status,{dashed:1,dashPattern:'6 5'});
txt('state-note','Other explicit labels: Optional / DNP',20,264,376,20,status,12,false,C.muted);
txt('marks-title','Direction, crossing & junction',40,864,1328,30,'1',20,true);
const dir=frame('direction-card','Arrow semantics',40,910,416,242);
[['Signal direction',false,true],['Bidirectional link',true,true],['Physical connection',false,false]].forEach(([label,both,arrow],i)=>{
 const y=69+i*59;pin('dir-a-'+i,22,y,dir);pin('dir-b-'+i,380,y,dir);
 edge('dir-edge-'+i,'dir-a-'+i,'dir-b-'+i,dir,C.control,{both,arrow,label});
});
const crossing=frame('crossing-card','Crossing: not connected',496,910,416,242);
pin('cross-left',26,132,crossing);pin('cross-right',376,132,crossing);pin('cross-top',201,62,crossing);pin('cross-bottom',201,190,crossing);
edge('cross-horizontal','cross-left','cross-right',crossing,C.video,{arrow:false});
edge('cross-vertical','cross-top','cross-bottom',crossing,C.control,{from:[.5,1],to:[.5,0],arrow:false});
const junction=frame('junction-card','Junction: connected',952,910,416,242);
pin('join-left',26,132,junction);pin('join-right',376,132,junction);pin('join-bottom',201,190,junction);
v('join-dot','',204,135,8,8,junction,{shape:'ellipse',fillColor:C.control,strokeColor:C.control},{kind:'junction'});
edge('join-in','join-left','join-dot',junction,C.control,{arrow:false});
edge('join-right-edge','join-dot','join-right',junction,C.control,{arrow:false});
edge('join-down','join-dot','join-bottom',junction,C.control,{from:[.5,1],to:[.5,0],arrow:false});
txt('grammar-footer','Color identifies the signal family, not a chip vendor. Use arrows only when direction is known.',40,1188,1328,24,'1',12,false,C.muted);
finish(p2);

// Page 3: generic reference topology, never a claim about an unspecified deployed board.
const p3=begin('audio-example','External DSP Audio Example','Reference topology  /  Peripherals surround their actual processing unit',800);
const ecu=frame('audio-ecu','Cockpit ECU',320,136,800,472,'1',{fillColor:C.panel,strokeColor:'#8594A5',strokeWidth:1.4},'physical-enclosure');
const board=frame('audio-board','Main Board',24,60,752,384,ecu,{fillColor:'#FFFFFF'},'board');
symbol('example-soc','soc','Cockpit SoC','Application processor',272,56,208,board);
symbol('example-adc','adc','Audio ADC','Mic interface',24,224,192,board);
symbol('example-dsp','dsp','Audio DSP','External to SoC',272,224,208,board);
symbol('example-amp','amp','Digital<br>Amplifier','DAC + power stage',536,224,192,board);
symbol('example-mic','mic','Microphone','External input',40,420,240);
symbol('example-speaker','speaker','Speaker','External output',1152,420,216);
edge('audio-mic-adc','example-mic','example-adc','1',C.audio,{label:'Analog',width:2.6});
edge('audio-adc-dsp','example-adc','example-dsp',board,C.audio,{label:'TDM',width:2.6});
edge('audio-dsp-amp','example-dsp','example-amp',board,C.audio,{label:'TDM',width:2.6});
edge('audio-amp-speaker','example-amp','example-speaker','1',C.audio,{label:'Drive',width:2.6});
edge('soc-dsp-stream','example-soc','example-dsp',board,C.audio,{from:[.3,1],to:[.3,0],both:true,label:'TDM',labelOffset:[-28,0],width:2.6});
edge('soc-dsp-control','example-soc','example-dsp',board,C.comm,{from:[.75,1],to:[.75,0],both:true,label:'I2C',labelOffset:[28,0]});
txt('audio-legend-title','Legend',40,656,100,24,'1',14,true);
pin('audio-legend-a',150,660,'1');pin('audio-legend-b',226,660,'1');
edge('audio-legend-wire','audio-legend-a','audio-legend-b','1',C.audio,{arrow:false,width:2.6});
txt('audio-legend-label','Audio',254,654,160,26,'1',13,false,C.muted);
pin('control-legend-a',424,660,'1');pin('control-legend-b',500,660,'1');
edge('control-legend-wire','control-legend-a','control-legend-b','1',C.comm,{arrow:false});
txt('control-legend-label','Communication',528,654,250,26,'1',13,false,C.muted);
txt('audio-footer','External to the SoC does not mean external to the ECU or board. This is a reference, not a BOM.',40,716,1328,24,'1',12,false,C.muted);
finish(p3);

// Page 4: compact native connector symbols, each with a single-line identity.
const p4=begin('connector-symbols','Connector Symbols','Physical forms  /  48 px height  /  Single-line labels  /  Protocol names belong on links',472);
const cg=frame('connector-families','Connector families',40,128,1328,248);
const connectorSpecs=[
 ['coax-connector','Coax (Connector)','Shield and center contact'],
 ['shielded-connector','Shielded (Connector)','Symbolic paired contacts'],
 ['usb-a','USB Type-A','Rectangular opening and offset tongue'],
 ['coax-connector','J11 (FAKRA ×4)','Example: confirmed designator and family'],
 ['usb-c','USB Type-C','Capsule opening and centered tongue'],
 ['connector','Connector','Unknown physical type remains generic']
];
connectorSpecs.forEach(([type,title,note],i)=>{
 const x=24+(i%3)*432,y=56+Math.floor(i/3)*96;
 connector('connector-catalog-'+i,type,title,x,y,undefined,cg);
 txt('connector-note-'+i,note,x,y+52,416,18,cg,12,false,C.muted);
});
txt('connector-footer','Illustrative contacts are not pin counts. Coax does not automatically mean FAKRA; GMSL and FPD-Link are protocols.',40,406,1328,24,'1',12,false,C.muted);
finish(p4);

const outputIndex=process.argv.indexOf('--output');
if(outputIndex!==-1&&!process.argv[outputIndex+1])throw Error('--output requires a path');
const output=outputIndex===-1?path.join(skill,'assets/cockpit-hardware-symbols.drawio'):path.resolve(process.argv[outputIndex+1]);
const vars={purpose:'Cockpit system diagram compact hardware template',contractVersion:theme.version,status:'Canonical reference specimen',sourceTemplate:{name:'cockpit-hardware-symbols.drawio',sha256:'bfcece358c3ebc2108eda0fd458daf71f232f19757ca7ea3881cc892ae1cb99e',note:'Approved symbol geometry; compact layout regenerated under v1 tokens. Source review artifact preserved separately.'},fontLicense:license,fontVersions:manifest.fonts,signalPalette:theme.signalColors};
const xml=`<?xml version="1.0" encoding="UTF-8"?>\n<mxfile ${A({host:'Electron',compressed:false,vars:JSON.stringify(vars)})}>${pages.join('\n')}</mxfile>\n`;
fs.writeFileSync(output,xml,{flag:process.argv.includes('--overwrite')?'w':'wx'});
console.log(JSON.stringify({output,pages:pages.length,bytes:Buffer.byteLength(xml),deviceHeight:theme.node.height,connectorHeight:theme.connector.height}));
