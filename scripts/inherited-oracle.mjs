/** Independent geometry-to-line-name checker for inherited-name experiments.
 *
 * stdin is a JSON array of {key,width,height,cuts,sides}. Cuts are endpoint
 * pairs; sides are {id,bounds:[x0,y0,x1,y1],symbol}. This checker NEVER chooses
 * a name, calls the production naming rule, or assumes a four-symbol palette.
 * It builds geometry independently and samples the two shores of each real
 * atomic edge inside the supplied axis-aligned rectangles. Python's separate
 * audit_line_names then checks shore-orbit consistency from rotation + names.
 *
 * engine.js has a fixed 900 by 600 frame. Input coordinates are affinely
 * scaled to that frame and canonicalized on the engine's 1e-6 pixel grid.
 * Sub-grid rectangles are rejected rather than silently merged. Probes use
 * strict rectangle interiors and an offset smaller than every coordinate gap.
 */

import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {buildMap, WIDTH, HEIGHT} from '../web/engine.js';

// Match engine.js vertex canonicalization; integer areas below use BigInt so
// even very thin rectangles can be checked for exact tiled-frame coverage.
const GRID = 1e6;
const FRAME_X = WIDTH * GRID;
const FRAME_Y = HEIGHT * GRID;

/** Throw a precise input/scope error, caught independently for each case. */
function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

/** Return one numeric coordinate, rejecting NaN, infinities and coercions. */
function coordinate(value, label) {
  requireCondition(typeof value === 'number' && Number.isFinite(value),
    `${label} must be a finite number`);
  return value;
}

/** Validate a rectangular tiling and canonicalize cuts without selecting names. */
function prepare(item) {
  requireCondition(item && typeof item === 'object' && !Array.isArray(item),
    'each case must be an object');
  const width = coordinate(item.width, 'width');
  const height = coordinate(item.height, 'height');
  requireCondition(width > 0 && height > 0, 'width and height must be positive');
  requireCondition(Array.isArray(item.cuts), 'cuts must be an array');
  requireCondition(Array.isArray(item.sides) && item.sides.length > 0,
    'sides must be a nonempty array of rectangles');

  // Axis-by-axis scaling preserves all axis-aligned incidences and directions.
  const integerPoint = (point, label) => {
    requireCondition(Array.isArray(point) && point.length === 2,
      `${label} must be a two-coordinate point`);
    const x = coordinate(point[0], `${label}.x`);
    const y = coordinate(point[1], `${label}.y`);
    requireCondition(x >= 0 && x <= width && y >= 0 && y <= height,
      `${label} lies outside the input frame`);
    return [Math.round(x / width * FRAME_X), Math.round(y / height * FRAME_Y)];
  };
  const pixelPoint = point => point.map(value => value / GRID);
  const xCoordinates = new Set([0, FRAME_X]);
  const yCoordinates = new Set([0, FRAME_Y]);
  const recordPoint = point => {
    xCoordinates.add(point[0]);
    yCoordinates.add(point[1]);
  };
  const strokes = item.cuts.map((cut, index) => {
    requireCondition(Array.isArray(cut) && cut.length === 2,
      `cut ${index} must contain exactly two endpoints`);
    const a = integerPoint(cut[0], `cut ${index} start`);
    const b = integerPoint(cut[1], `cut ${index} end`);
    requireCondition(cut[0][0] === cut[1][0] || cut[0][1] === cut[1][1],
      `cut ${index} is not axis-aligned; oblique cuts are outside this oracle's scope`);
    requireCondition(a[0] !== b[0] || a[1] !== b[1],
      `cut ${index} collapses on the geometry coordinate grid`);
    recordPoint(a);
    recordPoint(b);
    return {a: pixelPoint(a), b: pixelPoint(b)};
  });

  const ids = new Set();
  let tiledArea = 0n;
  const rectangles = item.sides.map((side, index) => {
    requireCondition(side && typeof side === 'object' && !Array.isArray(side),
      `side ${index} must be an object`);
    requireCondition((typeof side.id === 'string' && side.id.length > 0) ||
      (typeof side.id === 'number' && Number.isSafeInteger(side.id)),
    `side ${index} must have a nonempty string or safe-integer id`);
    const identity = JSON.stringify(side.id);
    requireCondition(!ids.has(identity), `side ${index} repeats a side id`);
    ids.add(identity);
    requireCondition(Number.isSafeInteger(side.symbol) && side.symbol > 0,
      `side ${index} symbol must be a positive safe integer, with no palette upper bound`);
    requireCondition(Array.isArray(side.bounds) && side.bounds.length === 4,
      `side ${index} bounds must be [x0,y0,x1,y1]`);
    const a = integerPoint(side.bounds.slice(0, 2), `side ${index} lower bounds`);
    const b = integerPoint(side.bounds.slice(2, 4), `side ${index} upper bounds`);
    requireCondition(a[0] < b[0] && a[1] < b[1],
      `side ${index} is inverted, empty or below the geometry coordinate grid`);
    recordPoint(a);
    recordPoint(b);
    tiledArea += BigInt(b[0] - a[0]) * BigInt(b[1] - a[1]);
    return {id: side.id, symbol: String(side.symbol),
      integerBounds: [...a, ...b], bounds: [...pixelPoint(a), ...pixelPoint(b)]};
  });
  for (let i = 0; i < rectangles.length; i++) {
    const a = rectangles[i].integerBounds;
    for (let j = i + 1; j < rectangles.length; j++) {
      const b = rectangles[j].integerBounds;
      requireCondition(!(Math.max(a[0], b[0]) < Math.min(a[2], b[2]) &&
        Math.max(a[1], b[1]) < Math.min(a[3], b[3])),
      `rectangle interiors overlap: sides ${i} and ${j}`);
    }
  }
  requireCondition(tiledArea === BigInt(FRAME_X) * BigInt(FRAME_Y),
    'the nonoverlapping rectangles do not cover the whole frame on the geometry grid');

  // Every normal probe travels less than one eighth of the narrowest canonical
  // grid interval, not a fixed epsilon that could jump across a narrow strip.
  let smallestGap = Infinity;
  for (const values of [xCoordinates, yCoordinates]) {
    const ordered = [...values].sort((a, b) => a - b);
    for (let i = 1; i < ordered.length; i++) {
      smallestGap = Math.min(smallestGap, ordered[i] - ordered[i - 1]);
    }
  }
  const offset = Math.min(1e-5, smallestGap / GRID / 8);
  requireCondition(Number.isFinite(offset) && offset > 0,
    'cannot choose a positive shore-probe offset');
  return {strokes, rectangles, offset};
}

/** Resolve one strictly interior probe or the explicit exterior symbol 1. */
function probe(point, rectangles) {
  const [x, y] = point;
  if (x < 0 || x > WIDTH || y < 0 || y > HEIGHT) {
    return {kind: 'outside', id: null, symbol: '1'};
  }
  const matches = rectangles.filter(({bounds: [x0, y0, x1, y1]}) =>
    x0 < x && x < x1 && y0 < y && y < y1);
  requireCondition(matches.length === 1,
    `shore probe (${x},${y}) has ${matches.length} strict rectangle matches`);
  return {kind: 'inside', id: matches[0].id, symbol: matches[0].symbol};
}

/** Inspect one completed candidate assignment without relying on engine colors. */
export function inspectInheritedCase(item) {
  const result = {key: item?.key ?? null, rotation: [], names: [],
    edge_conflicts: [], face_count: null, errors: []};
  try {
    const {strokes, rectangles, offset} = prepare(item);
    const map = buildMap({strokes});
    result.face_count = map.faces.length;
    // Incremental rectangular cuts stay connected to the existing frame.
    // Reject islands instead of feeding virtual connectors to the line auditor.
    requireCondition(!map.edges.some(edge => edge.virtual),
      'virtual connectors are outside the connected rectangular-cut oracle scope');
    const names = [];
    const conflicts = [];
    map.edges.forEach((edge, index) => {
      const a = map.vertices[edge.a];
      const b = map.vertices[edge.b];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      requireCondition((dx === 0) !== (dy === 0),
        `atomic edge ${index} is not a nonzero axis-aligned segment`);
      const length = Math.hypot(dx, dy);
      const midpoint = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      // Mathematical left in screen coordinates y-down is (dy,-dx).
      const normal = [dy / length * offset, -dx / length * offset];
      const left = probe([midpoint[0] + normal[0], midpoint[1] + normal[1]], rectangles);
      const right = probe([midpoint[0] - normal[0], midpoint[1] - normal[1]], rectangles);
      names.push([left.symbol, right.symbol]);
      // A dangling real bridge has the SAME rectangle on both shores and must
      // not be mistaken for an equal-name separator. The Python rotation audit
      // independently establishes the actual side-orbit identities afterward.
      const sameIdentity = left.kind === right.kind && left.id === right.id;
      if (!sameIdentity && left.symbol === right.symbol) {
        conflicts.push({edge: index, symbol: left.symbol,
          left_side: left.id, right_side: right.id, endpoints: [a, b]});
      }
    });
    result.rotation = map.rotation.map(turn => [...turn]);
    result.names = names;
    result.edge_conflicts = conflicts;
  } catch (error) {
    // An unsupported or malformed case must not expose a partial certificate.
    result.errors.push(error instanceof Error ? error.message : String(error));
  }
  return result;
}

/** CLI batch entry point: one malformed case does not hide other case results. */
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const input = JSON.parse(readFileSync(0, 'utf8'));
    requireCondition(Array.isArray(input), 'stdin must contain a JSON array of cases');
    process.stdout.write(`${JSON.stringify(input.map(inspectInheritedCase))}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
