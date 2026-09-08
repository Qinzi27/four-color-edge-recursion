/** UI is a view of committed line names. Drafts never enter construction state. */
import {createConstruction,commitPath,isAnchor,exportConstruction,importConstruction} from './construction.js';
import {CONSTRUCTION_CASES} from './construction-cases.js';
const $=selector=>document.querySelector(selector),canvas=$('#canvas');
const palette=['#63bbea','#ffcd4d','#b795e3','#61c8a8'];
let state=createConstruction(),draft=[],undo=[],activeCase=CONSTRUCTION_CASES[0],cursor=0,selectedEdge=null,last=null;
const near=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const symbols=values=>'{'+values.map(c=>c+1).join(', ')+'}';

/** Insert untrusted text with DOM APIs, never interpolate it into HTML. */
function svg(tag,attrs={},text){const element=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))element.setAttribute(k,String(v));if(text!==undefined)element.textContent=text;return element;}
function status(message,kind='split'){$('#status').textContent=message;$('#status').dataset.kind=kind;}
function draw(){
  canvas.replaceChildren(svg('rect',{x:-18,y:-18,width:936,height:636,fill:palette[0]}));
  state.map.faces.forEach((f,i)=>{if(i!==state.map.outerFace)canvas.append(svg('path',{d:f.points.map((p,k)=>(k?'L':'M')+p.join(',')).join(' ')+' Z',fill:palette[state.colors[i]],'fill-rule':'evenodd'}));});
  const defs=svg('defs'),marker=svg('marker',{id:'direction',markerWidth:8,markerHeight:8,refX:7,refY:3,orient:'auto',markerUnits:'strokeWidth'});
  marker.append(svg('path',{d:'M0,0 L7,3 L0,6 Z',fill:'#b72b20'}));defs.append(marker);canvas.append(defs);
  state.map.edges.forEach((e,i)=>{if(e.virtual)return;const a=state.map.vertices[e.a],b=state.map.vertices[e.b],chosen=i===selectedEdge;
    canvas.append(svg('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:chosen?'#b72b20':'#18314c','stroke-width':chosen?5:2.4,...(chosen?{'marker-end':'url(#direction)'}:{})}));
    // These ordered labels belong to directed lines, not region identifiers.
    if(!e.frame&&(state.map.edges.length<45||chosen)&&near(a,b)>70){const [l,r]=state.names[i];canvas.append(svg('text',{x:(a[0]+b[0])/2+8,y:(a[1]+b[1])/2-8,fill:'#102b48','font-size':17,'font-family':'monospace','paint-order':'stroke',stroke:'#fff','stroke-width':4},`(${l+1},${r+1})`));}
  });
  if(draft.length){canvas.append(svg('polyline',{points:draft.map(p=>p.join(',')).join(' '),fill:'none',stroke:['blocked','invalid'].includes(last?.status)?'#b72b20':'#9a5900','stroke-width':4,'stroke-dasharray':'10 6'}));draft.forEach(p=>canvas.append(svg('circle',{cx:p[0],cy:p[1],r:5,fill:'#fff',stroke:'#9a5900','stroke-width':2})));}
  $('#stats').textContent=`${state.history.length} 次提交 · ${state.document.strokes.length}/80 线段 · ${new Set(state.colors).size} 种符号 · 证书 ${state.verification.passed?'通过':'失败'}`;
  $('#undo').disabled=!undo.length;$('#next').disabled=!activeCase||cursor>=activeCase.steps.length;
  $('#next').textContent=activeCase?`案例下一步 ${Math.min(cursor+1,activeCase.steps.length)}/${activeCase.steps.length} →`:'案例下一步 →';
  $('#history').replaceChildren(...state.history.map(e=>{const li=document.createElement('li');li.textContent=e.kind==='bridge'?`${e.step}. 连接桥：${e.parent} 保持符号 ${e.parentSymbol+1}，ΔF=0`:`${e.step}. ${e.parent}(${e.parentSymbol+1}) → ${e.children.map(c=>c.id+'('+String(c.symbol+1)+')'+(c.inherits?' 继承':' 新标')).join(' / ')}`;return li;}));
  if(selectedEdge!==null){const i=selectedEdge,e=state.map.edges[i],a=state.map.vertices[e.a],b=state.map.vertices[e.b],[l,r]=state.names[i];$('#detail').textContent=`红箭头 ${a.join(',')} → ${b.join(',')}\n线名：(${l+1}, ${r+1})\n反向：(${r+1}, ${l+1})\n左侧谱系：${state.sideIds[state.map.faceOfDart[2*i]]}\n右侧谱系：${state.sideIds[state.map.faceOfDart[2*i+1]]}\n${l===r?'桥：两侧属于同一侧空间':'分割线：两侧符号不同'}`;}
  else $('#detail').textContent='图上的 (a,b) 标注属于线。切换“检查线名”并点线，红箭头指明读取方向。';
  const event=last?.event??state.history.at(-1);
  if(last?.certificate){const c=last.certificate;$('#proof').textContent=`受阻，原状态未改\n父侧 ${c.parent}：a=${c.parentSymbol+1}\n`+c.options.map((o,i)=>`子侧 ${i+1}：T=${symbols(o.externalSymbols)}\n可选=${symbols(o.available)}`).join('\n')+'\n只针对当前冻结预标，不是四色不可解证书。';}
  else if(event)$('#proof').textContent=`${event.kind==='split'?'分割':'桥'} · ΔF=${event.deltaFaces}, ΔC=${event.deltaComponents}\na=${event.parentSymbol+1}\nT=${symbols(event.externalSymbols)}\n${event.selectedSymbol===null?'无新符号':`直接取 c=${event.selectedSymbol+1}`}\n回溯次数：0\n线侧一致 / 邻接 / 闭路校验：通过`;
  else $('#proof').textContent='初始画框：外侧符号 1，内侧符号 2。没有已提交分割。';
}

/** Atomic commit: keep rejected paths visible and all committed names intact. */
function apply(points,fromCase=false){const previous=state,result=commitPath(state,points);last=result;selectedEdge=null;
  if(!fromCase)activeCase=null;
  if(result.state!==previous){undo.push(previous);state=result.state;draft=[];}else draft=points;
  status(result.message,result.status);draw();return result;
}
function resetCase(item,complete=false){activeCase=item;cursor=0;state=createConstruction(item?.seed?.());draft=[];undo=[];last=null;selectedEdge=null;
  $('#title').textContent=item?.title??'从一条有名字的线开始';$('#description').textContent=item?.description??'画框已有两侧名字；接线或闭环后，程序只按受限规则选取新标记。';
  for(const b of $('#cases').children)b.classList.toggle('active',b.dataset.id===item?.id);
  status('已载入起始线名；可逐步重放，也可自己接线。');
  if(complete)while(cursor<item.steps.length)next();draw();
}
function next(){if(!activeCase||cursor>=activeCase.steps.length)return;const step=activeCase.steps[cursor++],result=apply(step.points,true);if(result.status!==step.expectedStatus)status('案例预期与运行结果不一致：'+result.message,'invalid');}

/** Pointer projection explicitly excludes invisible helper edges. */
function nearestLine(point){let best={distance:Infinity,point,index:null};state.map.edges.forEach((e,index)=>{if(e.virtual)return;const a=state.map.vertices[e.a],b=state.map.vertices[e.b],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy))),p=[a[0]+t*dx,a[1]+t*dy],distance=near(point,p);if(distance<best.distance)best={distance,point:p,index};});return best;}
canvas.addEventListener('click',event=>{const matrix=canvas.getScreenCTM();if(!matrix)return;const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());let point=[Math.max(0,Math.min(900,p.x)),Math.max(0,Math.min(600,p.y))];
  const mode=$('#mode').value,nearest=nearestLine(point),threshold=10/Math.max(matrix.a,.1);
  if(mode==='inspect'){selectedEdge=nearest.distance<threshold?nearest.index:null;draw();return;}
  if(mode==='loop'&&draft.length>=3&&near(point,draft[0])<threshold){apply([...draft,draft[0]]);return;}
  if(mode==='path'&&nearest.distance<threshold)point=nearest.point;
  if(!draft.length&&mode==='path'&&!isAnchor(state,point)){status('接线起点需要落在边界或实线上。空白起笔请选“独立闭环”。','draft');return;}
  if(draft.length&&near(point,draft.at(-1))<1e-5)return;
  if(draft.length>=81){status('草稿点数达到上限。','invalid');return;}
  last=null;draft.push(point);
  if(mode==='path'&&draft.length>=2&&isAnchor(state,point))apply(draft);else{status('草稿尚未提交：继续点击折点，或完成锚定 / 闭环。','draft');draw();}
});
$('#submit').addEventListener('click',()=>{if(draft.length>=2)apply(draft);else status('先给出至少两个点。','draft');});
$('#cancel').addEventListener('click',()=>{draft=[];last=null;status('草稿已取消；已提交线名不变。');draw();});
$('#mode').addEventListener('change',()=>{draft=[];last=null;selectedEdge=null;status('操作模式已切换；未提交草稿已清除。');draw();});
$('#undo').addEventListener('click',()=>{if(!undo.length)return;state=undo.pop();draft=[];last=null;selectedEdge=null;activeCase=null;status('已回到上一步完整线名证书。');draw();});
$('#restart').addEventListener('click',()=>resetCase(activeCase));$('#next').addEventListener('click',next);$('#blank').addEventListener('click',()=>resetCase(null));
$('#apply-points').addEventListener('click',()=>{try{const p=JSON.parse($('#points').value);if(!Array.isArray(p)||p.some(q=>!Array.isArray(q)||q.length!==2||q.some(x=>typeof x!=='number'||!Number.isFinite(x))))throw new Error('坐标需要有限数字点对。');apply(p);}catch(e){status(e.message,'invalid');}});
document.addEventListener('keydown',event=>{if(event.key==='Escape')$('#cancel').click();});
/** User-triggered downloads only; no uploaded drawing leaves the browser. */
function download(content,type,name){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#export').addEventListener('click',()=>download(JSON.stringify(exportConstruction(state,draft),null,2),'application/json','line-first-construction.json'));
$('#svg-export').addEventListener('click',()=>{const copy=canvas.cloneNode(true);copy.setAttribute('xmlns','http://www.w3.org/2000/svg');download(new XMLSerializer().serializeToString(copy),'image/svg+xml','line-first-construction.svg');});
$('#import').addEventListener('click',()=>$('#file').click());
$('#file').addEventListener('change',async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>5*1024*1024)throw new Error('案例文件不能超过 5 MB。');const result=importConstruction(JSON.parse(await file.text()));undo.push(state);state=result.state;draft=result.pending;activeCase=null;cursor=0;last=null;selectedEdge=null;$('#title').textContent='导入的线名实验';$('#description').textContent='起始线名和每一步操作均已重新验证；未信任保存的最终证书。';status('导入成功：全部操作重放，证书一致。');draw();}catch(e){status('导入失败，原状态保留：'+e.message,'invalid');}finally{event.target.value='';}});
for(const item of CONSTRUCTION_CASES){const button=document.createElement('button');button.type='button';button.dataset.id=item.id;button.textContent=item.title;button.addEventListener('click',()=>resetCase(item));$('#cases').append(button);}
resetCase(CONSTRUCTION_CASES[0],true);
