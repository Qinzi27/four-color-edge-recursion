# 全未决面候选试排：冻结协议

本协议在正式生产与 oracle 查询之前保存。发起思路属于 Qinzi27；本轮是
四进制候选表示下的可靠删色增强，不宣称新四色证明、原创基本定理或一般完备。

冻结前开发校准除微型单元夹具外，还用既有
`examples/quaternary-real-regressions-2026-09-21.json` 的 cases[0] 做过一次
probe_limit=24 的生产检查：第 24 次 S10=2 被拒绝后预算停止。它是已知开发样本，
没有 oracle 查询，不属于新输入验证，也不计入正式 8192 上限实验成绩。

## 数学动机与版本

旧奇环 EQ 版只在当前母线选定的面上试最小候选。上轮离线扫描发现真实可达
状态中的 S3=2/3/4 可由条件传播分别反证，但 S3 尚未被选中；这可能阻止提前
推出 S3=1，再沿真实共边排除 S4/S5=1。本轮验证这一明确机制。

新增 `quaternary-low-color-all-candidate-v1`：先保留原始共邻奇环的有证书 EQ，
再在每个持久状态按输入面顺序、候选色升序逐个临时锚定并传播。若实际矛盾，
删除该候选，保留其余承诺，重启全扫描。若完整扫描无删色，则仍按原母线
调度选择当前最低色，复用这次扫描中对应的 trial。仅临时试探，不撤回已提交色。

可靠性理由：若传播在约束 C 与临时 v=c 下推出矛盾，则 C 的任何合法解均不
含 v=c，因而删色保留 C 的所有解。反复删色、重启仍保持此性质；有限候选数
限制删色次数。这不是“存活候选必可延拓”的证明，也不保证更改顺序后总完成。
`inconclusive` 始终只是未能反证。S10=1 的远程逻辑 NEQ 缺口不预设已修复。

## 输入与资源预声明

- 保留上轮奇环清单的全部 329 记录，包括 19 个既有几何排除和 1 个抽象诊断。
- 新种子 20262601、20262602，矩形贯穿切分与完整弦各 5 刀，全部前缀。
- 双环多边形 n=5/6/7，旋转 17 度，全部逐笔前缀；坐标规则见新输入脚本。
- 新声明共 7 历史、81 前缀引用、75 个去重绘图。全清单与旧库按源线集合 key
  去重后统计；相同家族、相同前缀不能当成独立样本或独立家族。
- 几何最多 40 面，旧引擎仍为 80 线段；每图单有界面锚和旧外框双锚两模式。
  所有历史前缀各自标准初始化，不继承上一图的颜色。
- 两策略都给 128 次提交、8192 次 trial 传播上限；旧版先前是 512，本轮仅提高
  上限以公平配对。旧回归结果在只规范化 probe_limit 后必须逐字段相同。
- 每次原始精确查询最多 200000 节点；字面赋值笛卡尔积不超过 262144 才全枚举。
  超限枚举明确 not_run；精确查询耗尽是 unknown；生产预算耗尽是 incomplete。

## 独立核验与报告口径

两生产端均完成后才启动离线 oracle；oracle 仅依据原始 separator NEQ、初始
锚点和实际提交，查询某个临时候选时再加该单项。EQ、推导单例、删色 states
不得成为 oracle 前提。桥/点触不变成 NEQ；逻辑 EQ 不合并物理面身份。

每个 trial/删色/提交都保存完整输入、传播轨迹及引用；检查器独立重建确定性
扫描、重启、缓存复用、母线选侧和资源停止条件。共享原几何解析、调度元信息
和已有字面传播轨迹检查器，不能称整条软件栈完全独立。独立精确求解器不使用
被测传播；保存证据复验不重新运行求解器、生产程序或传播。

分别报告规则删减保解、逐步提交可延拓、完整完成率及试探/轨迹/时间成本。
未选择候选的 UNSAT 与实际错误提交分开；保持修复/退步/持续失败/未知分类。
记录已知 S3 链条及 S10 残余，而不将“候选减少”自动解释成提速或新成功。
运行时间来自固定先旧后新顺序的单轮配对，仅作成本观测。

冻结全部旧 177 源文件，加本轮 9 文件；正式清单保存源码/输入哈希和全部绘图。
输出使用唯一新文件名与逐图检查点；旧文档、脚本、网页、冻结报告保留。

## 复现命令

使用 Python 3.10+（Windows 推荐 `python -X utf8`）：

```text
python -X utf8 scripts/validate_quaternary_all_candidate.py prepare --manifest outputs/quaternary-all-candidate-manifest-2026-09-26.json.gz
python -X utf8 scripts/validate_quaternary_all_candidate.py run --manifest outputs/quaternary-all-candidate-manifest-2026-09-26.json.gz --output outputs/quaternary-all-candidate-2026-09-26.json.gz
python -X utf8 scripts/validate_quaternary_all_candidate.py check --manifest outputs/quaternary-all-candidate-manifest-2026-09-26.json.gz --report outputs/quaternary-all-candidate-2026-09-26.json.gz --output outputs/quaternary-all-candidate-artifact-check-2026-09-26.json
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-quaternary-all-candidate-2026-09-26.json
```
