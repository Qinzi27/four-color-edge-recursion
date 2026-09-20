# 先前操作审计：哪些变化降低了完成数

日期：2026-09-20。研究发起思路来自 Qinzi27。本次响应“检查此前哪个操作可以优化结果”，只审计已有规则、归档与一个同状态分叉；新组合实验另行报告，不改写冻结结果。

**用户指出的退步有数据依据：在同一批7069张图上，v2完成7068张，v3完成7065张，v4完成7060张。最近的联合过滤仍沿用v4的选面规则，没有恢复此前完成率最高的操作。** 前一次仅解释“9个旧失败没有新增”，未充分交代这条版本比较，容易让读者误以为当前起点已经是历史最佳。

## 1. 核对的是原始完整归档

本次直接读取三个压缩报告的 `drawings`，逐项统计 `runs[policy].status`，并比较所有几何键集合。三个集合完全相同，均为7069张不同几何；没有用不同大小的实验集比较完成率。

| 冻结策略 | 完成 | 冲突 | 范围拒绝 | 相对上一版的变化 |
|---|---:|---:|---:|---|
| v2：`mother-level-peer-sides-v2` | **7068** | **1** | 0 | 本表历史最佳完整结果 |
| v3：`stage-anchored-level-sides-v3` | 7065 | 4 | 0 | 修复v2的1例，新增4例失败 |
| v4：`peer-batch-ready-sides-v4` | 7060 | 9 | 0 | 修复v3的4例，新增9例失败 |

归档包含363条历史、7678次历史前缀引用、302次静态引用；引用可以重复指向同一几何。7069是去重图数，既不能与引用数相加，也不能把相邻历史前缀当作独立随机样本。这是已检查语料上的完成数，不能推断一般地图成功率或理论完备性。

旧说明中可定位这些数字：[v2完整结果](LEVEL_SIDES_FULL-2026-09-19.md)第68–80行、[v3完整结果](STAGED_LEVEL_RESULTS-2026-09-19.md)第58–67行、[v4完整结果](PEER_BATCH_RESULTS-2026-09-19.md)第16–25行。这里“冲突”表示固定贪心路径走入死路，不表示地图不可四色。

## 2. 实际改变了什么操作

| 操作 | v2 | v3 | v4 |
|---|---|---|---|
| 外侧规范化 | 外侧取1 | 相同 | 相同 |
| 唯一初始内侧2 | 外框首边的指定内岸 | 首条合格贯通母线上与外框真实共边的侧；无合格母线时使用声明好的框内首侧 | 沿用v3 |
| 后续主动选面 | 母线优先，再按当前候选和邻接等优先级选择 | 沿用v2 | 先限制为最早ready阶段的未定面，再按母线及局部优先级选择 |
| 候选过滤 | 完整最终图上的Hall／二元关系传播 | 相同 | 相同 |
| 最后取值 | `min(D)`，冲突即停止 | 相同 | 相同 |

源码定位，以本次核对的冻结版本为准：

- [v2核心](../fourcolor/level_sides_peer.py)第32–53行定义 `select_peer_occurrence`，第69行固定外1内2，第77行调用该选择器。
- [v3核心](../fourcolor/staged_levels.py)第37–111行定义 `select_initial_retained`，第127、134行实施新初始化；第142行仍调用旧选择器。
- [v4核心](../fourcolor/peer_batches.py)第91–92行计算最小ready阶段并硬筛候选面，第159行调用 `select_ready_occurrence`。第134–137行说明沿用v3初始化以单独考察调度变化。

两种初始化中的“一个真实外框邻面取2”都可以由全局颜色置换解释：外侧固定1后，该邻面不能用1，剩余三个名字可互换，因此任选一个邻面归一为2不丢失全部解。**v3的初始化不是错误的数学约束；不同锚点改变了后续贪心轨迹，才可能改变完成数。** 后续任意取 `min(D)` 不继承这次规范化的安全性。

类似地，v4的“一个面何时成为粗区域中的单元素”几何判据有证明。但“只能先给最早ready阶段的面主动取色”是实现中的调度约定；几何引理不推出它总比旧顺序好。它不是用户“从内侧出发”“等级辅助”的想法必然要求的数学公理。撤销这道硬门槛，可以保留几何层次描述，而不必否定层次研究本身。

## 3. 同一状态下，首次分叉在哪里

本次从v4报告的 `least_conflict.geometry` 实际重跑三个原函数。图为 `guillotine-20260946` 第18步，包含外侧共20个面，完整几何键为：

`83774b23a0d4ca689637eb9555de40af629ace7e0de4eedd9855bb4864c7baba`

v3与v4都先将外侧取1、侧ID为1的面取2。v3/v4首轮规范化之后，`propagation_phases[1]["outcome"]` 的完整字典相等；候选域与二元关系状态没有不同。v2的框首边内岸恰好也是侧1，所以在这个图上，初始化没有造成后续的差异。

| 相同传播状态后的下一主动操作 | v3 | v4 |
|---|---|---|
| 被选面ID | 13 | 4 |
| 当前候选域 | `{3,4}` | `{2,3,4}` |
| 所在整母线 | `L:113,0>113,600`，即 x=113 的竖线 | `L:324,0>324,600`，即 x=324 的竖线 |
| 该面的ready阶段 | 5 | 2 |
| 按最小值规则取色 | 3 | 2 |
| 完整后续结果 | 完成 | 此步之后冲突 |

v4先排除ready为5的侧13，因而不能沿旧顺序继续处理它，转而给ready为2的侧4取2。本例在相同输入、相同初始承诺、相同传播固定点上，明确展示了ready硬门槛改变轨迹的位置。重新运行的v2也完成；其后续主动轨迹与v3去掉初始规范化步骤后相同。

这证明了该例的具体退步来源，不证明简单去掉ready门槛后就能解决所有图：完整归档中v3仍有4个自身失败，v2仍有1个自身失败。不得逐图事后选成功版本，冒充一套已经全通过的固定规则。

## 4. 三版失败并集已在现有49图中

三版失败集合两两不相交，并集有14张图。以下为从原始 `drawings` 状态直接提取的完整清单；步骤是历史前缀，不是算法内部的主动取色次数。

| 失败版本 | 历史 | 步骤 | 面数 | 几何键 |
|---|---|---:|---:|---|
| v2 | guillotine-20261213 | 17 | 19 | `8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132` |
| v3 | heldout-guillotine-20261936 | 16 | 18 | `dc9cebec632a0762379de1441eea298761571ed5faf53f484d3672c4a6ce8739` |
| v3 | heldout-guillotine-20261936 | 18 | 20 | `3a04a25433017abf6f2ee9fcca7691e0e9a8e6f7ccfaa29398b7d2530932f102` |
| v3 | heldout-guillotine-20261936 | 19 | 21 | `c0ac50852324a137e4950cfec3433a4b5f2c286471119927683a05691346410e` |
| v3 | heldout-guillotine-20261936 | 20 | 22 | `24a1e4a943b811f0c67889cea04fbdbfd6ba269e326bc7a952e07d6a98d3fafa` |
| v4 | guillotine-20260946 | 18 | 20 | `83774b23a0d4ca689637eb9555de40af629ace7e0de4eedd9855bb4864c7baba` |
| v4 | guillotine-20260946 | 19 | 21 | `66b1a56305161b76660d5d2567a7f9720ecde941c8df98f922e594da95d898ed` |
| v4 | guillotine-20260946 | 20 | 22 | `4a06575daa04c673667f33ae291ca23e5012b5fb78c51849e6331a8f560c7bf4` |
| v4 | guillotine-20261041 | 21 | 23 | `49d23c2b2264addeb951705f1ba030aea546f06da3a46163feb9e0f81c44f977` |
| v4 | guillotine-20261041 | 22 | 24 | `0201bcb2c3404ffa6e6b71236350806a352287218609f742cf39c78296299f29` |
| v4 | guillotine-20260968 | 24 | 26 | `2edf6c16cb2053dd5143624a5c1b35e2e1c5f769fb9c138921a0d8157055f7ec` |
| v4 | guillotine-20260936 | 21 | 23 | `8a2c8689af2c57209cf86fadaf2de8a7fccd57c2b73d12360d99e329897bcb73` |
| v4 | guillotine-20260936 | 22 | 24 | `d60280254c2e606f8bbb9320e45f77de5cbd417e2c620b28c8508d7af6388be5` |
| v4 | guillotine-20260950 | 19 | 21 | `ed0cc170289dbcffef0a8e41634a1fb165bff0a09873a8abae56da6af8bc17df` |

名称中的 `heldout` 是当初历史名称的一部分；这些图如今已被检查过，不能再称新的未知留出。`guillotine-20260968` 第24步还对应一个静态引用；这里按同一几何只计一次。

当前49图等于v4归档的40个 `diagnostic_keys` 与9个 `failure_keys` 的并集。本次集合比较确认它已包含上述14例，无需再根据新模式成绩挑选输入。每张图的完整几何可从v4报告 `detailed_examples[key]["geometry"]` 取得。

在这49图上提取各版归档结果，v2为48完成/1冲突，v3为45完成/4冲突，v4为40完成/9冲突。这里仅是**同一49图的归档筛选统计**，不是新一轮49图重跑结果；本文件中新执行的原求解器对照限于上一节那一张图。

## 5. 旧九侧引理没有被删除，但也一直没有接入

[九侧隐含异名引理](IMPLICIT_INEQUALITY-2026-09-19.md)利用九个不同面之间十九条真实共边，推出两个可能不直接相邻的面必须异色。它有独立几何证书和证明，不需要穷举整图配色。

旧覆盖报告 `outputs/peer-batches-implicit-inequality-coverage-2026-09-19.json` 的字段明确为：

```text
failure_records_checked = 9
fatal_choices_excluded_by_template = 3
production_attempts_added = 0
applied_to_v4 = false
```

三例是 `guillotine-20260946` 第18、19、20步；它们的原首错候选可被该固定模板排除。**这是3/9的历史候选排除覆盖，不是3张图的新策略完成结果。** 本次没有把这一覆盖倒算成7063张完成。

旧文 [v4完整结果](PEER_BATCH_RESULTS-2026-09-19.md)第186行已提出“先把有证明的隐含关系接入候选过滤，再冻结为另一版本重跑”。前一轮转向了另一种局部联合约束，尚未完成这项集成；因此准确说法是“一个已有可检验的强化操作还没有落实”，而非“已经工作的规则被后来代码删掉”。

前一轮 [联合边界实验](JOINT_BOUNDARY_RESULTS-2026-09-20.md)依然保留v4的初始化与ready选择器，只增加局部传播。原始报告显示两模式均40完成/9冲突，首错候选排除均为0/9。局部二元关系变强，不能作为完整求解效果已经优化的替代证据。

## 6. 内向外精确接口分支解决的是另一项任务

[内向外顺序实验](INSIDE_OUT_EXPERIMENT-2026-09-20.md)第3、19行明确：它保留全部合法的活动边界状态，未接入原线命名贪心算法。第44、48行限定了63张图、最多17个面、1917次运行的范围；其主要比较量是边界宽度、状态数与转移量。

保留完整边界关系的算法可以把当前不能决定的多个可能性一并传给下一步；原v2/v3/v4每次则只承诺一个名字。前者在小图接口实验中的通过、状态压缩或特定结构加速，不能替代后者在7069图上的完成数。由内向外处理的研究价值可以成立，同时当前v4调度仍可能比v2差；这两件事需要分别评估。

本审计支持先恢复强基线和补齐遗漏的已证操作，再以相同输入分开比较“初始化”“ready门槛”“隐含关系”各自影响。具体新组合的成绩由独立实验报告给出，不能从这里的历史数字推出。

## 7. 文件完整性与复现

本次重新计算以下文件的SHA-256，并分别核对v2/v3/v4归档列出的22、26、30个源文件哈希；三个列表均无不匹配。哈希绑定的是现存归档及其相应代码，不是对一般算法正确性的证明。

| 文件 | SHA-256 |
|---|---|
| `outputs/level-sides-peer-full-2026-09-19.json.gz` | `5085627be22653ea9b6ea13de5ff851c452a8c702996ee6eda0672d2d72eca07` |
| `outputs/staged-levels-full-2026-09-19.json.gz` | `87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910` |
| `outputs/peer-batches-full-2026-09-19.json.gz` | `fb004374e06ee0ace87328a8559e108b23e0e9b71663e1a35158738a5e3ad543` |
| `outputs/peer-batches-implicit-inequality-coverage-2026-09-19.json` | `4ce71014ccd6773e22178ec3e713710dd9c6801bd719e9d496fa80739cb2e4a6` |
| `outputs/joint-boundary-pilot-2026-09-20.json.gz` | `c36929db33c886453eff8e8192ec91746ba06422d16437b108bc642fa5ec48a6` |

以下只读Python片段在仓库根目录运行，可复查完整统计、集合包含关系及同状态分叉；不修改归档、不生成覆盖输出。代码中的面编号是面身份，数字色名只出现在域与 `symbol` 字段中。

```python
import gzip
import json
from collections import Counter
from pathlib import Path

from fourcolor.level_sides_peer import restart_level_peer_names
from fourcolor.staged_levels import restart_staged_level_names
from fourcolor.peer_batches import restart_peer_batch_names

# Read the actual frozen reports, not only their compact summaries.
reports = []
for name in ("level-sides-peer", "staged-levels", "peer-batches"):
    path = Path("outputs") / f"{name}-full-2026-09-19.json.gz"
    report = json.loads(gzip.decompress(path.read_bytes()))
    reports.append(report)
    print(report["policy"], Counter(
        row["runs"][report["policy"]]["status"]
        for row in report["drawings"]
    ))

key_sets = [{row["key"] for row in report["drawings"]}
            for report in reports]
assert all(keys == key_sets[0] for keys in key_sets)
failures = [{row["key"] for row in report["drawings"]
             if row["runs"][report["policy"]]["status"] != "solved"}
            for report in reports]
assert [len(keys) for keys in failures] == [1, 4, 9]
assert all(not failures[i] & failures[j]
           for i in range(3) for j in range(i + 1, 3))
selected = set(reports[2]["diagnostic_keys"]) | set(reports[2]["failure_keys"])
assert len(selected) == 49 and set.union(*failures) <= selected

# Restart each original algorithm on the same frozen geometry.
example = reports[2]["least_conflict"]
assert example["key"] == (
    "83774b23a0d4ca689637eb9555de40af629ace7e0de4eedd9855bb4864c7baba"
)
geometry = example["geometry"]
v2 = restart_level_peer_names(geometry)
v3 = restart_staged_level_names(geometry)
v4 = restart_peer_batch_names(geometry)
assert [v2["status"], v3["status"], v4["status"]] == [
    "solved", "solved", "conflict"
]
assert v3["propagation_phases"][1]["outcome"] == (
    v4["propagation_phases"][1]["outcome"]
)
assert (v3["trace"][1]["side"], v3["trace"][1]["symbol"]) == (13, 3)
assert (v4["trace"][1]["side"], v4["trace"][1]["symbol"]) == (4, 2)
for label, outcome in (("v3", v3), ("v4", v4)):
    row = outcome["trace"][1]
    ready = v4["batch_geometry"]["side_ready_stage"][row["side"]]
    print(label, row["mother"], row["side"], row["domain"],
          row["symbol"], ready)
```

本审计新增文档，不更改原求解器、旧报告或网页。新实验和是否发布由后续独立记录说明。
