# 线侧结构、概率推断与神经网络：先例及首轮验证

日期：2026-09-18。原始线侧递归思路由 Qinzi27 提出。本记录区分文献事实、本文建模选择和有限实验，不主张已取得新理论、通用四色算法或神经网络性能突破。

## 1. 检索结论

**存在非常接近的先例。** 有序有向边、局部因子、边界扩张计数、递归分解和神经消息传递分别已有研究。此次定点检索既不能确认“完整组合从未出现”，也不足以评价某个具体新定理的原创性。

| 论文 | 已有内容与本项目对应 | 尚不能由该论文或对应关系推出 |
| --- | --- | --- |
| Kschischang, Frey & Loeliger (2001), *Factor Graphs and the Sum-Product Algorithm*，[原文](https://www.mit.edu/~6.454/www_fall_2002/lizhong/factorgraph.pdf)，DOI 10.1109/18.910572 | 将全局函数分解为局部因子的乘积，用求和消去内部变量；对应带权接口消息。核对 §II 与 §V。 | 含环图上的普通迭代 BP 一般不能视为精确边界汇总；不能把本项目递归历史树当成因子图无环的证明。 |
| Bedini & Jacobsen (2010), *A tree-decomposed transfer matrix for computing exact Potts model partition functions for arbitrary graphs, with applications to planar graph colourings*，[原文](https://arxiv.org/pdf/1003.4847)，arXiv:1003.4847，DOI 10.1088/1751-8113/43/38/385001 | 树分解、转移矩阵、接口状态及融合权重，直接连接图着色与配分函数。核对摘要及分解、融合部分。 | 递归保存边界状态并计算权重本身不是新增通用方法；原文特定性能结果不能移作本项目性能承诺。 |
| Dvořák & Lidický，*Coloring count cones of planar graphs*，2019 预印本、2022 期刊，[正文](https://arxiv.org/html/1907.04066v2)，[期刊](https://doi.org/10.1002/jgt.22767) | 定义边界四色预着色的内部扩张数；正文 §1 式 (1) 给出两个兼容边界计数向量相乘再求和的拼接式。它是“可行性到计数”的直接先例。 | 本文对象受近三角剖分/对偶近三价图等条件约束；不能覆盖任意未定义的线网操作。网页正文显示日期不作为发表年，采用 arXiv 版本记录及期刊元数据。 |
| Lambourne et al. (2021), *BRepNet: A Topological Message Passing System for Solid Models*，[CVPR 正式页](https://openaccess.thecvf.com/content/CVPR2021/html/Lambourne_BRepNet_A_Topological_Message_Passing_System_for_Solid_Models_CVPR_2021_paper.html) | coedge（有向边使用）有 next、previous、mate、parent face、parent edge；拓扑步行定义有序局部神经核。§3.1–3.4 与线优先、左右面及转角次序很接近。 | 目标是 CAD 实体面分割，非四色构造；学习预测不保证精确联合接口概率或组合可扩张性。 |
| Ying et al. (2021), *Do Transformers Really Perform Bad for Graph Representation?*（Graphormer），[NeurIPS 原文](https://proceedings.neurips.cc/paper/2021/file/f1c1592588411002af340cbaedd6fc33-Paper.pdf) | §3.1 将度、最短路距离和路径边特征用于结构编码/注意力偏置。 | 图结构进入 Transformer 已有先例；这些特征不等于平面嵌入的完整旋转次序和分割历史，注意力权重不自动成为合法命名概率。 |
| Kuck et al. (2020), *Belief Propagation Neural Networks*，[NeurIPS 原文](https://proceedings.neurips.cc/paper_files/paper/2020/file/07217414eb3fbe24d4e5b6cafb91ca18-Paper.pdf) | 学习 BP 迭代和配分函数估计；§3 给出特定结构与算子条件下的性质。 | 其树形及二值 log-supermodular 等条件不能自动用于四色硬约束、任意环图或任意 Transformer。 |
| Robeva & Seigal (2019), *Duality of Graphical Models and Tensor Networks*，2017 预印本，[arXiv](https://arxiv.org/abs/1710.01437)，[作者论文](https://seigal.github.io/robeva2019duality.pdf) | 离散无向图模型的局部势对应张量；边缘化对应收缩，提供另一种理解接口求和的语言。 | 对偶是超图结构上的数学对应，不能把它和地图的原图—对偶图混用；本轮未复现其算法。 |

BRepNet 的 CVF PDF 直接访问受限，正文通过[斯坦福托管的正式论文副本](https://graphics.stanford.edu/courses/cs348n-22-winter/PapersReferenced/Lambourne%20et%20al.%20-%202021%20-%20BRepNet%20A%20topological%20message%20passing%20system%20for%20solid%20models.pdf)核对。Robeva–Seigal 主要核对摘要与定理 2.1，不声称本轮逐页审读所有文献。

检索范围：图着色接口计数/配分函数、有向边及 coedge 神经网络、图 Transformer 结构编码、学习 BP。查询词包括 `tree-decomposed transfer matrix`、`Coloring count cones of planar graphs`、`directed-edge message passing`、`half-edge coedge neural network`、`graph structural encoding`、`learned belief propagation`。一手来源为作者论文、arXiv、CVF、NeurIPS。访问日期均为 2026-09-18。不是系统综述，未完成所有后续引用追踪。

尝试的结构化端点为 `https://export.arxiv.org/api/query`：一组 `id_list=1003.4847,1907.04066,1710.01437&max_results=3`，另一组 `id_list=2104.00706,2106.05234,2007.00295&max_results=3`。本环境网络连接失败，未取得 Atom 记录；改用上述一手页面，不能将 API 失败解释为论文不存在。

## 2. 本轮实验要回答什么

限定问题：已知连通平面线网的有向线及接点旋转次序，有些线侧符号缺失、另一些被噪声替换。显式加入同侧等号和分割线异名约束，对符号恢复和概率误差产生什么影响？

变量仍由线侧输入产生：每个 dart 的左侧符号为变量；`audit_line_names` 从线连接派生同侧轨道。真正分割线的两轨道要求异名；桥的两个 dart 属于同一轨道，要求同名。不是把未知符号直接当成已知颜色，也没有修改现有无枚举构造入口。

设完整符号配置为 x、观测为 y，使用未归一化权重：

`W(x; y) = 1[x 满足所选结构约束] × ∏_d likelihood_d(x_d; y_d)`。

概率是 `W / sum(W)`。若总权为零，明确报不可行，不悄悄输出均匀分布。未知观测使用常数 1；观察到符号 y 时，正确符号的似然为 `1-epsilon`，另外三个各为 `epsilon/3`。这是主动指定的合成模型，不是原线名理论自动推导出的噪声规律。

三个消融模型：

1. `independent`：每个 dart 单独推断，忽略结构依赖。
2. `orbit`：合并同侧轨道的观测，保留同侧相等，去掉分割线两侧异名。
3. `joint`：保留两类约束，枚举小规模完整轨道配置，得到精确联合后验的边缘概率与整套 MAP 配置。

这三个是概率模型/推断基线，**没有训练神经网络或 Transformer**。`joint` 使用标准有限枚举，默认最多检查 65,536 个候选轨道配置；它不是新算法，也不改变原方法“不回溯选标”的约束。前三者用不同约束，因此消融只能检验信息的作用，不能归因于线侧记法的独有优势。本轮只研究静态线侧命名，不验证递归构造顺序、接口压缩效率或学习模型的泛化能力。

## 3. 设计及防止误判

- 四个符号；六种固定嵌入：单桥、三角形、带悬枝三角形、四面体、四辐条轮图、五辐条轮图。最多 10 条原图边、6 个同侧轨道，`4^6=4096` 个候选轨道配置。
- 随机种子 `20260918`。每个拓扑从合法完整命名中均匀抽取真值。每个 dart 独立以概率 0.5 缺失；其余经过错误率 0、0.15 或 0.35 的四符号替换通道。
- 每个拓扑/噪声水平默认 12 次，共 216 次。六个拓扑的重复噪声观测不算作 216 个不同图；本轮也没有训练/测试划分或跨图泛化结论。
- 概率推断使用与生成过程一致的已知噪声参数。结果是匹配模型下的演示，未检验噪声参数估计、模型失配、真实数据或相关观测。
- 独立 oracle 用 `PlaneMap` 的面变量与逐边约束直接求加权和，与线侧模块比较边缘概率、log 配分函数和 MAP 权重。它拥有同样的信息；若两表示等价，结果必须一致。
- Brier score 为每个 dart 的四类平方误差之和，再对 dart 平均，越低越好；分别记录全体和被遮蔽的符号。全体指标按 dart 加权，大图权重更大。
- 单变量后验各自取最大值可能破坏联合合法性，即使概率计算完全精确。因此合法率使用整套 MAP 配置；符号准确率使用单变量边缘 argmax，二者分别记录。
- `joint` 的 MAP 合法率由可行集合的定义保证，100% 不代表新理论；数值准确率或 Brier 的改善也不等于胜过已有 BP、BRepNet、Graphormer。
- 同侧聚合将每个 dart 当成独立测量。真实重复录入若共用一次观测，不能沿用该乘积而重复计证据。
- 颜色是无语义名字时需注意置换对称。测试检验概率的全局置换和方向反转；MAP 平局采用固定顺序，平局解本身不能要求颜色置换等变。

另有一个不依赖随机数的边界反例：均匀合法命名下，单桥两侧一定相等、三角形某边两侧一定不同，但每一侧单独看均为四符号均匀分布。若只存单变量边缘并假定独立，两者都错误地给出“相等概率 1/4”。它验证联合依赖不可随意丢弃，不构成新的概率论结果。

## 4. 运行与后续门槛

标准库、Python 3.10+，不安装依赖：

```sh
python -m unittest discover -s tests -v
python scripts/validate_probabilistic_names.py
python scripts/validate.py --output outputs/validation-probability-fresh.json
```

首个实验脚本默认保存带 UTC 时间戳的新报告；显式 `--output` 指向已有文件时拒绝覆盖。常规 `validate.py` 使用新文件名避免覆盖旧验证报告。核心文件为 `fourcolor/probabilistic_names.py`，数学及数值测试为 `tests/test_probabilistic_names.py`。实验报告保留逐例观测、真值、指标、种子、拓扑和来源文件 SHA-256，无私人机器路径。

本轮报告：[216 次概率实验](../outputs/probabilistic-names-2026-09-18.json)、[项目常规验证](../outputs/validation-probability-2026-09-18.json)、[工作日志](WORKLOG-2026-09-18-PROBABILITY.md)。

| 模型 | 遮蔽符号准确率 | 遮蔽符号 Brier，越低越好 | 整套 MAP 合法率 |
| --- | ---: | ---: | ---: |
| 独立 dart | 26.75% | 0.7500 | 13.43% |
| 同侧轨道 | 72.98% | 0.3352 | 66.67% |
| 完整约束 | 82.91% | 0.2255 | 100.00% |

精确线侧推断与等信息的面变量 oracle 在 216 次实例上逐例一致：边缘概率最大绝对差 `8.548717289613705e-15`，log 配分函数最大绝对差 `7.105427357601002e-15`，全部 MAP 权重匹配。完整约束模型的合法率来自定义，不能作为新的普适保证。概率误差变化是在匹配合成模型上的描述性结果，未报告显著性或真实任务效益。

下一轮神经模型的合理门槛：先定义超出精确小图规模的任务与资源预算，再比较普通 BP/消元、有序 coedge 消息网络和结构 Transformer；保留等信息的普通图编码对照。训练/测试按底层图分组，不能让同图的不同编号、颜色置换或构造历史分散到两边；另留更大规模和新拓扑图族测试。若要主张接口压缩，应测压缩后不同外部上下文中的概率误差，而不只测训练图上的补全准确率。

可提出的新问题是“某个明确定义的图族能否用更小的充分联合接口状态，并给出误差或精确性证明”。是否新颖需要进一步针对性检索；此次实验仅建立可复现起点。
