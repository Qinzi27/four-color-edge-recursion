/** Replay the unchanged published construction policy on supplied cut histories.
 * Inputs contain geometry only: no saved target colors are installed as seeds.
 * This research adapter stops at the first block and never calls B/C or BFS.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {createConstruction, commitPath, readSideNames} from '../web/construction.js';
import {WIDTH, HEIGHT} from '../web/engine.js';

/** Recover original integer geometry from the browser's fixed affine frame. */
function snapshot(state, bounds) {
  const [left, right, bottom, top] = bounds;
  const restore = (x, scale, offset, length) => {
    const value = x / scale * length + offset;
    assert.ok(Math.abs(value - Math.round(value)) < 1e-4, 'Nonintegral restored family coordinate');
    return Math.round(value);
  };
  assert.deepEqual(readSideNames(state.map, state.names), state.colors);
  assert.equal(state.colors[state.map.outerFace], 0);
  const rectangles = state.map.faces.flatMap((face, i) => {
    if(i === state.map.outerFace) return [];
    const xs = face.points.map(p => p[0]), ys = face.points.map(p => p[1]);
    return [{id: state.sideIds[i], bounds: [
      restore(Math.min(...xs), WIDTH, left, right-left),
      restore(Math.max(...xs), WIDTH, left, right-left),
      restore(Math.min(...ys), HEIGHT, bottom, top-bottom),
      restore(Math.max(...ys), HEIGHT, bottom, top-bottom),
    ], color: state.colors[i]}];
  });
  rectangles.sort((a,b) => JSON.stringify(a.bounds).localeCompare(JSON.stringify(b.bounds)));
  return {rectangles, exterior_color: 0};
}

/** Run each transaction through commitPath, including its real tie rules. */
export function replayWebCase(item) {
  assert.ok(Array.isArray(item.history) && item.history.length <= 80);
  assert.ok(Array.isArray(item.bounds) && item.bounds.length === 4);
  const [left,right,bottom,top] = item.bounds;
  const transform = ([x,y]) => [(x-left)/(right-left)*WIDTH, (y-bottom)/(top-bottom)*HEIGHT];
  let state = createConstruction();
  const trace = [];
  for(let index=0; index<item.history.length; index++) {
    const step = item.history[index], before = snapshot(state,item.bounds);
    const result = commitPath(state, step.points.map(transform));
    assert.ok(['split','blocked'].includes(result.status), result.message);
    if(result.status === 'blocked') assert.equal(result.state, state);
    state = result.state;
    trace.push({step:index+1, status:result.status, operation:step,
      before, after:snapshot(state,item.bounds), certificate:result.certificate ?? null,
      message:result.message});
    if(result.status === 'blocked') break;
  }
  const blocked = trace.at(-1)?.status === 'blocked';
  return {m:item.m, variant:item.variant, policy:'web_commitPath',
    initialization:'createConstruction() default exterior 0, interior 1',
    scope:'unchanged published one-daughter policy; no repair fallback',
    status:blocked?'blocked':'completed', stop_step:blocked?trace.length:null,
    reached_final_parent:trace.length === item.history.length,
    intended_steps:item.history.length, trace,
    final_state:snapshot(state,item.bounds)};
}

/** Structured stdin/stdout keeps paths, code, and untrusted input separate. */
function main() {
  const input = JSON.parse(fs.readFileSync(0,'utf8'));
  assert.equal(input.schema_version,1);
  assert.ok(Array.isArray(input.cases));
  const results = input.cases.map(replayWebCase);
  process.stdout.write(JSON.stringify({schema_version:1,node_version:process.version,results}));
}

if(process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
