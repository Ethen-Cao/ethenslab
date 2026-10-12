#!/usr/bin/env node
// One-way export of architecture-diagram v2 models to editable native draw.io cells.
// Do not rerun over a manually edited .drawio unless that replacement is intended.
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const require = createRequire(import.meta.url);
const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2), positional = [];
let overwrite = false, architectureRoot = resolve(skillRoot, '../architecture-diagram'), originLabels = {};
for (let i=0;i<args.length;i++) {
  if(args[i]==='--overwrite') overwrite=true;
  else if(args[i]==='--architecture-skill' && args[i+1]) architectureRoot=resolve(args[++i]);
  else if(args[i]==='--origin-labels' && args[i+1]) originLabels=JSON.parse(args[++i]);
  else if(args[i].startsWith('--')) throw new Error(`Unknown or incomplete option: ${args[i]}`);
  else positional.push(args[i]);
}
const [input, output] = positional;
if (positional.length!==2 || !output.endsWith('.drawio')) throw new Error('Usage: node scripts/build-drawio.mjs <model.json> <output.drawio> [--overwrite] [--architecture-skill <directory>] [--origin-labels <JSON>]');
if(!originLabels || Array.isArray(originLabels) || typeof originLabels!=='object' || Object.entries(originLabels).some(([key,value])=>!['vendor','native','oem','unknown'].includes(key)||typeof value!=='string'||!value.trim()||/[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\u3040-\u30ff]/u.test(value))) throw new Error('Origin labels must map known origins to nonempty English labels.');
const {validate, displayName, edgeType} = require(resolve(architectureRoot, 'assets/model.js'));
const model = JSON.parse(await readFile(resolve(input), 'utf8'));
const report = validate(model);
if (!report.ok) throw new Error(JSON.stringify(report.errors));
for(const warning of report.warnings) console.warn(`${warning.code}: ${warning.message}`);
const theme = JSON.parse(await readFile(resolve(architectureRoot, 'assets/theme.json'), 'utf8'));
const fontRoot=resolve(architectureRoot,'assets/fonts');
const fontManifest=JSON.parse(await readFile(resolve(fontRoot,'manifest.json'),'utf8'));
const fontLicense=await readFile(resolve(fontRoot,fontManifest.licenseFile),'utf8');
const fontSources={};
for(const font of fontManifest.fonts) {
  const bytes=await readFile(resolve(fontRoot,font.file));
  if(createHash('sha256').update(bytes).digest('hex')!==font.sha256 || bytes.subarray(0,4).toString('ascii')!=='wOF2') throw new Error(`Pinned font is invalid: ${font.file}`);
  fontSources[font.family]='data:font/woff2;base64,'+bytes.toString('base64');
}
if(!fontSources[theme.fonts.sans.family] || !fontSources[theme.fonts.mono.family]) throw new Error('Theme font families are absent from the pinned manifest.');
const containers = new Map(model.containers.map(c => [c.id, c]));
const nodes = new Map(model.nodes.map(n => [n.id, n]));
const colors = {oem:'#4285F4',native:'#34A853',vendor:'#FBBC04',unknown:'#ffffff'};
const palette={blue:'#4285F4',green:'#34A853',amber:'#FBBC04',purple:'#A78BFA',cyan:'#38BDF8',orange:'#FB923C',pink:'#F472B6',indigo:'#818CF8'};
const categoryPalette={oem:'blue',tier1:'amber','soc-vendor':'purple','os-vendor':'green',other:'cyan'};
const parties=new Map((model.parties||[]).map(p=>[p.id,p]));
const ink = '#202124', muted = '#5f6368', border = '#cbd1d8';
const sans = `${theme.fonts.sans.family},Arial,sans-serif`, mono = `'${theme.fonts.mono.family}','DejaVu Sans Mono',monospace`;
const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const attrs = obj => Object.entries(obj).filter(([,v])=>v!==undefined).map(([k,v])=>`${k}="${esc(v)}"`).join(' ');
const style = obj => Object.entries(obj).map(([k,v])=>`${k}=${v}`).join(';')+';';
const C = id => 'container-'+id, N = id => 'node-'+id, E = id => 'edge-'+id;
const figure = 'architecture-canvas';
const cells = ['<mxCell id="0"/>','<mxCell id="1" parent="0"/>'];
function geometry(x,y,w,h,extra='') {
  return `<mxGeometry ${attrs({x,y,width:w,height:h,as:'geometry'})}>${extra}</mxGeometry>`;
}
function vertex(id,value,s,parent,x,y,w,h,extra={}) {
  cells.push(`<mxCell ${attrs({id,value,style:style(s),vertex:1,parent,...extra})}>${geometry(x,y,w,h)}</mxCell>`);
}
function objectCell(id,label,s,parent,x,y,w,h,metadata={}) {
  cells.push(`<object ${attrs({id,label,...metadata})}><mxCell ${attrs({style:style(s),vertex:1,parent})}>${geometry(x,y,w,h)}</mxCell></object>`);
}
const boxBase = {rounded:1,absoluteArcSize:1,arcSize:2*theme.radii.node,html:1,whiteSpace:'wrap',shadow:0,glass:0,fontFamily:sans,fontColor:ink,rotation:0};
const title = (name,description,size=theme.type.node,code=false) =>
  `<div style="font-family:${code?mono:sans};font-size:${size}px;font-weight:700;line-height:1.25;">${esc(name)}</div>`+
  (description?`<div style="font-family:${new RegExp(theme.code.textPattern).test(description)?mono:sans};font-size:${theme.type.subtitle}px;font-weight:400;line-height:1.42;margin-top:4px;">${esc(description)}</div>`:'');
const plainText = {shape:'text',html:1,strokeColor:'none',fillColor:'none',fontFamily:sans,fontColor:ink,align:'left',verticalAlign:'middle',spacing:0,whiteSpace:'wrap',rounded:0};
vertex('figure-title',model.meta.title,{...plainText,fontFamily:theme.fonts.sans.family,fontSource:encodeURIComponent(fontSources[theme.fonts.sans.family]),fontSize:theme.type.title,fontStyle:1},'1',24,16,model.canvas.width,34);
if(model.meta.subtitle) vertex('figure-subtitle',model.meta.subtitle,{...plainText,fontSize:theme.type.body,fontColor:muted},'1',24,54,model.canvas.width,24);
// extFonts alone is insufficient in the tested Electron CLI. Register Mono even
// when no library node uses it; an empty native text cell adds no visible element.
vertex('font-registration-mono','',{...plainText,fontFamily:theme.fonts.mono.family,fontSource:encodeURIComponent(fontSources[theme.fonts.mono.family]),fontSize:1,selectable:0,movable:0},'1',24,80,1,1,{connectable:0});
objectCell(figure,'',{...boxBase,arcSize:2*theme.radii.shell,container:1,recursiveResize:0,collapsible:0,fillColor:'#ffffff',strokeColor:border,strokeWidth:theme.strokes.frame},'1',24,100,model.canvas.width,model.canvas.height,{modelId:model.meta.id,description:model.meta.description,sourceModel:input});
function depth(c) {let d=0;while(c.parent){d++;c=containers.get(c.parent);}return d;}
for(const c of [...model.containers].sort((a,b)=>depth(a)-depth(b))) {
  const p=containers.get(c.parent), x=c.x-(p?.x||0),y=c.y-(p?.y||0);
  const fill=c.kind==='process'?'#ffffff':['domain','hypervisor','hardware-region'].includes(c.kind)?'#f5f6f7':'#fafbfc';
  const fontSize=c.kind==='domain'?theme.type.domain:theme.type.container;
  const s={...boxBase,arcSize:2*(c.kind==='domain'?theme.radii.domain:theme.radii.container),container:1,recursiveResize:0,collapsible:0,connectable:0,fillColor:fill,strokeColor:c.kind==='process'?'#aab3bf':border,strokeWidth:c.kind==='domain'?theme.strokes.domain:theme.strokes.frame,align:'left',verticalAlign:'top',spacing:0,spacingLeft:16,spacingRight:16,spacingTop:14,fontSize};
  if(c.kind==='layer') Object.assign(s,{shape:'swimlane',horizontal:1,startSize:c.subtitle?72:54,swimlaneFillColor:fill,swimlaneLine:1});
  objectCell(C(c.id),title(c.title,c.subtitle,fontSize),s,p?C(p.id):figure,x,y,c.w,c.h,{modelId:c.id,kind:c.kind,domainType:c.domainType,platform:c.platform,role:c.role,hosts:c.hosts?.join(','),evidence:c.evidence?.join(',')});
}
function nodeFill(n) {
  if(['memory','hardware'].includes(n.entityType))return '#edf0f2';
  if(n.configured)return '#ffffff';
  if(model.meta.colorMode==='origin')return colors[n.origin]||'#ffffff';
  if(model.meta.colorMode==='responsibility') {
    const party=parties.get(n.responsibleParty);
    return palette[party?.paletteKey||categoryPalette[party?.category]]||'#ffffff';
  }
  return '#edf3f8';
}
for(const n of model.nodes) {
  const p=containers.get(n.parent), x=n.x-p.x, y=n.y-p.y;
  const neutral=['memory','hardware'].includes(n.entityType);
  const fill=nodeFill(n);
  const s={...boxBase,fillColor:fill,strokeColor:neutral?'#9aa0a6':'#72808f',strokeWidth:theme.strokes.node,align:'center',verticalAlign:'middle',spacing:8,fontSize:theme.type.node,fontColor:neutral?ink:'#102116'};
  if(n.configured)Object.assign(s,{dashed:1,dashPattern:'6 5'});
  const label=title(displayName(n),n.description,theme.type.node,theme.code.nodeTypes.includes(n.entityType));
  const metadata={modelId:n.id,entityType:n.entityType,canonicalName:displayName(n),origin:n.origin,responsibleParty:n.responsibleParty,configured:n.configured,layerRole:n.layerRole,resourceId:n.resourceId,interfacePath:n.interfacePath,moduleName:n.moduleName,executionContext:n.executionContext,evidence:(n.evidence||[]).join(',')};
  if(n.entityType==='memory') {
    objectCell(N(n.id),'',{shape:'group',container:1,recursiveResize:0,collapsible:0,fillColor:'none',strokeColor:'none'},C(n.parent),x,y,n.w,n.h,metadata);
    vertex(N(n.id)+'-back','',s,N(n.id),8,0,n.w-8,n.h-8,{connectable:0});
    vertex(N(n.id)+'-middle','',s,N(n.id),4,4,n.w-8,n.h-8,{connectable:0});
    vertex(N(n.id)+'-front',label,s,N(n.id),0,8,n.w-8,n.h-8,{connectable:0});
  }else objectCell(N(n.id),label,s,C(n.parent),x,y,n.w,n.h,metadata);
}
const NORMAL={top:[0,-1],bottom:[0,1],left:[-1,0],right:[1,0]};
const same=(a,b)=>Math.abs(a-b)<0.001;
function anchor(n,side,offset=0) {
  if(side==='top')return{x:n.x+n.w/2+offset,y:n.y};
  if(side==='bottom')return{x:n.x+n.w/2+offset,y:n.y+n.h};
  if(side==='left')return{x:n.x,y:n.y+n.h/2+offset};
  return{x:n.x+n.w,y:n.y+n.h/2+offset};
}
function clean(points) {
  const out=[];
  for(const p of points) {
    const a=out.at(-1),b=out.at(-2);
    if(a&&same(a.x,p.x)&&same(a.y,p.y))continue;
    if(a&&!same(a.x,p.x)&&!same(a.y,p.y))throw new Error('Non-orthogonal route');
    if(b&&((same(b.x,a.x)&&same(a.x,p.x)&&(a.y-b.y)*(p.y-a.y)>0)||(same(b.y,a.y)&&same(a.y,p.y)&&(a.x-b.x)*(p.x-a.x)>0)))out.pop();
    out.push(p);
  }
  return out;
}
function route(e) {
  const fs=e.fromSide||'bottom',ts=e.toSide||'top';
  const a=anchor(nodes.get(e.from),fs,e.fromOffset||0),b=anchor(nodes.get(e.to),ts,e.toOffset||0);
  const points=[a];
  if(e.via?.length) {
    let p=a;
    for(const step of e.via){p={x:step.x??p.x,y:step.y??p.y};points.push(p);}
    if(!same(p.x,b.x)&&!same(p.y,b.y))points.push(['top','bottom'].includes(ts)?{x:b.x,y:p.y}:{x:p.x,y:b.y});
  }else {
    const u=NORMAL[fs],v=NORMAL[ts];
    const straight=(same(a.x,b.x)&&u[0]===0&&v[0]===0&&u[1]===-v[1]&&Math.sign(b.y-a.y)===u[1])||(same(a.y,b.y)&&u[1]===0&&v[1]===0&&u[0]===-v[0]&&Math.sign(b.x-a.x)===u[0]);
    if(!straight) {
      if(u[0]===0&&v[0]===0){const y=u[1]!==v[1]?(a.y+b.y)/2:u[1]<0?Math.min(a.y,b.y)-24:Math.max(a.y,b.y)+24;points.push({x:a.x,y},{x:b.x,y});}
      else if(u[1]===0&&v[1]===0){const x=u[0]!==v[0]?(a.x+b.x)/2:u[0]<0?Math.min(a.x,b.x)-24:Math.max(a.x,b.x)+24;points.push({x,y:a.y},{x,y:b.y});}
      else points.push(u[0]===0?{x:a.x,y:b.y}:{x:b.x,y:a.y});
    }
  }
  return clean([...points,b]);
}
function ancestors(n) {const ids=[];let p=n.parent;while(p){ids.push(p);p=containers.get(p)?.parent;}return [...ids,figure];}
function commonParent(a,b) {const other=new Set(ancestors(b));return ancestors(a).find(id=>other.has(id));}
function connection(n,side,offset=0) {
  if(side==='top'||side==='bottom')return{x:(n.w/2+offset)/n.w,y:side==='top'?0:1};
  return{x:side==='left'?0:1,y:(n.h/2+offset)/n.h};
}
function labelGeometry(points,position) {
  const lengths=points.slice(1).map((b,i)=>Math.hypot(b.x-points[i].x,b.y-points[i].y));
  const total=lengths.reduce((a,b)=>a+b,0);let best=null,walk=0;
  const target=position||{x:(points[0].x+points.at(-1).x)/2+44,y:(points[0].y+points.at(-1).y)/2};
  for(let i=0;i<lengths.length;i++) {
    const a=points[i],b=points[i+1],dx=b.x-a.x,dy=b.y-a.y;
    const t=Math.max(0,Math.min(1,((target.x-a.x)*dx+(target.y-a.y)*dy)/(lengths[i]**2)));
    const p={x:a.x+t*dx,y:a.y+t*dy},distance=Math.hypot(target.x-p.x,target.y-p.y);
    if(!best||distance<best.distance)best={distance,x:2*(walk+t*lengths[i])/total-1,dx:target.x-p.x,dy:target.y-p.y};
    walk+=lengths[i];
  }
  return `<mxGeometry ${attrs({x:best.x,y:0,relative:1,as:'geometry'})}><mxPoint ${attrs({x:best.dx,y:best.dy,as:'offset'})}/></mxGeometry>`;
}
const relations={dependency:{color:muted,width:theme.strokes.dependency},control:{color:'#356dc9',width:theme.strokes.control},data:{color:'#237a44',width:theme.strokes.data},notification:{color:'#356dc9',width:theme.strokes.notification,dash:'3 5'},config:{color:muted,width:theme.strokes.config,dash:'6 5'}};
const routes=new Map();
for(const e of model.edges) {
  const a=nodes.get(e.from),b=nodes.get(e.to),points=route(e),parent=commonParent(a,b),p=containers.get(parent),origin={x:p?.x||0,y:p?.y||0};
  const from=connection(a,e.fromSide||'bottom',e.fromOffset||0),to=connection(b,e.toSide||'top',e.toOffset||0),type=edgeType(e),paint=relations[type];
  if(points.length<2)throw new Error(`Route has fewer than two distinct points: ${e.id}`);
  routes.set(e.id,{points,type,parent,origin});
  const s={edgeStyle:'segmentEdgeStyle',rounded:0,curved:0,html:1,jumpStyle:'arc',jumpSize:2*theme.geometry.bridgeRadius,strokeColor:paint.color,strokeWidth:paint.width,startArrow:'none',endArrow:'open',endFill:0,endSize:theme.geometry.arrowLength,exitX:from.x,exitY:from.y,exitDx:0,exitDy:0,exitPerimeter:0,entryX:to.x,entryY:to.y,entryDx:0,entryDy:0,entryPerimeter:0,fontFamily:sans,fontSize:theme.type.label,fontColor:paint.color,labelBackgroundColor:'#ffffff',spacing:3};
  if(paint.dash)Object.assign(s,{dashed:1,dashPattern:paint.dash});
  const hints=points.slice(1,-1).map(p=>`<mxPoint ${attrs({x:p.x-origin.x,y:p.y-origin.y})}/>`).join('');
  const edgeXML=`<mxCell ${attrs({style:style(s),edge:1,parent:parent===figure?figure:C(parent),source:N(e.from),target:N(e.to)})}><mxGeometry relative="1" as="geometry">${hints?`<Array as="points">${hints}</Array>`:''}</mxGeometry></mxCell>`;
  cells.push(`<object ${attrs({id:E(e.id),label:'',modelId:e.id,relation:e.relation,mechanism:e.mechanism,evidence:(e.evidence||[]).join(',')})}>${edgeXML}</object>`);
  const label=e.label||(e.relation==='ipc'?e.mechanism:null);
  if(label) {
    const font=new RegExp(theme.code.textPattern).test(label)?mono:sans;
    const html=`<span style="font-family:${font};font-size:${theme.type.label}px;background:#ffffff;border-radius:${theme.radii.label}px;padding:2px 4px;">${esc(label)}</span>`;
    const align={start:'left',middle:'center',end:'right'}[e.labelPosition?.anchor||'middle'];
    cells.push(`<mxCell ${attrs({id:E(e.id)+'-label',value:html,style:style({edgeLabel:1,html:1,align,verticalAlign:'middle',resizable:0,connectable:0,fillColor:'none',strokeColor:'none',fontSize:theme.type.label,fontFamily:sans,fontColor:paint.color,spacing:0}),vertex:1,connectable:0,parent:E(e.id)})}>${labelGeometry(points,e.labelPosition)}</mxCell>`);
  }
}
// Match the shared renderer's true-common-prefix branch semantics. A native dot
// is an edge child, so no fake component or free-floating raster overlay is added.
function branchPoint(a,b) {
  if(!same(a[0].x,b[0].x)||!same(a[0].y,b[0].y))return null;
  let i=1,j=1,p={...a[0]};
  while(i<a.length&&j<b.length) {
    const da={x:Math.sign(a[i].x-p.x),y:Math.sign(a[i].y-p.y)},db={x:Math.sign(b[j].x-p.x),y:Math.sign(b[j].y-p.y)};
    if(da.x!==db.x||da.y!==db.y)break;
    const ra=Math.abs(a[i].x-p.x)+Math.abs(a[i].y-p.y),rb=Math.abs(b[j].x-p.x)+Math.abs(b[j].y-p.y),step=Math.min(ra,rb);
    p={x:p.x+da.x*step,y:p.y+da.y*step};
    if(same(step,ra))i++;if(same(step,rb))j++;
  }
  return (same(p.x,a[0].x)&&same(p.y,a[0].y))||i===a.length||j===b.length?null:p;
}
let branchDots=0;
for(const group of model.junctions||[]) {
  const seen=new Set();let count=0;
  for(let i=0;i<group.edges.length;i++)for(let j=i+1;j<group.edges.length;j++) {
    const owner=group.edges[i],r=routes.get(owner),point=branchPoint(r.points,routes.get(group.edges[j]).points);
    if(!point)continue;
    const key=`${point.x},${point.y}`;if(seen.has(key))continue;seen.add(key);
    const radius=theme.geometry.junctionRadius;
    const dotGeometry=labelGeometry(r.points,point).replace('<mxGeometry ',`<mxGeometry width="${2*radius}" height="${2*radius}" `).replace('x="0" y="0" as="offset"',`x="${-radius}" y="${-radius}" as="offset"`);
    cells.push(`<mxCell ${attrs({id:'junction-'+group.id+'-'+count++,value:'',vertex:1,connectable:0,parent:E(owner),style:style({shape:'ellipse',fillColor:relations[r.type].color,strokeColor:relations[r.type].color,movable:0,resizable:0}),junctionGroup:group.id,junctionEdges:group.edges.join(',')})}>${dotGeometry}</mxCell>`);
    branchDots++;
  }
  if(!count)throw new Error(`Junction has no real shared-prefix branch: ${group.id}`);
}
const legendY=100+model.canvas.height+20;
let lx=24;
const legendChip=(name,color)=>{
  const w=Math.max(110,name.length*7+40);
  vertex('legend-chip-'+lx,'',{...boxBase,arcSize:2*theme.radii.label,fillColor:color,strokeColor:border,strokeWidth:1},'1',lx,legendY+6,20,13);
  vertex('legend-text-'+lx,name,{...plainText,fontSize:theme.type.legend,fontColor:muted},'1',lx+28,legendY,w-28,24);lx+=w+24;
};
const software=model.nodes.filter(n=>!['hardware','memory'].includes(n.entityType)&&!n.configured);
if(model.meta.colorMode==='origin') {
  vertex('legend-origin-title','Component origin',{...plainText,fontSize:theme.type.legend,fontStyle:1},'1',lx,legendY,130,24);lx+=148;
  const used=new Set(software.map(n=>n.origin||'unknown'));
  for(const key of ['vendor','native','oem','unknown'])if(used.has(key))legendChip(originLabels[key]||{vendor:'Vendor / Tier1',native:'Native / Upstream',oem:'OEM / Custom',unknown:'Unspecified origin'}[key],colors[key]);
} else if(model.meta.colorMode==='responsibility') {
  const heading=model.meta.responsibilityBasis[0].toUpperCase()+model.meta.responsibilityBasis.slice(1)+' responsibility';
  const w=Math.max(180,heading.length*7);
  vertex('legend-responsibility-title',heading,{...plainText,fontSize:theme.type.legend,fontStyle:1},'1',lx,legendY,w,24);lx+=w+20;
  for(const id of new Set(software.map(n=>n.responsibleParty||'unknown'))) {
    const party=parties.get(id);legendChip(party?.label||'Unspecified party',palette[party?.paletteKey||categoryPalette[party?.category]]||'#ffffff');
  }
}
for(const [type,name,w] of [['dependency','Dependency',140],['control','Call / IPC',136],['data','Data',100],['notification','Notification / interrupt',230],['config','Configuration / allocation',226]]) {
  if(!model.edges.some(e=>edgeType(e)===type))continue;
  const paint=relations[type],s={edgeStyle:'none',strokeColor:paint.color,strokeWidth:paint.width,endArrow:'none',startArrow:'none',html:1};
  if(paint.dash)Object.assign(s,{dashed:1,dashPattern:paint.dash});
  cells.push(`<mxCell ${attrs({id:'legend-line-'+type,style:style(s),edge:1,parent:'1'})}><mxGeometry relative="1" as="geometry"><mxPoint ${attrs({x:lx,y:legendY+12,as:'sourcePoint'})}/><mxPoint ${attrs({x:lx+28,y:legendY+12,as:'targetPoint'})}/></mxGeometry></mxCell>`);
  vertex('legend-text-'+type,name,{...plainText,fontSize:theme.type.legend,fontColor:muted},'1',lx+36,legendY,w-36,24);lx+=w+24;
}
const fontVars=JSON.stringify({fontLicense,fontFamilies:Object.keys(fontSources).join('; '),fontVersions:fontManifest.fonts.map(f=>({family:f.family,file:f.file,sha256:f.sha256})),modelMeta:model.meta,deployment:model.deployment,sources:model.sources,parties:model.parties});
const xml=`<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="Electron" compressed="false" vars="${esc(fontVars)}"><diagram ${attrs({id:model.meta.id+'-editable',name:model.meta.title})}><mxGraphModel ${attrs({dx:model.canvas.width+48,dy:model.canvas.height+160,grid:0,gridSize:8,guides:1,tooltips:1,connect:1,arrows:1,fold:0,page:0,pageScale:1,pageWidth:model.canvas.width+48,pageHeight:model.canvas.height+160,math:0,shadow:0,background:'#ffffff',extFonts:Object.entries(fontSources).map(([name,url])=>name+'^'+url).join('|')})}><root>\n${cells.join('\n')}\n</root></mxGraphModel></diagram></mxfile>\n`;
await mkdir(dirname(resolve(output)),{recursive:true});
try {await writeFile(resolve(output),xml,{flag:overwrite?'w':'wx'});}
catch(error) {if(error.code==='EEXIST')throw new Error(`Output exists; preserve manual edits. Choose another path or use --overwrite only when replacement is intended: ${output}`);throw error;}
console.log(JSON.stringify({output:resolve(output),containers:model.containers.length,nodes:model.nodes.length,edges:model.edges.length,edgeLabels:model.edges.filter(e=>e.label||e.relation==='ipc').length,branchDots,colorMode:model.meta.colorMode,editable:true,warnings:report.warnings}));
