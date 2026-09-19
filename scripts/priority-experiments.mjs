/** Fixed-corpus experiments for rebuilding all line-side names from geometry.
 * Each policy/direction is reported separately, including every fifth name.
 * The generator never stops at a former incremental algorithm's blocked step.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {CASES, caseDocument} from '../web/cases.js';
import {FIRST_SEED, generatedPaths} from './construction-experiments.mjs';
import {PRIORITY_POLICIES, nameByPriority} from '../web/priority-names.js';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
export const DIRECTIONS = ['clockwise', 'counterclockwise'];

/** Flatten every generated path; drawing history supplies no old names. */
function documentFromPaths(title, paths) {
  return {schemaVersion: 1, title, frame: {width: 900, height: 600},
    strokes: paths.flatMap(points => points.slice(1).map((b, i) => ({a: points[i], b})))};
}

/** D and E are exact geometries from the explanatory diagrams, not repairs. */
export function teachingDocuments() {
  const d = [
    [[0, 180], [900, 180]], [[300, 180], [300, 600]],
    [[600, 180], [600, 600]], [[450, 180], [450, 600]],
  ];
  const e = [
    [[0, 214], [900, 214]], [[0, 471], [900, 471]],
    [[0, 123], [900, 123]], [[312, 123], [312, 214]],
    [[339, 471], [339, 600]], [[199, 471], [199, 600]],
    [[598, 123], [598, 214]], [[454, 214], [454, 471]],
  ];
  return [{id: 'teaching-D', paths: d}, {id: 'teaching-E', paths: e}].map(row => ({
    id: row.id, family: 'teaching', seed: null, planned_paths: row.paths.length,
    document: documentFromPaths(row.id, row.paths),
  }));
}

/** Deliberately designed rule counterexamples, separate from the random corpus. */
export function targetedDocuments() {
  const boundary = [
    [[647, 0], [647, 600]], [[647, 339], [900, 339]],
    [[753, 339], [753, 600]], [[830, 339], [830, 600]],
  ];
  const saturation = [
    [[450, 0], [450, 600]], [[450, 300], [900, 300]],
    [[650, 0], [650, 300]], [[450, 120], [650, 120]],
    [[650, 100], [900, 100]], [[450, 240], [650, 240]],
  ];
  const left = saturation.map(points => points.map(([x, y]) => [x / 2, y]));
  const right = saturation.map(points => points.map(([x, y]) => [900 - x / 2, y]));
  const both = [...left, ...right, [[450, 0], [450, 600]]];
  return [{id: 'priority-boundary-4lines', paths: boundary},
    {id: 'priority-saturation-6lines', paths: saturation},
    {id: 'priority-two-direction-13lines', paths: both}].map(row => ({
    id: row.id, family: 'targeted', seed: null, planned_paths: row.paths.length,
    provenance: 'Constructed directed-rule counterexample; not an additional random sample.',
    document: documentFromPaths(row.id, row.paths),
  }));
}

/** Share one rotation-system certificate across all six assignments. */
function snapshot(map) {
  return {vertices: map.vertices, edges: map.edges, rotation: map.rotation,
    faces: map.faces.map(face => face.darts), faceOfDart: map.faceOfDart,
    outerFace: map.outerFace, original: map.original};
}

/** Retain the first fifth-name step without suggesting non-four-colorability. */
function firstFifth(trace) {
  const index = trace.findIndex(step => step.symbol > 4);
  return index < 0 ? null : {step: index + 1, ...trace[index]};
}

/** Report every rule independently; never choose its best result per map. */
export function summarize(records) {
  const rows = [];
  for (const policy of PRIORITY_POLICIES) for (const direction of DIRECTIONS) {
    const runs = records.map(record => ({record, run: record.runs.find(
      item => item.policy === policy && item.direction === direction)}));
    const paletteCounts = {};
    for (const {run} of runs) paletteCounts[run.paletteSize] = (paletteCounts[run.paletteSize] ?? 0) + 1;
    const failures = runs.filter(({run}) => !run.withinFour);
    rows.push({policy, direction, maps: runs.length,
      within_four: runs.length - failures.length, more_than_four: failures.length,
      maximum_palette: Math.max(...runs.map(({run}) => run.paletteSize)),
      palette_counts: paletteCounts, counterexample_ids: failures.map(({record}) => record.id),
      first_counterexample: failures.length ? {id: failures[0].record.id,
        seed: failures[0].record.seed, ...failures[0].run.first_fifth} : null});
  }
  return rows;
}

/** Execute the complete fixed corpus, preserving input geometry and traces. */
export function runPriorityExperiments() {
  const inputs = CASES.map(item => ({id: 'gallery-' + item.id, family: 'gallery', seed: null,
    planned_paths: null, document: caseDocument(item.id)})).concat(teachingDocuments(), targetedDocuments());
  for (let i = 0; i < 240; i++) {
    const seed = FIRST_SEED + i;
    const family = i < 160 ? 'guillotine' : i < 200 ? 'nested-rings-and-bridges' : 'boundary-fan';
    const paths = generatedPaths(family, seed);
    inputs.push({id: family + '-' + seed, family, seed, planned_paths: paths.length,
      document: documentFromPaths(family + '-' + seed, paths)});
  }
  const records = inputs.map(input => {
    let geometry = null;
    const runs = [];
    for (const policy of PRIORITY_POLICIES) for (const direction of DIRECTIONS) {
      const result = nameByPriority(input.document, {policy, direction});
      const current = snapshot(result.map);
      if (geometry === null) geometry = current;
      else assert.deepEqual(current, geometry, 'Naming order must not change final geometry');
      const {names, symbols, trace, paletteSize, withinFour, backtracks} = result;
      assert.equal(backtracks, 0);
      runs.push({policy, direction, names, symbols, trace, paletteSize, withinFour,
        backtracks, first_fifth: firstFifth(trace)});
    }
    return {...input, geometry, runs};
  });
  const sources = ['web/priority-names.js', 'web/engine.js', 'web/cases.js',
    'scripts/construction-experiments.mjs', 'scripts/priority-experiments.mjs'];
  return {schema_version: 1, experiment: 'full-geometry priority line-side naming',
    generated_maps: 240, gallery_maps: CASES.length, teaching_maps: 2, targeted_maps: 3,
    seed_range: [FIRST_SEED, FIRST_SEED + 239],
    random_generator: 'uint32 LCG: state = 1664525*state + 1013904223',
    policies: [...PRIORITY_POLICIES], directions: [...DIRECTIONS],
    input_scope: 'Every complete final geometry; no truncation at incremental blocked states.',
    algorithm_scope: 'Greedy smallest available positive integer; no four-name cap, recoloring, assignment enumeration, or backtracking.',
    interpretation: 'More than four names is a counterexample to this specified rule staying within four, NOT to four-colorability or to all possible priority rules. Six variants are not selected per map.',
    source_sha256: Object.fromEntries(sources.map(source => [source,
      createHash('sha256').update(fs.readFileSync(path.join(ROOT, source))).digest('hex')])),
    summaries: summarize(records), records};
}

// Importing the experiment helpers must not execute a second experiment.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
    && process.argv.includes('--emit')) {
  process.stdout.write(JSON.stringify(runPriorityExperiments()));
}
