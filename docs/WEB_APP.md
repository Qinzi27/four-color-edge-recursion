# 四色地图实验室：使用、算法与复现

公开入口：[GitHub Pages](https://qinzi27.github.io/four-color-edge-recursion/)，无需登录。
[递归模型图解](https://qinzi27.github.io/four-color-edge-recursion/model.html)与画板的
候选色标基线分开呈现；[方法审计](METHOD_REVIEW-2026-09-07.md)解释差异和待补规则。
发布工作流在 `.github/workflows/pages.yml`，只部署 `dist/` 的静态资源。

## 1. 本版做什么

首版是本仓库的交互研究工具，不是另一套四色定理证明。由 Qinzi27 提出边侧递归
思路，并要求着色采用直接选取色标而非遍历着色方案。网页据此提供一个可检查的
无回溯实验策略；该具体贪心优先级是实现选择，并不冒充已经证明的原创定理。

在仓库根目录运行（Node.js 20+，无需额外依赖）：

```sh
npm run dev
```

Windows PowerShell 如果阻止 `npm.ps1`，使用 `npm.cmd run dev`。
打开终端打印的地址。不要直接双击 `web/index.html`：模块 Worker 需要 HTTP 服务。

1. 选取四面体、网格、嵌套岛屿、悬空线、仅点接触、固定种子线段或空白案例。
2. 拖动画一条直线，或先后点击起点、终点。交点自动分段，靠近端点/已有边时吸附。
3. 勾选自动填色后，每次编辑自动识别区域并选色；否则手动点“选取色标并验证”。
4. 切到查边，点击实际边。箭头给方向，右侧显示左右面编号、色标与 XOR 差分。
5. Escape 取消未完成线段；撤销或 Ctrl/⌘+Z 回到前一张地图，包括清空和导入前状态。
6. 导出 JSON 保存原始线段的顺序和当前结果；导入时重新计算，不信任文件自带证书。
   导出 SVG 保存当前填色图。数据计算在浏览器内完成，没有应用级上传或持久存储。

JSON 导出中的 `strokes` 是可重放的画线顺序，不是原 Python `CloseSplit` 操作日志。
当前版编辑后重建面编号，并重新选色；**不承诺保留旧面的颜色或完整父子面谱系**。
无修改时再次点击填色复用当前结果，不重复运行选择。

## 2. 色标如何直接选取

面身份记为 `f`；色标 `0,1,2,3` 对应群元素 `00,01,10,11`，界面显示为 `1,2,3,4`。
候选集合用四位掩码表示：`1111` 表示四个都可用，而不是某一个颜色。
已赋色面只会从相邻未赋色面的候选集合中删除自己的色标：

$$M(f)=1111_2\;\&\;\neg\left(\bigvee_{g\sim f,\ c(g)\text{ 已确定}}2^{c(g)}\right).$$

选择规则固定如下：

1. 外部面先固定为 `00`，消除整体换名的一部分对称性。
2. 选候选数最少的未赋色面；相同时选邻接度最高的面，再相同选编号最小的面。
3. 若 `M(f)=0`，返回 `blocked`，保留部分着色和阻塞邻面，不再尝试另一种颜色。
4. 否则 `bit = M(f) & -M(f)` 直接取最低可用位，`c(f)=log2(bit)`。
5. 从未赋色邻面的候选集中删除该位。已赋色面不重新赋色。

这是单次选择加邻接传播，没有颜色分支、完整方案枚举或回溯。选择面时仍要扫描
面记录，识别区域和验证证书仍要走访图；这些不是枚举着色方案。
本实现的选色阶段复杂度为 `O(F² + E_dual)`，保留至多 `F` 条赋色记录。
它不生成颜色置换形成的重复方案，也不声称对所有同构地图作了统一规范化。

可用标记总共四个，不意味着候选集合永不为空。若要从实验推进到一般构造定理，
仍须证明特定分割类和选择规则下可延拓，或者提出有证明保证的额外边界状态规则。
这与“把所有可能颜色都试完”是不同的研究目标。

## 3. 一个必须如实报告的阻塞反例

以下是算法层的对偶邻接图，不是直线画板案例。0 号点固定色标 0：

```js
const adjacency = [
  [1,2,4,6,7], [0,2,5,7], [0,1,5,6], [4,5,6,7],
  [0,3,6,7], [1,2,3,6,7], [0,2,3,4,5], [0,1,3,4,5]
];
```

规则依次赋色 `0:0 → 6:1 → 2:2 → 5:0 → 1:1 → 7:2 → 3:3`，随后点 4
被邻点的四色全部排除，返回阻塞。但 `[0,1,2,0,3,3,1,2]` 是合法四色见证。
这是具有 8 点、18 边、12 三角面的平面图；测试给出三角面证书，检查每边两面、
每个顶点的 link 为单圈以及欧拉示性数 2。因此失败原因确实是规则，而不是输入非平面。
这个反例由有限构造核验，不是引用自文献，不作反例本身的新颖性声明。

## 4. 从直线到边侧模型

处理链是：原始线段 → 交点/重合段细分 → 去重实际边 → 旋转系统 → 面 → 候选色标选择
→ 左右岸/差分 → 完整证书检查。

画框为 `900 × 600`，边界计入图，框外另计一面。仅点接触不是面邻接。
孤立边界和嵌套岛屿用向右的隐藏桥接到其他连通分量，桥不创造新面；
渲染时隐藏桥不画出来，面填充用 even-odd 规则保留孔洞。
每次重建都检查这些桥的左右面相同。

数学坐标取 `(screenX,-screenY)`，顶点旋转顺序为逆时针。
每条边使用 dart `2i` 与 `2i+1`；左面后继是 `previous_CCW(twin(d))`。
成功赋色后检查：共享边的不同面异色、桥差分零、原图顶点 XOR 缺陷零、
对偶传播路径一致、欧拉关系和面积覆盖。完整检查仅为该次结果签发证书。

## 5. 限制与错误处理

- 最多 80 条输入线段、1,600 条细分边、400 个面；超限明确提示。
- 输入端点取 0.001 网格，交点身份取 0.000001 网格；几何使用浮点数，非精确算术。
  极近共线、极薄区域可能被拒绝，需要把边界稍微移开。拓扑校验不是浮点几何完备性证明。
- 只支持有限直线段；曲线可折线逼近，不支持从照片或手绘位图自动识别边界。
- Worker 超时或几何失败与色标阻塞分开报告；都不解释为需要第五色。
- 页面不暗中调用 Python 中的枚举器，也不在阻塞后自动替换为其他搜索算法。
- 可选 WebMCP 工具与按钮共享动作。支持检测及适配器模拟测试已实现；没有可用的
  受支持 WebMCP 浏览器验证上下文，因此不声称实际上下文验证通过。
- 本次未做浏览器点击/截图测试；自动验证覆盖数学引擎、输入、导出复算和适配器。

## 6. 复现与检查

```sh
npm test
npm run build
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/validate_web.py
```

`npm test` 包含 23 项：案例几何、单次赋色/候选集合重放、方向、点接触、重合、
桥、导入/导出、非法输入、贪心阻塞、冻结旧色的分面反例及 WebMCP 适配器模拟检查。
`validate_web.py` 用既有 Python `PlaneMap` 独立重建浏览器导出的旋转系统，
核验面、差分和积分；输入是 7 个内置案例及种子 `20260907` 的 30 张地图。
记录见 `outputs/web-validation.json`。所有成功记录都是有限证据。

`npm run build` 复制 `web/` 静态资源和独立的 `docs/explainer.html` 图解到 `dist/`；
不包含 Python、私人记录或密钥。
公开 GitHub 仓库不自动改变托管网站访问权限，也不能保证搜索引擎收录。

## English summary

The dependency-free web app planarizes straight segments, extracts oriented face
boundaries, and selects color markers from candidate bitmasks without backtracking.
It assigns each face at most once per run, reports a greedy obstruction explicitly,
and verifies completed assignments with the repository's edge-side/V4 model.
The rule is incomplete, as demonstrated by a planar eight-vertex regression graph.
JSON replays geometry and deterministic selection, not a formal proof or persistent
face lineage. The Python enumeration baseline remains separate and is never used
by the browser. See the commands above to reproduce the finite checks.
