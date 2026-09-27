# 剩余候选延拓扫描：计算前协议（2026-09-24）

固定共同奇环 EQ 生产版本，扫描上一轮已完成运行的实际持久状态。
本轮不修改或重跑生产算法，不向它反馈颜色，也不添加随机样本后筛选结果。
目标是区分候选域中仍有的颜色是否可延拓，以及现有提交前条件传播能否拒绝
不可延拓的颜色。这里的图是以面为顶点、真实共边为边的对偶约束图。

## 输入冻结与状态定义

完整使用 `quaternary-odd-cycle-eq-2026-09-24.json.gz` 的奇环版运行：
329 输入记录，309 准入几何×两标准初始化，加 1 抽象诊断，共 619 运行。
保留旧 10 几何导出错误及 9 独立几何准入错误，不查询这些未准入记录。
三角形版不重复扫描，不混计抽象例为几何反例。全部是已有输入的事后深入核查，
不是新盲测、独立图族或一般成功概率。

持久状态严格取 phase 0 加每次实际事件的 `after_phase`：已经提交的 trial
是持久状态，被拒绝的 trial 不是。不能仅按 `phase.kind == main` 筛选。
同一运行保持实际事件顺序；实际 reject 只删候选，不增加承诺。每个状态保留
原始初始化锚和此前实际 commit，推导单例、逻辑 EQ、拒绝删域不写入 oracle。

对每个候选域大小大于 1 的面，扫描其全部保留颜色；单例不重复逐色查询，
但每个持久状态仍检查当前承诺是否 SAT。最终 solved 状态没有此类候选。
通用扫描器若遇到最终 conflict/incomplete 也保留其未决候选，分别记录
preexisting_unsat/unknown，不冒称新错误承诺；本轮旧运行最终均 solved。

计算前逐项冻结完整状态/候选清单以及原始输入、旧 envelope、审计、全部
329 检查点、来源与上轮报告/复核的哈希。预冻结重验旧轨迹和保存的精确证据，
但不重新做配色或精确搜索。独立只读盘点为 3,630 持久状态、51,036 候选目标，
其中几何 3,624 状态/50,949 目标，抽象 6 状态/87 目标。619 个终态无目标。
正式 manifest 必须重建这些计数，若不一致先解决清单差异再运行。

## 候选分类与精确证据

每个目标保存四种位置分类：下一实际事件所选面的最小色（scheduled_min）、
该面的其他色、其他面的最小色、其他面的其他色。另保存是否实际 commit、
实际 rejected trial 或未选择。其他面的最小色不等于调度下一步会选它。
没有下一实际事件时，记录为其他面类别，不猜测未来动作。

预计位置计数分别为 3,011 / 4,291 / 14,170 / 29,564，实际提交 3,010、
实际拒绝 1、未选择 48,025。计数单位是“持久状态×面×颜色”，同一图和不同
阶段高度相关，不把 51,036 称为独立实例。

每个查询只依据原始 separator NEQ、初始化锚及此前实际承诺，并为目标
增加一个假设 v=c。不使用学习 EQ、完整目标解、当前域或试探后推出的颜色。
每查询最多 200,000 搜索节点；同运行按原始承诺集合缓存，保存完整 SAT
见证、完整 UNSAT 树或 UNKNOWN。缓存不跨原始图或不同运行。

先核查状态本身，再分类目标：

- 基础 SAT、目标 SAT：supported，有完整解见证。
- 基础 SAT、目标 UNSAT：unsupported，候选域尚未排除的全局无支持颜色。
- 基础 UNKNOWN 或目标 UNKNOWN：unknown，不视为无解或通过。
- 基础已 UNSAT：preexisting_unsat，不当作该目标新造成的失败。

目标没有被实际提交，就不是本策略实际错误提交。所有保存的原始查询输入
与精确结果都经独立验证；既有完整解只作证据，不能写回生产状态。

## 对无支持候选的条件传播诊断

对每个 unsupported 目标，在其已冻结的持久 `phase.document` 上仅追加该
候选锚，再运行原条件传播。保留已有学习 EQ 和此前可靠拒绝状态，但不把
outcome 的候选域重写成新的外部输入。该操作是离线的一个反事实分支，
不是生产算法重启，也不是修改真实历史。

独立重放完整传播轨迹：conflict 记 conditional_refuted，表示现有试探能
拒绝它；underdetermined 记 conditional_inconclusive，表示现有试探仍漏过。
若传播输出 solved 却与精确 UNSAT 相冲突，应保存审计错误，不能计为成功。
未被调度到的其他面即使有漏过颜色，也不自动构成原策略的错误决定。

最早证据按每次运行的实际事件序，再按面序/颜色序保存；不声称所得图为包含
极小或全局最小。若确有新的真实错误提交，再在保留原始输入后研究合法缩减；
仅候选无支持时先报告条件传播是否拒绝以及原实际动作。

## 落盘、资源与完成判定

不再增加一次完整着色实验。最多 54,666 个基础/候选查询引用，实际缓存后
查询数由报告记录；单查询节点上限如上，目标数全部预先固定。每个原图独立
检查点，可在同一冻结哈希下继续；异常、资源 UNKNOWN 和未完成不被隐藏。
保存结果复核独立重建状态、实际承诺、全部目标、分类与汇总，并验证所有精确
证据和条件传播轨迹，不重新运行生产器、条件传播或精确求解搜索。

分别报告几何/抽象、单/双锚、实际最低候选/其他候选、conditional_refuted /
conditional_inconclusive，以及当前域无支持与实际错误提交的区别。
本轮不改四进制语义、低色偏好、母线调度或任何冻结生产规则。

```powershell
python -X utf8 scripts/validate_quaternary_candidate_scan.py prepare --manifest outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz
python -X utf8 scripts/validate_quaternary_candidate_scan.py run --manifest outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz --output outputs/quaternary-candidate-scan-2026-09-24.json.gz
python -X utf8 scripts/validate_quaternary_candidate_scan.py check --manifest outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz --report outputs/quaternary-candidate-scan-2026-09-24.json.gz --output outputs/quaternary-candidate-scan-artifact-check-2026-09-24.json
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-quaternary-candidate-scan-2026-09-24.json
```

已存在输出时换唯一新名字，不覆盖旧证据。有限全部通过也不等于一般候选
完备、调度延拓保证或新的四色定理证明。
