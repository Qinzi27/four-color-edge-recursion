/** Geometry-only fixtures for whole-source-line and candidate-propagation work.
 * No coloring selection, priority naming, search, or backtracking is called.
 * The only colored fixtures are explicitly supplied human witnesses, checked
 * after geometric point location. A rejected witness is retained as evidence.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildMap, verifyColoring} from '../web/engine.js';
import {CASES, caseDocument} from '../web/cases.js';
import {FIRST_SEED, generatedPaths} from './construction-experiments.mjs';
import {teachingDocuments, targetedDocuments} from './priority-experiments.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));

/** Use all path segments, without consulting an incremental naming outcome. */
function documentFromPaths(title, paths) {
  return {schemaVersion: 1, title, frame: {width: 900, height: 600},
    strokes: paths.flatMap(points => points.slice(1).map((b, i) => ({a: points[i], b})))};
}

/** Preserve both original line sources and the noded rotation-system evidence. */
function snapshot(map) {
  return {vertices: map.vertices, edges: map.edges, rotation: map.rotation,
    faceOfDart: map.faceOfDart, faces: map.faces.map(face => face.darts),
    outerFace: map.outerFace, original: map.original};
}

/** Locate a strictly interior sample by ray parity; reject boundary ambiguity.
 * This is only used for the simple remote-contact teaching fixture, not as a
 * replacement for side orbits or a general geometric coloring algorithm.
 */
function containsStrictly(points, sample) {
  const [x, y] = sample;
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [ax, ay] = points[j], [bx, by] = points[i];
    const cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax);
    if (Math.abs(cross) < 1e-8 && x >= Math.min(ax, bx) && x <= Math.max(ax, bx)
        && y >= Math.min(ay, by) && y <= Math.max(ay, by)) {
      throw new Error('Witness sample is on a boundary; provide a strict interior point.');
    }
    if ((ay > y) !== (by > y) && x < ax + (bx - ax) * (y - ay) / (by - ay)) inside = !inside;
  }
  return inside;
}

/** Expand a supplied human assignment to every final face, then CHECK it.
 * Positive display integers 1..4 are converted to the engine's 0..3 domain
 * only when invoking verifyColoring. This function never searches for colors.
 */
export function witnessFromRows(map, rows, externalSymbol = 1) {
  assert.equal(externalSymbol, 1, 'The exterior anchor must remain one');
  const colors = Array(map.faces.length).fill(null), roleToFace = {external: map.outerFace};
  colors[map.outerFace] = externalSymbol;
  const witnessRows = rows.map(row => {
    assert.ok(Number.isInteger(row.symbol) && row.symbol >= 1 && row.symbol <= 4);
    assert.ok(!Object.hasOwn(roleToFace, row.role), 'Each role must be unique');
    const hits = map.faces.flatMap((face, side) => side !== map.outerFace
      && containsStrictly(face.points, row.point) ? [side] : []);
    assert.equal(hits.length, 1, 'Each sample must locate exactly one bounded side');
    const side = hits[0];
    assert.equal(colors[side], null, 'Two witness roles unexpectedly identify one side');
    colors[side] = row.symbol;
    roleToFace[row.role] = side;
    return {...row, point: [...row.point], face: side};
  });
  assert.ok(colors.every(symbol => symbol !== null), 'Human witness omitted a side');
  const faceRoles = Object.fromEntries(Object.entries(roleToFace).map(([role, face]) => [face, role]));
  const conflicts = map.edges.flatMap((edge, index) => {
    const left = map.faceOfDart[2 * index], right = map.faceOfDart[2 * index + 1];
    return left !== right && colors[left] === colors[right] ? [{edge: index,
      left, right, left_role: faceRoles[left], right_role: faceRoles[right],
      symbol: colors[left], a: map.vertices[edge.a], b: map.vertices[edge.b],
      virtual: edge.virtual, sources: edge.sources}] : [];
  });
  const verification = verifyColoring(map, colors.map(symbol => symbol - 1));
  assert.equal(verification.passed, conflicts.length === 0);
  return {provenance: 'Supplied human assignment; point location and verification only.',
    external_symbol: externalSymbol, witness_rows: witnessRows, role_to_face: roleToFace,
    colors, valid: verification.passed, conflictedges: conflicts, verification};
}

/** Fixed before/after map whose remote contact distinguishes the child sides. */
function remoteDocuments() {
  const before = [
    [[0, 400], [900, 400]], [[700, 0], [700, 400]],
    [[200, 200], [700, 200]], [[200, 200], [200, 400]],
  ];
  return [{id: 'remote-before', paths: before},
    {id: 'remote-after', paths: [...before, [[450, 200], [450, 400]]]}].map(row => ({
    id: row.id, family: 'whole-line-targeted', seed: null,
    planned_paths: row.paths.length, document: documentFromPaths(row.id, row.paths),
  }));
}

/** Preserve the 252-map baseline, then add three targeted before/after inputs. */
export function wholeLineFixtures() {
  const teaching = teachingDocuments();
  const inputs = CASES.map(item => ({id: 'gallery-' + item.id, family: 'gallery', seed: null,
    document: caseDocument(item.id)})).concat(teaching, targetedDocuments());
  for (let i = 0; i < 240; i++) {
    const seed = FIRST_SEED + i;
    const family = i < 160 ? 'guillotine' : i < 200 ? 'nested-rings-and-bridges' : 'boundary-fan';
    const paths = generatedPaths(family, seed);
    inputs.push({id: family + '-' + seed, family, seed, planned_paths: paths.length,
      document: documentFromPaths(family + '-' + seed, paths)});
  }
  const d = teaching.find(row => row.id === 'teaching-D');
  inputs.push({id: 'D-before', family: 'whole-line-targeted', seed: null, planned_paths: 3,
    document: {...d.document, title: 'D-before', strokes: d.document.strokes.slice(0, 3)}});
  inputs.push(...remoteDocuments());
  const records = inputs.map(input => {
    const map = buildMap(input.document);
    const record = {...input, geometry: snapshot(map)};
    if (input.id === 'teaching-D') record.transition_role = 'D-after';
    if (input.id === 'remote-before') {
      const rows = [{point: [100, 100], symbol: 2, role: 'A'},
        {point: [300, 300], symbol: 1, role: 'B'},
        {point: [800, 100], symbol: 4, role: 'R'},
        {point: [100, 500], symbol: 3, role: 'D'}];
      record.external_symbol = 1;
      record.witness_rows = rows;
      record.witnesses = {baseline: witnessFromRows(map, rows)};
      assert.equal(record.witnesses.baseline.valid, true);
    }
    if (input.id === 'remote-after') {
      const fixed = [{point: [100, 100], symbol: 2, role: 'A'},
        {point: [800, 100], symbol: 4, role: 'R'},
        {point: [100, 500], symbol: 3, role: 'D'}];
      const endpointRows = [...fixed, {point: [300, 300], symbol: 1, role: 'west'},
        {point: [600, 300], symbol: 4, role: 'east'}];
      const switchedRows = [...fixed, {point: [300, 300], symbol: 4, role: 'west'},
        {point: [600, 300], symbol: 1, role: 'east'}];
      record.external_symbol = 1;
      record.witnesses = {endpoint_only: witnessFromRows(map, endpointRows),
        side_switched: witnessFromRows(map, switchedRows)};
      assert.equal(record.witnesses.endpoint_only.valid, false);
      assert.equal(record.witnesses.side_switched.valid, true);
      assert.ok(record.witnesses.endpoint_only.conflictedges.every(edge =>
        [edge.left_role, edge.right_role].includes('east')
        && [edge.left_role, edge.right_role].includes('R')));
    }
    return record;
  });
  assert.equal(records.length, 255);
  assert.equal(new Set(records.map(row => row.id)).size, records.length);
  const sources = ['web/engine.js', 'web/cases.js', 'scripts/construction-experiments.mjs',
    'scripts/priority-experiments.mjs', 'scripts/whole-line-fixtures.mjs'];
  return {schema_version: 1, purpose: 'Geometry fixtures and manually supplied remote-contact witnesses.',
    seed_range: [FIRST_SEED, FIRST_SEED + 239], baseline_maps: 252, extra_maps: 3,
    random_generator: 'uint32 LCG: state = 1664525*state + 1013904223',
    scope: 'All complete final geometries; no old naming state, no coloring solver, no priority naming execution.',
    transitions: [{before: 'D-before', after: 'teaching-D', inserted_path: [[450, 180], [450, 600]]},
      {before: 'remote-before', after: 'remote-after', inserted_path: [[450, 200], [450, 400]]}],
    source_sha256: Object.fromEntries(sources.map(source => [source,
      createHash('sha256').update(fs.readFileSync(path.join(ROOT, source))).digest('hex')])),
    records};
}

// Keep imports silent; the CLI emits one JSON object and never writes a file.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
    && process.argv.includes('--emit')) {
  process.stdout.write(JSON.stringify(wholeLineFixtures()));
}
