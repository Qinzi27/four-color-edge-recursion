/** Experimental full restart of directed line-side names on FINAL geometry.
 * This module is not wired into the public drawing app. Old names and drawing
 * chronology are not inputs. Side orbits come from line endpoint rotations;
 * one assignment propagates to every dart of that orbit. Priority choices are
 * explicit heuristics, not a theorem or a settled mother-line recursion.
 * Names are positive integers without a four-name cap. A fifth name is evidence
 * against this particular rule's four-name bound, never against the map itself.
 */
import {buildMap} from './engine.js';

export const PRIORITY_POLICIES=Object.freeze(['boundary','layer-constraint','constraint-layer']);
export const PRIORITY_VERSION='0.1.0';

/** Rotate a side-boundary walk to a geometric start, independent of edge IDs.
 * Reversing scan order changes only tie-breaking, not the darts' left/right
 * meanings. Virtual same-side bridges never discover another side.
 */
function orderedBoundary(map,side,direction) {
  const darts=map.faces[side].darts;
  const tail=d=>map.vertices[map.edges[d>>1][d%2?'b':'a']];
  const key=d=>[tail(d)[1],tail(d)[0],tail(d^1)[1],tail(d^1)[0]];
  const compare=(a,b)=>{
    const p=key(a),q=key(b);
    for(let i=0;i<p.length;i++)if(p[i]!==q[i])return p[i]-q[i];
    return 0;
  };
  const start=darts.indexOf([...darts].sort(compare)[0]);
  const result=[...darts.slice(start),...darts.slice(0,start)];
  return direction==='clockwise'?result:result.reverse();
}

/** Precompute root distances and a geometric BFS discovery order.
 * The resulting parent is a DISCOVERY link, not a claim of unique geometric
 * parenthood. All additional closing/non-tree contacts remain constraints.
 */
function rootOrder(map,direction) {
  const depth=Array(map.faces.length).fill(null),rank=Array(map.faces.length).fill(null);
  const parent=Array(map.faces.length).fill(null),queue=[map.outerFace];
  depth[map.outerFace]=0;rank[map.outerFace]=0;
  for(let k=0;k<queue.length;k++)for(const dart of orderedBoundary(map,queue[k],direction)) {
    if(map.edges[dart>>1].virtual)continue;
    const other=map.faceOfDart[dart^1];
    if(depth[other]!==null)continue;
    depth[other]=depth[queue[k]]+1;rank[other]=queue.length;
    parent[other]={side:queue[k],dart};queue.push(other);
  }
  if(queue.length!==map.faces.length)throw new Error('Real separators did not reach every side.');
  return {depth,rank,parent};
}

/** Lexicographic priority: explicit final rank prevents hidden ID tie-breaks. */
function priorityKey(policy,depth,saturation,rank) {
  if(policy==='boundary')return [rank];
  return policy==='layer-constraint'?[depth,-saturation,rank]:[-saturation,depth,rank];
}

/** Name one final line network, without retries or color-assignment search.
 * boundary: static rooted boundary-discovery order;
 * layer-constraint: nearer root, then more DISTINCT known opposing names;
 * constraint-layer: more distinct known names, then nearer root.
 * Saturation is updated after each assignment. All policies only process the
 * frontier touching a named side. Color counts are outputs, not assumptions.
 */
export function nameByPriority(document,options={}) {
  const policy=options.policy??'layer-constraint',direction=options.direction??'clockwise';
  if(!PRIORITY_POLICIES.includes(policy))throw new Error('Unknown priority policy.');
  if(!['clockwise','counterclockwise'].includes(direction))throw new Error('Unknown boundary direction.');
  const map=buildMap(document),root=rootOrder(map,direction);
  const symbols=Array(map.faces.length).fill(null),dartNames=Array(map.edges.length*2).fill(null),trace=[];
  const assign=(side,symbol)=>{
    symbols[side]=symbol;
    for(const dart of map.faces[side].darts)dartNames[dart]=symbol;
  };
  assign(map.outerFace,1);
  while(trace.length<map.faces.length-1) {
    const frontier=[];
    for(let side=0;side<map.faces.length;side++)if(symbols[side]===null) {
      // Read all opposite shores, not merely the discovery/parent edge.
      const known=[];
      for(const dart of map.faces[side].darts)if(dartNames[dart^1]!==null)
        known.push({dart,other:map.faceOfDart[dart^1],symbol:dartNames[dart^1]});
      if(!known.length)continue;
      const forbidden=[...new Set(known.map(item=>item.symbol))].sort((a,b)=>a-b);
      const key=priorityKey(policy,root.depth[side],forbidden.length,root.rank[side]);
      frontier.push({side,forbidden,key});
    }
    frontier.sort((a,b)=>{
      for(let i=0;i<a.key.length;i++)if(a.key[i]!==b.key[i])return a.key[i]-b.key[i];
      return 0;
    });
    if(!frontier.length)throw new Error('Unresolved side without a rooted frontier.');
    const chosen=frontier[0],forbidden=new Set(chosen.forbidden);
    let symbol=1;
    while(forbidden.has(symbol))symbol++;
    assign(chosen.side,symbol);
    trace.push({side:chosen.side,symbol,forbidden:chosen.forbidden,
      depth:root.depth[chosen.side],rank:root.rank[chosen.side],
      discovery:root.parent[chosen.side],priorityKey:chosen.key});
  }
  const names=map.edges.map((_,i)=>[dartNames[2*i],dartNames[2*i+1]]);
  // An unrestricted-name check stays valid even when a proposed rule uses 5+.
  names.forEach((pair,i)=>{
    const sameSide=map.faceOfDart[2*i]===map.faceOfDart[2*i+1];
    if((pair[0]===pair[1])!==sameSide)throw new Error('Line-name invariant failed.');
  });
  const paletteSize=new Set(symbols).size;
  return {map,names,symbols,trace,paletteSize,withinFour:paletteSize<=4,
    policy,direction,backtracks:0,oldNamesUsed:false,version:PRIORITY_VERSION};
}
