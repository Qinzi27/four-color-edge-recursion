/** Emit deterministic browser-engine records for the independent Python checker. */
import {analyzeDrawing,exportDocument} from '../web/engine.js';
import {CASES,caseDocument} from '../web/cases.js';
const seed=20260907;let state=seed;
const random=()=>{state=(Math.imul(1664525,state)+1013904223)>>>0;return state/2**32;};
const inputs=CASES.map(c=>({id:c.id,document:caseDocument(c.id)}));
for(let n=0;n<30;n++){
  const strokes=[];for(let i=0;i<3+n%10;i++)strokes.push({a:[0,Math.round((20+560*random())*1000)/1000],b:[900,Math.round((20+560*random())*1000)/1000]});
  inputs.push({id:`seeded-lines-${n}`,document:{title:`Seed ${seed} sample ${n}`,strokes}});
}
const records=inputs.map(({id,document})=>{const result=analyzeDrawing(document);return{id,...exportDocument(document,result)};});
process.stdout.write(JSON.stringify({seed,randomFamily:'3..12 left-to-right segments; 30 samples',records}));
