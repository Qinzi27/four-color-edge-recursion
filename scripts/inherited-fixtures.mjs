/** Export geometry-only histories; do not invoke any naming/coloring method. */
import {generatedPaths} from './construction-experiments.mjs';

const records = [...Array.from({length: 160}, (_, i) => ({seed: 20260908 + i, cohort: 'baseline'})),
  ...Array.from({length: 20}, (_, i) => ({seed: 20261201 + i, cohort: 'fresh-seeds'}))]
  .map(row => ({...row, family: 'guillotine', paths: generatedPaths('guillotine', row.seed)}));
console.log(JSON.stringify({schema_version: 1, records}));
