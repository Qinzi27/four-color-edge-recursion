# 单次 Kempe 插线修复：承接旧规则的代价择优与独立核验

2026-09-20。用户同意尝试 arXiv:2603.24880 与本项目的连接后，先审计已有程序，再进行独立实验。

**结果：没有增加单次交换的可修复范围；在相同成功案例上减少了部分改名代价。** 本轮保留旧 C 规则的全部候选，按事先规定的代价选择，并为每个目标生成固定目标 SCC 证书。规则机制属于经典 Kempe 交换，项目此前已经实现；本轮不主张新颖性、一般完备性或近线性四色算法。

## 1. 先纠正既有工作的定位

`scripts/rename-diagnostics.mjs` 的 `postSplitRepair` 已经实现插线后一次完整双色分量交换，称为 C 规则；`scripts/validate_renaming.py` 已独立验证。

冻结输入 `outputs/renaming-round-2026-09-18-v2.json` 包含全部 160 个矩形贯穿分割的**首次受阻状态**，种子为 20260908–20261067。旧成绩为 B=62、C=95、交集5、并集152，额外 B→C 修复7，剩余困难例最短需要3次 split-stage 交换。本轮只比较 C，不能与 B 或 B→C 的成功数量相加。

这160个状态不是160条完整构造历史的通过率。v2/v3/v4 的最新失败是完整最终图上的部分域贪心冲突，没有合法完整旧命名及明确待提交子侧边，不能直接传入本接口。报告将这类输入明确标为 `not_applicable_missing_complete_inherited_coloring`，没有把本轮结果加到7069图基线上。

## 2. 输入、穷尽条件与证书

H是侧一致类的异色约束图，c是H上的完整合法四色命名。待提交边xy不属于H，两个不同子侧继承相同颜色a；fixed中的侧必须保持原色。这里的顶点不是原图几何顶点，也不是单个dart。

对每个b≠a，分别求包含x、y的完整(a,b)双色连通分量。若分量包含另一子侧或任意固定侧，则不能采用；否则交换分量内的a、b，得到目标t。最多6次分量检查，所有失败原因均保留。

**单次交换族内的充要条件：** 至少存在一种b，使x与y属于不同双色分量，且其中至少一个分量不包含固定侧。

必要性：若一次交换能使原来同色的x、y异色，它必须只改变其中一个，其颜色对必须包含a，并避开固定侧。因此它必是上述某个候选。充分性：分量内部异色保持；边界外不可能有a或b色的邻点，否则也在同一分量；另一子侧不变，所以新增xy约束成立。

对每个有效分量K，固定目标依赖图恰为H[K]每条边的双向化。K连通，因而整个K恰为一个SCC。只允许每点直接且恰好一次改成t时：

\[
\min\max_B |B|=|K|,\qquad
\min\max_B\sum_{v\in B}w(v)=\sum_{v\in K}w(v).
\]

单点分量同样成立。这是既有固定目标定理在Kempe操作上的直接应用，不是新的图着色定理。分量可能很大，常数次交换不意味着只改常数个旧侧。

## 3. 预先固定的代价与选择

选择按以下元组的字典序最小值执行：

1. 改变的未分裂旧侧数：两个子侧及固定外侧权重0，其他侧权重1。
2. 改变的全部侧数，含被交换的一个子侧。
3. 改变的有序左右名字记录数：新几何中，至少一侧改色的边记录ID并集。
4. 按输入侧顺序排列的分量索引元组、颜色对，作为确定性平局规则。

第3项统计每条边的完整 `(左名,右名)` 记录一次；不同于逐dart写入数、XOR色差改变边数、旧图细分前的原记录数。即使一条边两侧同时换色而XOR色差不变，该有序记录仍发生改变，必须计数。本轮不声称第1项最优会在任意图上同时最小化第3项。

通用API还允许非负整数侧权重及任意多个固定侧。未提供记录映射时，记录成本为None，表示未测量而不是零成本。API只检查约束图，不自行认证平面嵌入。

固定四色时只有6次连通性扫描和至多6个SCC计划；在通常哈希成本下，核心为O(V+E+R)，R是传入的侧—记录关联总量。这不是完整四色求解复杂度；失败立即返回 `stalled`，不调用多步状态搜索或全目标oracle。

## 4. 同输入正式实验

正式报告：[kempe-split-2026-09-20-v2.json](../outputs/kempe-split-2026-09-20-v2.json)。对每个输入，先复用旧独立验证器重建旋转系、旧/新面身份、父子映射与实际共边，再运行新规则。初次报告保留；v2增加960条尝试的独立覆盖/分量/拒绝理由核验，并拒绝错误候选起点及重复依赖，选择规则和结果不变。

| 指标 | 旧C首可用 | 代价择优 |
|---|---:|---:|
| 160个首次受阻状态中的成功数 | 95 | 95 |
| 停滞数 | 65 | 65 |
| 95个共同成功状态的未分裂旧侧改动总和 | 171 | 105 |
| 相同状态的全部改色侧数总和 | 266 | 200 |
| 相同状态的新几何有序边记录写入总和 | 1058 | 765 |

195个合法候选全部经过独立核验。候选数分布为：65个状态没有候选，3个状态有1个，88个有2个，4个有4个。

逐状态对照：34例少改未分裂旧侧，61例持平；总改色侧数同样34例改善、61例持平；有序边记录44例改善、51例持平。该数据内三项均无增加，但这里只对第1项及字典序目标有候选族内最优保证，不能推出一般的多目标单调改进。

例如种子20260908：旧规则改8个未分裂旧侧、总计9个侧、35条有序边记录；择优后分别为1、2、7。这仍是在新细分几何上计数，未换成原图细分前的记录口径。

这些总和只是固定数据中的操作量汇总，不是独立统计样本或墙钟时间加速证据。报告中的单次核心耗时仅供诊断，没有据此作性能优越性结论。

## 5. 独立全目标比较与保留的失败

对全部最终侧数≤10的108例，重新枚举固定外侧为0的全部合法目标，并与之前的完整目标档案逐个集合比较，共2910份合法目标，一致。

- 64例单次交换成功：所选目标的旧侧改动数全部达到全目标最小值。
- 44例单次规则停滞：仍存在合法全图目标。没有让oracle代替生产规则输出解。

“64例达到下界”限于这批有限输入、这个旧侧成本；不证明任意图的一次Kempe目标总是全局最优，也不证明其峰值SCC或记录写入在全目标范围最优。

困难例 `guillotine-20260927` 保持停滞。旧文档已有至少3次split交换、最少改2个未分裂旧侧的证明与独立有限核验；新报告保存6次检查及阻塞分量，不把此次单步失败写成不可四色。

## 6. 与论文的真实关系及下一步

Inoue等的 [arXiv:2603.24880v2](https://arxiv.org/html/2603.24880v2) §2.1、§3.1 用D-可约性保证适当的边界修复，并在整体算法中协调许多可约构型。本文只取其相关操作模型，与本地已有C规则及SCC成本连接；没有复现作者的构型库、放电检验、修复等级或近线性算法。

一个完整合法着色上的Kempe交换，在原图二进制色差层中对应双色面集合边界的偶度翻转，可能包含多个圈。它始终从合法着色出发，不能直接用于当前 `q(A)>0` 的不完整第一层状态。

现在有两个明确的后续问题：

1. 能否对一个由几何定义的插线图类，证明上面的单步条件总成立，并给出分量代价界？
2. 对单步停滞，能否用有限可约构型提供保证前进的恢复证书？旧多步BFS可作小图oracle，不能无声明地充当新规则后备。

下一步实验应预先固定操作集和目标，优先解释保留的65个停滞。重复解出旧95例已不再构成新的适用范围收益。

## 7. 运行与核验

本轮新增 `fourcolor/kempe_split.py`、专项测试和 `scripts/validate_kempe_split.py`，未改旧算法。使用项目可用的Python 3.10+；命令中的python应指向真实解释器，避免不可运行的系统商店占位程序。

```powershell
# 默认生成唯一新报告，已存在路径会拒绝覆盖。
python -X utf8 scripts/validate_kempe_split.py

# 单独运行新核心和证书核验测试。
python -X utf8 -m unittest discover -s tests -p "test_kempe_split*.py" -v

# 完整项目检查；综合报告使用新文件名。
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-kempe-split-rerun.json
```

报告保存所有输入/相关源码SHA-256，并确认运行前后一致。核心测试通过独立的子集/割连通性枚举检查1156个四点场景；报告验证另检查实际边、完整分量、双向依赖、字面左右名字改变、目标集合与最小旧侧成本，并设置篡改证书和拒绝覆盖回归测试。最终19项专项测试、693项全项目测试及综合数学检查全部通过；完整记录见 [本轮worklog](WORKLOG-2026-09-20-KEMPE-SPLIT.md)。

## English summary

The single post-split Kempe-component repair was already implemented as rule C. This experiment adds a reusable cost-ranked API and fixed-target SCC certificates without extending the move family. On 160 frozen first-blocked rectangular splits, both versions repair 95 states. Among those successes, 34 require fewer changed unsplit old sides and 44 require fewer ordered edge-name record writes under the declared lexicographic selector. On all 108 instances with at most ten final side classes, an independent enumeration confirms 2910 legal targets; all 64 successful single-swap selections attain minimum old-side change count, while 44 cases remain stalled despite feasible targets. These are bounded diagnostics, not completed-history success rates, novelty claims, or an implementation of the near-linear four-coloring algorithm.
