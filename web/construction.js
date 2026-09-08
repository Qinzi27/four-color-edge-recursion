/** Certified line-first construction. No coloring search or greedy fallback.
 * Geometry supplies side-continuation orbits; committed ordered line names
 * supply all old symbols. A split changes ONE daughter side, freezing all
 * other old side spaces. The two-contact theorem is checked before commit.
 */
import {buildMap,normalizeDocument,verifyColoring,WIDTH,HEIGHT} from './engine.js';
export const CONSTRUCTION_VERSION='1.0.0';
const TOL=1e-5;
const near=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1])<TOL;
const cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1]];
const midpoint=(a,b)=>[(a[0]+b[0])/2,(a[1]+b[1])/2];
export const lineId=(a,b)=>a.join(',')+'>'+b.join(',');

/** Inclusive geometric membership, used only with validated finite points. */
export function onSegment(p,a,b){
  const ab=sub(b,a),ap=sub(p,a),len=Math.hypot(...ab);
  return len>TOL&&Math.abs(cross(ab,ap))/len<TOL&&ap[0]*ab[0]+ap[1]*ab[1]>=-TOL*len
    &&(p[0]-b[0])*ab[0]+(p[1]-b[1])*ab[1]<=TOL*len;
}

/** Public anchors are real geometry only; invisible bridges are never anchors. */
export function isAnchor(state,p){return state.map.edges.some(e=>!e.virtual&&onSegment(p,state.map.vertices[e.a],state.map.vertices[e.b]));}

/** Return a single intersection, an overlap, or null. */
function contact(a,b,c,d){
  const r=sub(b,a),s=sub(d,c),q=sub(c,a),den=cross(r,s);
  if(Math.abs(den)>1e-9){const t=cross(q,s)/den,u=cross(q,r)/den;
    return t>=-1e-9&&t<=1+1e-9&&u>=-1e-9&&u<=1+1e-9?{point:[a[0]+t*r[0],a[1]+t*r[1]]}:null;}
  if(Math.abs(cross(q,r))/Math.hypot(...r)>TOL)return null;
  const common=[a,b,c,d].filter(p=>onSegment(p,a,b)&&onSegment(p,c,d));
  const unique=common.filter((p,i)=>!common.slice(0,i).some(q=>near(p,q)));
  return unique.length>1?{overlap:true}:unique.length?{point:unique[0]}:null;
}

/** Read one symbol per derived side orbit FROM line names, never solve for it. */
export function readSideNames(map,names){
  if(!Array.isArray(names)||names.length!==map.edges.length||names.some(p=>!Array.isArray(p)||p.length!==2||p.some(c=>!Number.isInteger(c)||c<0||c>3)))throw new Error('线名必须逐边给出两个 0..3 色标。');
  const colors=Array(map.faces.length).fill(null);
  names.forEach((pair,e)=>pair.forEach((symbol,side)=>{const f=map.faceOfDart[2*e+side];if(colors[f]!==null&&colors[f]!==symbol)throw new Error('同侧线名不一致。');colors[f]=symbol;}));
  if(colors.some(c=>c===null)||!verifyColoring(map,colors).passed)throw new Error('线名证书不合法。');
  return colors;
}

/** Starting names are explicit. Non-default seeds are audited precolorings. */
export function createConstruction(seed=null){
  const document=normalizeDocument(seed?.document||{title:'已证明规则 · 空白画框',strokes:[]});
  const map=buildMap(document);
  if(seed&&!seed.names)throw new Error('导入起始地图必须同时提供已验证的线名，不能隐藏调用求解器。');
  const names=seed?structuredClone(seed.names):map.edges.map((e,i)=>[0,1].map(side=>map.faceOfDart[2*i+side]===map.outerFace?0:1));
  const colors=readSideNames(map,names);
  if(colors[map.outerFace]!==0)throw new Error('外部侧符号必须是 1（内部编码 0）。');
  return {document,map,names,colors,sideIds:map.faces.map((_,i)=>'S'+i),history:[],
    initial:{document:structuredClone(document),names:structuredClone(names)},verification:verifyColoring(map,colors)};
}

/** Locate an old side via the nearest REAL line crossed by an eastward ray. */
function locateSide(map,p){
  let best=Infinity,face=null;
  map.edges.forEach((e,i)=>{if(e.virtual)return;const a=map.vertices[e.a],b=map.vertices[e.b];
    if((a[1]>p[1])===(b[1]>p[1]))return;
    const x=a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]);
    if(x>p[0]+TOL&&x<best){best=x;face=map.faceOfDart[2*i+(b[1]>a[1]?1:0)];}});
  if(face===null)throw new Error('无法从已知线定位新路径的侧空间。');return face;
}

/** Validate a whole stroke transaction before changing any committed names. */
function validatePath(state,input){
  if(!Array.isArray(input)||input.length<2||input.length>81)throw new Error('路径需要 2–81 个点。');
  const segments=input.slice(1).map((b,i)=>({a:input[i],b}));
  const clean=normalizeDocument({strokes:segments}).strokes;
  const points=[clean[0].a,...clean.map(s=>s.b)],closed=near(points[0],points.at(-1));
  if(closed&&points.length<4)throw new Error('闭环至少需要三条非重叠线段。');
  for(let i=0;i<clean.length;i++)for(let j=i+1;j<clean.length;j++){
    const hit=contact(clean[i].a,clean[i].b,clean[j].a,clean[j].b);if(!hit)continue;
    const adjoining=j===i+1||(closed&&i===0&&j===clean.length-1);
    const shared=j===i+1?clean[i].b:points[0];
    if(hit.overlap||!adjoining||!near(hit.point,shared))throw new Error('路径自交或重叠；请拆成不自交的基本操作。');
  }
  for(const segment of clean)for(const e of state.map.edges){if(e.virtual)continue;
    const hit=contact(segment.a,segment.b,state.map.vertices[e.a],state.map.vertices[e.b]);if(!hit)continue;
    if(hit.overlap||closed||(!near(hit.point,points[0])&&!near(hit.point,points.at(-1))))throw new Error('路径途中碰到旧线或与旧线重叠；请在第一次接触处结束，再开始下一笔。');
  }
  return {points,segments:clean,closed,anchored:!closed&&isAnchor(state,points[0])&&isAnchor(state,points.at(-1))};
}

/** Attempt a single transaction. Failure returns the SAME prior state. */
export function commitPath(state,input){
  let path;
  try{path=validatePath(state,input);}catch(error){return {status:'invalid',message:error.message,state,points:input};}
  if(!path.closed&&!path.anchored)return {status:'draft',message:'尚未完成锚定：两端接回边界/已知线，或完成独立闭环后才能提交。',state,points:path.points};
  try{
    const oldColors=readSideNames(state.map,state.names),offset=state.document.strokes.length;
    const document=normalizeDocument({...state.document,strokes:[...state.document.strokes,...path.segments]});
    const map=buildMap(document),parents=Array(map.faces.length).fill(null);
    const bind=(child,parent)=>{if(parents[child]!==null&&parents[child]!==parent)throw new Error('旧侧身份映射不一致，已拒绝提交。');parents[child]=parent;};
    const ancestors=Array(map.edges.length).fill(null);
    // A new subsegment of an old real line inherits each side's identity.
    map.edges.forEach((e,i)=>{if(e.virtual)return;const a=map.vertices[e.a],b=map.vertices[e.b],m=midpoint(a,b);
      const old=state.map.edges.findIndex(q=>!q.virtual&&onSegment(m,state.map.vertices[q.a],state.map.vertices[q.b]));
      if(old<0)return;const q=state.map.edges[old],u=state.map.vertices[q.a],v=state.map.vertices[q.b];
      const same=(b[0]-a[0])*(v[0]-u[0])+(b[1]-a[1])*(v[1]-u[1])>0;
      bind(map.faceOfDart[2*i],state.map.faceOfDart[2*old+(same?0:1)]);
      bind(map.faceOfDart[2*i+1],state.map.faceOfDart[2*old+(same?1:0)]);
      ancestors[i]=lineId(u,v);
    });
    const parent=locateSide(state.map,midpoint(path.segments[0].a,path.segments[0].b));
    map.edges.forEach((e,i)=>{if(e.sources.some(s=>s>=offset)){bind(map.faceOfDart[2*i],parent);bind(map.faceOfDart[2*i+1],parent);}});
    if(parents.some(p=>p===null))throw new Error('侧谱系不完整，已拒绝提交。');
    const delta=map.faces.length-state.map.faces.length;
    if(delta!==0&&delta!==1)throw new Error('这一笔不是一次基本连接/分割。');
    const deltaComponents=map.original.components-state.map.original.components;
    if(path.closed?(delta!==1||deltaComponents!==1):delta!==1+deltaComponents)throw new Error('真实连通分量与分割增量不符，已拒绝提交。');
    const daughters=parents.flatMap((p,i)=>p===parent?[i]:[]),oldSymbol=oldColors[parent];
    if(daughters.length!==delta+1)throw new Error('分割父子关系校验失败。');
    const colors=parents.map(p=>oldColors[p]),sideIds=parents.map(p=>state.sideIds[p]);
    const options=daughters.map(child=>{
      // Read opposing symbols along the child's OLD real boundary lines.
      const external=new Set(),boundary=[];
      for(const d of map.faces[child].darts){const i=d>>1,e=map.edges[i],other=map.faceOfDart[d^1];
        if(e.virtual||parents[other]===parent)continue;
        external.add(oldColors[parents[other]]);boundary.push({line:lineId(map.vertices[e.a],map.vertices[e.b]),oppositeSymbol:oldColors[parents[other]]});}
      const symbols=[...external].sort(),available=[0,1,2,3].filter(c=>c!==oldSymbol&&!external.has(c));
      return {child,externalSymbols:symbols,available,boundary};
    });
    let selected=null;
    if(delta===1){
      selected=options.filter(o=>o.externalSymbols.length<=2&&o.available.length).sort((a,b)=>a.externalSymbols.length-b.externalSymbols.length||a.child-b.child)[0];
      if(!selected)return {status:'blocked',message:'两侧都遇到其余三种符号：冻结其他旧侧时无法扩张。停止本规则，不增加第五色，也不回溯。',state,points:path.points,
        certificate:{parent:state.sideIds[parent],parentSymbol:oldSymbol,options,scope:'This fixed precoloring cannot extend; not a non-four-colorability certificate.'}};
      colors[selected.child]=selected.available[0];
      daughters.forEach((f,i)=>{sideIds[f]=state.sideIds[parent]+'.'+i;});
    }
    const names=map.edges.map((e,i)=>[colors[map.faceOfDart[2*i]],colors[map.faceOfDart[2*i+1]]]);
    readSideNames(map,names);
    const verification=verifyColoring(map,colors);
    const changedLines=map.edges.flatMap((e,i)=>{
      if(e.virtual)return [];const a=map.vertices[e.a],b=map.vertices[e.b];
      return [{id:lineId(a,b),sourceLines:e.sources,ancestor:ancestors[i],name:names[i],left:sideIds[map.faceOfDart[2*i]],right:sideIds[map.faceOfDart[2*i+1]]}];
    });
    const event={step:state.history.length+1,kind:delta?'split':'bridge',points:path.points,closed:path.closed,
      parent:state.sideIds[parent],parentSymbol:oldSymbol,children:daughters.map(f=>({id:sideIds[f],symbol:colors[f],inherits:colors[f]===oldSymbol})),
      externalSymbols:selected?.externalSymbols??[],selectedSymbol:selected?colors[selected.child]:null,
      deltaFaces:delta,deltaComponents,
      backtracks:0,lineNames:changedLines};
    const next={document,map,names,colors,sideIds,history:[...state.history,event],initial:state.initial,verification};
    return {status:event.kind,message:delta?'分割完成，线名与四符号证书已验证。':'连接完成但未分割：桥两侧仍同名。',state:next,event,points:path.points};
  }catch(error){return {status:'invalid',message:error.message,state,points:path.points};}
}

/** Export operations and exact witnesses, not a screenshot-only success claim. */
export function exportConstruction(state,pending=[]){return {kind:'line-first-construction',schemaVersion:1,algorithmVersion:CONSTRUCTION_VERSION,
  seed:structuredClone(state.initial),operations:state.history.map(e=>structuredClone(e.points)),pending:structuredClone(pending),
  certificate:{names:structuredClone(state.names),sideIds:[...state.sideIds],history:structuredClone(state.history),verified:state.verification.passed}};}

/** Recompute every operation. Imported certificates never become trusted input. */
export function importConstruction(input){
  if(!input||input.kind!=='line-first-construction'||input.schemaVersion!==1||!Array.isArray(input.operations)||input.operations.length>80)throw new Error('不是受支持的线命名实验文件。');
  let state=createConstruction(input.seed);
  for(const points of input.operations){const result=commitPath(state,points);if(!['split','bridge'].includes(result.status))throw new Error('导入重放失败：'+result.message);state=result.state;}
  if(input.certificate&&(JSON.stringify(input.certificate.names)!==JSON.stringify(state.names)||JSON.stringify(input.certificate.sideIds)!==JSON.stringify(state.sideIds)||JSON.stringify(input.certificate.history)!==JSON.stringify(state.history)))throw new Error('保存的证书与重新计算结果不一致。');
  const pending=input.pending??[];
  if(!Array.isArray(pending)||pending.length>81||pending.some(p=>!Array.isArray(p)||p.length!==2||p.some(x=>typeof x!=='number'||!Number.isFinite(x))||p[0]<0||p[0]>WIDTH||p[1]<0||p[1]>HEIGHT))throw new Error('草稿点格式错误。');
  return {state,pending:structuredClone(pending)};
}
