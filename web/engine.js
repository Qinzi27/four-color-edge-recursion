/** Plane-map geometry and coloring, shared verbatim by browser and Node tests.
 * Coordinates use a y-down drawing plane. Rotations use mathematical y=-screenY.
 * Color markers are selected once from four-bit candidate masks, without
 * backtracking or enumerating assignments. A blocked selection is not a proof
 * of non-four-colorability. The edge-side model checks completed assignments.
 */
export const VERSION = '0.2.0';
export const WIDTH = 900;
export const HEIGHT = 600;
export const LIMITS = Object.freeze({strokes:80, edges:1600, faces:400});
const EPS = 1e-7;
const KEY_SCALE = 1e6;
const cross = (a,b) => a[0]*b[1]-a[1]*b[0];
const sub = (a,b) => [a[0]-b[0],a[1]-b[1]];
const distance2 = (a,b) => (a[0]-b[0])**2+(a[1]-b[1])**2;
const key = p => Math.round(p[0]*KEY_SCALE)+','+Math.round(p[1]*KEY_SCALE);
const canonicalPoint = p => p.map(v=>Math.round(v*KEY_SCALE)/KEY_SCALE);

export class ModelError extends Error {
  constructor(message, code='geometry') { super(message); this.name='ModelError'; this.code=code; }
}

/** Validate untrusted JSON atomically before replacing any current drawing. */
export function normalizeDocument(input) {
  if (!input || typeof input!=='object' || !Array.isArray(input.strokes)) throw new ModelError('案例文件需要 strokes 线段数组。','input');
  if (input.schemaVersion!==undefined && input.schemaVersion!==1) throw new ModelError('不支持该案例文件版本。','input');
  if (input.strokes.length>LIMITS.strokes) throw new ModelError('最多支持 '+LIMITS.strokes+' 条原始线段。','limit');
  if (input.frame && (input.frame.width!==WIDTH || input.frame.height!==HEIGHT)) throw new ModelError('案例画框必须是 900 × 600。','input');
  function point(p) {
    if (!Array.isArray(p)||p.length!==2||p.some(v=>typeof v!=='number'||!Number.isFinite(v))) throw new ModelError('线段端点必须是两个有限数值。','input');
    if(p[0]<0||p[0]>WIDTH||p[1]<0||p[1]>HEIGHT) throw new ModelError('线段端点超出画框。','input');
    return p.map(v=>Math.round(v*1000)/1000);
  }
  const strokes=input.strokes.map((s,i)=>{
    if(!s||typeof s!=='object') throw new ModelError('第 '+(i+1)+' 条线段格式错误。','input');
    const a=point(s.a),b=point(s.b);
    if(distance2(a,b)<1e-10) throw new ModelError('第 '+(i+1)+' 条线段长度为零。','input');
    return {a,b};
  });
  return {schemaVersion:1, title:typeof input.title==='string'?input.title.slice(0,80):'我的地图', frame:{width:WIDTH,height:HEIGHT},strokes};
}

/** A fixed frame makes the outer face explicit and bounds virtual ray bridges. */
function sourcesFor(doc) {
  const p=[[0,0],[WIDTH,0],[WIDTH,HEIGHT],[0,HEIGHT]];
  return p.map((a,i)=>({a,b:p[(i+1)%4],kind:'frame',source:-1})).concat(doc.strokes.map((s,i)=>({...s,kind:'stroke',source:i})));
}

/** Node all proper intersections, T junctions and collinear overlaps, then union edges. */
export function planarize(sources) {
  const cuts=sources.map(()=>[0,1]);
  const add=(i,t)=>{if(t>=-EPS&&t<=1+EPS)cuts[i].push(Math.max(0,Math.min(1,t)));};
  for(let i=0;i<sources.length;i++)for(let j=i+1;j<sources.length;j++){
    const A=sources[i],B=sources[j],r=sub(A.b,A.a),s=sub(B.b,B.a),q=sub(B.a,A.a),den=cross(r,s);
    if(Math.abs(den)>1e-10){
      const t=cross(q,s)/den,u=cross(q,r)/den;
      if(t>=-EPS&&t<=1+EPS&&u>=-EPS&&u<=1+EPS){add(i,t);add(j,u);}
    }else if(Math.abs(cross(q,r))<EPS){
      // Every overlapping endpoint is a split location, including duplicates.
      const axis=Math.abs(r[0])>=Math.abs(r[1])?0:1;
      const axisB=Math.abs(s[0])>=Math.abs(s[1])?0:1;
      add(i,(B.a[axis]-A.a[axis])/r[axis]);add(i,(B.b[axis]-A.a[axis])/r[axis]);
      add(j,(A.a[axisB]-B.a[axisB])/s[axisB]);add(j,(A.b[axisB]-B.a[axisB])/s[axisB]);
    }
  }
  const vertices=[],ids=new Map(),edges=[],seen=new Map();
  const vertex=p=>{const k=key(p);if(!ids.has(k)){ids.set(k,vertices.length);vertices.push(canonicalPoint(p));}return ids.get(k);};
  sources.forEach((source,i)=>{
    const ts=cuts[i].sort((a,b)=>a-b),r=sub(source.b,source.a);
    for(let n=1;n<ts.length;n++){
      const a=vertex([source.a[0]+r[0]*ts[n-1],source.a[1]+r[1]*ts[n-1]]);
      const b=vertex([source.a[0]+r[0]*ts[n],source.a[1]+r[1]*ts[n]]);
      if(a===b)continue;
      const k=Math.min(a,b)+':'+Math.max(a,b);
      if(seen.has(k)){
        const old=edges[seen.get(k)];
        if(source.kind!=='virtual')old.virtual=false;
        if(source.kind==='frame')old.frame=true;
        if(source.source>=0&&!old.sources.includes(source.source))old.sources.push(source.source);
      }else{
        seen.set(k,edges.length);edges.push({a,b,virtual:source.kind==='virtual',frame:source.kind==='frame',sources:source.source<0?[]:[source.source]});
      }
    }
  });
  if(edges.length>LIMITS.edges)throw new ModelError('交点太密集，细分边数超过 '+LIMITS.edges+'；请减少线段。','limit');
  return {vertices,edges};
}

function components(graph) {
  const adjacent=graph.vertices.map(()=>[]);
  for(const e of graph.edges){adjacent[e.a].push(e.b);adjacent[e.b].push(e.a);}
  const labels=Array(graph.vertices.length).fill(-1);let count=0;
  for(let v=0;v<labels.length;v++)if(labels[v]===-1){
    labels[v]=count;const stack=[v];
    while(stack.length){const u=stack.pop();for(const w of adjacent[u])if(labels[w]===-1){labels[w]=count;stack.push(w);}}
    count++;
  }
  return {labels,count};
}

/** Connect islands with invisible graph bridges; rebuild them after every edit.
 * Each new bridge joins distinct components, preserving every actual face.
 */
export function buildMap(input) {
  const doc=normalizeDocument(input),sources=sourcesFor(doc);
  let graph=planarize(sources),parts=components(graph);
  const original={vertices:graph.vertices.length,edges:graph.edges.length,components:parts.count};
  const expectedFaces=original.edges-original.vertices+original.components+1;
  for(let iteration=0;parts.count>1;iteration++){
    if(iteration>LIMITS.strokes*2)throw new ModelError('岛屿连接未收敛，请检查重合边界。');
    const frameVertex=graph.vertices.findIndex(p=>key(p)==='0,0'),framePart=parts.labels[frameVertex];
    const component=parts.labels.find(c=>c!==framePart);
    const candidates=graph.vertices.map((p,i)=>({p,i})).filter(v=>parts.labels[v.i]===component)
      .sort((u,v)=>v.p[0]-u.p[0]||u.p[1]-v.p[1]);
    const {p:start}=candidates[0];let nearest=Infinity;
    for(const e of graph.edges){
      if(parts.labels[e.a]===component)continue;
      const a=graph.vertices[e.a],b=graph.vertices[e.b];
      if(Math.abs(a[1]-b[1])<EPS){
        if(Math.abs(start[1]-a[1])<EPS)for(const p of [a,b])if(p[0]>start[0]+EPS)nearest=Math.min(nearest,p[0]);
      }else{
        const t=(start[1]-a[1])/(b[1]-a[1]);
        if(t>=-EPS&&t<=1+EPS){const x=a[0]+t*(b[0]-a[0]);if(x>start[0]+EPS)nearest=Math.min(nearest,x);}
      }
    }
    if(!Number.isFinite(nearest))throw new ModelError('无法稳定连接岛屿，请把过近的边界稍微移开。');
    sources.push({a:start,b:[nearest,start[1]],kind:'virtual',source:-1});
    const oldCount=parts.count;
    graph=planarize(sources);parts=components(graph);
    if(parts.count>=oldCount)throw new ModelError('边界距离低于几何计算精度，请稍微移开重合端点。');
  }
  const rotation=graph.vertices.map(()=>[]);
  graph.edges.forEach((e,i)=>{rotation[e.a].push(2*i);rotation[e.b].push(2*i+1);});
  const tail=d=>graph.edges[d>>1][d%2?'b':'a'];
  const head=d=>tail(d^1);
  // Negate y because screen y increases downward.
  for(let v=0;v<rotation.length;v++)rotation[v].sort((d,e)=>{
    const p=graph.vertices[v],a=graph.vertices[head(d)],b=graph.vertices[head(e)];
    return Math.atan2(-(a[1]-p[1]),a[0]-p[0])-Math.atan2(-(b[1]-p[1]),b[0]-p[0]);
  });
  const previous=Array(graph.edges.length*2);
  for(const order of rotation)order.forEach((d,i)=>previous[d]=order[(i+order.length-1)%order.length]);
  const faceOfDart=Array(graph.edges.length*2).fill(-1),faces=[];
  for(let start=0;start<faceOfDart.length;start++)if(faceOfDart[start]===-1){
    const darts=[];let d=start;
    while(faceOfDart[d]===-1){faceOfDart[d]=faces.length;darts.push(d);d=previous[d^1];}
    if(d!==start)throw new ModelError('面遍历未闭合。');
    const points=darts.map(d=>graph.vertices[tail(d)]);
    let area=0;for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length];area-=(a[0]*b[1]-b[0]*a[1])/2;}
    faces.push({darts,points,area});
  }
  if(faces.length>LIMITS.faces)throw new ModelError('闭合区域超过 '+LIMITS.faces+'；请减少线段。','limit');
  const outerFaces=faces.map((f,i)=>({f,i})).filter(({f})=>f.area< -EPS);
  if(outerFaces.length!==1||faces.some(f=>Math.abs(f.area)<EPS))throw new ModelError('出现数值不稳定的极细区域，请把过近的线段稍微移开。');
  if(graph.vertices.length-graph.edges.length+faces.length!==2||faces.length!==expectedFaces)throw new ModelError('平面嵌入校验失败，不能可靠识别这些区域。');
  const areaSum=faces.filter(f=>f.area>0).reduce((s,f)=>s+f.area,0);
  if(Math.abs(areaSum-WIDTH*HEIGHT)>0.01)throw new ModelError('区域面积没有完整覆盖画框。');
  for(let i=0;i<graph.edges.length;i++)if(graph.edges[i].virtual&&faceOfDart[2*i]!==faceOfDart[2*i+1])throw new ModelError('隐藏连接改变了分区，已停止着色。');
  const adjacency=faces.map(()=>new Set());
  graph.edges.forEach((e,i)=>{const a=faceOfDart[2*i],b=faceOfDart[2*i+1];if(a!==b){adjacency[a].add(b);adjacency[b].add(a);}});
  return {...graph,rotation,faceOfDart,faces,outerFace:outerFaces[0].i,adjacency:adjacency.map(s=>[...s].sort((a,b)=>a-b)),original,document:doc};
}

/** Direct marker selection: maintain candidate masks, select one bit, never retry.
 * Priority: smallest candidate set, highest dual degree, then lowest face ID.
 * This is a deterministic greedy rule, NOT a complete four-coloring algorithm.
 * Optional fixedColors model a partial coloring; fixed choices are never changed.
 */
export function selectMarkers(map, options={}) {
  const start=performance.now(), size=map.faces.length;
  const colors=options.fixedColors===undefined?Array(size).fill(-1):[...options.fixedColors];
  if(colors.length!==size||colors.some(c=>!Number.isInteger(c)||c< -1||c>3))throw new ModelError('固定色标必须逐面给出 -1 或 0..3。','input');
  if(colors[map.outerFace]!==-1&&colors[map.outerFace]!==0)throw new ModelError('画框外部固定使用色标 1（00）。','input');
  colors[map.outerFace]=0;
  for(let f=0;f<size;f++)if(colors[f]>=0&&map.adjacency[f].some(n=>colors[n]===colors[f]))throw new ModelError('固定色标在相邻面之间冲突。','input');
  const masks=colors.map((c,f)=>c>=0?1<<c:map.adjacency[f].reduce((m,n)=>colors[n]<0?m:m&~(1<<colors[n]),15));
  const trace=colors.flatMap((color,face)=>color<0?[]:[{type:'fixed',face,color,candidates:1<<color}]);
  const popcount=mask=>(mask&1)+((mask>>1)&1)+((mask>>2)&1)+((mask>>3)&1);
  let blockedFace=null;
  while(true){
    let chosen=-1,bestCount=5,bestDegree=-1;
    // Visit face records to choose an order; do not enumerate coloring schemes.
    for(let f=0;f<size;f++)if(colors[f]<0){
      const count=popcount(masks[f]),degree=map.adjacency[f].length;
      if(count<bestCount||count===bestCount&&degree>bestDegree){chosen=f;bestCount=count;bestDegree=degree;}
    }
    if(chosen<0)break;
    if(masks[chosen]===0){blockedFace=chosen;break;}
    const candidates=masks[chosen],bit=candidates&-candidates,color=Math.log2(bit);
    const neighbors=map.adjacency[chosen].filter(n=>colors[n]>=0).map(face=>({face,color:colors[face]}));
    colors[chosen]=color;masks[chosen]=bit;
    trace.push({type:'select',face:chosen,color,candidates,neighbors});
    // Only neighboring candidate sets change; no assigned face is revisited.
    for(const n of map.adjacency[chosen])if(colors[n]<0)masks[n]&=~bit;
  }
  const blockingNeighbors=blockedFace===null?[]:map.adjacency[blockedFace].filter(n=>colors[n]>=0).map(face=>({face,color:colors[face]}));
  return {status:blockedFace===null?'solved':'blocked',colors,masks,blockedFace,blockingNeighbors,
    assignments:trace.length,backtracks:0,trace,algorithm:'candidate-mask / most-constrained-first / lowest-bit / no-backtracking',
    elapsedMs:Math.round((performance.now()-start)*100)/100};
}

/** Independently check shore labels, primal conservation and dual reconstruction. */
export function verifyColoring(map,colors) {
  if(!Array.isArray(colors)||colors.length!==map.faces.length||colors.some(c=>!Number.isInteger(c)||c<0||c>3))throw new ModelError('颜色证书格式错误。');
  const differences=map.edges.map((e,i)=>colors[map.faceOfDart[2*i]]^colors[map.faceOfDart[2*i+1]]);
  const adjacency=map.edges.every((e,i)=>map.faceOfDart[2*i]===map.faceOfDart[2*i+1]||differences[i]!==0);
  const bridges=map.edges.every((e,i)=>map.faceOfDart[2*i]!==map.faceOfDart[2*i+1]||differences[i]===0);
  const defects=map.rotation.map(darts=>darts.reduce((sum,d)=>sum^differences[d>>1],0));
  const links=map.faces.map(()=>[]);
  map.edges.forEach((e,i)=>{const a=map.faceOfDart[2*i],b=map.faceOfDart[2*i+1];links[a].push([b,differences[i]]);links[b].push([a,differences[i]]);});
  const recovered=Array(map.faces.length).fill(null);recovered[map.outerFace]=0;const queue=[map.outerFace];let dual=true;
  for(let k=0;k<queue.length;k++)for(const [v,d]of links[queue[k]]){
    const expected=recovered[queue[k]]^d;
    if(recovered[v]===null){recovered[v]=expected;queue.push(v);}else if(recovered[v]!==expected)dual=false;
  }
  dual=dual&&recovered.every(c=>c!==null)&&colors.every((c,i)=>(c^colors[map.outerFace])===recovered[i]);
  const euler=map.vertices.length-map.edges.length+map.faces.length===2;
  return {passed:adjacency&&bridges&&defects.every(d=>d===0)&&dual&&euler,adjacency,bridges,vertexConservation:defects.every(d=>d===0),dualConsistency:dual,euler,differences,defects,recovered};
}

export function analyzeDrawing(input,options={}) {
  const map=buildMap(input);
  const selection=options.colorize===false?{status:'uncolored',colors:null,assignments:0,backtracks:0,trace:[]}:selectMarkers(map,options);
  const verification=selection.status==='solved'?verifyColoring(map,selection.colors):null;
  if(verification&&!verification.passed)throw new ModelError('着色验证未通过，结果已拒绝。');
  return {map,selection,verification};
}

/** Plain JSON certificate can be reconstructed with the repository's Python core. */
export function exportDocument(doc,result=null) {
  const normalized=normalizeDocument(doc);
  const exported={...normalized,algorithmVersion:VERSION,precision:{inputGrid:0.001,intersectionKey:1e-6},result:null};
  if(result){
    const {map,selection,verification}=result;
    exported.result={vertices:map.vertices,edges:map.edges,rotation:map.rotation,faceOfDart:map.faceOfDart,faces:map.faces.map(f=>f.darts),outerFace:map.outerFace,colors:selection.colors,selection:{status:selection.status,assignments:selection.assignments,backtracks:0,algorithm:selection.algorithm,blockedFace:selection.blockedFace,trace:selection.trace},verification};
  }
  return exported;
}
