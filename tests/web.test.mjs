/** Reproducible engine tests; no browser, dependencies or coloring search required. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {analyzeDrawing,buildMap,selectMarkers,verifyColoring,exportDocument,normalizeDocument} from '../web/engine.js';
import {CASES,caseDocument} from '../web/cases.js';
import {registerMapTools} from '../web/webmcp.js';
const doc=strokes=>({schemaVersion:1,strokes});
const edge=(a,b)=>({a,b});
const expected={tetrahedron:5,grid:21,islands:4,dangling:2,touching:4,seeded:48,blank:2};

/** Replay a selection trace with an independent Set-based candidate oracle. */
function checkTrace(map,selection){
  const replay=Array(map.faces.length).fill(-1),seen=new Set();
  for(const s of selection.trace){
    assert(!seen.has(s.face),'one assignment per face');seen.add(s.face);
    if(s.type==='select'){
      const forbidden=new Set(map.adjacency[s.face].map(n=>replay[n]));
      const available=[0,1,2,3].filter(c=>!forbidden.has(c));
      assert.equal(s.candidates,available.reduce((mask,c)=>mask+(2**c),0));
      assert.equal(s.color,available[0]);
    }
    replay[s.face]=s.color;
    for(const n of map.adjacency[s.face])assert(replay[n]<0||replay[n]!==s.color);
  }
  assert.deepEqual(replay,selection.colors);assert.equal(selection.backtracks,0);
  for(let f=0;f<replay.length;f++)if(replay[f]<0){
    const blocked=new Set(map.adjacency[f].map(n=>replay[n]));
    assert.equal(selection.masks[f],[0,1,2,3].filter(c=>!blocked.has(c)).reduce((m,c)=>m+2**c,0));
  }
}
for(const c of CASES)test(`case ${c.id}: topology, marker trace, certificate`,()=>{
  const r=analyzeDrawing(caseDocument(c.id));assert.equal(r.map.faces.length,expected[c.id]);
  assert.equal(r.selection.status,'solved');assert.equal(r.verification.passed,true);checkTrace(r.map,r.selection);
});
test('tetrahedron actually uses four markers',()=>assert.equal(new Set(analyzeDrawing(caseDocument('tetrahedron')).selection.colors).size,4));
test('dangling and invisible bridge edges have identical shores and zero difference',()=>{
  const r=analyzeDrawing(caseDocument('dangling'));let count=0;
  r.map.edges.forEach((e,i)=>{if(!e.frame){assert.equal(r.map.faceOfDart[2*i],r.map.faceOfDart[2*i+1]);assert.equal(r.verification.differences[i],0);count++;}});assert(count>0);
});
test('corner contact is not face adjacency',()=>{
  const m=buildMap(caseDocument('touching')),islands=m.faces.map((f,i)=>({f,i})).filter(({f})=>Math.abs(f.area-69300)<.01);
  assert.equal(islands.length,2);assert(!m.adjacency[islands[0].i].includes(islands[1].i));
});
test('duplicate, reversed and overlapping lines do not create extra faces',()=>{
  const strokes=[edge([0,300],[900,300]),edge([900,300],[0,300]),edge([200,300],[700,300])];
  const m=buildMap(doc(strokes));assert.equal(m.faces.length,3);assert.equal(m.original.components,1);
});
test('T junction on a boundary creates three bounded regions',()=>assert.equal(buildMap(doc([edge([0,300],[900,300]),edge([450,0],[450,300])])).faces.length,4));
test('left of a downward dart is screen-east',()=>{
  const m=buildMap(doc([edge([450,0],[450,600])])),i=m.edges.findIndex(e=>e.sources.includes(0));
  const f=m.faces[m.faceOfDart[2*i]];assert(f.points.some(p=>p[0]===900));assert(!f.points.some(p=>p[0]===0));
});
test('export/import recomputes identical geometry, masks and colors',()=>{
  const a=analyzeDrawing(caseDocument('islands')),saved=JSON.parse(JSON.stringify(exportDocument(a.map.document,a)));
  saved.result.colors=[999];const b=analyzeDrawing(saved);
  assert.deepEqual(a.map,b.map);assert.deepEqual(a.selection.colors,b.selection.colors);assert.deepEqual(a.selection.trace,b.selection.trace);
});
test('uncolored mode has no complete certificate',()=>{const r=analyzeDrawing(caseDocument('grid'),{colorize:false});assert.equal(r.verification,null);assert.equal(r.selection.colors,null);});
test('invalid inputs are rejected before processing',()=>{
  for(const bad of [null,{strokes:'bad'},doc([edge([0,0],[0,0])]),doc([edge([-1,0],[2,2])]),doc([edge([NaN,0],[2,2])]),{schemaVersion:2,strokes:[]},doc(Array(81).fill(edge([0,0],[1,1])))])assert.throws(()=>normalizeDocument(bad));
});
test('corrupt coloring cannot pass verification',()=>{const m=buildMap(caseDocument('tetrahedron'));assert.equal(verifyColoring(m,Array(m.faces.length).fill(0)).passed,false);});

// A planar triangulation which defeats this no-backtracking rule, although a
// four-color witness exists. This is an algorithm-level dual graph fixture.
const adjacency=[[1,2,4,6,7],[0,2,5,7],[0,1,5,6],[4,5,6,7],[0,3,6,7],[1,2,3,6,7],[0,2,3,4,5],[0,1,3,4,5]];
const triangles=[[0,1,2],[2,6,0],[7,5,3],[3,4,6],[1,0,7],[2,5,1],[0,4,6],[4,3,7],[6,5,3],[7,1,5],[5,2,6],[4,0,7]];
test('blocking fixture is a sphere triangulation: two faces per edge, cyclic links, Euler 2',()=>{
  const counts=new Map();
  for(const t of triangles)for(let i=0;i<3;i++){const a=t[i],b=t[(i+1)%3];assert(adjacency[a].includes(b));const k=[a,b].sort((x,y)=>x-y).join(':');counts.set(k,(counts.get(k)||0)+1);}
  assert.equal(counts.size,18);assert([...counts.values()].every(n=>n===2));assert.equal(8-counts.size+triangles.length,2);
  for(let v=0;v<8;v++){
    const link=new Map(adjacency[v].map(n=>[n,[]]));
    for(const t of triangles)if(t.includes(v)){const [a,b]=t.filter(n=>n!==v);link.get(a).push(b);link.get(b).push(a);}
    assert([...link.values()].every(ns=>ns.length===2));const seen=new Set(),stack=[adjacency[v][0]];
    while(stack.length){const n=stack.pop();if(seen.has(n))continue;seen.add(n);stack.push(...link.get(n));}assert.equal(seen.size,link.size);
  }
});
test('greedy obstruction preserves partial coloring, never calls it non-four-colorable',()=>{
  const m={faces:Array(8).fill(null),outerFace:0,adjacency},s=selectMarkers(m);
  assert.equal(s.status,'blocked');assert.equal(s.blockedFace,4);assert.equal(s.assignments,7);checkTrace(m,s);
  const witness=[0,1,2,0,3,3,1,2];assert(adjacency.every((ns,f)=>ns.every(n=>witness[n]!==witness[f])));
});
test('fixed colors are preserved and conflicting fixed colors rejected',()=>{
  const m=buildMap(caseDocument('tetrahedron')),s=selectMarkers(m);
  const again=selectMarkers(m,{fixedColors:s.colors});assert.deepEqual(again.colors,s.colors);
  assert.throws(()=>selectMarkers(m,{fixedColors:Array(m.faces.length).fill(0)}));
});
test('a single face split need not extend if all surrounding old colors are frozen',()=>{
  // Each half will touch all three old ring colors, so both demand color 0.
  const inner=[[450,150],[650,225],[650,375],[450,450],[250,375],[250,225]];
  const outer=[[450,0],[900,150],[900,450],[450,600],[0,450],[0,150]];
  const strokes=inner.map((a,i)=>edge(a,inner[(i+1)%6])).concat(inner.map((a,i)=>edge(a,outer[i])));
  const before=buildMap(doc(strokes)),oldColors=[0,3,1,2,3,1,2,0];
  assert.equal(before.faces.length,8);assert.equal(verifyColoring(before,oldColors).passed,true);
  const after=buildMap(doc([...strokes,edge(inner[0],inner[3])])),fixed=[0,3,1,2,3,1,2,-1,-1];
  assert.equal(after.faces.length,9);
  for(const f of [7,8]){
    assert.equal(after.faces[f].area,45000);
    assert.deepEqual([...new Set(after.adjacency[f].filter(n=>n<7).map(n=>fixed[n]))].sort(),[1,2,3]);
  }
  assert(after.adjacency[7].includes(8));assert.equal(selectMarkers(after,{fixedColors:fixed}).status,'blocked');
  // The same final map remains four-colorable when old ring colors may change.
  const witness=[0,1,2,1,2,1,2,0,3];assert.equal(verifyColoring(after,witness).passed,true);
});
test('WebMCP adapter mock checks names, shared actions, invalid input and cleanup (not browser validation)',async()=>{
  const registered=new Map();let state={caseId:'blank'};
  const dispose=registerMapTools({context:{registerTool:(tool,opts)=>registered.set(tool.name,{tool,opts})},snapshot:()=>state,caseIds:['blank'],loadCase:async id=>(state={caseId:id}),addSegments:async strokes=>{normalizeDocument(doc(strokes));return(state={count:strokes.length});}});
  assert.equal(registered.size,3);const read=registered.get('get_map_state').tool;
  assert.equal(read.annotations.readOnlyHint,true);assert.deepEqual(read.execute({}),state);
  assert.throws(()=>registered.get('load_map_case').tool.execute({caseId:'missing'}));
  await registered.get('add_map_segments').tool.execute({strokes:[edge([0,0],[1,1])]});assert.deepEqual(read.execute({}),{count:1});
  dispose();assert(registered.get('get_map_state').opts.signal.aborted);
});
test('browser source has no backtracking solver import or result branch',async()=>{
  const app=await readFile(new URL('../web/app.js',import.meta.url),'utf8');
  assert(!app.includes('solveColors'));assert(!app.includes('result.search'));
});
