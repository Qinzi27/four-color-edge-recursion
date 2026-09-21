# 2026-09-20：文献连接的自主研究第一轮

用户同意自主推进前一轮列出的研究方向。本轮选择最直接的 Kempe 停滞诊断与保守改色预算，不同时展开所有文献方向。

## 变更范围

- 新增 `fourcolor/kempe_reconfiguration.py`、`tests/test_kempe_reconfiguration.py`：全部完整双色分量上的有预算 BFS；最短步数层内按累计有序边记录写入、累计旧侧改色择优；11项专项测试。
- 新增 `fourcolor/conservative_recoloring.py`、`tests/test_conservative_recoloring.py`：不依赖 Kempe 的冲突分支终点搜索；10项专项测试，含完整小图oracle及1100点零权重链。
- 新增 `scripts/validate_kempe_progress.py`、`tests/test_kempe_progress_validation.py`：几何重建、旧独立分量枚举器、2910个小图目标、91,312份低成本赋值核验与篡改检查；8项专项测试。
- 新增 `docs/KEMPE_PROGRESS-2026-09-20.md`：数学对象、目标与过程成本、单锚点论证、退化度充分条件、实验表及负结果。
- 仅向 `NEXT_STEP.md` 追加本轮结果。保留原单步文件、旧所有策略、原始材料与已有未跟踪图片。

## 固定输入与协议

输入 `outputs/renaming-round-2026-09-18-v2.json` 的 SHA-256 为 `a9aba8d8d9fb2b579fb878dfee00f6e4c261a6c7d17cf85ccc84f98e2b8d29ce`；对照为上一轮 `outputs/kempe-split-2026-09-20-v2.json`。

种子20260908–20261067的全部160个首次受阻快照都运行；无新抽样。每例最多50,000个路径状态、6步；目标预算0至4、每预算200,000节点。两核心都在截断时返回unknown。没有模型调用、网络求解、安装依赖或修改环境。

初版 `outputs/kempe-progress-2026-09-20.json` 保留。代码审查确认最短层成本与单锚点论证，但发现输入辅助模块未列入哈希；另删除了不适当的“preregistered”措辞。正式v2补齐依赖、加入全160例独立成本下界，结果未变。v1之后还补强过核心独立测试，所以当前源文件应以v2哈希清单为准。

## 结果与边界

65个单步停滞中64个最少2步、1个最少3步，全部160例都有合法路线。旧组合流程已能覆盖这160例，因此这不是新覆盖率纪录。本轮新贡献是统一操作模型、路径成本、全体目标成本下界及53个3-退化停滞例的已知定理解释。

净旧侧最小成本在65例中分别为1:41、2:20、3:2、4:2；其中两个成本4的具体实例排除统一成本≤3的设想。三个最短层累计写入优先的路线没有最小净旧侧成本，保留该差别。选中路线没有观察到旧侧改回原色，未把文献例子冒充本地发现。

## 验证

- 初版全项目 `python -m unittest discover -s tests -v`：720项通过，日志 `outputs/kempe-progress-unittest-2026-09-20.txt`。其后添加2项独立成本下界验证测试。
- 正式v2报告 `outputs/kempe-progress-2026-09-20-v2.json`：`all_passed=true`、运行前后13个输入/源码哈希不变。
- 完整最终 `python scripts/validate.py --output outputs/validation-kempe-progress-2026-09-20.json`：722项测试全部通过，无失败、错误或跳过；四面体穷举、series-parallel修复、递归构造、预着色障碍检查全部完成。日志 `outputs/kempe-progress-validation-2026-09-20.txt`。
- 结束时再次确认v2所列13项输入/源码与当前字节一致；正式报告SHA-256为 `c22defc7bf3e170febbd7865cfe0485c9429d3f76d4f83d34b3cb638a4dca3bd`。`git diff --check`通过。

本轮仅本地研究交付，无提交、推送、网页接入或发布。下一步是从成本4的反例与准备性换色路径提取结构条件，而非继续把有限搜索包装成一般算法。
