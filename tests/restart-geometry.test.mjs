/** Bounded geometry-export regression tests; no coloring method is exercised. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {exportRestartGeometry} from '../scripts/restart-geometry.mjs';

const HELPER = fileURLToPath(new URL('../scripts/restart-geometry.mjs', import.meta.url));
const ROOT = fileURLToPath(new URL('../', import.meta.url));

/** Construct fresh source segments without adding names or solver answers. */
const document = paths => ({strokes: paths.map(([a, b]) => ({a: [...a], b: [...b]}))});
const horizontal = () => document([[[0, 300], [900, 300]]]);
const ring = () => document([
  [[250, 180], [650, 180]], [[650, 180], [650, 420]],
  [[650, 420], [250, 420]], [[250, 420], [250, 180]],
]);


test('an omitted frame means the explicit 900 by 600 frame, not an unbounded plane', () => {
  const result = exportRestartGeometry({key: 'blank', document: {strokes: []}});
  assert.equal(result.status, 'geometry_ok');
  assert.equal(result.width, 900);
  assert.equal(result.height, 600);
  assert.equal(result.coloring_performed, false);
  assert.deepEqual(result.errors, []);
  assert.equal(result.geometry.faces.length, 2);
  assert.equal(result.geometry.edges.length, 4);
  assert.ok(result.geometry.edges.every(edge => edge.frame && !edge.virtual));
  assert.equal(result.geometry.original.components, 1);
});


test('a supported explicit frame succeeds while other sizes return no partial geometry', () => {
  const good = exportRestartGeometry({key: 'exact', document: {
    frame: {width: 900, height: 600}, strokes: [],
  }});
  assert.equal(good.status, 'geometry_ok');
  for (const frame of [{width: 901, height: 600}, {width: 900, height: 599}]) {
    const bad = exportRestartGeometry({key: 'wrong-size', document: {frame, strokes: []}});
    assert.equal(bad.status, 'geometry_error');
    assert.equal(bad.geometry, null);
    assert.equal(bad.errors.length, 1);
    assert.equal(bad.errors[0].code, 'input');
  }
});


test('color annotations are not read and the helper imports no coloring operation', () => {
  const doc = horizontal();
  // Throwing getters detect even a read of old annotations, not merely their
  // accidental acceptance as a starting coloring for the new geometry.
  const poison = () => { throw new Error('old color annotations must not be read'); };
  for (const field of ['colors', 'names', 'fixedColors', 'initial_names', 'result']) {
    Object.defineProperty(doc, field, {enumerable: true, get: poison});
  }
  const item = {key: 'ignore-old-names', document: doc};
  Object.defineProperty(item, 'initial_names', {get: poison});
  const result = exportRestartGeometry(item);
  assert.equal(result.status, 'geometry_ok');
  assert.equal(result.coloring_performed, false);
  assert.ok(!Object.hasOwn(result.geometry, 'colors'));
  assert.ok(!Object.hasOwn(result.geometry, 'names'));
  // This source-bound guard complements the behavior check: geometry exports
  // must not later acquire a hidden call to any engine coloring entry point.
  const source = readFileSync(HELPER, 'utf8');
  assert.doesNotMatch(source, /\b(selectMarkers|analyzeDrawing|verifyColoring)\b/);
});


test('ordinary splits preserve rotation and whole-line edge metadata', () => {
  const result = exportRestartGeometry({key: 'one-split', document: horizontal()});
  assert.equal(result.status, 'geometry_ok');
  const geometry = result.geometry;
  assert.equal(geometry.faces.length, 3);
  assert.deepEqual(geometry.real_bridge_edge_ids, []);
  assert.deepEqual(geometry.virtual_bridge_edge_ids, []);
  assert.deepEqual(geometry.rotation.flat().sort((a, b) => a - b),
    Array.from({length: 2 * geometry.edges.length}, (_, i) => i));
  assert.equal(geometry.vertices.length - geometry.edges.length + geometry.faces.length, 2);
  assert.ok(geometry.edges.every(edge => typeof edge.frame === 'boolean'
    && typeof edge.virtual === 'boolean' && Array.isArray(edge.sources)));
  assert.deepEqual(geometry.edges.filter(edge => !edge.frame).map(edge => edge.sources), [[0]]);
});


test('a real hanging bridge has equal interior shores and is not labelled exterior', () => {
  const result = exportRestartGeometry({key: 'hanging',
    document: document([[[0, 300], [400, 300]]])});
  assert.equal(result.status, 'geometry_ok');
  const geometry = result.geometry;
  assert.equal(geometry.faces.length, 2);
  assert.equal(geometry.real_bridge_edge_ids.length, 1);
  assert.deepEqual(geometry.virtual_bridge_edge_ids, []);
  const [bridge] = geometry.same_shore_edges;
  assert.equal(bridge.virtual, false);
  assert.equal(bridge.is_exterior_face, false);
  assert.notEqual(bridge.face, geometry.outerFace);
  assert.equal(geometry.faceOfDart[2 * bridge.edge], bridge.face);
  assert.equal(geometry.faceOfDart[2 * bridge.edge + 1], bridge.face);
});


test('an independent closed ring retains same-shore virtual topology bridges', () => {
  const result = exportRestartGeometry({key: 'ring', document: ring()});
  assert.equal(result.status, 'geometry_ok');
  const geometry = result.geometry;
  assert.equal(geometry.original.components, 2);
  assert.equal(geometry.faces.length, 3);
  assert.equal(geometry.virtual_bridge_edge_ids.length, 1);
  assert.deepEqual(geometry.real_bridge_edge_ids, []);
  for (const index of geometry.virtual_bridge_edge_ids) {
    assert.equal(geometry.faceOfDart[2 * index], geometry.faceOfDart[2 * index + 1]);
    assert.equal(geometry.edges[index].frame, false);
    assert.deepEqual(geometry.edges[index].sources, []);
  }
  assert.equal(geometry.original.vertices - geometry.original.edges + geometry.faces.length,
    1 + geometry.original.components);
});


test('face polygons are optional drawing data and neither call mutates the input', () => {
  const doc = ring();
  const before = JSON.stringify(doc);
  const plain = exportRestartGeometry({key: 'drawing', document: doc});
  const drawn = exportRestartGeometry({key: 'drawing', document: doc, includeFacePoints: true});
  assert.equal(plain.status, 'geometry_ok');
  assert.equal(drawn.status, 'geometry_ok');
  assert.equal(JSON.stringify(doc), before);
  assert.ok(!Object.hasOwn(plain.geometry, 'face_points'));
  const {face_points: points, ...rest} = drawn.geometry;
  assert.deepEqual(rest, plain.geometry);
  assert.equal(points.length, drawn.geometry.faces.length);
  assert.ok(points.every(polygon => polygon.every(point => point.length === 2
    && point.every(Number.isFinite))));
});


test('CLI batches retain failed cases and continue; malformed envelopes fail explicitly', () => {
  const cases = [
    {key: 'before', document: horizontal()},
    {key: 'bad-frame', document: {frame: {width: 901, height: 600}, strokes: []}},
    {key: 'missing-document'},
    {key: 'after', document: {strokes: []}},
  ];
  const run = spawnSync(process.execPath, [HELPER], {
    cwd: ROOT, input: JSON.stringify({cases}), encoding: 'utf8',
  });
  assert.equal(run.status, 0, run.stderr);
  assert.equal(run.stderr, '');
  const output = JSON.parse(run.stdout);
  assert.equal(output.schema_version, 1);
  assert.equal(output.coloring_performed, false);
  assert.deepEqual(output.results.map(row => row.key), cases.map(row => row.key));
  assert.deepEqual(output.results.map(row => row.status),
    ['geometry_ok', 'geometry_error', 'geometry_error', 'geometry_ok']);
  assert.ok(output.results.filter(row => row.status === 'geometry_error')
    .every(row => row.geometry === null && row.errors.length === 1));
  const invalid = spawnSync(process.execPath, [HELPER], {
    cwd: ROOT, input: JSON.stringify({cases: 'not-an-array'}), encoding: 'utf8',
  });
  assert.equal(invalid.status, 1);
  assert.equal(invalid.stdout, '');
  assert.match(invalid.stderr, /cases array/);
});
