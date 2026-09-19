/** Geometry-only export for independent full-network restarts.
 *
 * stdin: {cases:[{key:string,document:{strokes,frame?},includeFacePoints?:boolean}]}
 * stdout: {schema_version:1,results:[{key,status,width,height,geometry,errors}]}
 *
 * Every case is independent, including prefixes after a formerly failed naming
 * attempt. Input colors, side names and fixed-color annotations are never read.
 * The engine's 900 x 600 frame and numerical limits are retained explicitly.
 * A hanging edge/bridge is valid geometry: its two darts share one face, which
 * need not be the exterior. Virtual island connectors remain topology only.
 */

import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildMap, WIDTH, HEIGHT, LIMITS} from '../web/engine.js';


/** Export one map or an explicit error, never a partial geometry certificate. */
export function exportRestartGeometry(item) {
  const result = {
    key: typeof item?.key === 'string' ? item.key : null,
    status: 'geometry_error', width: WIDTH, height: HEIGHT,
    coloring_performed: false, geometry: null, errors: [],
  };
  try {
    if (!item || typeof item !== 'object' || Array.isArray(item)
        || typeof item.key !== 'string' || item.key.length === 0) {
      const error = new Error('Each case requires a nonempty string key and a document.');
      error.code = 'input';
      throw error;
    }
    // buildMap normalizes/copies the document and reads only geometry. In
    // particular, no old supplied coloring is used to choose or validate names.
    const map = buildMap(item.document);
    const bridges = [];
    for (let edge = 0; edge < map.edges.length; edge++) {
      const first = map.faceOfDart[2 * edge], second = map.faceOfDart[2 * edge + 1];
      if (first === second) bridges.push({
        edge, face: first, virtual: map.edges[edge].virtual,
        is_exterior_face: first === map.outerFace,
      });
    }
    const geometry = {
      vertices: map.vertices,
      // frame and sources are required by the existing whole-line adapter;
      // sources index input stroke segments, not colors or face identities.
      edges: map.edges.map(edge => ({
        a: edge.a, b: edge.b, virtual: edge.virtual,
        frame: edge.frame, sources: [...edge.sources],
      })),
      rotation: map.rotation,
      faceOfDart: map.faceOfDart,
      faces: map.faces.map(face => [...face.darts]),
      outerFace: map.outerFace,
      original: map.original,
      same_shore_edges: bridges,
      real_bridge_edge_ids: bridges.filter(edge => !edge.virtual).map(edge => edge.edge),
      virtual_bridge_edge_ids: bridges.filter(edge => edge.virtual).map(edge => edge.edge),
    };
    // Optional drawing data are the engine's existing face polygons. They are
    // not newly inferred regions and have no associated names or fill colors.
    if (item.includeFacePoints === true) {
      geometry.face_points = map.faces.map(face => face.points.map(point => [...point]));
    }
    result.status = 'geometry_ok';
    result.geometry = geometry;
  } catch (error) {
    result.errors.push({
      code: typeof error?.code === 'string' ? error.code : 'geometry',
      message: error instanceof Error ? error.message : String(error),
    });
  }
  return result;
}


/** One malformed case cannot hide another case's geometry or failure record. */
function main() {
  try {
    const input = JSON.parse(readFileSync(0, 'utf8'));
    if (!input || typeof input !== 'object' || !Array.isArray(input.cases)) {
      throw new Error('stdin must be an object containing a cases array.');
    }
    const results = input.cases.map(exportRestartGeometry);
    process.stdout.write(JSON.stringify({
      schema_version: 1,
      width: WIDTH, height: HEIGHT,
      coordinate_system: 'x-right, y-down; mathematical CCW rotations; 1e-6 pixel vertex grid',
      engine_limits: LIMITS,
      coloring_performed: false,
      bridge_semantics: 'Equal shore identities, not an inequality or an automatic exterior label.',
      results,
    }) + '\n');
  } catch (error) {
    process.stderr.write((error instanceof Error ? error.message : String(error)) + '\n');
    process.exitCode = 1;
  }
}


// Imports are silent so Node tests and future runners can reuse the function.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
