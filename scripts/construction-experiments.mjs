/** Reproducible finite experiments. Seeds are consecutive, failures retained.
 * Traversing geometry for validation is not enumerating color assignments.
 * This module never calls selectMarkers, a coloring solver, or backtracking.
 */
import assert from 'node:assert/strict';
import {createConstruction,commitPath,exportConstruction,importConstruction} from '../web/construction.js';
import {CONSTRUCTION_CASES} from '../web/construction-cases.js';
export const FIRST_SEED=20260908;
const rng=seed=>()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);

/** Geometry-only generation: do not consult symbols to choose a favorable map. */
export function generatedPaths(family,seed){
  const random=rng(seed),paths=[];
  if(family==='guillotine'){
    const rectangles=[[0,0,900,600]];
    for(let n=0;n<24;n++){
      const eligible=rectangles.map((r,i)=>({r,i})).filter(({r})=>r[2]-r[0]>=20&&r[3]-r[1]>=20);
      if(!eligible.length)break;
      const {r:[x0,y0,x1,y1],i}=eligible[Math.floor(random()*eligible.length)],vertical=random()<.5;
      if(vertical){const x=Math.round(x0+(x1-x0)*(.3+.4*random()));paths.push([[x,y0],[x,y1]]);rectangles.splice(i,1,[x0,y0,x,y1],[x,y0,x1,y1]);}
      else{const y=Math.round(y0+(y1-y0)*(.3+.4*random()));paths.push([[x0,y],[x1,y]]);rectangles.splice(i,1,[x0,y0,x1,y],[x0,y,x1,y1]);}
    }
  }else if(family==='nested-rings-and-bridges'){
    const start=30+Math.floor(random()*15),gap=24+Math.floor(random()*8),bounds=[];
    for(let i=0;i<6;i++){const t=start+i*gap;bounds.push(t);paths.push([[t,t],[900-t,t],[900-t,600-t],[t,600-t],[t,t]]);}
    for(let i=0;i<bounds.length;i++)paths.push([[i?bounds[i-1]:0,300],[bounds[i],300]]);
    for(let i=0;i<bounds.length;i++)paths.push([[900-bounds[i],300],[i?900-bounds[i-1]:900,300]]);
  }else if(family==='boundary-fan'){
    for(let i=0;i<12;i++)paths.push([[0,0],[900,20+45*i+Math.floor(random()*20)]]);
  }else throw new Error('Unknown family');
  return paths;
}

/** Serialize independent-oracle input without methods or machine-local paths. */
function snapshot(state){const m=state.map;return {edges:m.edges.map(e=>({a:e.a,b:e.b,virtual:e.virtual})),rotation:m.rotation,faces:m.faces.map(f=>f.darts),faceOfDart:m.faceOfDart,names:state.names,original:m.original};}
export function runExperiments(includeSnapshots=false){
  const records=[],snapshots=[];
  function run(id,steps,seed=null,family='gallery',initial=null){
    let state=createConstruction(initial),outcome='complete',rejected=null;
    const audit=()=>{assert.ok(state.verification.passed);if(includeSnapshots)snapshots.push({id,step:state.history.length,...snapshot(state)});};audit();
    for(let index=0;index<steps.length;index++){
      const op=steps[index],old=state,r=commitPath(state,op.points??op);
      if(op.expectedStatus)assert.equal(r.status,op.expectedStatus,id+': '+r.message);
      if(['split','bridge'].includes(r.status)){
        state=r.state;assert.equal(r.event.backtracks,0);
        for(let i=0;i<old.sideIds.length;i++){const label=old.sideIds[i];if(label!==r.event.parent){const j=state.sideIds.indexOf(label);assert.ok(j>=0);assert.equal(state.colors[j],old.colors[i]);}}
        if(r.status==='split'){assert.ok(r.event.externalSymbols.length<=2);assert.ok(!r.event.externalSymbols.includes(r.event.selectedSymbol));}
        audit();
      }else{
        assert.equal(r.state,old);outcome=r.status;rejected={step:index+1,points:r.points,certificate:r.certificate??null,message:r.message};
        if(family!=='gallery')assert.equal(outcome,'blocked',id+': '+r.message);
        if(outcome==='blocked'){assert.equal(r.certificate.options.length,2);r.certificate.options.forEach(o=>{assert.equal(o.externalSymbols.length,3);assert.deepEqual(o.available,[]);});}
        break;
      }
    }
    assert.deepEqual(importConstruction(exportConstruction(state)).state.names,state.names);
    const {certificate:_certificate,...replay}=exportConstruction(state,rejected?.points??[]);
    records.push({id,family,seed,planned_steps:steps.length,committed_steps:state.history.length,splits:state.history.filter(e=>e.kind==='split').length,bridges:state.history.filter(e=>e.kind==='bridge').length,outcome,
      faces:state.map.faces.length,symbol_count:new Set(state.colors).size,backtracks:0,verified:true,
      replay,final_names:state.names,rejected});
  }
  for(const c of CONSTRUCTION_CASES)run(c.id,c.steps,null,'gallery',c.seed?.());
  for(let i=0;i<240;i++){const seed=FIRST_SEED+i,family=i<160?'guillotine':i<200?'nested-rings-and-bridges':'boundary-fan';run(family+'-'+seed,generatedPaths(family,seed),seed,family);}
  const families=[...new Set(records.map(r=>r.family))].map(family=>{const rows=records.filter(r=>r.family===family);return {family,maps:rows.length,committed_steps:rows.reduce((s,r)=>s+r.committed_steps,0),outcomes:Object.fromEntries([...new Set(rows.map(r=>r.outcome))].map(o=>[o,rows.filter(r=>r.outcome===o).length]))};});
  return {schema_version:1,algorithm:'line-first / two-contact guard / minimum external-set then side-index / minimum available symbol / no backtracking',seed_range:[FIRST_SEED,FIRST_SEED+239],random_generator:'uint32 LCG: state = 1664525*state + 1013904223',generated_maps:240,gallery_maps:CONSTRUCTION_CASES.length,families,records,...(includeSnapshots?{snapshots}:{}),scope:'Finite correctness and failure records, not proof of a successful construction order for every map.',browser_ui_tested:false};
}
if(process.argv.includes('--emit'))process.stdout.write(JSON.stringify(runExperiments(true)));
