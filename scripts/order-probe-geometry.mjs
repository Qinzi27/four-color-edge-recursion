/** Isolated geometry exporter for the declared high-segment inversion study.
 *
 * The frozen engine file is read and hash-checked, never edited. Exactly one
 * source token raises LIMITS.strokes from 80 to 256 in an in-memory data module.
 * Edges/faces, tolerances, normalization, planarization and face traversal are
 * unchanged. No analyzeDrawing/selectMarkers/coloring function is called.
 */

import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const ENGINE_SHA256 = '1451287b703e6f90765a1ed96acd2c4c5fc30d467be6c207da81f4b982035d84';
const OLD_LIMIT = 'export const LIMITS = Object.freeze({strokes:80, edges:1600, faces:400});';
const NEW_LIMIT = 'export const LIMITS = Object.freeze({strokes:256, edges:1600, faces:400});';
const hash = data => createHash('sha256').update(data).digest('hex');
const engineBytes = readFileSync(new URL('../web/engine.js', import.meta.url));
if (hash(engineBytes) !== ENGINE_SHA256) throw new Error('Frozen engine SHA-256 differs.');
const original = engineBytes.toString('utf8');
if (original.split(OLD_LIMIT).length !== 2) throw new Error('Expected exactly one frozen LIMITS declaration.');
const modified = original.replace(OLD_LIMIT, NEW_LIMIT);
const {buildMap, WIDTH, HEIGHT, LIMITS} = await import(
  'data:text/javascript;base64,' + Buffer.from(modified).toString('base64'));
if (LIMITS.strokes !== 256 || LIMITS.edges !== 1600 || LIMITS.faces !== 400) {
  throw new Error('Research limit profile differs from the declared profile.');
}
const profile = {
  version: 'order-probe-geometry-strokes256-v1',
  original_engine_sha256: ENGINE_SHA256,
  in_memory_engine_sha256: hash(modified),
  exporter_sha256: hash(readFileSync(fileURLToPath(import.meta.url))),
  exact_replacement: {from: OLD_LIMIT, to: NEW_LIMIT, occurrences: 1},
  limits: LIMITS,
  old_engine_file_modified: false,
  scope: 'geometry-only resource profile; not the unchanged 80-stroke production engine',
};

/** Preserve each case and its error, without substituting a simpler drawing. */
function exportOne(item) {
  const result = {key: typeof item?.key === 'string' ? item.key : null,
    status: 'geometry_error', width: WIDTH, height: HEIGHT,
    coloring_performed: false, geometry: null, errors: []};
  try {
    if (!item || typeof item !== 'object' || Array.isArray(item)
        || typeof item.key !== 'string' || !item.key) {
      const error = new Error('Each case requires a nonempty string key and a document.');
      error.code = 'input';
      throw error;
    }
    const map = buildMap(item.document);
    const bridges = [];
    for (let edge = 0; edge < map.edges.length; edge++) {
      const a = map.faceOfDart[2 * edge], b = map.faceOfDart[2 * edge + 1];
      if (a === b) bridges.push({edge, face: a, virtual: map.edges[edge].virtual,
        is_exterior_face: a === map.outerFace});
    }
    result.geometry = {
      vertices: map.vertices,
      edges: map.edges.map(edge => ({a: edge.a, b: edge.b, virtual: edge.virtual,
        frame: edge.frame, sources: [...edge.sources]})),
      rotation: map.rotation, faceOfDart: map.faceOfDart,
      faces: map.faces.map(face => [...face.darts]), outerFace: map.outerFace,
      original: map.original, same_shore_edges: bridges,
      real_bridge_edge_ids: bridges.filter(edge => !edge.virtual).map(edge => edge.edge),
      virtual_bridge_edge_ids: bridges.filter(edge => edge.virtual).map(edge => edge.edge),
    };
    result.status = 'geometry_ok';
  } catch (error) {
    result.errors.push({code: typeof error?.code === 'string' ? error.code : 'geometry',
      message: error instanceof Error ? error.message : String(error)});
  }
  return result;
}

const input = JSON.parse(readFileSync(0, 'utf8'));
if (!input || typeof input !== 'object' || !Array.isArray(input.cases)) {
  throw new Error('stdin must contain a cases array.');
}
process.stdout.write(JSON.stringify({schema_version: 1,
  coloring_performed: false, engine_profile: profile,
  results: input.cases.map(exportOne)}) + '\n');
