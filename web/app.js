/** UI actions share one validated model. Workers identify regions and select markers. */
import {WIDTH,HEIGHT,normalizeDocument,exportDocument} from './engine.js';
import {CASES,caseDocument} from './cases.js';
import {registerMapTools} from './webmcp.js';
const $=id=>document.getElementById(id),canvas=$('canvas');
const NS='http://www.w3.org/2000/svg',PALETTE=['#63bbea','#ffcd4d','#b795e3','#61c8a8'];
let drawing=caseDocument('tetrahedron'),activeCase='tetrahedron',result=null;
let mode='draw',anchor=null,press=null,selectedEdge=null,worker=null,pending=null,requestId=0;
const undoStack=[],distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const marker=c=>c>=0?`${c+1} (${c.toString(2).padStart(2,'0')})`:'未赋色';
const maskText=m=>'{'+[0,1,2,3].filter(c=>m&(1<<c)).map(c=>c+1).join(', ')+'}';
function node(tag,attrs={},text=null){const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==null)n.textContent=text;return n;}
function paragraph(text){const n=document.createElement('p');n.textContent=text;return n;}
function error(message=''){$('error').hidden=!message;$('error').textContent=message;}
function closest(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0;return[a[0]+t*dx,a[1]+t*dy];}
function inside(p,polygon){let yes=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){const a=polygon[i],b=polygon[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes;}return yes;}
/** Interior labels must not land in a hole of an annular face. */
function labelPoint(points){
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  let best=null,clearance=-1;
  for(let i=0;i<9;i++)for(let j=0;j<9;j++){const p=[minX+(i+.5)*(maxX-minX)/9,minY+(j+.5)*(maxY-minY)/9];if(!inside(p,points))continue;const d=Math.min(...points.map((a,k)=>distance(p,closest(p,a,points[(k+1)%points.length]))));if(d>clearance){best=p;clearance=d;}}
  return clearance>12?best:null;
}
function renderCanvas(){
  canvas.replaceChildren();const colors=result?.selection.colors;
  canvas.append(node('rect',{x:-18,y:-18,width:936,height:636,fill:colors?PALETTE[0]:'#e7eef5'}),node('rect',{width:WIDTH,height:HEIGHT,fill:'#fff'}));
  if(result){
    const{map,selection}=result;
    map.faces.forEach((face,f)=>{if(f===map.outerFace)return;const d=face.points.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ')+'Z',path=node('path',{d,fill:colors?.[f]>=0?PALETTE[colors[f]]:'#f4f7fa','fill-rule':'evenodd'});if(selection.blockedFace===f){path.setAttribute('fill','#ffd5d5');path.setAttribute('stroke','#c63838');path.setAttribute('stroke-width','5');}path.append(node('title',{},`F${f} · 色标 ${marker(colors?.[f])}`));canvas.append(path);});
    map.edges.forEach((e,i)=>{if(e.virtual)return;const a=map.vertices[e.a],b=map.vertices[e.b];canvas.append(node('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:i===selectedEdge?'#f04b32':'#18314c','stroke-width':i===selectedEdge?6:e.frame?3:2.3,'stroke-linecap':'round'}));});
    if(map.faces.length<=60)map.faces.forEach((face,f)=>{if(f===map.outerFace||face.area<600)return;const p=labelPoint(face.points);if(p)canvas.append(node('text',{x:p[0],y:p[1],'text-anchor':'middle','dominant-baseline':'middle',fill:'#10283e','font-size':17,'font-family':'system-ui,sans-serif','pointer-events':'none'},`F${f}${colors?.[f]>=0?' · '+(colors[f]+1):''}`));});
    if(selectedEdge!==null){const e=map.edges[selectedEdge],a=map.vertices[e.a],b=map.vertices[e.b],length=distance(a,b),u=[(b[0]-a[0])/length,(b[1]-a[1])/length],m=[(a[0]+b[0])/2,(a[1]+b[1])/2],tip=[m[0]+u[0]*10,m[1]+u[1]*10];canvas.append(node('path',{d:`M${tip}L${m[0]-u[0]*7+u[1]*8},${m[1]-u[1]*7-u[0]*8}L${m[0]-u[0]*7-u[1]*8},${m[1]-u[1]*7+u[0]*8}Z`,fill:'#b91f18'}));}
  }else{for(const s of drawing.strokes)canvas.append(node('line',{x1:s.a[0],y1:s.a[1],x2:s.b[0],y2:s.b[1],stroke:'#18314c','stroke-width':2.3}));canvas.append(node('rect',{width:WIDTH,height:HEIGHT,fill:'none',stroke:'#18314c','stroke-width':3}));}
  canvas.append(node('g',{id:'pending-line','pointer-events':'none'}));
}
function renderDetails(){
  $('map-title').textContent=drawing.title;$('map-description').textContent=CASES.find(c=>c.id===activeCase)?.description||'画线分区 · 直接选色标 · 不回溯';$('undo').disabled=!undoStack.length;
  for(const button of $('cases').children)button.classList.toggle('active',button.dataset.case===activeCase);
  const detail=$('edge-detail');detail.replaceChildren();
  if(result&&selectedEdge!==null){const{map,selection}=result,e=map.edges[selectedEdge],left=map.faceOfDart[2*selectedEdge],right=map.faceOfDart[2*selectedEdge+1];detail.append(paragraph(`e${selectedEdge}：沿红色箭头前进`),paragraph(`左侧 F${left}：${marker(selection.colors?.[left])}`),paragraph(`右侧 F${right}：${marker(selection.colors?.[right])}`));if(selection.colors?.[left]>=0&&selection.colors?.[right]>=0)detail.append(paragraph(`边差分：${(selection.colors[left]^selection.colors[right]).toString(2).padStart(2,'0')}`));if(left===right)detail.append(paragraph('同一面在两侧：这是桥，不造成新分区。'));if(e.frame)detail.append(paragraph(`画框边界；外部面是 F${map.outerFace}。`));}
  else detail.append(paragraph('切换「查边」，点一条边，查看方向及左右两面的颜色。'));
  const checks=$('checks'),history=$('history');checks.replaceChildren();history.replaceChildren();
  if(!result){$('stats').textContent=`${drawing.strokes.length} 条原始线段`;$('solver-detail').textContent='识别分区后，用候选色标集合直接选择；不枚举着色方案。';return;}
  const{map,selection,verification}=result;$('stats').textContent=`${map.faces.length-1} 个画框内区域 · 外部另计 1 面 · ${drawing.strokes.length} 条线段`;
  const rows=verification?[[verification.adjacency,'相邻面异色'],[verification.bridges,'桥两侧同面，差分为零'],[verification.vertexConservation,'原图每个顶点缺陷为零'],[verification.dualConsistency,'对偶闭路差分一致'],[verification.euler,'欧拉关系成立']]:[[true,'平面嵌入与区域面积检查通过'],[false,selection.status==='blocked'?'存在未赋色面，不签发完整证书':'尚未进行色标选择']];
  for(const[pass,text]of rows){const li=document.createElement('li');li.textContent=(pass?'✓ ':'○ ')+text;checks.append(li);}
  $('solver-detail').textContent=selection.status==='uncolored'?'自动填色已关闭。点击「选取色标并验证」运行一次选择。':`每面最多赋色一次；已赋色 ${selection.assignments}/${map.faces.length} 面，回溯 0 次。候选最少优先 → 直接取最低可用色标。${selection.status==='blocked'?` F${selection.blockedFace} 的候选集为空；这是当前规则阻塞，不是地图需要第五色。`:''}`;
  for(const step of selection.trace){const li=document.createElement('li');li.textContent=step.type==='fixed'?`F${step.face}：固定色标 ${step.color+1}（外部）`:`F${step.face}：${maskText(step.candidates)} → ${step.color+1}`;history.append(li);}
}
function snapshot(){return{title:drawing.title,caseId:activeCase,strokes:drawing.strokes.length,status:pending?'computing':result?.selection.status||'error',faces:result?.map.faces.length??null,assignments:result?.selection.assignments??0,backtracks:0,verified:result?.verification?.passed??false,blockedFace:result?.selection.blockedFace??null};}
/** Cancel stale computations: an old result must never recolor a newer drawing. */
function recompute(colorize=$('autocolor').checked){
  if(pending){clearTimeout(pending.timer);pending.reject(new Error('已被更新的地图替代。'));pending=null;}
  worker?.terminate();result=null;selectedEdge=null;renderCanvas();renderDetails();error();$('state').textContent='识别与选色中…';const id=++requestId;
  return new Promise((resolve,reject)=>{
    const fail=message=>{if(pending?.id!==id)return;worker?.terminate();clearTimeout(pending.timer);pending=null;error(message);$('state').textContent='未完成';reject(new Error(message));};
    try{worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});}catch(e){error('当前浏览器不能启动计算，请通过网站地址访问。');$('state').textContent='未完成';reject(e);return;}
    pending={id,resolve,reject,timer:setTimeout(()=>fail('几何计算超时，请撤销或减少线段；没有进行回溯搜索。'),10000)};
    worker.onerror=()=>fail('计算发生错误，请撤销最近一笔或导出地图反馈。');
    worker.onmessage=event=>{if(event.data.requestId!==requestId||pending?.id!==id)return;if(event.data.error){fail(event.data.error.message);return;}clearTimeout(pending.timer);pending=null;result=event.data.result;$('state').textContent=result.selection.status==='solved'?'色标已验证':result.selection.status==='blocked'?'色标选择阻塞':'已识别区域';renderCanvas();renderDetails();resolve(snapshot());};
    worker.postMessage({requestId:id,document:drawing,options:{colorize}});
  });
}
async function replaceDrawing(doc,caseId=null,remember=true){const normalized=normalizeDocument(doc);if(remember){undoStack.push({doc:structuredClone(drawing),caseId:activeCase});if(undoStack.length>100)undoStack.shift();}drawing=normalized;activeCase=caseId;anchor=null;press=null;return recompute();}
async function addSegments(strokes){if(!Array.isArray(strokes)||!strokes.length)throw new Error('请提供至少一条线段。');return replaceDrawing({...drawing,title:'我的地图',strokes:[...drawing.strokes,...strokes]});}
function safe(action){return(...args)=>Promise.resolve().then(()=>action(...args)).catch(e=>{if(!e.message.includes('替代'))error(e.message);});}
async function loadCase(id){return replaceDrawing(caseDocument(id),id);}
async function colorize(){if(result&&result.selection.status!=='uncolored'){renderDetails();return snapshot();}return recompute(true);}
function setMode(value){mode=value;anchor=null;press=null;$('draw').setAttribute('aria-pressed',String(mode==='draw'));$('inspect').setAttribute('aria-pressed',String(mode==='inspect'));$('canvas-hint').textContent=mode==='draw'?'拖动画线，或点击起点与终点；靠近端点和边会吸附。':'点击边查看左右面；箭头指定该边的方向。';renderCanvas();}
function pointFromEvent(event){
  const matrix=canvas.getScreenCTM();if(!matrix)return[0,0];const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());let point=[Math.max(0,Math.min(WIDTH,p.x)),Math.max(0,Math.min(HEIGHT,p.y))];
  if(mode==='draw'&&result){const threshold=10/Math.max(.1,Math.hypot(matrix.a,matrix.b));let best=threshold;const original=[...point];for(const v of result.map.vertices){const d=distance(original,v);if(d<best){best=d;point=[...v];}}if(best===threshold)for(const e of result.map.edges){if(e.virtual)continue;const q=closest(original,result.map.vertices[e.a],result.map.vertices[e.b]),d=distance(original,q);if(d<best){best=d;point=q;}}}
  return point.map(v=>Math.round(v*1000)/1000);
}
canvas.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();press=pointFromEvent(event);canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(mode!=='draw'||(!press&&!anchor))return;const start=anchor||press,end=pointFromEvent(event);$('pending-line')?.replaceChildren(node('line',{x1:start[0],y1:start[1],x2:end[0],y2:end[1],stroke:'#e44227','stroke-width':3,'stroke-dasharray':'8 6'}),node('circle',{cx:start[0],cy:start[1],r:5,fill:'#e44227'}));});
canvas.addEventListener('pointerup',safe(async event=>{
  if(!press)return;const down=press,end=pointFromEvent(event);press=null;if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);
  if(mode==='inspect'){if(!result)return;let nearest=14,chosen=null;result.map.edges.forEach((e,i)=>{if(e.virtual)return;const d=distance(end,closest(end,result.map.vertices[e.a],result.map.vertices[e.b]));if(d<nearest){nearest=d;chosen=i;}});selectedEdge=chosen;renderCanvas();renderDetails();return;}
  if(distance(down,end)>4){anchor=null;await addSegments([{a:down,b:end}]);}else if(anchor){const start=anchor;anchor=null;if(distance(start,end)>.01)await addSegments([{a:start,b:end}]);else renderCanvas();}else{anchor=end;$('pending-line')?.replaceChildren(node('circle',{cx:end[0],cy:end[1],r:5,fill:'#e44227'}));}
}));
canvas.addEventListener('pointercancel',()=>{press=null;anchor=null;renderCanvas();});
$('cases').replaceChildren();for(const c of CASES){const b=document.createElement('button');b.type='button';b.className='case';b.dataset.case=c.id;b.textContent=c.title;const description=document.createElement('span');description.textContent=c.description;b.append(description);b.addEventListener('click',safe(()=>loadCase(c.id)));$('cases').append(b);}
$('draw').addEventListener('click',()=>setMode('draw'));$('inspect').addEventListener('click',()=>setMode('inspect'));
const undo=safe(async()=>{const p=undoStack.pop();if(p)await replaceDrawing(p.doc,p.caseId,false);});
$('undo').addEventListener('click',undo);$('clear').addEventListener('click',safe(()=>loadCase('blank')));$('colorize').addEventListener('click',safe(colorize));$('autocolor').addEventListener('change',safe(()=>recompute()));
document.addEventListener('keydown',event=>{if(event.key==='Escape'){anchor=null;press=null;renderCanvas();}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA'].includes(event.target.tagName)){event.preventDefault();undo();}});
$('help').addEventListener('click',()=>$('help-dialog').showModal());
function download(contents,type,name){const url=URL.createObjectURL(new Blob([contents],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export-json').addEventListener('click',()=>download(JSON.stringify(exportDocument(drawing,result),null,2),'application/json','four-color-map.json'));
$('export-svg').addEventListener('click',()=>{const copy=canvas.cloneNode(true);copy.querySelector('#pending-line')?.remove();copy.setAttribute('xmlns',NS);copy.setAttribute('width','936');copy.setAttribute('height','636');copy.append(node('title',{},`${drawing.title} — ${result?.selection.status||'uncolored'}; no backtracking`));download(new XMLSerializer().serializeToString(copy),'image/svg+xml','four-color-map.svg');});
$('import-button').addEventListener('click',()=>$('import-json').click());$('import-json').addEventListener('change',safe(async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;if(file.size>2*1024*1024)throw new Error('案例文件不能超过 2 MB。');await replaceDrawing(JSON.parse(await file.text()));}));
registerMapTools({context:document.modelContext,snapshot,loadCase,addSegments,caseIds:CASES.map(c=>c.id)});
window.addEventListener('pagehide',()=>{worker?.terminate();if(pending)clearTimeout(pending.timer);});
safe(()=>recompute())();
