/** Independent finite checks of priority selection and line-side certificates. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {nameByPriority,PRIORITY_POLICIES} from '../web/priority-names.js';
import {verifyColoring} from '../web/engine.js';
import {CASES} from '../web/cases.js';

const document=paths=>({strokes:paths.map(([a,b])=>({a,b}))});
const D=document([[[0,180],[900,180]],[[300,180],[300,600]],[[600,180],[600,600]],[[450,180],[450,600]]]);
const obstruction=document([[[450,0],[450,600]],[[450,300],[900,300]],[[650,0],[650,300]],
  [[450,120],[650,120]],[[650,100],[900,100]],[[450,240],[650,240]]]);

/** Compare certificates by geometric shores, not transient face/edge indices. */
function geometricCertificate(result) {
  const {map,names}=result;
  return map.edges.filter(e=>!e.virtual).map(e=>{
    const i=map.edges.indexOf(e),a=map.vertices[e.a],b=map.vertices[e.b];
    return a[0]<b[0]||a[0]===b[0]&&a[1]<b[1]
      ?[a,b,names[i]]:[b,a,[...names[i]].reverse()];
  }).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
}

/** Re-evaluate every greedy priority using independent neighbor-set records. */
function checkTrace(result) {
  const {map,trace,policy}=result,known=Array(map.faces.length).fill(null);
  const ranks=Array(map.faces.length).fill(null),depths=Array(map.faces.length).fill(null);
  known[map.outerFace]=1;ranks[map.outerFace]=0;depths[map.outerFace]=0;
  const queue=[map.outerFace];
  for(let k=0;k<queue.length;k++)for(const other of map.adjacency[queue[k]])if(depths[other]===null) {
    depths[other]=depths[queue[k]]+1;queue.push(other);
  }
  for(const step of trace)ranks[step.side]=step.rank;
  assert.deepEqual([...ranks].sort((a,b)=>a-b),ranks.map((_,i)=>i));
  for(const step of trace) {
    const candidates=map.faces.flatMap((_,side)=>{
      if(known[side]!==null)return [];
      const forbidden=[...new Set(map.adjacency[side].map(n=>known[n]).filter(n=>n!==null))].sort((a,b)=>a-b);
      if(!forbidden.length)return [];
      const key=policy==='boundary'?[ranks[side]]:policy==='layer-constraint'
        ?[depths[side],-forbidden.length,ranks[side]]:[-forbidden.length,depths[side],ranks[side]];
      return [{side,forbidden,key}];
    });
    candidates.sort((a,b)=>{for(let i=0;i<a.key.length;i++)if(a.key[i]!==b.key[i])return a.key[i]-b.key[i];return 0;});
    const chosen=candidates[0];assert.equal(step.side,chosen.side);
    assert.deepEqual(step.priorityKey,chosen.key);assert.deepEqual(step.forbidden,chosen.forbidden);
    assert.equal(step.depth,depths[step.side]);
    let symbol=1;while(chosen.forbidden.includes(symbol))symbol++;
    assert.equal(step.symbol,symbol);known[step.side]=symbol;
  }
  assert.deepEqual(known,result.symbols);
  assert.equal(result.backtracks,0);assert.equal(result.oldNamesUsed,false);
  result.names.forEach((pair,i)=>{
    assert.deepEqual(pair,[known[map.faceOfDart[2*i]],known[map.faceOfDart[2*i+1]]]);
    assert.equal(pair[0]===pair[1],map.faceOfDart[2*i]===map.faceOfDart[2*i+1]);
  });
}

for(const item of CASES)for(const policy of PRIORITY_POLICIES)for(const direction of ['clockwise','counterclockwise'])
  test(`priority certificate: ${item.id}, ${policy}, ${direction}`,()=>checkTrace(nameByPriority(item,{policy,direction})));

test('fifth name is reported, not hidden by retries or a four-name palette',()=>{
  for(const policy of PRIORITY_POLICIES) {
    const r=nameByPriority(obstruction,{policy});checkTrace(r);
    assert.equal(r.paletteSize,5);assert.equal(r.withinFour,false);
    assert.deepEqual(r.trace.at(-1).forbidden,[1,2,3,4]);
    const reverse=nameByPriority(obstruction,{policy,direction:'counterclockwise'});
    assert.equal(reverse.paletteSize,4);assert.ok(verifyColoring(reverse.map,reverse.symbols.map(c=>c-1)).passed);
  }
});

test('a four-name certificate exists independently of the failed priority rule',()=>{
  const r=nameByPriority(obstruction);
  // Explicit geometric side IDs in this exact fixture: O,A,B,C,D,E,F,G.
  const witness=[1,2,3,4,2,3,1,4];
  assert.ok(verifyColoring(r.map,witness.map(c=>c-1)).passed);
});

test('a mirrored 13-line case defeats all six fixed policies yet has a four-name witness',()=>{
  const half=(point,mirrored)=>[mirrored?900-point[0]/2:point[0]/2,point[1]];
  const strokes=[{a:[450,0],b:[450,600]},...obstruction.strokes.map(s=>({a:half(s.a,false),b:half(s.b,false)})),
    ...obstruction.strokes.map(s=>({a:half(s.a,true),b:half(s.b,true)}))];
  // A diagnostic oracle supplied this explicit witness; production rules never
  // import that oracle. Check the witness directly without running a search.
  const witness={'outside':1,'0,0,225,600':2,'225,0,325,120':3,'325,0,450,100':2,
    '450,0,575,100':3,'575,0,675,120':2,'675,0,900,600':4,
    '450,300,675,600':2,'225,300,450,600':4,'450,100,575,300':4,
    '325,100,450,300':1,'225,120,325,240':4,'225,240,325,300':3,
    '575,120,675,240':1,'575,240,675,300':3};
  for(const policy of PRIORITY_POLICIES)for(const direction of ['clockwise','counterclockwise']) {
    const r=nameByPriority({strokes},{policy,direction});
    assert.equal(r.paletteSize,5);checkTrace(r);
    const colors=r.map.faces.map((f,i)=>{
      const key=i===r.map.outerFace?'outside':[Math.min(...f.points.map(p=>p[0])),Math.min(...f.points.map(p=>p[1])),
        Math.max(...f.points.map(p=>p[0])),Math.max(...f.points.map(p=>p[1]))].join(',');
      assert.ok(key in witness,key);return witness[key]-1;
    });
    assert.ok(verifyColoring(r.map,colors).passed);
  }
});

test('history permutation, input direction and poisoned old names do not affect restart',()=>{
  for(const policy of PRIORITY_POLICIES)for(const direction of ['clockwise','counterclockwise']) {
    const expected=geometricCertificate(nameByPriority(D,{policy,direction}));
    for(let offset=0;offset<D.strokes.length;offset++) {
      const reordered=[...D.strokes.slice(offset),...D.strokes.slice(0,offset)].map(s=>({a:s.b,b:s.a}));
      const input={strokes:reordered,names:[[99,99]],history:['must not be used']};
      assert.deepEqual(geometricCertificate(nameByPriority(input,{policy,direction})),expected);
    }
  }
});

test('unsupported priorities reject and caller geometry is not mutated',()=>{
  const before=JSON.stringify(D);nameByPriority(D);
  assert.equal(JSON.stringify(D),before);
  assert.throws(()=>nameByPriority(D,{policy:'unknown'}));
  assert.throws(()=>nameByPriority(D,{direction:'random'}));
});

test('experimental priority module is not wired into either public app entry point',async()=>{
  for(const file of ['app.js','rules-app.js'])assert.ok(!(await readFile(new URL('../web/'+file,import.meta.url),'utf8')).includes('priority-names'));
});
