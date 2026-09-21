# 2026-09-20 工作记录：单次 Kempe 插线修复代价实验

## 授权与范围

用户在 arXiv:2603.24880 对照讨论后同意尝试。审计发现此前建议的单次目标生成已经是旧 C 规则，因此先在对话中纠正，再把新增工作固定为通用接口、单次候选族代价择优、SCC证书与独立验证。没有把已存在的成功重新计为新增适用能力。

本轮新增：

- `fourcolor/kempe_split.py`：完整合法H命名、两子侧、固定侧、权重及记录映射输入；六次完整分量尝试；全部合法目标及字典序最优候选；失败显式返回stalled。
- `tests/test_kempe_split.py`：11项核心测试，其中独立子集/割oracle覆盖1156个四点场景；另含2500点非递归案例。
- `scripts/validate_kempe_split.py`、`tests/test_kempe_split_validation.py`：320幅旧/新几何重建、195目标、960尝试、实际线记录及全目标对照；8项防篡改/防覆盖测试。
- `docs/KEMPE_SPLIT_COST-2026-09-20.md`：条件与证明、代价定义、收益与停滞、文献及后续问题。
- `NEXT_STEP.md` 追加此次接续点。

## 冻结实验与结果

输入仍为 `outputs/renaming-round-2026-09-18-v2.json` 的全部160个首次受阻矩形状态，种子20260908–20261067。原文件SHA-256：

```text
a9aba8d8d9fb2b579fb878dfee00f6e4c261a6c7d17cf85ccc84f98e2b8d29ce
```

新旧C均95成功、65停滞。195个合法候选精确等于旧独立完整分量枚举的候选集合。共同成功案例中34例少改旧侧、44例少写新几何有序边记录；本批各项无增加。总成本分别171→105、266→200、1058→765（未分裂旧侧、所有改色侧、有序边记录）。

全部≤10侧的108例重新枚举2910个合法最终目标，与旧档案集合一致。64个单步成功的旧侧成本均达全目标下界；44个单步停滞仍有合法目标，oracle没有参与核心选择。

正式报告 `outputs/kempe-split-2026-09-20-v2.json` 的SHA-256：

```text
944d2609d39ac410dc34ecba7ddfaa5640782a8bfeee92c540a58cecf8a7cd7e
```

首份 `outputs/kempe-split-2026-09-20.json` 保留。独立复核发现验证器此前只检查候选集合和尝试条数，对候选seed、重复依赖及每条尝试的拒绝理由未完全验证。实际报告中的这些字段另行核对全部正确。随后加强验证器与2项回归、生成v2；生产核心、选择规则及统计结果未变。

## 实际验证

运行环境为真实Python 3.12.14，标准库；没有安装依赖。

1. 补强前 `python -X utf8 -m unittest discover -s tests -v`：691项通过，日志 `outputs/kempe-split-unittest-2026-09-20.txt`。
2. 最终 `python -X utf8 -m unittest discover -s tests -p "test_kempe_split*.py" -v`：19项通过。
3. 最终 `python -X utf8 scripts/validate_kempe_split.py --output outputs/kempe-split-2026-09-20-v2.json`：全部实验核验通过。
4. 最终 `python -X utf8 scripts/validate.py --output outputs/validation-kempe-split-2026-09-20.json`：重新运行全部693项测试，0失败、0错误、0跳过；额外四面体穷举、串并联修复、递归历史与预着色障碍检查通过。日志 `outputs/kempe-split-validation-2026-09-20.txt`。
5. 完成后正式报告所列全部输入/源码SHA-256仍匹配；`git diff --check`通过。

综合验证报告SHA-256：

```text
e1f86a88abb2b59ccc1039ae522472777089eb1b466aa59e6b4b02dbd021f1c8
```

旧JS/网页算法未变，本轮没有重新跑Node或浏览器检查。旧输入、冻结成绩及此前未跟踪的 `docs/figures/inside-out-2026-09-20/` 保留。当前新增源码与报告只在本地，未提交或发布。

## 判断边界

- 160例是首次受阻快照，不是完整历史通过率；95/160不能并入v2/v4的7069图结果。
- v2/v4失败时的部分颜色域没有本接口所需完整合法旧命名，明确标注不适用。
- 记录数是新细分图中有序左右名字记录的并集，不能称为原图记录数、dart数或XOR色差翻转边数。
- 候选族内最优不保证全目标最优；64例全目标旧侧最优只是有限观察。
- 没有实现论文D-可约构型库、全局协调算法或q(A)>0的圈层修复。

后续应先解释65个停滞的结构，在明确图类及允许动作下寻求前进条件/代价界。重复完成旧95例不是新的研究收益。
