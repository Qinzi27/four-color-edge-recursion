# 母线—局部侧名方法：相关工作与新颖性边界

检索日期：2026-09-19。配套 [数学方法草案](MATHEMATICAL_METHOD-2026-09-19.md)。

## 1. 结论先行

**构成方法的若干基本思想已有明确先例，但本轮不能断定整套方法已经被完全重复，也不能认证原创。**

已有先例包括：有向线侧/组合地图、四色转三种非零色差、两树递归文法、全局颜色置换去重、边界预着色延拓和重配置。
目前可比较的候选特色是：**整母线身份＋当前位置分段侧名＋历史初生名＋阶段锚定＋重新构建当前约束＋确定性最小取名**的组合。
是否有新的数学结果，要比较状态信息和合法转换，而不是“母线”“等级”等术语。

冻结程序还不完全实现这个历史模型；尤其初始内部 2 锚与最终框内首侧 2 锚不应混同。
因此在状态/转换规则尚未完整确定时，不宜声称“发现了全新通用四色算法”。

## 2. 最接近的工作：逐项对照

| 已有工作 | 读取深度 | 明确重合 | 不能直接推出的结论 |
| --- | --- | --- | --- |
| Kauffman (2005)，*Reformulating the map color theorem* | 作者全文 §2–3、§7，期刊 pp.146–150、166–172 | 三价图三边着色、formations、树与重结合 | 一条跨很多接点的母线不等于文法单节点；没有证明这里的最低色名选择总成功 |
| Cooper–Rowland–Zeilberger (2012)，*Toward a language theoretic proof of the four color theorem* | 作者全文 §1–3、Props.10–11、§6 | 三符号分叉文法、两棵树共同叶词、置换等价类 | 不是单棵任意分割历史；局部拼接要求对应叶区间及根标记相容 |
| Cori–Dulucq (1986)，*Colourings of planar maps and the equality of two languages* | Crossref 元数据、出版社目录及 CRZ 作者补记；扫描正文未读通 | 地图着色与形式语言方向的更早先例 | 本轮不能据题名断定具体规则逐项等价 |
| Csar–Sengupta–Suksompong (2014)，*On a Subposet of the Tamari Lattice* | 21 页预印本 §7，Theorems 7.6、7.7、7.9；期刊元数据 | 受限树对共同词、保持根接口的局部置换 | 范围限特定 comb-poset 关系，不是所有母线图的构造法 |
| Robertson–Sanders–Seymour–Thomas (1997)，*The Four-Colour Theorem* | 作者全文 §2(2.4)、§3，印刷 pp.5–9；未重审整篇证明 | 保存整个 ring 的可延拓着色信息 | 两个端点不自动包含整个接口；该文 tri-colouring 不能直接当作用户的母线颜色对 |
| Ito 等 (2025)，*Reconfiguration of colorings in triangulations of the sphere* | 最新期刊摘要/书目，2022 原稿导论及结果 pp.1–3 | 精确定义单点变色与 Kempe 换色及其不同可达性 | 范围为可三色的球面三角剖分等特定设置，不保证任意图上的局部改名 |

原始来源和书目如下；表中“明确重合/不能推出”是本项目的对照分析，不是论文原话：

1. Louis H. Kauffman. Discrete Mathematics **302(1–3)**, 145–172 (2005). DOI [10.1016/j.disc.2004.07.031](https://doi.org/10.1016/j.disc.2004.07.031)；[作者全文](https://homepages.math.uic.edu/~kauffman/MapReform.pdf)。arXiv [math/0112266](https://arxiv.org/abs/math/0112266) 是 2001 初稿、2003 修订，不能把预印本日期当期刊年份。
2. Bobbe Cooper, Eric Rowland, Doron Zeilberger. Advances in Applied Mathematics **48(2)**, 414–431 (2012). DOI [10.1016/j.aam.2011.11.002](https://doi.org/10.1016/j.aam.2011.11.002)；[作者全文](https://sites.math.rutgers.edu/~zeilberg/mamarim/mamarimPDF/4ct.pdf)；[arXiv:1006.1324](https://arxiv.org/abs/1006.1324)。
3. R. Cori, S. Dulucq. CAAP ’86, LNCS **214**, 6–16 (1986). DOI [10.1007/BFb0022655](https://doi.org/10.1007/BFb0022655)。[CRZ 作者网页 2014-05-22 补记](https://sites.math.rutgers.edu/~zeilberg/mamarim/mamarimhtml/4ct.html)明确承认这一前驱；[扫描件](https://sites.math.rutgers.edu/~zeilberg/akherim/CoriDulucq86.pdf)有 11 页，但本轮文本/截图未能读通，不冒称全文核对。
4. Sebastian A. Csar, Rik Sengupta, Warut Suksompong. Order **31(3)**, 337–363 (2014). DOI [10.1007/s11083-013-9305-5](https://doi.org/10.1007/s11083-013-9305-5)；[预印本全文](https://arxiv.org/pdf/1108.5690)。online 为 2013-10-03，卷年为 2014。另有 FPSAC 2012 会议版，不混用它的定理编号与期刊版页码。
5. Neil Robertson, Daniel Sanders, Paul Seymour, Robin Thomas. Journal of Combinatorial Theory, Series B **70(1)**, 2–44 (1997). DOI [10.1006/jctb.1997.1750](https://doi.org/10.1006/jctb.1997.1750)；[作者全文](https://thomas.math.gatech.edu/PAP/fc.pdf)。
6. Takehiro Ito, Yuni Iwamasa, Yusuke Kobayashi, Shun-ichi Maezawa, Yuta Nozaki, Yoshio Okamoto, Kenta Ozeki. Journal of Computational Geometry **16(1)**, 253–294 (2025). [期刊原页与 DOI](https://jocg.org/index.php/jocg/article/view/4763)，DOI `10.20382/jocg.v16i1a8`；[早期预印本](https://arxiv.org/abs/2210.17105)。Crossref 本轮返回 Resource not found，但期刊官方元数据明确存在；数据库没返回不代表论文不存在。

## 3. 哪些仅是等价表达，哪些还可能产生新结果

### 3.1 局部色差和文法：已有等价关系

将四个面色编码为 `F₂²`，三侧颜色 `a,b,c` 给出

\[
(a\oplus b)\oplus(b\oplus c)=a\oplus c.
\]

若三侧颜色互异，三个差为三个不同的非零元素，正对应三符号分叉规则。
所以只把色名改写成有序对、括号或树，并没有独立降低四色问题的难度。
桥的两侧相同，色差为 0；不能忽略桥而声称得到处处非零的流。
一般线侧对也不是标准“边着色”：共享顶点的线对无需按普通边着色规则互不相同。

### 3.2 最小数字的两个含义

完成着色后，用一个全局置换取得规范代表，是去重；CRZ 已讨论这种等价类。
构造中在若干候选里不可逆地选最小值，则是贪心决策。
前者不会改变是否有解，后者可能改变剩余问题，因此不能用置换规范化证明贪心安全。

### 3.3 线侧记录与已有数据结构

[CGoGN 官方组合地图文档](https://cgogn.github.io/combinatorial_maps.html)用 darts、轨道和嵌入属性区分顶点、边、面，要求同一轨道属性一致。
因此“由有向线和连续侧恢复面身份”有成熟背景。母线跨若干原子边保存一个位置相关 profile，是可实现的上层组织方式；本轮没有证明这种组织本身是新的数据结构。

更值得争取的结果是：在明确的图类里，用较少的母线接口信息就足以保证下一次选名可延拓，
或证明有限、确定的同步改名规则总会结束并保持合法性。
这里的“较少”须有状态量或复杂度界及已有方法对照，不只是图上记号看起来少。

## 4. 2026 年的新工作：需要更新比较基准

Yuta Inoue, Ken-ichi Kawarabayashi, Atsuyuki Miyashita, Bojan Mohar, Carsten Thomassen, Mikkel Thorup：
*The Four Color Theorem with Linearly Many Reducible Configurations and Near-Linear Time Coloring*，
[arXiv:2603.24880](https://arxiv.org/abs/2603.24880)。
本轮核到 v2 元数据（2026-05-07 修订）；按**预印本**引用，不补造期刊发表记录。

已读取摘要、引言及 [全文 §13.2](https://arxiv.org/html/2603.24880v2#S13.SS2)的递归接口描述。
作者报告 `O(n log n)` 四色算法，使用可约配置、阻碍圈和 Kempe 改色等机制。
其递归保留规定范围内的边界着色情形再拼接，而非这里的两端母线最低名规则。
本轮没有复现作者计算检查，也没有独立审查整篇证明。
不能用本项目已经取得的样本运行结果来主张优于该复杂度，也不能借它证明我们的规则。

作者公开了 [计算检查资料](https://github.com/near-linear-4ct/)。本轮只作为研究定位来源，没有下载或运行其代码。

## 5. 相关但不宜当作直接依据的线索

- Dvořák–Lidický，*Coloring count cones of planar graphs*，[arXiv:1907.04066](https://arxiv.org/abs/1907.04066)，DOI `10.1002/jgt.22767`：本轮重新核对元数据/摘要，讨论近三角剖分外边界着色的延拓计数。它是接口形式化的重要邻近方向；旧全文对照见 [既有综述](RELATED_WORK.md)。
- Dvořák–Moore–Seifrtová–Šámal，[arXiv:2312.13061](https://arxiv.org/abs/2312.13061)：本轮元数据/摘要复核。题名中的 near-Eulerian-triangulations 有特殊假设，不外推其预着色延拓刻画。
- Axenovich–Hutchinson–Lastrina (2011)，*List precoloring extension in planar graphs*，DOI [10.1016/j.disc.2011.03.007](https://doi.org/10.1016/j.disc.2011.03.007)，[原文](https://arxiv.org/pdf/1006.5596)：读导论、Definition 1、Theorems 1–2。候选 list 是既有形式化，但该文的 5-list 条件不能替用户四色规则作保证。
- Balasa (2000)，*Modeling Non-Slicing Floorplans with Binary Trees*，[大学存档](https://cecs.uci.edu/~papers/compendium94-03/papers/2000/iccad00/pdffiles/01a_3.pdf)：仅核到题名/索引摘要，正文编码与截图访问失败，未作为具体定理依据。递归切割布局与任意平面地图不是相同输入类；非 slicing 布局可以有二叉树编码，也不意味着可按贯通切割生成。

本轮检索也命中自行发布的四色证明主张（例如 arXiv `2602.16996`、`2104.14399` 以及 ResearchGate 的 block-line/homology 稿件）。
它们只进入待审线索，不作数学证据，也不因标题相近认定抄重。
这些稿件未在本轮逐条审查，因此“未找到完全重复”尤其不能理解成排除了所有预印本。

## 6. 有界检索策略与局限

使用 arXiv API、Crossref API、作者全文/网页、期刊官方页及 web 定向搜索。
没有规定发表起始年；截至本次访问日。不是系统综述、引文网络穷尽检索或专业查新认证。

主要实际检索式：

- arXiv：`(ti:"four color" OR ti:"map color") AND (all:grammar OR all:recursive OR all:boundary)`，按 submittedDate 降序，`max_results=10`，返回 4 条。此窄查询没有覆盖所有近邻，不能用其命中数估计整个领域。
- Crossref：`query.bibliographic=Toward a language theoretic proof of the four color theorem`，`rows=2`，再按已核 DOI 精确获取相关条目。
- web：`"common parse words" "four color"`；`"Cooper" "Rowland" "Zeilberger" "Conjecture 19"`；`"four color" "parse words" 2020 2021 2022 2023 2024 2025`。
- web：`planar graph four coloring reconfiguration Kempe recoloring`；`four coloring precoloring extension planar graph boundary cycle`；`slicing floorplans guillotine nonslicing floorplans binary tree original paper pdf`。
- web：`"four color" "mother line" coloring`；`"four colour" "side labels" recursive`；`"四色" "母线" 命名`。自定义术语产生不少无关结果，因此已转向结构性关键词，未把无命中当原创依据。
- 对命中的 2026 年近线性论文、Csar 等后续及 JoCG 新期刊版，再做精确题名/作者检索和原始来源复核。

请求参数、返回标识、部分元数据及访问限制保存在 [检索记录](../outputs/method-literature-2026-09-19.json)。
它保存的是元数据和核对结果，不复制论文全文。
arXiv 辅助解析器会丢掉旧式 ID 的 `math/` 前缀，本次按返回的正式链接纠正，并保留这一数据清洗说明。

没有找到可核验的 CRZ Conjecture 19 最新解决来源；这不等于证明它仍未解决。
搜索引擎的“最近抓取”不作为发表日期。

## 7. 对项目下一步的建议

保持当前实现；以 [数学草案](MATHEMATICAL_METHOD-2026-09-19.md)为主线，先明确一个可证明的输入类和转换规则。
最有价值的比较问题不是“别人是否也画线”，而是：

> 当实际边界变复杂时，我们的母线分段记录能否充分保存可延拓信息，并保证所选最小名字不会消灭所有完成方案？

如果对此给出新的定理、状态压缩界或改名界，就可能形成可比较的贡献；
如果只是与已有完整边界状态一一换名，则更适合定位为解释性表示和可复现工具。
本轮没有替用户宣告两者中的任何一个已经成立。

## 8. 检索和评议工作流说明

本轮使用 `paper-lookup` 做元数据/原文路由，`scientific-critical-thinking` 区分事实、解释和未证主张，
并用 `project-first-learning` 从本项目实际锚定错误进入形式化，不额外开设课程或改变算法。
方法评议未套用临床证据等级。

工作流来源：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*.
[当前 arXiv 记录](https://arxiv.org/abs/2609.00065)，DOI `10.48550/arXiv.2609.00065`；本次核到 v2，无期刊记录。
此项仅为工具/流程署名，**不是四色数学依据**。
