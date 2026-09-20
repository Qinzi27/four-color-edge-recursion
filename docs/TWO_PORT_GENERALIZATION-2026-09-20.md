# 从闭环顺序到接口关系：双接口推广与原图的三接口障碍

2026-09-20，接续 Qinzi27 的“那我们研究了什么，你接着推广吧”。

**当前研究问题是：局部闭环系统完成后，至少保留哪些外部接口信息，才能安全地继续构造或拼接？** 原来的线侧表示给出问题与几何对象；内外起点实验研究计算顺序；这一支研究进一步明确何时可以忘掉内部、何时必须保留联合约束。程序用于检查这些关系及其计算成本。

本轮完成双接口关系、消元、显式块拼接与至多三接口的精确签名。另从用户原图推导出一族闭式可延拓条件，并用原图证明两两信息不足的边界。核心框架属于已有变量消元和约束求解；不主张新四色证明、通用快速着色算法或新颖性已获确认。

## 1. 接口不是颜色标签，而是可延拓关系

设一个局部约束图为 H，按顺序声明接口 S。颜色数 q 固定为1至4，颜色名无固定含义。定义

\[
\Sigma_q(H;S)=\{\text{接口颜色的相等模式}:\text{该模式可延拓为 H 的合法着色}\}.
\]

颜色置换不改变是否合法，因此只需记录哪些接口相等，不需区分红、蓝等名字。接口顶点在地图应用中是**面变量**，不是原图的流端口。完整未来邻接必须已知；本轮不支持列表着色、任意固定色锚、计数或最小改色代价。

| 接口数 | 必须区分的颜色模式 | 本轮实现 |
|---:|---|---|
| 0 | 空模式可行或不可行 | 局部系统的存在性 |
| 1 | 一个类 | 可行时可以整体换名对齐 |
| 2 | `00`、`01` | 分别表示同色、异色，两个可行性位 |
| 3 | `000`、`001`、`010`、`011`、`012` | 至多五个可行性位，不能一般改成三个二元关系 |

当 q 小于模式所需色类数时，该模式直接不在候选中。一个签名只回答存在性，不记录该模式有多少种内部解。

这也回应最初的“圈块 rank”：`|Σ|` 可以衡量允许模式的数量，却不能单独决定能否拼接。只同色和只异色的签名都只有一个模式，交集却为空。若要比较约束强弱，在相同接口和调色板下可以看集合包含关系 `Σ₁⊆Σ₂`；它通常是偏序，不能用一个统一高低等级取代具体接口关系。

### 双接口的精确拼接命题

若若干块只共享相同的两个有序接口 a,b，内部彼此不交，也没有遗漏跨块约束，则

\[
\Sigma_q(H_1\cup H_2; a,b)=\Sigma_q(H_1;a,b)\cap\Sigma_q(H_2;a,b).
\]

必要性来自全局解限制到各块。充分性来自同一模式下可将各块完整着色作全局颜色置换，使两个接口同时对齐；内部互不干扰。程序先计算各块签名，每个可行模式存一个见证，拼接阶段取交集并合并见证，不再执行着色搜索。

一个必要负例：二色下，边 a-b 只允许异色；二边路径 a-x-b 只允许同色。两个块各自有解，签名交集却为空；合成的三角形确实无二色解。仅保存“这个圈已经填好了”不能表达这个冲突。

另一个非二色例子：K4去掉接口边 a-b 后，三色时 a,b 必须同色；四色时同色或异色都允许。这已经由签名程序和独立穷举核对。接口关系取决于允许颜色数。

## 2. 可执行的消元规则与安全恢复

定义 EQ、DIFF、ALL、EMPTY 四种二元关系，分别是只同色、只异色、两者皆可、无可行配对。q=1时 ALL 等于 EQ。

对当前约束图中只连接 a,b 的内部变量 x，删除 x 并留下

\[
R'_{ab}=R_{ab}\cap\{(\alpha,\beta):\exists\gamma,
 R_{ax}(\alpha,\gamma)\land R_{xb}(\gamma,\beta)\}.
\]

这里的求交不可省略，否则会丢掉 a,b 原有的不等关系。ALL 可以不显式保存，EMPTY 立即构成不可行证书。度0、1也类似处理。每次记录被删除变量的邻居与当时的关系；剩余核心求解完成后，按逆序恢复变量，选满足这份关系的最小颜色即可。

**这个阶段最小取色安全，是因为此前的存在量词消元保留了完整可延拓关系。** 它并不证明旧线侧命名算法在尚未获得充分关系时也能不可逆地取最小色。

每一步的正确性可以直接双向证明：旧解删去 x 后满足新关系；满足新关系的赋值按其存在见证补上 x，就恢复旧解。重复应用给出整体等价性。

实现只自动删除**当前非全关系图中度≤2的单变量**，并不自动识别任意复杂双接口块，也没有实现 SPQR 分解。剩余 EQ 类先收缩、检查类内 DIFF 冲突，然后由已冻结的 orbit 精确程序求解残核。这是预先声明的固定阶段，不是失败时隐蔽切换算法。

对树宽≤2的图（partial 2-tree），若没有提前发现矛盾，规则可以消完：抑制度2顶点、连接其邻居是 minor 操作，删除全关系边进一步简化；树宽≤2的非空剩余图始终有度≤2顶点。代码使用按输入顺序排序的堆，因此不将这一实现称为无开销线性算法。

### 已有方法边界

\[
\mathrm{DIFF}\circ\mathrm{DIFF}=\begin{cases}
\mathrm{EQ},&q=2,\\
\mathrm{ALL},&q\ge3.
\end{cases}
\]

因此对初始只有不等边的普通三／四色图，这版消元会退化为已知的低度剥离；二色时才产生非平凡的同色传递。四色还可以采用更强的度≤3安全删除，二色也有经典二分图算法；本轮没有把这些已有事实当成自己的新发现。

## 3. 用户原图给出的三接口障碍

三条蓝线齐全时，完整面邻接图是 `K₂ ∨ 3K₁`。设 U、D 是被分开的上、下面，它们相邻；O、I₁、I₂ 是外面和两个岛，它们分别邻接 U、D，彼此没有不等边。

保留 O、I₁、I₂ 为接口，将 U、D 视为内部。假如三个接口已经使用 d 种颜色，U、D 都不能用这 d 种色，而且二者还必须不同。因此

\[
\text{内部可补全}\iff q-d\ge2\iff d\le q-2.
\]

在四色下得到精确表：

| O、I₁、I₂ 的相等模式 | 是否能补全 U、D |
|---|---|
| `000` | 可以 |
| `001` | 可以 |
| `010` | 可以 |
| `011` | 可以 |
| `012` | 不可以：只剩一种颜色，U、D却相邻 |

但任意一对接口的投影都允许同色和异色；每对的全部16种具名赋色都可出现在某个完整解中。**三对 ALL 相交仍会接受012，真正的三元关系却禁止它。** 这是“单侧域或两两关系可能不足以表达整个闭环”的明确证据，不是程序偶然失败。

三色时只有000模式可行；二色时所有模式均不可行。它也解释原图最低需要三色。审计直接读取旧 `circle-rank-mask-7` 图，核对原编号接口 `[0,3,4]`、内部 `[1,2]`，再映射到新示例的接口 `[0,1,2]`、内部 `[3,4]`，没有另造不同的邻接图充当原图。

### 从两个岛推广到一族图

对任意 k≥1，考虑平面图 `K₂ ∨ kK₁`：两个相邻内部点 U、D，共同邻接 k 个独立接口。它可画为 k 条内部互不相交的二边 U-D 路径，再加直接边 UD，属于二端串并联图。

同一证明给出完整条件 `接口使用颜色数≤q−2`。四色下，允许至多两个色类，故

\[
\#\text{接口轨道}=S(k,1)+S(k,2)=2^{k-1},
\quad
\#\text{具名接口赋色}=4+6(2^k-2)=6\cdot2^k-8.
\]

这里 S(k,r) 为第二类 Stirling 数。k=3时是4种模式、40个具名赋色。**一个简短的“至多两种颜色”条件可以表示随 k 指数增长的模式集合。** 这是今后研究紧凑接口描述的具体切入点；不能据此断言任意局部图都能这样压缩。

对每个 k≥1，整个图的色数仍为3：它含三角形，而将全部接口涂同色、U和D各用一种另外的颜色即得三着色。接口状态数量增长与最少颜色数增长是不同问题。

这类“不同取值数上界”已有 AtMostNValue 约束研究。本轮新增的是从用户图追踪到该关系的明确映射、闭式推导和可重复检验；不是首创这一约束类型。

## 4. 三接口程序如何实现

`interface_signature` 接受至多三个有序接口。逐一检查至多五种相等模式：同类接口收缩，不同类之间补不等约束，调用明确的消元＋残核求解程序。可行时展开原变量并整体换名，保存一个符合指定模式的完整见证。

这些补边属于签名查询的辅助约束图，可能非平面，并不表示向原地图添加了几何边。程序没有把辅助图的点解释为新面。小接口只保证查询数量少，不保证每个查询本身容易；一般残核仍可能昂贵。

## 5. 性能实验：更强的基线改变了结论

预先固定83个不同图标识、186组图×颜色条件：旧63图各测试四色与此前独立求得的最少色；另加8个圈（3至128顶点）、6个梯图（4至64顶点）、6个轮图（4至17顶点），各测2、3、4色，包含10个不可行条件。新图只标为平面约束图，顶点0只是固定根，不伪称无界外面。

比较三个版本：旧 orbit 精确前沿；新增 reduced 消元＋残核；独立 DSATUR 选点＋精确回溯参考。DSATUR按饱和度、静态度、ID确定顺序，不采用输入BFS顺序；程序返回一个解及搜索计数。所有版本计入BFS和各自公共API开销，三轮轮换执行顺序，单独测量 Python traced memory。

正式报告：[two-port-benchmark-2026-09-20.json](../outputs/two-port-benchmark-2026-09-20.json)，SHA-256 `7603583d1e5078c2d1eb180499bc70b3c6ae5e3d4bf9c437a6f5c912cd76d9bd`。

| 范围 | reduced 比 orbit 快／慢 | reduced 比 DSATUR参考快／慢 |
|---|---:|---:|
| 旧63图，四色 | 47 / 16 | 0 / 63 |
| 旧63图，最少色 | 44 / 19 | 1 / 62 |
| 新增20图，各三种颜色 | 42 / 18 | 14 / 46 |
| 全部186条件 | 133 / 53 | 15 / 171 |

每个条件三次时间的中位数（ms）：

| 例子 | orbit | reduced | DSATUR参考 |
|---|---:|---:|---:|
| 原图三蓝线，q=3 | 0.0451 | 0.0360 | 0.0183 |
| 128顶点圈，q=4 | 3.7547 | 0.4298 | 1.8734 |
| 64顶点梯图，q=4 | 1.3819 | 0.2890 | 0.5548 |
| 17顶点轮图，q=4 | 0.2118 | 0.2654 | 0.0766 |

圈和梯图可消完；轮图最小度为3，当前规则无可删变量，预处理增加开销。原图虽可完全消完，但仍进行3次关系合成、3次求交、2次单端支持检查、8次恢复尝试；残核DP状态为0不代表没有计算或内存。

全部558次可行性/见证检查一致，保存1,674次原始计时及558次独立内存测量，源与输入前后哈希一致。旧orbit保留完整前缀诊断，新reduced保存消元记录和残核诊断，DSATUR没有生成同等详细轨迹；这属于公共程序接口比较，不是剥除一切诊断后的内核比较。没有固定CPU、硬件隔离或显著性检验，三轮小规模计时不建立总体或渐近优势。

**相对本项目旧DP有部分改善，但整体仍慢于本轮DSATUR参考；不能只选圈、梯图或旧程序作对照而宣布通用先进性。** 更快地求一个完整解，与保留全部接口可延拓关系，也需要分开衡量。

## 6. 验证与可运行入口

新增26项测试，完整627项单元测试通过。新消元核对984条轨迹，独立DSATUR基线核对304个图×调色板；接口测试进一步用完整赋色核对4,140个接口调用。

正式审计为 [interface-signatures-2026-09-20.json](../outputs/interface-signatures-2026-09-20.json)，SHA-256 `405551cf27a5626e4f796527b996efc3aa22789992863ecf3eef5c00105ac90d`，全部通过：

- 全部 n≤4 的76张简单图、1至4色、全部0至3个接口子集：4,140次接口调用、8,274次模式查询、4,209个完整见证；接口顺序和处理顺序均反转，以核对身份映射。
- `K₂ ∨ kK₁`，k=1..6、q=1..4：24个条件、97,698个完整赋色，逐项核对闭式判据与计数。
- 种子 `20260920` 的80组显式双接口块，四种颜色数：320次拼接、205,152个完整赋色，核对签名交集与恢复见证。
- 原图映射直接对照旧输入；11个源码与1份输入报告的起止哈希一致；拒绝覆盖也已实测。

新CLI已运行两个例子：原图返回四个允许模式，冲突两块返回不可行。源代码均新增，上一轮实现、报告和哈希保持不变。

项目通用验证 `scripts/validate.py` 也已另行通过627项测试及既有数学核验，报告为 [validation-two-port-2026-09-20.json](../outputs/validation-two-port-2026-09-20.json)。结束时复核本轮及上一轮七份实验/示例报告的来源，全部源码哈希匹配。网页未改变，本轮未重复Node/浏览器检查，也未上传GitHub。

```powershell
# 计算你原图的完整三接口签名，输出四个允许模式及012失败
python -X utf8 scripts/solve_two_port.py --mode signature --input examples/three-blue-lines-interface.json --output outputs/three-port-example-rerun.json

# 两块各自可二色，但接口关系冲突；输出不可行不是程序报错
python -X utf8 scripts/solve_two_port.py --mode glue --input examples/two-port-incompatible-pieces.json --output outputs/two-port-glue-rerun.json

python -X utf8 scripts/validate_interface_signatures.py --output outputs/interface-signatures-rerun.json
python -X utf8 scripts/benchmark_two_port.py --output outputs/two-port-benchmark-rerun.json
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-two-port-rerun.json
```

文件已存在时拒绝覆盖。`--mode reduce` 接受 n、edges、可选 order/palette_size 的普通图JSON，执行消元＋残核求解；signature还需terminals，glue需pieces。不接受未实现的附加约束。

## 7. 文献定位与真正待解决的问题

Rina Dechter，*Bucket Elimination: A Unifying Framework for Reasoning*，Artificial Intelligence 113 (1999), 41–85，[作者全文](https://ics.uci.edu/~csp/r48b.pdf)，§2.1、PDF第4–7页。文中直接用二色图说明消元后推出同色／异色约束，再逆序恢复解。本轮的合成、投影及安全恢复属于这个已有框架。

Christian Bessiere 等，*Filtering Algorithms for the NValue Constraint*，[作者全文](https://homepages.laas.fr/ehebrard/papers/constraints2006.pdf)，§1与§3定义不同取值数及 AtMostNValue，并讨论传播难度。因此 `d≤2` 也有明确的已知约束类型。上述两份是本轮定向核对，访问2026-09-20；不声称已穷尽所有类似研究。

接下来值得研究的是：能否从用户的几何线侧构造中**直接识别并生成这种紧凑的联合约束**，使它比逐个接口模式搜索更便宜；以及它如何与旧取名规则中的锚、单侧域、两两关系共同保持正确性。本轮尚未把它接入旧v4，也未检验它是否修复旧9个冲突。

一个可检验的下一步是识别两个相邻内部面共同邻接的边界组，输出带来源证明的“边界至多q−2种色”约束，再检验它能排除哪些原有错误决定。这比再改一次内外顺序更直接对应当前发现，但应独立冻结规则、保留所有新增退步，并与已有 Hall / NValue 传播比较。

## English summary

The research question is the sufficient information that a completed local coloring subsystem must expose to its exterior. We implement exact two-terminal equality/difference signatures, their compatible gluing, degree-at-most-two variable elimination, and exact signatures on up to three ordered terminals. The original three-blue-line map yields a concrete ternary obstruction: its three external faces may use at most two colors under a four-color palette, although every pairwise projection is universal. The planar family K2 joined with k independent terminals has the exact extension condition d<=q-2. These are applications and direct consequences of established constraint-elimination and NValue principles. Benchmarks retain both improvements over the previous frontier DP and regressions against an independently implemented DSATUR-based exact reference.
