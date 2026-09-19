/** Finite renaming research oracle; NEVER imported by the browser marker.
 * Replays first-blocked rectangular histories, enumerates bounded Kempe repairs,
 * and records independently checkable witnesses. Not a general coloring rule.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {importConstruction, commitPath, readSideNames} from '../web/construction.js';
import {buildMap, verifyColoring} from '../web/engine.js';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
export const SOURCE = 'outputs/construction-validation-2026-09-08.json';
export const orderedNames = (map, colors) => map.edges.map((_, e) =>
  [colors[map.faceOfDart[2 * e]], colors[map.faceOfDart[2 * e + 1]]]);
export const proper = (adjacency, colors) => adjacency.every((ns, i) =>
  ns.every(j => colors[i] !== colors[j]));

/** Preserve rotation and line-side evidence, not just a displayed coloring. */
function packMap(map) {
  return {vertices: map.vertices, edges: map.edges, rotation: map.rotation,
    faceOfDart: map.faceOfDart, faces: map.faces.map(f => f.darts),
    original: map.original, outerFace: map.outerFace, adjacency: map.adjacency};
}

/** This independent geometric mapping is intentionally rectangular-only. */
export function prepareRectangularSplit(state, points) {
  const trial = commitPath(state, points);
  assert.ok(['split', 'blocked'].includes(trial.status), 'Expected a valid splitting path');
  const map = buildMap({...state.document, strokes: [...state.document.strokes,
    ...points.slice(1).map((b, i) => ({a: points[i], b}))]});
  function rectangleBounds(m) {
    assert.equal(m.original.components, 1, 'Only connected rectangular histories');
    m.edges.forEach((e, i) => {
      assert.ok(!e.virtual && m.faceOfDart[2*i] !== m.faceOfDart[2*i+1], 'No bridges in this diagnostic family');
      const a=m.vertices[e.a], b=m.vertices[e.b];
      assert.ok(a[0]===b[0] || a[1]===b[1], 'Only axis-aligned rectangles');
    });
    return m.faces.map((f, i) => {
      const xs=f.points.map(p=>p[0]), ys=f.points.map(p=>p[1]);
      const box=[Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
      if(i!==m.outerFace) {
        const area=(box[1]-box[0])*(box[3]-box[2]);
        assert.ok(Math.abs(Math.abs(f.area)-area)<1e-5, 'Nonrectangular side orbit');
        assert.ok(f.points.every(p=>p[0]===box[0]||p[0]===box[1]||p[1]===box[2]||p[1]===box[3]));
      }
      return box;
    });
  }
  const oldBoxes=rectangleBounds(state.map), newBoxes=rectangleBounds(map);
  const parents=newBoxes.map((box,i)=> {
    if(i===map.outerFace) return state.map.outerFace;
    const x=(box[0]+box[1])/2, y=(box[2]+box[3])/2;
    const hits=oldBoxes.flatMap((b,j)=>j!==state.map.outerFace && b[0]<x && x<b[1] && b[2]<y && y<b[3] ? [j] : []);
    assert.equal(hits.length,1, 'Each new rectangle has one old parent'); return hits[0];
  });
  const counts=state.map.faces.map((_,p)=>parents.filter(q=>q===p).length);
  assert.equal(counts.filter(n=>n===2).length,1);
  assert.ok(counts.every(n=>n===1||n===2));
  const parent=counts.indexOf(2), daughters=parents.flatMap((p,i)=>p===parent?[i]:[]);
  const [u,v]=daughters;
  assert.ok(map.adjacency[u].includes(v));
  const relaxed=map.adjacency.map((ns,i)=>ns.filter(j=>!(i===u&&j===v)&&!(i===v&&j===u)));
  const inherited=parents.map(p=>state.colors[p]);
  assert.ok(proper(relaxed,inherited));
  return {map,parents,parent,daughters,relaxed,inherited};
}

/** Enumerate whole two-symbol components, in a documented stable order. */
export function componentSwaps(adjacency, colors, outerFace, stage, required=null) {
  const result=[];
  for(let a=0;a<4;a++) for(let b=a+1;b<4;b++) {
    if(required!==null && a!==required && b!==required) continue;
    const seen=new Set();
    for(let f=0;f<colors.length;f++) {
      if(seen.has(f)||(colors[f]!==a&&colors[f]!==b)) continue;
      const component=[f]; seen.add(f);
      for(let i=0;i<component.length;i++) for(const n of adjacency[component[i]]) {
        if(!seen.has(n)&&(colors[n]===a||colors[n]===b)) {seen.add(n);component.push(n);}
      }
      if(component.includes(outerFace)) continue;
      component.sort((x,y)=>x-y);
      const after=[...colors];
      for(const p of component) after[p]=colors[p]===a?b:a;
      assert.ok(proper(adjacency,after));
      result.push({stage,pair:[a,b],component,before:[...colors],after});
    }
  }
  return result;
}

/** Only a full, proper four-symbol certificate counts as a repaired state. */
function witness(prepared, method, moves, colors) {
  const {map}=prepared, names=orderedNames(map,colors);
  assert.ok(verifyColoring(map,colors).passed);
  assert.equal(colors[map.outerFace],0);
  readSideNames(map,names);
  return {method,moves,colors:[...colors],names};
}

/** C: split first, then exchange one component containing exactly one daughter. */
export function postSplitRepair(prepared, oldColors) {
  const {map,parents,parent,daughters,relaxed}=prepared;
  const inherited=parents.map(p=>oldColors[p]);
  for(const move of componentSwaps(relaxed,inherited,map.outerFace,'split',oldColors[parent])) {
    if(daughters.filter(f=>move.component.includes(f)).length!==1) continue;
    return witness(prepared,'C',[move],move.after);
  }
  return null;
}

/** Diagnose existence of B, C, B->C; candidate enumeration is explicit. */
export function diagnoseRecord(record) {
  const {state}=importConstruction(record.replay), points=record.rejected.points;
  assert.deepEqual(state.names,record.final_names);
  assert.equal(commitPath(state,points).status,'blocked');
  const prepared=prepareRectangularSplit(state,points);
  const candidates=componentSwaps(state.map.adjacency,state.colors,state.map.outerFace,'old');
  let B=null, BC=null;
  for(const move of candidates) {
    const result=commitPath({...state,colors:move.after,names:orderedNames(state.map,move.after)},points);
    if(result.status==='split') {B=witness(prepared,'B',[move],result.state.colors);break;}
  }
  const C=postSplitRepair(prepared,state.colors);
  // BC is measured ONLY in the subset that has neither one-step repair.
  if(!B&&!C) for(const move of candidates) {
    const after=postSplitRepair(prepared,move.after);
    if(after) {BC={...after,method:'BC',moves:[move,...after.moves]};break;}
  }
  return {seed:record.seed,operations:record.replay.operations,pending:points,
    old_colors:state.colors,old_names:state.names,old_map:packMap(state.map),
    new_map:packMap(prepared.map),parents:prepared.parents,parent:prepared.parent,
    daughters:prepared.daughters,relaxed:prepared.relaxed,inherited:prepared.inherited,
    B,C,BC};
}

/** Exact-label BFS on the split graph with ONLY the new-line constraint removed.
 * Completes a whole goal layer so layer counts and shortest-depth claims audit.
 * All two-symbol pairs are permitted, including preparatory moves away from the
 * daughters. Bounds report inconclusive, never 'no possible repair'.
 */
export function searchSplitRepairs(row,{maxDepth=6,maxStates=50000}={}) {
  assert.ok(Number.isInteger(maxDepth)&&maxDepth>=0);
  assert.ok(Number.isInteger(maxStates)&&maxStates>=1);
  const start=row.inherited, key=c=>c.join(''), seen=new Map([[key(start),{colors:start,moves:[]}]]);
  let layer=[seen.get(key(start))];
  const layers=[1];
  for(let depth=0;depth<=maxDepth;depth++) {
    const goals=layer.filter(node=>proper(row.new_map.adjacency,node.colors));
    if(goals.length) return {status:'found',depth,layer_counts:layers,goal_count:goals.length,
      visited:seen.size,max_depth:maxDepth,max_states:maxStates,
      witness:{method:'split-BFS',...goals[0],names:orderedNames(row.new_map,goals[0].colors)}};
    if(depth===maxDepth) return {status:'depth_limit',layer_counts:layers,visited:seen.size,max_depth:maxDepth,max_states:maxStates};
    const next=[];
    for(const node of layer) for(const move of componentSwaps(row.relaxed,node.colors,row.new_map.outerFace,'split')) {
      const id=key(move.after); if(seen.has(id)) continue;
      if(seen.size>=maxStates) return {status:'state_limit',layer_counts:layers,visited:seen.size,max_depth:maxDepth,max_states:maxStates};
      const child={colors:move.after,moves:[...node.moves,move]};seen.set(id,child);next.push(child);
    }
    if(!next.length) return {status:'exhausted_component',layer_counts:layers,visited:seen.size,max_depth:maxDepth,max_states:maxStates};
    layer=next;layers.push(layer.length);
  }
}

/** Small independent assignment oracle for the one hard case, not production.
 * Counts changed UNSPLIT old side identities; daughters are excluded from cost.
 */
export function minimumOldChanges(row) {
  const map=row.new_map;
  assert.ok(map.faces.length<=10,'Assignment oracle is bounded to ten sides');
  let total=0,best=Infinity,bestCount=0,bestColors=null;
  const colors=[];
  function visit(i) {
    if(i===map.faces.length) {
      total++;
      const changed=colors.reduce((sum,c,f)=>sum+(row.parents[f]!==row.parent && c!==row.old_colors[row.parents[f]]?1:0),0);
      if(changed<best) {best=changed;bestCount=1;bestColors=[...colors];}
      else if(changed===best) bestCount++;
      return;
    }
    for(const c of (i===map.outerFace?[0]:[0,1,2,3])) {
      if(map.adjacency[i].some(j=>j<i&&colors[j]===c)) continue;
      colors[i]=c;visit(i+1);
    }
  }
  visit(0);
  return {proper_assignments:total,minimum_changed_unsplit:best,minimizers:bestCount,colors:bestColors,
    names:bestColors?orderedNames(map,bestColors):null};
}

/** Check a supplied simultaneous-renaming certificate, without finding colors.
 * u depends on v if u wants v's OLD symbol across an H adjacency. A DAG can
 * be executed dependency-first: old neighbors have moved out of the way, while
 * already updated neighbors cannot conflict because the final assignment was
 * checked. This proves sufficiency, not existence of such certificates.
 */
export function verifyDependencyCertificate(row, changes) {
  const colors=[...row.inherited], final=[...colors], targets=new Map();
  for(const {side,symbol} of changes) {
    assert.ok(Number.isInteger(side)&&side>=0&&side<colors.length);
    assert.ok(Number.isInteger(symbol)&&symbol>=0&&symbol<4);
    assert.ok(side!==row.new_map.outerFace&&!targets.has(side));
    assert.notEqual(colors[side],symbol);
    targets.set(side,symbol);final[side]=symbol;
  }
  assert.ok(proper(row.new_map.adjacency,final),'Supplied final names must satisfy every line');
  const dependencies=[...targets].map(([side,symbol])=>({side,
    blockers:row.relaxed[side].filter(n=>colors[n]===symbol).sort((a,b)=>a-b)}));
  for(const item of dependencies) for(const n of item.blockers)
    assert.ok(targets.has(n),'A requested name is blocked by an unchanged side');
  const done=new Set(),steps=[];
  while(done.size<targets.size) {
    const ready=dependencies.filter(d=>!done.has(d.side)&&d.blockers.every(n=>done.has(n)))
      .sort((a,b)=>a.side-b.side)[0];
    assert.ok(ready,'Cyclic dependency: this sufficient rule does not apply');
    const before=[...colors];colors[ready.side]=targets.get(ready.side);
    assert.ok(proper(row.relaxed,colors));
    steps.push({side:ready.side,from:before[ready.side],to:colors[ready.side],before,after:[...colors]});
    done.add(ready.side);
  }
  const names=orderedNames(row.new_map,colors);readSideNames(row.new_map,names);
  return {method:'supplied dependency-DAG certificate; no selection or search',
    changes,dependencies,steps,colors,names};
}

/** Recreate the prior 160 first-blocked diagnostics and attack the residual case. */
export function runDiagnostics() {
  const raw=fs.readFileSync(path.join(ROOT,SOURCE),'utf8');
  const input=JSON.parse(raw).records.filter(r=>r.family==='guillotine');
  assert.equal(input.length,160);
  const records=input.map(diagnoseRecord);
  const count=f=>records.filter(f).length;
  const counts={total:records.length,B:count(r=>r.B),C:count(r=>r.C),intersection:count(r=>r.B&&r.C),
    union:count(r=>r.B||r.C),BC_extra:count(r=>r.BC),remaining:count(r=>!r.B&&!r.C&&!r.BC)};
  const hard=records.find(r=>r.seed===20260927);
  assert.ok(hard&&!hard.B&&!hard.C&&!hard.BC);
  const bfs=searchSplitRepairs(hard),minimum=minimumOldChanges(hard);
  // This explicitly supplied witness was discovered by a separate diagnostic;
  // the verifier does not pretend to have derived a general selection rule.
  const dependency=verifyDependencyCertificate(hard,[
    {side:3,symbol:2},{side:2,symbol:3},{side:9,symbol:0}]);
  if(bfs.witness) readSideNames(hard.new_map,bfs.witness.names);
  return {schema_version:1,scope:'Finite first-blocked-state repair diagnostics; NOT completed histories or a non-search algorithm.',
    source_report:SOURCE,source_hash_normalization:'UTF-8 text, CRLF normalized to LF',
    source_sha256:createHash('sha256').update(raw.replace(/\r\n/g,'\n')).digest('hex'),
    symbols:'internal 0..3; displayed 1..4; outer fixed 0',
    family:'axis-aligned guillotine rectangles',seed_range:[20260908,20261067],
    ordering:'pair ascending, component minimum side ascending, exact-label BFS; no color-isomorphism reduction',
    counts,records,hard_case:{seed:hard.seed,bfs,minimum,dependency}};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2),report=runDiagnostics(),serialized=JSON.stringify(report,null,2)+'\n';
  if(args.includes('--emit')) process.stdout.write(serialized);
  else {
    const i=args.indexOf('--output'),output=i>=0?args[i+1]:'outputs/renaming-round-2026-09-18-v2.json';
    if(!output) throw new Error('--output requires a new filename');
    const target=path.resolve(ROOT,output);fs.mkdirSync(path.dirname(target),{recursive:true});
    fs.writeFileSync(target,serialized,{encoding:'utf8',flag:'wx'});
    console.log(JSON.stringify({output:output,counts:report.counts,hard_case:report.hard_case},null,2));
  }
}
