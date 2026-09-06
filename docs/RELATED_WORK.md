# 相关工作与证据边界 / Related work

检索核对日期：2026-09-06。本页用于确定本模型的已有背景和待比较位置，不是系统综述，也不是原创性保证。检索以作者论文、arXiv 原始记录、作者所属机构和出版社链接为主。未逐一核对所有后续引文，因此仅把某篇文章在发表时提出的问题称为“该文问题”，不声称它截至今天仍未解决。

| 来源 | 与模型的关系 | 当前可支持的主张 |
|---|---|---|
| Louis H. Kauffman, *Reformulating the Map Color Theorem*, arXiv:math/0112266, 2001，修订2003 | 三价图三边着色、向量积、formations 和等价重述 | 左右色差/Tait 着色属于已有研究背景；换符号不能独立构成新颖性 |
| Bobbe Cooper, Eric Rowland, Doron Zeilberger, *Toward a language theoretic proof of the four color theorem*, 2012 | 二叉树、文法、共同解析词 | 二叉括号和树递归已有紧密先例；一般共同解析词命题与四色定理等价 |
| Andrea Bedini, Jesper Lykke Jacobsen, *A tree-decomposed transfer matrix…*, 2010 | 树分解、转移矩阵、精确 Potts 配分函数与色多项式 | 沿递归分解保存着色相关状态不是新的通用思路 |
| Frederic Dorn 等, *Efficient Exact Algorithms on Planar Graphs: Exploiting Sphere Cut Decompositions*, 2010 | 平面分支分解、非交叉分割和精确动态规划 | 接口循环次序和非交叉结构已有算法背景；该文并非本仓库的四色算法 |
| Zdeněk Dvořák, Bernard Lidický, *Coloring count cones of planar graphs*, arXiv:1907.04066 | 边界四色预着色的内部扩张计数 | 精确边界关系可视为“扩张数是否大于0”；边界计数已有专门研究 |
| Zdeněk Dvořák, Benjamin Moore, Michaela Seifrtová, Robert Šámal, *Precoloring extension in planar near-Eulerian-triangulations*, 2023 | 特定近三角剖分的四色预着色扩张 | 该文给出必要拓扑条件及若干完整刻画；这些条件不能直接外推到所有平面图 |
| Georges Gonthier, *A computer-checked proof of the Four Colour Theorem*；*Formal Proof—The Four-Color Theorem*, 2008 | 组合结构、证明检查、计算证书 | 已有完整形式化四色证明；本仓库的 Python 检验不等同于证明助手的核验证明 |
| Jeff Erickson, *Planar Graphs*, 2023 课程讲义 | 半边、旋转系统、两岸、对偶 | 为左右面身份和重边、自环表示提供标准背景；其方向约定与本仓库需显式换算 |

## 可访问的原始来源

- [Kauffman 的作者预印本](https://arxiv.org/abs/math/0112266)。本次核对作者、题名、版本记录和摘要中列出的等价方向；不据此评价其讨论的各个猜想后来的进展。
- [Cooper–Rowland–Zeilberger 的作者预印本](https://arxiv.org/abs/1006.1324)，[期刊 DOI](https://doi.org/10.1016/j.aam.2011.11.002)。摘要明确陈述二叉树共同解析词条件及其与四色定理的等价关系；本仓库没有复现该论文的全部文法理论。
- [Bedini–Jacobsen 的作者预印本](https://arxiv.org/abs/1003.4847)，[期刊 DOI](https://doi.org/10.1088/1751-8113/43/38/385001)。核对树分解与转移矩阵结合的目标；不把摘要报告的特定实验复杂度作为本仓库性能承诺。
- [Dorn 等的期刊 DOI](https://doi.org/10.1007/s00453-009-9296-1)；[Utrecht 大学收录的2005会议版](https://research-portal.uu.nl/en/publications/efficient-exact-algorithms-on-planar-graphs-exploiting-sphere-cut/)，会议版 DOI 为 [10.1007/11561071_11](https://doi.org/10.1007/11561071_11)。期刊与会议版题名略有差异，不能把会议版的年、页码写到期刊记录中。本次期刊 DOI 直连未返回正文，机构会议元数据已读取；研究定位同时核对了期刊论文公开摘要。
- [Dvořák–Lidický 的作者预印本](https://arxiv.org/abs/1907.04066)，[可读全文](https://arxiv.org/html/1907.04066v2)，[期刊 DOI](https://doi.org/10.1002/jgt.22767)。作者有两位，不能漏记 Bernard Lidický。该文研究近三角剖分外边界预着色的扩张计数和相关锥。
- [Dvořák 等2023年的作者预印本](https://arxiv.org/abs/2312.13061)，[可读全文](https://arxiv.org/html/2312.13061v1)。其假设包括内部三角形面和内部偶度顶点；摘要明确的完整刻画覆盖外面长度至多5，以及另一类特定奇度边界三着色情形。
- [Gonthier 的作者技术报告全文](https://www.microsoft.com/en-us/research/wp-content/uploads/2012/10/4colproof.pdf)，[2008年 AMS 文章](https://www.ams.org/notices/200811/tx081101382p.pdf)。本次 AMS 链接返回403，已读取 Microsoft Research 托管的作者技术报告。技术报告与 AMS 文章为不同文献，不能把一个链接当作另一个的全文访问证据。
- [Erickson 的大学课程原始讲义](https://jeffe.web.engr.illinois.edu/teaching/comptop/2023/notes/09-planar-graphs.html)。本次读取定义、旋转系统及对偶部分。

## 本项目当前定位

“有序左右面颜色”“二叉递归历史”“四色对应 Klein 四元群”“边界状态动态规划”和“可核对证书”均有相关成熟背景。本仓库给出这些概念与用户原始分割记号之间的明确连接、桥和对偶的例外处理，以及有限图类上的精确修复基准。目前将其称为一个**可重复研究模型**是合适的，将其称为已查新的新理论或一般四色新证明则缺少依据。

可能产生可发表新增结果的位置包括：证明某个严格定义的图类可以使用更小的充分边界状态；给出新的最小冲突或修复界；或者证明带面身份和谱系的局部重写系统在某类图上终止且合流。每项都要与现有图分解、流优化和文法方法作具体比较，不能只比较命名。

完整可导入引用记录见 [references.bib](../references.bib)。本页没有复制论文图像或大段正文，仓库中的示意图应为独立绘制并注明其教学/模型用途。
