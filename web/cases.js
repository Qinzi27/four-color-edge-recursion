/** Original, deterministic teaching maps; no third-party image licensing needed. */
import { WIDTH, HEIGHT } from './engine.js';
const line=(a,b)=>({a,b});
const polygon=points=>points.map((a,i)=>line(a,points[(i+1)%points.length]));
const triangle=[[450,80],[160,510],[740,510]],center=[450,350];
function grid(){const result=[];for(const x of [180,360,540,720])result.push(line([x,0],[x,HEIGHT]));for(const y of [150,300,450])result.push(line([0,y],[WIDTH,y]));return result;}
function seeded(seed){
  // LCG is specified for reproducible pseudo-random examples, not cryptography.
  let value=seed>>>0;const random=()=>((value=(Math.imul(value,1664525)+1013904223)>>>0)/4294967296);
  const result=[];for(let i=0;i<11;i++)result.push(line([0,Math.round(random()*HEIGHT)],[WIDTH,Math.round(random()*HEIGHT)]));return result;
}
export const CASES=[
  {id:'tetrahedron',title:'四面体地图',description:'内部三块与外围区域两两相邻，四种颜色都需要。',strokes:[...polygon(triangle),...triangle.map(p=>line(p,center))]},
  {id:'grid',title:'横纵网格',description:'线与线的每个交点都会细分，生成 20 个画框内区域。',strokes:grid()},
  {id:'islands',title:'嵌套岛屿',description:'独立闭环与带孔区域：隐藏桥连接嵌入，不创造新面。',strokes:[...polygon([[100,100],[800,100],[800,500],[100,500]]),...polygon([[300,220],[600,220],[600,400],[300,400]])]},
  {id:'dangling',title:'悬空与交叉',description:'开放的 X 和悬空线并不围出新区域。',strokes:[line([250,150],[550,420]),line([250,420],[550,150]),line([0,300],[170,300])]},
  {id:'touching',title:'只在一点接触',description:'两个区域仅在顶点接触时，不要求颜色不同。',strokes:[...polygon([[120,90],[450,90],[450,300],[120,300]]),...polygon([[450,300],[780,300],[780,510],[450,510]])]},
  {id:'seeded',title:'随机分割',description:'固定种子 20260907 的 11 条横切线，每次都可复现。',strokes:seeded(20260907)},
  {id:'blank',title:'空白画框',description:'自由添加线段；画框外部也参与着色。',strokes:[]},
];
export function caseDocument(id){const item=CASES.find(c=>c.id===id);if(!item)throw new Error('未知案例');return {schemaVersion:1,title:item.title,frame:{width:WIDTH,height:HEIGHT},strokes:item.strokes.map(s=>({a:[...s.a],b:[...s.b]}))};}
