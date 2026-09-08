/** Public fixtures: failed steps are retained, not filtered out of the gallery. */
import {buildMap} from './engine.js';
const split=points=>({points,expectedStatus:'split'});
const step=(points,expectedStatus)=>({points,expectedStatus});
const rectangle=[[250,180],[650,180],[650,420],[250,420],[250,180]];
const triangle=[[450,80],[160,510],[740,510],[450,80]];
const A=[[300,0],[300,600]],B=[[300,400],[900,400]],C=[[150,0],[150,600]],D=[[150,200],[300,200]];
const inner=[[450,150],[650,225],[650,375],[450,450],[250,375],[250,225]];
const outer=[[450,0],[900,150],[900,450],[450,600],[0,450],[0,150]];
/** Explicit, separately verified precoloring; no hidden solver is called. */
export function hexSeed(){
  const document={title:'六边形 · 已核验预标输入',strokes:[...inner.map((p,i)=>({a:p,b:inner[(i+1)%6]})),...inner.map((p,i)=>({a:p,b:outer[i]}))]};
  const map=buildMap(document),colors=[0,3,1,2,3,1,2,0];
  return {document,names:map.edges.map((e,i)=>[colors[map.faceOfDart[2*i]],colors[map.faceOfDart[2*i+1]]])};
}
export const CONSTRUCTION_CASES=[
  {id:'tetrahedron',title:'四种符号确实出现',description:'3 步构造四面体邻接：每一步都留下可检查的线名。',steps:[split(triangle),split([[450,80],[450,350],[160,510]]),split([[740,510],[450,350]])]},
  {id:'order-blocked',title:'同图对照 A · 受阻',description:'A → B → C → D：前三步合法，第四步两个子侧都遇到其余三种符号。',steps:[split(A),split(B),split(C),step(D,'blocked')]},
  {id:'order-success',title:'同图对照 B · 成功',description:'相同最终线段，改成 A → C → D → B，四步都可直接选标。不是通用顺序算法。',steps:[split(A),split(C),split(D),split(B)]},
  {id:'horizontal',title:'边界 → 边界',description:'两端锚定的一笔横线；一个子侧继承，另一个子侧改名。',steps:[split([[0,300],[900,300]])]},
  {id:'polyline',title:'折线也可锚定',description:'点击若干折点；只有整个简单路径完成锚定才提交。',steps:[split([[0,180],[200,180],[400,300],[700,420],[900,420]])]},
  {id:'loop',title:'空白起笔 → 闭环',description:'独立闭环不必从旧线上起笔。闭合前所有线段仍是草稿。',steps:[split(rectangle)]},
  {id:'nested',title:'嵌套闭环',description:'内外两环都有真实两侧；辅助桥不参与锚定。',steps:[split(rectangle),split([[350,240],[550,240],[550,360],[350,360],[350,240]])]},
  {id:'bridge',title:'第一桥 / 第二次分割',description:'先闭环，再接左桥（不分割），最后接右线（增加一个侧空间）。',steps:[split(rectangle),step([[0,300],[250,300]],'bridge'),split([[650,300],[900,300]])]},
  {id:'free-end',title:'自由端不提交',description:'只有起点锚定仍然是草稿；不创建分割，不更新任何旧线名。',steps:[step([[0,300],[450,300]],'draft')]},
  {id:'virtual-anchor',title:'虚拟线不是锚点',description:'隐形辅助桥的内部点不能作为真实线的起点。',steps:[split(rectangle),step([[775,180],[775,0]],'draft')]},
  {id:'crossing',title:'穿越旧线被拒绝',description:'一次基本操作不能中途穿越旧线；应在接触处结束，再另起一笔。',steps:[split([[0,300],[900,300]]),step([[450,0],[450,600]],'invalid')]},
  {id:'oblique-anchor',title:'斜线精确锚定',description:'分数坐标的接触必须保留，不能先粗舍入再判断锚定。',steps:[split([[0,0],[900,599]]),split([[100,599*100/900],[0,200]])]},
  {id:'hex-precolored',title:'预标阻塞证书',description:'从显式已验证的六边形线名开始，不声称这些线名由当前顺序生成。',seed:hexSeed,steps:[step([inner[0],inner[3]],'blocked')]},
];
