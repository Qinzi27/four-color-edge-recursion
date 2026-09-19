/** Preserve the previous 255-map corpus and add 60 fresh seeded geometries.
 * Held-out here means unused in selecting this extension, not a new sampling
 * model. No naming or coloring function supplies fixture answers.
 */
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import {buildMap} from '../web/engine.js';
import {generatedPaths} from './construction-experiments.mjs';
import {wholeLineFixtures} from './whole-line-fixtures.mjs';

const baseline = wholeLineFixtures();
const added = Array.from({length: 60}, (_, i) => {
  const family = i < 20 ? 'guillotine' : i < 40 ? 'nested-rings-and-bridges' : 'boundary-fan';
  const seed = 20261201 + i;
  const paths = generatedPaths(family, seed);
  const document = {schemaVersion: 1, title: `extension-${family}-${seed}`,
    frame: {width: 900, height: 600},
    strokes: paths.flatMap(points => points.slice(1).map((b, j) => ({a: points[j], b})))};
  const map = buildMap(document);
  return {id: document.title, family, seed, cohort: 'fresh-seeds', document,
    geometry: {vertices: map.vertices, edges: map.edges, rotation: map.rotation,
      faceOfDart: map.faceOfDart, faces: map.faces.map(face => face.darts),
      outerFace: map.outerFace, original: map.original}};
});
const filename = new URL('./relation-fixtures.mjs', import.meta.url);
console.log(JSON.stringify({schema_version: 1,
  baseline_maps: 255, fresh_maps: 60, fresh_seed_range: [20261201, 20261260],
  source_sha256: {...baseline.source_sha256,
    'scripts/relation-fixtures.mjs': createHash('sha256').update(fs.readFileSync(filename)).digest('hex')},
  records: [...baseline.records.map(row => ({...row, cohort: 'baseline'})), ...added]}));
