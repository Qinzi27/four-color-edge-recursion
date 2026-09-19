# 初始化—分级统一版：全库重跑结果

日期：2026-09-19。发起思路：Qinzi27。实现策略：`stage-anchored-level-sides-v3`。

结论：同一冻结规则独立重跑 **7069 张图，7065 完成、4 冲突、0 范围拒绝**。
原 6113 图组全部完成，旧六例和蓝框例均完成；后来加入的 961 图组有 4 个中间步骤退步。
不是全库通过。四例的理论原因另存 [冲突档案](STAGED_LEVEL_CONFLICTS-2026-09-19.md)，供下一轮分析，未据结果临时更改规则。

## 1. 统一了什么

完整运行前规则见 [固定规格](STAGED_LEVEL_RULES-2026-09-19.md)。这次保留当前边界、Hall 条件和二元关系过滤，只改初始内侧锚的确定方式；等级仍只辅助排序。

对当前几何 `G_t`，母线 `M` 的每个位置区间 `I` 保存当前双侧记录

\[
P_t(M,I)=(c(F_L),c(F_R)).
\]

母线身份、侧身份、当前色名、历史出生名、处理等级是不同对象。一个中途 T/X 接点不自动截断整条母线。桥两侧为同一侧，不产生异色条件。

每次加线后，重新从当前几何构建状态，不读取上次的颜色承诺：

1. 外框出生描述仍为 `(1,2)`，但先只固定**当前外侧为 1**。
2. 按预定顺序找首条合格贯通母线：真正两端都接外框，且有当前区间的未定侧与真实外框边共边。
3. 在该母线选中的真实外框邻侧，候选为 `{2,3,4}`，取最小名 2。**不再额外把最终左上小侧固定成 2。**
4. 无合格贯通母线时，使用运行前已声明的框内首侧规范化，不在失败后重试首侧。
5. 后续按已知母线等级优先、同级按数值端点顺序；未知等级为 `None`，进入待处理组，不拒绝图。
6. 线内依据当前紧迫度选择侧，完整传播约束后取 `min(D)`；冲突就保存，不换算法或旧解兜底。

为了精确复现，线内优先级是按字典序取最大：

\[
U(F)=4-|D(F)|,\qquad
N(F)=\#\{Q\sim F:|D(Q)|>1\},
\]
\[
Q(I)=\sum_{F\text{ 为区间 }I\text{ 的未定侧}}(4-|D(F)|),\quad
\operatorname{priority}=(U,N,Q,\text{既有支撑平局项}).
\]

同分按既有区间参数和 dart 顺序。这里的数值位置约定是可复现的实现选择，并非已经证明的几何不变量。支撑项沿用旧版，没有增加找闭环分组算法。

当前直接禁名和进一步推导必须分开：

\[
B(F)=\{c(Q):Q\sim F,\ |D(Q)|=1\},\qquad
D(F)\subseteq\{1,2,3,4\}\setminus B(F).
\]

`D` 中进一步删除的名字有 Hall／关系证书；不是把祖先用过的数字永久禁止。
关系过滤涉及全体侧对，不能称为严格只看两端的局部算法。
本版仍在当前完整图上调度母线剖面，**不是唯一历史的粗到细重演**，也未把首线另一整侧永远锁成 3。

## 2. 完整结果与对照

| 统计口径 | 归档 v2 | 本轮独立重跑 v3 |
| --- | ---: | ---: |
| 去重图完成 | 7068 / 7069 | 7065 / 7069 |
| 原图组完成 | 6112 / 6113 | 6113 / 6113 |
| 后来种子组完成 | 961 / 961 | 957 / 961 |
| 历史的全部前缀完成 | 362 / 363 | 362 / 363 |
| 最终图完成 | 363 / 363 | 363 / 363 |
| 静态引用完成 | 302 / 302 | 302 / 302 |

两图组重叠 5 张，所以总数为 `6113+961−5=7069`。363 条历史共 7678 个前缀引用；加上静态引用共 7980 个引用。图的侧数范围为 2–57，包含外侧。

相对 v2：共同成功 7064 张，修复 1 张，退步 4 张。不能把旧结果与新结果择优拼成一个算法的全通过。
v2 为哈希绑定的归档对照，本轮没有重算 v2，亦没有把其颜色传给新算法。

- 6780 张按贯通母线选择初始保留侧；289 张采用无合格贯通母线模式。
- 7069 次首侧命名全部取 2。296 张含未知等级母线的图没有被拒绝。
- 共 45898 次主动命名，含 7069 次初始化；其中 6718 次取 1。不得直接与旧版不含初始化的主动次数比较。
- 全跑约 480 秒，4 workers、283 个检查点批次；这不是跨版本性能基准。
- 图集已参与既往调优，文件名 `heldout` 不代表本次未见测试集。

## 3. 冲突保留

四例均属于 `heldout-guillotine-20261936` 的第 **16、18、19、20** 步。第 17、21 步重启后恢复，最终第 24 步也成功。因此“最终图全成功”仍不等于“每一步成功”。

四例都在 `L:190,0>190,600` 上先确定侧 2 的名为 2；第二次主动选择把另一侧的候选 `{1,2}` 取为 1，然后产生关系矛盾。
独立诊断证明第 2 次确实是首次不可延伸的决定，而不只是最后才报错：旧合法解整体交换 `2↔3`，能保持此前全部决定，并让第二侧取 2。没有将这个诊断见证喂回生产规则。

最小例留白：[PNG](figures/staged-levels-2026-09-19/least-conflict-blank.png) / [SVG](figures/staged-levels-2026-09-19/least-conflict-blank.svg)。
同图[旧合法对照](figures/staged-levels-2026-09-19/least-conflict-v2-valid-witness.png)不是新规则输出。
原[蓝框例新结果](figures/staged-levels-2026-09-19/blue-anchor-solved.png)的底部侧 10 确实保留为 2。

## 4. 验证与证据边界

全跑期间每张图逐阶段核验初始化、等级、选线、最小取名和完整传播证书。26 个源码／规格哈希起止相同。
共重放 932862 条 Hall 事件、1154269 条关系事件、1989689 项有序色对删除。

另一个汇总审计重新导出全部 7069 个几何，检查 7065 个成功结果的真实共边及侧轨道，核对全部 283 批次、所有分母和状态转移，重放 4 个失败及 7 个预声明诊断的完整证书；对 15 个固定最小哈希样本加 7 个诊断另行求解，共 22 个。**这不是第二轮完整求解。**

最终 489 项 Python 测试通过；通用验证再次通过 489 项及额外小型数学检查。本轮较早完成的完整 Node 文件集 107 项通过，此后 JavaScript 未改。
测试通过验证实现遵守规则，不把冲突结果变成算法成功。

首个 2 的安全性来自保持外侧 1 的全局颜色置换，详见运行前规格。此后每次取最小名字是否保留完整解是另一命题。本轮四例反驳的是**这个冻结实现无条件安全落名**的断言，不是地图不可四色，也不是否定尚可继续形式化的母线思想。

## 5. 复现和文件

Python 3.10+ 用于核心及证书；原项目 Node 几何导出器用于重建输入。图像输出额外使用项目已有 Pillow。下面均从仓库根运行，并使用尚不存在的输出路径：

```sh
python -X utf8 scripts/validate_staged_levels_full.py --output outputs/staged-levels-rerun.json.gz --summary outputs/staged-levels-rerun-summary.json --checkpoints outputs/staged-levels-rerun-parts --workers 4 --batch-size 25
python -X utf8 scripts/audit_staged_levels_full.py --report outputs/staged-levels-rerun.json.gz --summary outputs/staged-levels-rerun-summary.json --output outputs/staged-levels-rerun-audit.json
python -X utf8 scripts/diagnose_staged_levels_failures.py --input outputs/staged-levels-rerun.json.gz --output outputs/staged-levels-rerun-conflicts.json
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/staged-levels-rerun-tests.json
```

关键入口与报告：

- 核心：`fourcolor/staged_levels.py::restart_staged_level_names`。
- [全报告](../outputs/staged-levels-full-2026-09-19.json.gz)、[汇总](../outputs/staged-levels-full-summary-2026-09-19.json)、[独立审计](../outputs/staged-levels-full-audit-2026-09-19.json)。
- [四例理论诊断数据](../outputs/staged-levels-failure-diagnosis-2026-09-19.json)、[最终软件验证](../outputs/validation-staged-levels-final-2026-09-19.json)。
- [图像来源清单](figures/staged-levels-2026-09-19/manifest.json)：保留准确几何、数值色名、PNG/SVG 和来源哈希。

全报告 SHA-256：`87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910`。
审计 SHA-256：`1de095c02f47a91ad69e51513c8f8a1ddde1fdc263e4ead6deb48a41177e2701`。

本轮科研批判性思维流程促使我们预先冻结规则、保留退步并分开定理与有限实验；科研可视化流程保留精确坐标、细带、数字冗余标记及来源。这些工作流程不充当数学证明。
旧实现、用户手稿、旧证据、网站均保留；未提交、未上传 GitHub、未改许可。
