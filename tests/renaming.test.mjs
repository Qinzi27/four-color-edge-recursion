/** Research-oracle regressions: finite witnesses are not production rules. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createConstruction,commitPath} from '../web/construction.js';
import {diagnoseRecord,runDiagnostics,searchSplitRepairs,verifyDependencyCertificate,
  prepareRectangularSplit,componentSwaps} from '../scripts/rename-diagnostics.mjs';

const source=JSON.parse(fs.readFileSync(new URL('../outputs/construction-validation-2026-09-08.json',import.meta.url),'utf8'));
const record=seed=>source.records.find(r=>r.family==='guillotine'&&r.seed===seed);

test('reproduce all finite first-blocked counts and the exact-label BFS bound',()=>{
  const report=runDiagnostics();
  const saved=JSON.parse(fs.readFileSync(new URL('../outputs/renaming-round-2026-09-18-v2.json',import.meta.url),'utf8'));
  assert.deepEqual(report,saved,'The saved witnesses must equal a fresh deterministic rerun');
  assert.deepEqual(report.counts,{total:160,B:62,C:95,intersection:5,union:152,BC_extra:7,remaining:1});
  assert.equal(report.hard_case.bfs.depth,3);
  assert.deepEqual(report.hard_case.bfs.layer_counts,[1,5,15,31]);
  assert.equal(report.hard_case.bfs.goal_count,12);
  assert.equal(report.hard_case.minimum.proper_assignments,30);
  assert.equal(report.hard_case.minimum.minimum_changed_unsplit,2);
  assert.equal(report.hard_case.minimum.minimizers,1);
  assert.deepEqual(report.hard_case.dependency.colors,report.hard_case.minimum.colors);
});

test('cut-before and cut-after are complementary, and input replay is immutable',()=>{
  for(const [seed,b,c] of [[20260911,true,false],[20260914,false,true],[20261022,false,false]]) {
    const input=record(seed),saved=JSON.stringify(input),r=diagnoseRecord(input);
    assert.equal(Boolean(r.B),b);assert.equal(Boolean(r.C),c);
    if(seed===20261022)assert.ok(r.BC);
    assert.equal(JSON.stringify(input),saved);
  }
});

test('bounded search exhaustion is not reported as impossible coloring',()=>{
  const row=diagnoseRecord(record(20260927));
  assert.equal(searchSplitRepairs(row,{maxDepth:2}).status,'depth_limit');
  assert.equal(searchSplitRepairs(row,{maxStates:1}).status,'state_limit');
  assert.throws(()=>searchSplitRepairs(row,{maxDepth:-1}));
});

test('dependency certificate preserves outside and validates all line names',()=>{
  const row=diagnoseRecord(record(20260927)),before=JSON.stringify(row);
  const proof=verifyDependencyCertificate(row,[{side:3,symbol:2},{side:2,symbol:3},{side:9,symbol:0}]);
  assert.deepEqual(proof.steps.map(s=>s.side),[9,2,3]);
  assert.deepEqual(proof.dependencies,[{side:3,blockers:[2]},{side:2,blockers:[9]},{side:9,blockers:[]}]);
  assert.equal(proof.colors[row.new_map.outerFace],0);
  assert.equal(JSON.stringify(row),before);
  assert.throws(()=>verifyDependencyCertificate(row,[{side:3,symbol:2}]));
  assert.throws(()=>verifyDependencyCertificate(row,[{side:0,symbol:1}]));
  assert.throws(()=>verifyDependencyCertificate(row,[{side:3,symbol:2},{side:3,symbol:3}]));
});

test('a cyclic but proper target is outside the dependency-DAG rule',()=>{
  // Disjoint anchored toy adjacency: the 1/2 swap is valid as a simultaneous
  // Kempe move but cannot be scheduled as single-side dependency-first moves.
  const row={inherited:[0,1,2],relaxed:[[1,2],[0,2],[0,1]],new_map:{outerFace:0,adjacency:[[1,2],[0,2],[0,1]]}};
  assert.throws(()=>verifyDependencyCertificate(row,[{side:1,symbol:2},{side:2,symbol:1}]),/Cyclic/);
});

test('component candidates are whole components and do not change the exterior',()=>{
  const moves=componentSwaps([[1],[0,2],[1]],[0,1,0],0,'split');
  assert.ok(!moves.some(m=>m.pair[0]===0&&m.pair[1]===1));
  assert.ok(moves.every(m=>m.after[0]===0));
});

test('rectangular diagnostic refuses drafts and nonrectangular geometry',()=>{
  const s=createConstruction();
  assert.throws(()=>prepareRectangularSplit(s,[[0,200],[10,200]]));
  const tilted=commitPath(s,[[0,0],[900,599]]).state;
  assert.throws(()=>prepareRectangularSplit(tilted,[[0,300],[900,600]]));
});
