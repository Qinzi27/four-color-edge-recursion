/** Regression tests for the proved rule, never a search for a convenient color. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createConstruction,commitPath,isAnchor,readSideNames,exportConstruction,importConstruction} from '../web/construction.js';
import {CONSTRUCTION_CASES} from '../web/construction-cases.js';

for(const item of CONSTRUCTION_CASES)test('construction gallery: '+item.id,()=>{
  let state=createConstruction(item.seed?.());
  for(const op of item.steps){const before=JSON.stringify(exportConstruction(state)),old=state,r=commitPath(state,op.points);
    assert.equal(r.status,op.expectedStatus,r.message);state=r.state;assert.equal(state.verification.passed,true);
    if(['split','bridge'].includes(r.status)){
      assert.equal(r.event.backtracks,0);assert.equal(state.map.faces.length-old.map.faces.length,r.status==='split'?1:0);
      // Every unaffected old side identity retains its symbol, even if indices move.
      old.sideIds.forEach((id,i)=>{if(id===r.event.parent)return;const j=state.sideIds.indexOf(id);assert.notEqual(j,-1);assert.equal(state.colors[j],old.colors[i]);});
      if(r.status==='split'){assert.ok(r.event.externalSymbols.length<=2);assert.ok(!r.event.externalSymbols.includes(r.event.selectedSymbol));assert.notEqual(r.event.selectedSymbol,r.event.parentSymbol);assert.equal(r.event.children.filter(c=>c.inherits).length,1);}
    }else {assert.equal(state,old);assert.equal(JSON.stringify(exportConstruction(state)),before);}
    if(r.status==='blocked'){assert.equal(r.certificate.options.length,2);for(const o of r.certificate.options){assert.equal(o.externalSymbols.length,3);assert.deepEqual(o.available,[]);}}
    assert.deepEqual(importConstruction(exportConstruction(state)).state.names,state.names);
  }
});

test('self intersections, overlaps, outside coordinates and old-line contact are atomic rejections',()=>{
  const state=createConstruction();
  for(const points of [[[0,0],[900,0]],[[0,100],[800,500],[100,500],[900,100]],[[0,100],[901,100]],[[0,100],[0,100]],[[100,100],[300,100],[300,300],[0,0],[100,100]],[[NaN,0],[0,100]]]){
    const r=commitPath(state,points);assert.equal(r.status,'invalid',JSON.stringify(points));assert.equal(r.state,state);
  }
});
test('virtual bridge never becomes an anchor; a real bridge does',()=>{
  let s=createConstruction();s=commitPath(s,CONSTRUCTION_CASES.find(c=>c.id==='loop').steps[0].points).state;
  assert.equal(isAnchor(s,[775,180]),false);s=commitPath(s,[[0,300],[250,300]]).state;assert.equal(isAnchor(s,[125,300]),true);
});
test('old real bridge becomes a genuine separator after the second connection',()=>{
  let s=createConstruction();const item=CONSTRUCTION_CASES.find(c=>c.id==='bridge');
  for(const op of item.steps.slice(0,2))s=commitPath(s,op.points).state;
  const edge=s.map.edges.findIndex(e=>e.sources.includes(4));assert.equal(s.names[edge][0],s.names[edge][1]);
  s=commitPath(s,item.steps[2].points).state;const changed=s.map.edges.findIndex(e=>e.sources.includes(4));assert.notEqual(s.names[changed][0],s.names[changed][1]);
});
test('exact oblique anchor survives normalization',()=>{
  let s=commitPath(createConstruction(),[[0,0],[900,599]]).state;const p=[100,599*100/900];assert.ok(isAnchor(s,p));const r=commitPath(s,[p,[0,200]]);assert.equal(r.status,'split');assert.deepEqual(r.points[0],p);
});
test('same target geometry has both a blocked and a successful input history',()=>{
  const bad=CONSTRUCTION_CASES.find(c=>c.id==='order-blocked'),good=CONSTRUCTION_CASES.find(c=>c.id==='order-success');
  assert.deepEqual(bad.steps.map(s=>JSON.stringify(s.points)).sort(),good.steps.map(s=>JSON.stringify(s.points)).sort());
});
test('seed names and imported certificates are not trusted',()=>{
  const s=createConstruction(),file=exportConstruction(s,[[0,100],[50,100]]);
  assert.deepEqual(importConstruction(file).pending,[[0,100],[50,100]]);
  file.certificate.names[0][0]=3;assert.throws(()=>importConstruction(file),/证书/);
  const bad=exportConstruction(s);bad.seed.names[0][0]=3;assert.throws(()=>importConstruction(bad));
  assert.throws(()=>createConstruction({document:s.document}));assert.throws(()=>readSideNames(s.map,[]));
  assert.throws(()=>importConstruction({...exportConstruction(s),operations:[[[0,100],[50,100]]]}),/重放失败/);
  assert.throws(()=>importConstruction({...exportConstruction(s),pending:[[Infinity,0]]}),/草稿/);
});
test('four-symbol witness really contains a K4 among interior side spaces',()=>{
  let s=createConstruction();for(const op of CONSTRUCTION_CASES[0].steps)s=commitPath(s,op.points).state;
  const ids=s.map.faces.map((_,i)=>i).filter(i=>i!==s.map.outerFace);
  assert.equal(ids.length,4);for(const i of ids)for(const j of ids)if(i!==j)assert.ok(s.map.adjacency[i].includes(j));
  assert.equal(new Set(s.colors).size,4);
});
test('new page control IDs are wired and production module never imports a solver',async()=>{
  const app=await readFile(new URL('../web/rules-app.js',import.meta.url),'utf8');
  const html=await readFile(new URL('../web/rules.html',import.meta.url),'utf8');
  const engine=await readFile(new URL('../web/construction.js',import.meta.url),'utf8');
  for(const [,id] of app.matchAll(/\$\('#([^']+)'\)/g))assert.ok(html.includes(`id="${id}"`),id);
  assert.ok(!/selectMarkers|analyzeDrawing|worker|search_construction_gap/.test(engine));
  assert.ok(html.includes('不是新的四色定理证明'));
});
