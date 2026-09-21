# 2026-09-21：连续历史、父图刚性与原创性核查

用户授权：继续下一步测试，并核查原创性。沿用上一轮真实错缝矩形族，先固定旧策略和历史，再单独定义连续修复策略；不修改旧冻结成绩或已有网页规则。

## 完成内容

- 新 `fourcolor/triangle_chain_replay.py` 与 `scripts/replay_triangle_chain_web.mjs`：从单矩形真实重放 plain、strip、forest 和未改动网页模块，记录每次合法提交、首次停止及几何状态。
- 新 `scripts/validate_triangle_chain_replay.py`：448 条旧策略历史全部提前停止；160 个实际停点最少成本 0，288 个最少成本 1；全部停点可以单次 Kempe 修复。诊断不回流旧策略。
- 新 `fourcolor/kempe_history_policy.py`：原 forest 成功决定保留，实际停点才执行一次成本择优完整 Kempe 分量交换；无候选即停止。新增 `scripts/validate_kempe_history_continuation.py` 独立核对真实几何、旧身份、继承色、完整候选、实际提交及成本。
- 128 条新策略历史全部完成，共 3,712 刀、1,792 次 Kempe 后备；后备单步成本均与独立最小终点成本一致。旧 forest 的同批 128 条对照全部提前停止；每条旧成功前缀均与新策略一致。
- 最后一步均实际达到最少 `2m` 成本，参数为 `m=1,…,8`。累计历史改色并未证明最优；一般参数上的完成性也未证明。
- 新旧父图刚性证明：内部是以 `p-v1` 为根边的 2-tree，固定外侧后恰六种合法旧配色。因此最后 `2m` 成本对该父图的任意合法旧配色成立；另一份合法旧配色不能预防这最后一刀。任意参数命题有直接证明，独立脚本另核对 8 个参数的全部 48 个旧配色。
- 两条查新分支覆盖 Color-Fixing、动态 recourse、Kempe distance、diamond contraction、MinHOM、2-tree 唯一三色、前瞻修复等。组成方法存在明确先例；特定完整几何命题与实验整合的文献原创性未确立。没有把检索未命中当成首创证明。

## 可复现材料

面向阅读的主报告：

- `docs/TRIANGLE_CHAIN_REPLAY-2026-09-21.md`
- `docs/TRIANGLE_CHAIN_PARENT_RIGIDITY-2026-09-21.md`
- `docs/NOVELTY_ASSESSMENT-2026-09-21.md`
- `docs/NOVELTY_DYNAMIC_NOTES-2026-09-21.md`
- `docs/NOVELTY_STRUCTURE_NOTES-2026-09-21.md`

`outputs/replay-novelty-summary-2026-09-21.json` 从三个正式报告直接抽取摘要，保存报告字节哈希及源码核对数量；不是独立新增实验。完整轨迹保存为可用标准库解压的 gzip JSON，避免重复交付庞大明文。旧策略原始 JSON 同时保留。

| 正式报告 | SHA-256 | 源码/输入核对数 |
|---|---|---:|
| `triangle-chain-replay-2026-09-21.json` | `727e72fe27de386c830fc2b4d5025b2a7d1ce7fe510d7d51efc710815e6e42b6` | 22 |
| 其 `.json.gz` 副本 | `ddccbc32f6c97f63fbb6df88278396d590aa77fcdf53ed80bd02d96c64e2a678` | 相同内容 |
| `kempe-history-continuation-2026-09-21.json.gz` | `2f1c4341cd8887c16bf93362682d2a9f28322f42d52b8f1ed158d9d83e88de1a` | 27 |
| `triangle-chain-parent-rigidity-2026-09-21.json` | `6b129abd75572a627f458ccae441a6d1c9c0b8b07bf3f6742cbcb478f44453ff` | 3 |

输入、源码均使用仓库相对路径，未把本机路径、私人会话或记忆材料写入研究报告。保留节点上限与 `unknown` 语义；本轮正式成本报告全部精确完成。

## 验证

新增 37 项 Python 测试：重放适配 8、旧重放独立验证 9、新连续策略 8、新连续验证 6、父图刚性 6。包含遗漏步骤、错误几何、继承色、旧侧权重、缺边/重复边、实际提交与候选不符、篡改旧成功前缀以及截断计数的反例检查。

- `python -X utf8 -m unittest discover -s tests -v`：786 项全部通过，153.125 秒；日志 `outputs/replay-novelty-unittest-2026-09-21.txt`。
- `python -X utf8 scripts/validate.py --output outputs/validation-replay-novelty-2026-09-21.json`：786 项测试通过，综合数学验证完成；日志 `outputs/replay-novelty-validation-2026-09-21.txt`。该入口按项目要求会再次运行单元测试。
- `npm test`：107 项全部通过；日志 `outputs/replay-novelty-node-2026-09-21.txt`。真实网页策略另由 Node 模块重放 64 条历史；没有声称完成浏览器 UI 验证。
- 对连续核心和几何独立审计另做只读交叉审查，未发现阻塞问题；14 项相关测试再次通过。
- 报告源哈希在正式运行前后及收尾核对一致。查新查询、网页范围及原始 API 连接失败分别保存至 `outputs/novelty-dynamic-2026-09-21.json` 和 `outputs/novelty-structure-2026-09-21.json`。

## 解释与后续

功能层面新增了能真实连续执行的明确修复组合；证据层面把指定困难初态推进为实际轨迹，以及父图任意合法配色的成本定理。理论机制来自已有唯一三色性和 Kempe 技术；未确立原创算法、运行时间优势、一般完备性或新的四色证明。

下一步优先证明该明确策略和历史族对任意 `m` 的可完成性、所需候选及累计改色界，再对照已有修复方法做公平性能实验。单纯扩大成功样本不能替代这个证明；先改变旧配色也不能突破本父图最后一步的下界。

本轮仍为本地研究产物，未接入网页、未提交、未推送或发布，未改变复用许可。
