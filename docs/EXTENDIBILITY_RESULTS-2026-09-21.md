# 回到核心：每次落名是否仍可完成全图

发起思路属于 Qinzi27。本轮冻结 `mother-peer-structural-reuse-v1`，推进原线侧
几何重启方法的可延拓检验；没有用精确求解器替它选色，也没有改变既有规则。

**目前结论：下面两个有限输入范围内，实际每一步落名均保留完整合法解；
一般输入上的同一性质尚未证明。** 原先只统计最终完成率，现在可以检查并保存
“第一次错误承诺”的前后证据。另有一个已严格核查的条件性障碍，但尚未证明
当前算法会走到该状态，不能称为本算法反例。

## 1. 本轮完整穷举成绩

计算前范围、完整性依据、去重与资源限制见
[预声明协议](EXTENDIBILITY_PROTOCOL-2026-09-21.md)。两个实际清单都先写入
manifest，绑定 80 个源/协议/测试文件，再运行候选。执行前按参数重新生成
清单核对，执行结束再检查源文件哈希。

| 核查项 | 3×3 矩形贯穿切分，最多 5 刀 | 3×3 内部 12 条单位边的全部子集 |
|---|---:|---:|
| 规范输入线段集合 | 357 | 4,096 |
| 合法历史/代表历史 | 2,145 条全部有序历史 | 4,096 条固定顺序代表历史 |
| 历史前缀引用 | 12,173 | 28,672 |
| 完成配色 | 357 | 4,096 |
| 全部历史前缀完成且逐状态有解 | 2,145 | 4,096 |
| 实际主动落名次数 | 872 | 6,114 |
| SAT→UNSAT 错误承诺 | 0 | 0 |
| 初始化无解 / oracle 未决 | 0 / 0 | 0 / 0 |
| 枚举的初始化后字面赋值 | 204,849 | 973,123 |
| 其中合法完整赋色 | 2,185 | 15,170 |
| 全解保留核查覆盖的图 | 357 | 4,096 |

第二族包括悬线、桥、孤岛和非矩形区域；并不枚举所有线段插入排列。两族
可能具有相同图结构或几何，不能相加成独立样本量或一般成功概率。

每图先运行候选，再检查初始化及累计主动承诺。所有 SAT 状态均存有完整
合法四色见证，并按真实共边和当时锚点复核。全部符合初始化的合法赋色中，
每个传播固定点保留所有符合当时主动承诺的解；这检验的是可靠性，而非传播
能否识别全部不可行候选。颜色 1/2 的初始化对称归约不把其余名字合并。

## 2. 核查器确实能够找出首错

以已经存在的 19 面旧失败作为阳性对照，不混入新穷举成绩：

- 禁用结构查询时，初始化有解，首次提交 `S10=2` 后无解。保存了此前完整
  配色与提交后覆盖全部分支的 UNSAT 树，独立复核器逐分支检查。
- 当前结构版在该图的全部实际承诺之后仍有解。它自身先通过结构反证排除
  错误提议；oracle 是运行结束后的核查，不参与修复。
- 证据：`outputs/extendibility-controls-2026-09-21.json`。

新增 oracle 只使用标准库，不导入生产传播代码。SAT 给完整见证；UNSAT 给
完整字面四色分支树；达到节点上限返回 `unknown`。证书验证不重用 MRV 选点
或生产传播逻辑。测试覆盖小图全枚举、锚点、预算边界、删分支/伪冲突/伪见证。

## 3. 一个明确的条件性障碍，以及可补充的同名信息

取五圈 `t0,t1,t2,t3,t4`；两点 U、V 都邻接五圈全部点，彼此不邻接；再加只
邻接 t0 的叶子 z。这里的点是抽象面约束变量，给出的旋转系统证明约束图平面，
尚未给出母线几何和当前策略的可达历史。

若 U、V 不同名，五圈只剩另外两种名字，奇圈不能二着色，故

\[
\text{所有合法四名赋值都满足 }U=V.
\]

固定 `U=2,z=1` 时，精确穷举有 **20** 个完整解，全部 `V=2`。现有 Hall 与
二元路径传播仍给 V 留下 `{1,2}`；提议 `V=1` 会使完整解从 20 变成 0。
但若去掉已有承诺，`V=z=1` 确有完整合法解，所以即便“无条件必异名”查询完全
准确，它也不能把 `V=z` 判为全局不允许。现有共享三角形查询实际为 inconclusive。

这定位了信息差别：**提议本身是否可能，与提议能否同当前累计承诺兼容，是
两个问题。** 此例可以用“公共邻域含奇圈 ⇒ 两点必同名”的可靠 EQ 证书补上；
不能说所有无条件 EQ+NEQ 也都不足。该证书目前仅作诊断，未插入生产策略。

另一方面，本例的 U/V 邻域对称，当前最小名调度可能始终避开所给预着色状态。
因此本轮明确保留 `current_policy_reachability=not_established`，不把任意
预着色障碍包装成真实运行失败，也不据此宣布原思路错误。C7 对照还核查了
65,536 个字面赋值与 84 个完整解；它是同一障碍族的另一个有限成员。

证据与诊断入口：`outputs/conditional-obstruction-2026-09-21.json`、
`scripts/diagnose_conditional_obstruction.py`。

## 4. 更大格网的独立预声明抽样

在小规模完整穷举之外，另固定 `Random(20262121)`，对 5×5 格的 40 条内部
单位线段按 0.60/0.75/0.90 三个保留概率分别抽取 128 个不同掩码。完整 384
份输入和 81 项来源绑定先保存，再执行候选；总时限 600 秒，未完成项必须为
unknown。它仅核验这 384 张终图，不声称覆盖其全部加线历史。

| 保留概率 | 图数 | 实际主动承诺 | 面数范围 | 学到的结构关系 |
|---|---:|---:|---:|---:|
| 0.60 | 128 | 653 | 3–17 | 0 |
| 0.75 | 128 | 1,226 | 10–22 | 0 |
| 0.90 | 128 | 2,098 | 15–26 | 0 |

384 张全部完成，冲突、范围外和未决均为 0。3,977 次主动承诺对应的全部
4,361 个阶段，都由独立重放检查并用该图实际最终合法配色逐项见证可延拓。
这种存在性见证是精确的，但没有枚举这些较大图的全部合法赋色，不能混同
前两组的规则全解保留核查。成功路径没有调用 oracle，也没有任何搜索救援。

此批 10,881 次结构查询没有产生新学习关系；前两组小穷举也没有学习事件。
因此它们主要增强既有成功流程和逐步核查的覆盖，不能用来宣布结构反证又
修复了新失败。已知两次结构修复仍以先前冻结报告为准。

证据目录为 `outputs/grid-commitment-probe-2026-09-21/`；
`manifest.json` SHA-256 为
`0a46242b1e813b9adeee0456a5559aecfb89bbaa191a0d1cfcf08d7469d7aea0`，
`report.json.gz` 为
`0bcf2db59a6415fb8abcb665c93548997baca279ecd61de75f8628d2a316ef3f`。
入口 `scripts/probe_grid_commitments.py`，分别使用 `--prepare --directory` 和
`--execute --directory` 指向新的输出目录。保留原始探索副本；本目录为字节一致副本。

## 5. 文件、复现与限制

新增核心检验入口 `scripts/audit_commit_extendibility.py`；独立 oracle 为
`scripts/exact_extendibility_oracle.py`；两族生成器为
`scripts/exhaustive_rectangular_histories.py`、`scripts/exhaustive_grid_subsets.py`。
使用新的输出文件名：

```bash
python scripts/audit_commit_extendibility.py prepare --family guillotine --max-cuts 5 --assignment-limit 65536 --manifest outputs/my-guillotine-manifest.json
python scripts/audit_commit_extendibility.py run --manifest outputs/my-guillotine-manifest.json --output outputs/my-guillotine-audit.json.gz
python scripts/audit_commit_extendibility.py prepare --family grid-subsets --assignment-limit 65536 --manifest outputs/my-grid-manifest.json
python scripts/audit_commit_extendibility.py run --manifest outputs/my-grid-manifest.json --output outputs/my-grid-audit.json.gz
python scripts/diagnose_conditional_obstruction.py --output outputs/my-conditional-obstruction.json
```

| 完整结果 | SHA-256 |
|---|---|
| `outputs/extendibility-guillotine-2026-09-21.json.gz` | `941a40bb7de763425708c8c8ee3fcf572839f9fe23e707e9f1eb67417dd797bc` |
| `outputs/extendibility-grid-subsets-2026-09-21.json.gz` | `4dbab1894cb30d80af7d385af5a8c1715bd62ec1ef2ce6ca5122a75a44ca2278` |
| `outputs/extendibility-controls-2026-09-21.json` | `5edd7f3ada8dcb5b68b84c61be92c1e405b5718c19ccbdb59e120a6a5581a5e1` |

共享 Node 几何解析和 Python `PlaneMap` 表示的边界已在协议说明；本轮不声称
整个软件栈完全独立。没有实际新失败，故没有虚构反例缩减。完整穷举仅限声明
的有限对象，不能证明一般完备性、原创性、速度改善或四色定理的新证明。

核心剩余义务仍是：对本算法实际可达的每个 S，证明被选择的 `v=c` 满足
`E_G(S)≠∅ ⇒ E_G(S∪{v=c})≠∅`，或者找到首个违反它的合法几何历史。
本轮把该义务落实成了可执行、可留证、能识别已知首错的检查。

验证：完整 **869 项** Python 单元测试通过；`scripts/validate.py` 综合验证
再次通过同一 869 项及其数学核查，报告为
`outputs/validation-extendibility-2026-09-21.json`。保存后重新读取两份穷举
报告，全部 **11,439 个** oracle 状态证据与各 80 项来源绑定再次通过；11 个
新脚本/测试文件通过 Python 3.10 语法解析（不是 Python 3.10 环境运行声明）。
记录为 `outputs/extendibility-artifact-check-2026-09-21.json`。
本轮没有更改生产算法或网页，也未提交或推送。
