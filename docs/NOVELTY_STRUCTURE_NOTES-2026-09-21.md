# 结构压缩与矩形下界的原创性初查

检索日期：2026-09-21。范围是本项目的共享边三角形等色压缩、三类精确成本、路径平方矩形族；这是有边界的先例检索，不是穷尽查新或优先权认证。起始研究想法属于 Qinzi27。检索未修改任何数学实现。

## 1. 可以立即作出的判断

| 本项目内容 | 查到的先例或数学关系 | 当前定位 |
|---|---|---|
| 三色图中，两个共边三角形的对顶点必同色 | 已有 diamond contraction，以及 implicit identity / 3-color bound / frozen pair 术语 | 已知规则的应用，不能称原创压缩原理 |
| 路径平方的三色周期刚性、仅六种字面颜色排列 | 路径平方是 2-tree；2-tree 唯一三色可染（忽略全局色名置换）已有文献 | 已知唯一着色结构的特例 |
| 每个等色类保留三种字面颜色的改色代价 | 最小成本图同态 MinHOM 早已允许顶点与颜色共同决定代价 | 适配本项目目标的精确建模，不是新的优化问题 |
| 两行矩形、指定合法父态、最后一刀、最少改色 2m 且一次 Kempe 达到 | 本轮已读先例中未找到完全相同的几何与成本命题 | 可以保留为本项目明确证明的构造，文献原创性未查明 |
| 可审计实现、冻结数据、几何重放、独立最优性核验 | 属于可重复研究的工程与实验贡献 | 有实际价值，不能单凭测试通过认定算法理论创新 |

核心结论是：目前最稳妥的定位为**已有理论基础上的受限算法实现、精确实例分析与几何下界构造**。不能把“未搜到同一个 2m 公式”当作原创证明；与已知模型等价或容易从已知命题推出，也会削弱理论新颖性。

## 2. 已核对的直接先例

### 2.1 强制等色与 diamond contraction

José Antonio Martín H. (2013), *Solving Hard Computational Problems Efficiently: Asymptotic Parametric Complexity 3-Coloring Algorithm*, PLOS ONE 8(1): e53437.

- DOI：[10.1371/journal.pone.0053437](https://doi.org/10.1371/journal.pone.0053437)。
- [出版社全文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0053437)；[出版社 PDF](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0053437&type=printable)。
- 正文位置：PDF 第 3 页，Definition 1–2 及 Algorithm 1 第 1–3 步；HTML 的 “Description of the algorithm” 部分。
- 短引（本来源只摘以下两句片段，合计不超过 25 个词）：

> “Contract every u,v of a diamond subgraph until no more diamond subgraphs exist”
>
> “return the current contraction sequence (i.e., a legal 3-coloring).”

中译：反复收缩 diamond 子图中的那对顶点，直到不能继续；当收缩到三角形时，返回收缩序列所编码的合法三色着色。

这里的 diamond 是两个共享一条边的三角形，即 K4 缺一条边。其两个非邻接顶点在任意合法三色着色中必同色，正对应本项目的局部等色证书。论文还明确讨论可检查的收缩证书。引用它只用于确认这一规则及证书形式已有先例；本轮没有核验或借用该文有关随机复杂度的更强主张。

相关术语的作者原文：Martín H. (2011), *Minimal non-extensible precolorings and implicit-relations*, [arXiv:1104.0510](https://arxiv.org/abs/1104.0510)，[PDF 第 5 页 Definition 3.3](https://arxiv.org/pdf/1104.0510) 给出 implicit-identity：所有合法着色都不能让指定两点异色。本项目求出的是由局部三角形关系证明的等色子集，不应默认已识别图中全部隐含等色关系。

### 2.2 2-tree 的唯一三色性

David E. Brown and Breeann M. Flesch (2014), *A Characterization of 2-Tree Proper Interval 3-Graphs*, Journal of Discrete Mathematics, Article 143809.

- [出版社全文及 DOI](https://onlinelibrary.wiley.com/doi/10.1155/2014/143809)。
- 正文位置：第 2 节事实列表 (i)，列表位于 Theorem 4 后；一般 k-tree 结果另见同节 Theorem 2。

> “a 2-tree is uniquely 3-colorable”

中译：2-tree 的三色着色在忽略颜色名称置换后是唯一的。该文 Theorem 2 将基础结果归于 Borowiecki–Patil (1986)，*On colouring and the chromatic polynomial of k-trees*, J. Combin. Inform. System Sci. 11, 124–128；本轮未读到 1986 原文，故不对它作直接引文。

**映射到本项目的推导**：从第一个三角形开始，按索引增加顶点，每个新点恰连接前两个相邻点，因此内部路径平方是 2-tree。每次被前两个异色点强制使用第三色，于是 β(i+3)=β(i)。六种颜色排列是已知唯一三色性在固定字面颜色下的展开。

作为另一个已读定位，Naoki Matsumoto (2019), *Triangles in uniquely 3-colorable graphs on surfaces*, [AJC 75(1), 17–31](https://ajc.maths.uq.edu.au/pdf/75/ajc_v75_p017.pdf)，第 18 页定义唯一着色，第 19 页 Theorem 1.2(b) 重述 Chartrand–Geller 的 maximal outerplanar 判别。1969 原始论文 [10.1016/S0021-9800(69)80087-6](https://doi.org/10.1016/S0021-9800(69)80087-6) 本轮只拿到出版社摘要；它是追溯线索，不能写成已读原定理全文。

### 2.3 字面颜色成本与 MinHOM

Gregory Gutin, Pavol Hell, Arash Rafiey, Anders Yeo (2008), *A dichotomy for minimum cost graph homomorphisms*, European Journal of Combinatorics 29(4), 900–911.

- [DOI](https://doi.org/10.1016/j.ejc.2007.11.012)；[作者托管正式版全文](https://cs.indstate.edu/~arash/publication/mincost060919.pdf)。
- 正文位置：第 901 页，Section 1 对 ci(u) 和 MinHOM 的定义；第 902 页说明无自环完全目标图对应 general optimum cost chromatic partition。

> “each possible assignment of a value to a variable has an associated cost.”

中译：变量取每一个可能的值，都可以有对应代价。

**本项目的精确归约（本报告推导）**：目标图取无自环 K4，即合法四色；设 c_j(v)=w_v[j≠α(v)]。固定点用单元素允许色表限制（或用大于全部有限代价之和的禁止色罚值，并检查解是否触罚）。本项目的最小净改色就是该成本模型的特例。固定通邻外侧并删除它后，剩余变量的目标图为 K3。

若已证明同一等色类 A 的成员总同色，则聚合代价 c_j(A)=Σ(v∈A)c_j(v)。这样保持所有可行终点及代价，是目标函数可加性的直接结果。它不能证明某条 Kempe 路径存在或最短；可达性与终点成本仍须分开验证。文献一般输入的复杂度结果也不能自动移植为本项目受限几何类的复杂度结论。

## 3. 名称相近但问题不同的矩形文献

Elad Horev, Matthew J. Katz, Roi Krakovski, Maarten Löffler (2009), *Polychromatic 4-Coloring of Guillotine Subdivisions*, Information Processing Letters 109(13), 690–694，[DOI](https://doi.org/10.1016/j.ipl.2009.03.006)，[作者论文介绍页](https://webspace.science.uu.nl/~loffl001/publications/html/Polychromatic_4-Coloring_of_Guillotine_Subdivisions)。本轮读取作者摘要，未读取该文全文。

它给几何顶点上色，要求每个面边界含全部颜色；本项目给面/侧一致性类上色，要求共边两面异色。两者不能因都有 guillotine 和 four-coloring 就被当成相同结果。该文可以作为几何递归构造的背景，但其结论不直接解决本项目的净改色下界。

## 4. 对后续原创性工作的约束

1. 精确陈述候选贡献应同时包含：几何可实现性、允许的初态、固定外侧、最后一刀、成本定义，以及达到下界的合法动作。任何一个条件变动都要重新比较文献。
2. 目前最有价值的新增问题是“指定既有取名策略能否产生该困难初态”，以及“哪些可维持不变量能避免它”。对任意合法初态的存在性构造，不等于对某一在线策略的对抗下界。
3. 如要称作算法改进，需要与既有 diamond reduction、一般最小成本着色或结构动态规划在同一输入、同一成本口径上比较；不能仅比较我们自己前后版本。
4. 若找不到新的理论保证，也可以如实形成一个有明确用途的可重复研究工具或基准构造。独立推导与学术首创是两个判断。

## 5. 检索记录和访问限制

机器可读记录在 `outputs/novelty-structure-2026-09-21.json`。本分支共 10 次 web 调用（批量查询、打开、定位）及 1 次 Crossref API 尝试，未调用 arXiv API；通过浏览工具读取 arXiv 作者预印本。未穷尽数据库，也未遍历全部引文。

- 主题词覆盖 uniquely 3-colorable、2-tree、implicit identity、diamond contraction、minimum cost homomorphism、guillotine recoloring。
- Crossref 的 curl 请求未连接成功（curl exit 7），没有拿到结构化元数据；随后用作者及出版社页面核对。
- PMC 页面出现验证码，改用 PLOS 出版社全文；ScienceDirect 1969 全文打开失败，保留其摘要级访问标记。
- 只将作者原文、出版社全文或作者机构页面作为论据；百科、聚合站和论坛只用于发现线索，不用于确立结论。
- 采用 paper-lookup 的检索与溯源流程；技能论文说明由本轮总报告统一记录。以上访问日期不等于网页抓取日期或论文发表日期。
