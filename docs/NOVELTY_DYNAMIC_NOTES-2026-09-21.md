# 动态着色与最小改色：定向查新记录

检索日期：2026-09-21。范围：dynamic / incremental graph coloring、recourse、Color-Fixing、Kempe 最短重构与未来邻接信息。本文是有边界的定向查新，不是穷尽检索或原创性鉴定。只向外部发送通用检索词，未上传本项目材料。

**当前判断：最小净改色目标、冲突边预算分支、按边界配色做动态规划、动态着色的大改动下界、Kempe 最短步数和提前预防冲突，都已有明确先例。本项目的真实贯穿矩形族、零成本子侧口径及精确 `2m` 证书仍需作为一个完整的特定命题查重；本轮没有找到逐项相同的表述，但不能因此认定原创。**

## 1. 最接近的已有工作

### A. Color-Fixing：最小净改色与预算搜索

Valentin Garnero, Konstanty Junosza-Szaniawski, Mathieu Liedloff, Pedro Montealegre, Paweł Rzążewski. *Fixing improper colorings of graphs*. Theoretical Computer Science 711 (2018), 66–78. [正式版 DOI](https://doi.org/10.1016/j.tcs.2017.11.013)；[已读取的 arXiv v2 全文](https://arxiv.org/html/1607.06911)。早期会议版为 SOFSEM 2015；这里定理编号均按 arXiv v2。

- §2.1 直接定义：从给定不合法着色到任意合法着色，最小化 Hamming 距离，即改色顶点数。
- §4.1 Algorithm 1、Theorem 15：选一条冲突边，分支改变其中一个端点；时间为 `(2(r−1))^k poly(n)`，参数为 `k+r`。
- §4.2 Theorem 23：按树分解袋的合法着色保存状态，可求最小修复成本，时间为 `r^t poly(n)`。
- §3.1 引入 List-Fix，可限制各顶点可用颜色。

短引文（§2.1）：“to be their Hamming distance”。译：将两种着色的距离定义为汉明距离。它支持“最少净改色”是已有问题；不提供合法中间路径保证。

与项目对应：`conservative_recoloring.py` 的冲突边分支属于这一已知路线的受限加权实现。项目还处理固定侧、零权重子侧、永久承诺、截断时返回 unknown；这些应作为实现差异逐项描述。不能把上述 `6^k` 直接套到任意零权重输入，因为零成本承诺仍会增加搜索深度。当前代码明确用可承诺顶点数约束深度。

### B. Dynamic Graph Coloring：大范围修复不是新现象

Luis Barba, Jean Cardinal, Matias Korman, Stefan Langerman, André van Renssen, Marcel Roeloffzen, Sander Verdonschot. *Dynamic Graph Coloring*. Algorithmica 81 (2019), 1319–1341；在线发表 2018。[已读取的出版社全文](https://link.springer.com/article/10.1007/s00453-018-0473-y)。

§1.2 给出三颗星的直观构造：保持两色时，连接同色根迫使至少 `n/3` 顶点改色；§4 推广为任何固定颜色数的动态改色下界。短引文（§1.2）：“we force the algorithm to recolor at least n/3 vertices”。译：迫使算法至少改变 `n/3` 个顶点的颜色。

因此“一条新边可能迫使线性多个顶点改色”本身不能作为本项目的新结论。差别在于：本项目指定四色色板、固定通邻外侧、由真实矩形切割实现、只计旧侧，并给出精确 `2m`；该文考察算法面对更新序列的保证。两种量词和图类不能互换。本项目目前也未证明其指定困难初态会由现有策略产生。

### C. Kempe Distance：交换步数已有独立研究

Marthe Bonamy, Marc Heinrich, Takehiro Ito, Yusuke Kobayashi, Haruka Mizuta, Moritz Mühlenthaler, Akira Suzuki, Kunihiro Wasa. *Shortest Reconfiguration of Colorings Under Kempe Changes*. STACS 2020, 35:1–35:14。[正式记录](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.STACS.2020.35)；[已读取 PDF](https://drops.dagstuhl.de/storage/00lipics/lipics-vol154-stacs2020/LIPIcs.STACS.2020.35/LIPIcs.STACS.2020.35.pdf)。

Theorem 2（第 35:6 页）给路径上的 Kempe Distance 一个 `O(nk)` 算法；Theorem 12（第 35:11 页）证明星图上的判定问题 NP-complete，这里颜色数属于输入。短引文：“Kempe Distance on stars is NP-complete.” 译：星图上的 Kempe 距离问题是 NP 完全的。

这说明找最少交换序列本身是已有优化问题。其目标端点预先给定；本项目通常先在所有修复终点中选低成本目标，再考虑路径。两者不能直接用同一成绩表比较；该 NP 完全性也不能直接声称适用于固定四色实例。一次交换可以包含多个顶点，因而步数与净改色数的区分首先是操作定义的区别。

### D. 插边之后的启发式修复

Jakob Bossek, Frank Neumann, Pan Peng, Dirk Sudholt. *Time Complexity Analysis of Randomized Search Heuristics for the Dynamic Graph Coloring Problem*. Algorithmica 83 (2021), 3148–3179。[出版社全文](https://link.springer.com/article/10.1007/s00453-021-00838-3)。

§1、§3.3 分析插边后的重优化；某些实例只增加一条边，也能令指定 Kempe 启发式很慢。§5 的局部定制算子说明，利用变化位置可改善部分时间界。这里研究算法运行时间，不等于终点 Hamming 成本或最短 Kempe 步数。本项目可借鉴其基线、更新位置、困难实例和算子消融设计，不能把现有有限样本成绩称为普遍复杂度改进。

### E. 预防未来冲突已有先例

Bradley Hardy, Rhyd Lewis, Jonathan Thompson. *Tackling the edge dynamic graph colouring problem with and without future adjacency information*. Journal of Heuristics 24 (2018), 321–343；在线发表 2017。[出版社全文](https://link.springer.com/article/10.1007/s10732-017-9327-z)。

§4 使用未来邻接概率定义预期冲突；§4.1.1 用 Kempe 交换保持当前合法性；§5.2 在当前合法状态中降低未来冲突。它的主要动态目标包含颜色数，不是我们的固定四色旧侧修复成本。可参考其“在冲突前调整”框架，但本项目若要建立新贡献，仍须给出针对贯穿切割的具体不变量、预算或性能保证。

### F. 相关但更新模型不同的几何着色

Bartłomiej Bosek, Anna Zych-Pawlewicz. *Dynamic Coloring of Unit Interval Graphs with Limited Recourse Budget*. ESA 2022, 25:1–25:14。[正式记录与摘要](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ESA.2022.25)。本轮只用摘要，不将其当成已阅读全文。

摘要给出单位区间插入模型的摊还改色上界和全动态模型的线性下界。与本项目都有几何约束，但单位区间插入/删除不是把一个矩形父面分成两个子面；也不能由路径平方与区间图的联系直接移植更新保证。

## 2. 原创性分层

| 项目内容 | 当前证据下的定位 |
|---|---|
| 最小化旧侧净改色数 | Color-Fixing / recourse 的受限问题实例；不能主张目标全新 |
| 冲突边两端分支与预算搜索 | 已知 FPT 分支思想的实现及扩展 |
| 两子侧的 16 行成本表 | 清晰的条件最优值表示；类似边界状态 DP 的基本工具，不单独证明创新 |
| 全部单次 Kempe 候选中按成本选最小值 | 有限候选集上的确定优化；有项目收益，但尚无新的复杂度结果或查新依据 |
| 插线可能引起大量旧侧改色 | 一般现象早已有动态着色下界 |
| 真实 guillotine 两排错缝、固定外侧、`2m` 精确成本且一次 Kempe 达到 | 本轮未找到完整同构表述；可作为项目特定命题保留，但新颖性未确认 |
| 提前避免困难初态 | 总体思想有先例；特定规则的不变量与保证仍是可研究问题 |

本表不替代唯一着色、2-tree、路径平方、矩形对偶方面的另一组查新。独立推导和实现是本项目的实际工作；它们不自动等于文献首次。

## 3. 可执行的研究建议

1. 对同一切割历史重放旧策略；同时记录最终净成本、累计改色量、Kempe 步数和搜索节点数，防止把一种指标的收益算成另一种。
2. 用 Color-Fixing 精确求解器作终点成本基线；保留路径合法性检查作为独立问题。
3. 比较当前策略、最低单次成本、带有限前瞻的策略；前瞻可借鉴 future adjacency，但必须只使用声明可获得的信息。
4. 若要形成更强的论文贡献，优先证明“在某种切割序列和策略下，哪些昂贵初态可达/不可达”，或给出新的受限复杂度、近似保证。单纯增加实现模块或通过更多测试不是原创性证据。

## 4. 检索溯源与限制

完整查询词、一次 API 失败及来源定位见 `outputs/novelty-dynamic-2026-09-21.json`。共 9 次 web 工具调用和 1 次 arXiv API 尝试；一次 web 调用可含多个检索词或打开请求，因此这不是 HTTP 请求数。没有穷尽分页、系统前向引文追踪或覆盖所有语言。

arXiv 原始 API 的 `all:"dynamic graph coloring"` 查询连接失败（curl 7，解析器为空输入）；后续使用出版社、Dagstuhl、arXiv 网页全文。不能把 API 失败当成无匹配。关键词 `guillotine recoloring` / `rectangular coloring recourse` 没有提供可确认的同题论文；名称不相同的文献仍可能包含等价结果。

本次检索采用 paper-lookup 技能记录访问边界与来源。方法工具来源：[Timothy Kassis, Vinayak Agarwal, Yuhuan He, Darshil Patel, Aubrey M. Brueckner (2026), Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://arxiv.org/abs/2609.00065)。访问时最新为 v2；这里只致谢检索流程，未将其作为图论结论证据。
