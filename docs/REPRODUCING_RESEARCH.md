# 外部复现：算法、完整实验、证书与图件

本指南包含截至 2026-10-03 的研究记录。发起思路属于 Qinzi27。
这里公开的是可复现的候选方法、成功和负结果，不是一份新的四色定理证明。

## 当前检查：三角饱和、支持普查、等价预筛与性能剖析（2026-10-01—03）

四轮分别冻结272、279、290、295项来源，前轮字节在后轮中完整保留。
见[本批发布范围](PUBLICATION-2026-10-03.md)与以下四份结果文档：
[三角饱和](QUATERNARY_TRIANGLE_SATURATION_RESULTS-2026-10-01.md)、
[支持普查](QUATERNARY_TRIANGLE_SATURATION_SUPPORT_RESULTS-2026-10-03.md)、
[等价预筛](QUATERNARY_TRIANGLE_SATURATION_PREFILTER_RESULTS-2026-10-03.md)、
[性能剖析](QUATERNARY_TRIANGLE_SATURATION_PROFILE_RESULTS-2026-10-03.md)。
各轮需要完整父归档和按图检查点，不能仅下载主报告。不要改写或重新压缩冻结文件。

先复核已保存结果，四个输出名均须尚不存在：

```text
python -X utf8 scripts/validate_quaternary_triangle_saturation.py check --manifest outputs/quaternary-triangle-saturation-manifest-2026-10-01.json.gz --report outputs/quaternary-triangle-saturation-2026-10-01.json.gz --output outputs/my-triangle-saturation-check.json
python -X utf8 scripts/validate_quaternary_triangle_saturation_support.py check --manifest outputs/quaternary-triangle-saturation-support-manifest-2026-10-03.json.gz --report outputs/quaternary-triangle-saturation-support-2026-10-03.json.gz --output outputs/my-triangle-support-check.json
python -X utf8 scripts/validate_quaternary_triangle_saturation_prefilter.py check --manifest outputs/quaternary-triangle-saturation-prefilter-manifest-2026-10-03.json.gz --report outputs/quaternary-triangle-saturation-prefilter-2026-10-03.json.gz --output outputs/my-triangle-prefilter-check.json
python -X utf8 scripts/validate_quaternary_triangle_saturation_profile.py check --manifest outputs/quaternary-triangle-saturation-profile-manifest-2026-10-03.json.gz --report outputs/quaternary-triangle-saturation-profile-2026-10-03.json.gz --output outputs/my-triangle-profile-check.json
```

这些`check`不重新生产、传播或执行oracle搜索，但各自核验范围不同：

| 检查 | 保存核验对象与边界 |
| --- | --- |
| 三角饱和 | 975配对的1,950次策略运行、规则案例、旧1,814项条件诊断；含原始精确证据重验及有限赋值核验 |
| 支持普查 | 975场景、5,042持久状态、60,777单候选与695,575允许色对；重验711,728份场景内去重的原始查询证据，生产轨迹审计按绑定旧档继承 |
| 等价预筛 | 975完整生产输出、1,846条件输出和6,120规则案例；检查等价与真实工作量，不重跑此前原始oracle审计或重新测时 |
| 性能剖析 | 975完整生产输出、全部函数及caller记录、总量／分层／排序；不重新剖析、重测时钟或重验旧oracle |

当前生产路径的975次完成、4,067次安全提交来自三角饱和阶段的离线核查，
后续等价实现通过完整输出相等继承。支持普查中的1,846项无联合支持色对
仍被持久矩阵允许，条件传播全部能反驳；`passed`不表示矩阵已排净这些组合。
预筛减少48.8%实际三角枚举，但两轮完整计时方向相反；剖析的copy自身耗时
56.47%仅供定位成本，不能直接解释为可获得同等加速。

最终本地回归为1,833项测试及综合验证通过，失败／错误／跳过均0，见
[保存的综合验证](../outputs/validation-quaternary-triangle-saturation-profile-final-2026-10-03.json)。
需要重新运行软件核查时使用新输出：

```text
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/my-profile-validation.json
```

四个入口均支持`prepare/run/check`。全量新实验先用唯一新manifest执行
`prepare --manifest outputs/my-<stage>-manifest.json.gz`，再以该manifest执行
`run --manifest ... --output outputs/my-<stage>.json.gz`，最后检查自己的主报告。
这里只是参数形状，`<stage>`需替换为所选阶段；各结果文档提供完整实例命令。
`run`含真实计算，而支持普查的`run`仅作离线扫描，不能把其oracle计时当作
配色生产耗时。预筛／剖析按单worker保存配对测量，正式计时期间避免并行负载。

检查点按图保存；未完成时可在来源与输入未变的情况下继续相同运行，已完成
主报告拒绝覆盖。图内中断仍可能重做该图，并非每一步都可恢复。资源耗尽或
异常不能计作通过。新输入、规则或复制逻辑的修改需另立冻结版本；不要改动
旧295项来源后继续要求旧清单通过。本地验证、推送和远端CI状态分别记录。

## 此前检查：逻辑异名、联合候选、奇轮与条件同名（2026-09-27—30）

本批五阶段依赖前序完整档案，见[发布范围](PUBLICATION-2026-09-30.md)。
请从完整仓库根目录执行，使用尚不存在的输出路径。最新版本冻结253项来源；
不要重排、重压缩或改换行，否则会破坏证据哈希。单候选与二元扫描仅作离线
诊断；三个算法阶段先生产，再用原始邻接及实际承诺独立检查。

最新版本的运行与保存复核：

```text
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/my-diamond-validation.json
python -X utf8 scripts/validate_quaternary_conditional_diamond.py run --manifest outputs/quaternary-conditional-diamond-manifest-2026-09-30.json.gz --output outputs/my-conditional-diamond.json.gz
python -X utf8 scripts/validate_quaternary_conditional_diamond.py check --manifest outputs/quaternary-conditional-diamond-manifest-2026-09-30.json.gz --report outputs/quaternary-conditional-diamond-2026-09-30.json.gz --output outputs/my-conditional-diamond-check.json
```

最后一条检查正式保存结果；检查自己的重跑结果时，将`--report`换成自己的文件。
`check`不重新生产、传播或精确搜索，但会检查全部保存证书与有限字面赋值。
两个残余未识别组合并不使证据检查失败：`passed`和执行完整标志不表示算法完备。

前序入口均支持同样的`prepare/run/check`和`--manifest/--report/--output`参数：

| 阶段 | 脚本后缀（`scripts/validate_`之后） | 正式清单（`outputs/`下） |
| --- | --- | --- |
| 逻辑NEQ | `quaternary_logical_neq.py` | `quaternary-logical-neq-manifest-2026-09-27.json.gz` |
| 单候选离线扫描 | `quaternary_logical_neq_candidate_scan.py` | `quaternary-logical-neq-candidate-scan-manifest-2026-09-29.json.gz` |
| 二元离线扫描 | `quaternary_logical_neq_pair_scan.py` | `quaternary-logical-neq-pair-scan-manifest-2026-09-29.json.gz` |
| 奇轮规则 | `quaternary_odd_wheel.py` | `quaternary-odd-wheel-manifest-2026-09-30.json.gz` |

各阶段完整资源、已执行范围及限制见对应RESULTS/PROTOCOL文档；新实验用新的
清单名先`prepare`冻结输入。20个新输入键、相关历史前缀以及两种初始化不能
合并解释成独立图族或普遍成功概率。完整验证通过也不替代一般可延拓性论证。

## 此前检查：顺序、同名证书、剩余候选与全候选试排（2026-09-23—26）

这五轮分别冻结来源、输入和预算，具体发布范围见
[2026-09-27归档说明](PUBLICATION-2026-09-27.md)。从完整仓库根目录运行，
保留此前归档及全部检查点；后续manifest依赖前序证据，不能只下载最新摘要。
以下`run`从既有冻结清单重新执行，`check`复核原正式报告的保存证据。
候选扫描的`run`只作离线诊断，不重新运行生产器；其他四轮的`run`包含生产与事后审计。
`check`不重新选色或执行oracle搜索，但规则核验与有限赋值枚举仍可能耗时。

所有`my-`输出名及自动生成的同前缀`-checkpoints/`目录都须使用尚不存在的新位置。
如需检查自己新跑的结果，把`check`中的`--report`改为相应`my-`报告；不要改名或覆盖
正式清单、正式检查点。`passed`表示保存证据的核查通过，不等于所有策略都完成。

### F. 母线顺序与外框支撑

```text
python -X utf8 scripts/validate_quaternary_order_probe.py run --manifest outputs/quaternary-order-probe-manifest-2026-09-23.json.gz --output outputs/my-order-probe.json.gz
python -X utf8 scripts/validate_quaternary_order_probe.py check --manifest outputs/quaternary-order-probe-manifest-2026-09-23.json.gz --report outputs/quaternary-order-probe-2026-09-23.json.gz --output outputs/my-order-probe-check.json
```

[44条输入记录](QUATERNARY_ORDER_PROBE_RESULTS-2026-09-23.md)含25个合格几何和19个保留的几何错误；
两种初始化共50次运行、566次安全提交。没有重现已知抽象危险状态，也未证明一般调度安全。
本轮隔离几何入口允许更多线段，旧几何引擎及配色规则未改。

### G. 共同三角形EQ

```text
python -X utf8 scripts/validate_quaternary_triangle_eq.py run --manifest outputs/quaternary-triangle-eq-manifest-2026-09-23.json.gz --output outputs/my-triangle-eq.json.gz
python -X utf8 scripts/validate_quaternary_triangle_eq.py check --manifest outputs/quaternary-triangle-eq-manifest-2026-09-23.json.gz --report outputs/quaternary-triangle-eq-2026-09-23.json.gz --output outputs/my-triangle-eq-check.json
```

[311组配对](QUATERNARY_TRIANGLE_EQ_RESULTS-2026-09-23.md)的完成数310→311，唯一修复是已知10顶点
抽象input-order诊断，不是新增真实母线失败修复。五顶点全部1,024图×1,024赋值核验规则实现。
逻辑EQ不合并面身份；新增规则使用原始真实邻接，不让oracle读取EQ或推导单例。

### H. 共同奇环EQ

```text
python -X utf8 scripts/validate_quaternary_odd_cycle_eq.py run --manifest outputs/quaternary-odd-cycle-eq-manifest-2026-09-24.json.gz --output outputs/my-odd-cycle-eq.json.gz
python -X utf8 scripts/validate_quaternary_odd_cycle_eq.py check --manifest outputs/quaternary-odd-cycle-eq-manifest-2026-09-24.json.gz --report outputs/quaternary-odd-cycle-eq-2026-09-24.json.gz --output outputs/my-odd-cycle-eq-check.json
```

[619组配对](QUATERNARY_ODD_CYCLE_EQ_RESULTS-2026-09-24.md)两版均完成，各3,010次安全提交。
76个场景补充EQ，初始候选项减少244，但实际事件序列和最终配色相同。
规则核查穷举预声明80图的7,337,984个图—赋值对，不是所有九顶点图。

### I. 既有可达状态的剩余候选扫描

```text
python -X utf8 scripts/validate_quaternary_candidate_scan.py run --manifest outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz --output outputs/my-candidate-scan.json.gz
python -X utf8 scripts/validate_quaternary_candidate_scan.py check --manifest outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz --report outputs/quaternary-candidate-scan-2026-09-24.json.gz --output outputs/my-candidate-scan-check.json
```

[冻结619条旧运行的3,630个持久状态](QUATERNARY_CANDIDATE_SCAN_RESULTS-2026-09-24.md)，
逐色查询51,036个未决面的候选，得到7个无支持目标，其中3个条件传播仍未决。
3,010次实际提交均有支持；3个漏检候选没有被实际选择。保留的51,603份原始精确证据
不进入生产器，也不能把这些共享图和状态的目标解释成独立随机样本。

### J. 全候选试排配对实验

```text
python -X utf8 scripts/validate_quaternary_all_candidate.py run --manifest outputs/quaternary-all-candidate-manifest-2026-09-26.json.gz --output outputs/my-all-candidate.json.gz
python -X utf8 scripts/validate_quaternary_all_candidate.py check --manifest outputs/quaternary-all-candidate-manifest-2026-09-26.json.gz --report outputs/quaternary-all-candidate-2026-09-26.json.gz --output outputs/my-all-candidate-check.json
```

[403条记录、767组配对](QUATERNARY_ALL_CANDIDATE_RESULTS-2026-09-26.md)含383个合格几何、
1个抽象例和19个旧几何排除。两版各767完成、3,399次安全提交，承诺序列和最终颜色全部相同；
新增完成修复/退步均0。共同试探上限8192下，实际probe为3,400→54,540（16.04倍），
传播轨迹220,534→6,372,700（28.90倍）。619份旧基线只规范化原512预算字段，结果仍逐项一致。

已知单锚图提前完成`S3=1111→1011→1001→2000`，排除S4/S5的1，但初始S10=1仍未被
条件传播识别为无解。新版本的1个unsupported存活probe统计只覆盖实际尝试事件，
不等于再次扫描了所有中间状态的完整候选清单；详见
[保存的已知案例包](../outputs/quaternary-all-candidate-known-gap-2026-09-26.json)。

75个新声明图含旧空框；严格新增为74图/148场景，两版全部完成且没有新增拒绝或修复。
两版各633运行满足全枚举预算，各134运行明确未全枚举；这里633是运行数，与经典633构形无关。
55条历史的每个前缀重新初始化，不表示继承前图配色。生产后半批并行且与其他检查有时间重叠，
正式耗时不作为严格速度基准；确定性的试探/轨迹次数是本轮成本比较重点。

原正式落盘复核应同时读取
`outputs/quaternary-all-candidate-artifact-check-2026-09-26.json`与
`outputs/quaternary-all-candidate-parallel-check-execution-2026-09-26.json`：
后者绑定1,534次冻结检查器调用和对应的完整参数摘要复用。上面的标准`check`命令
可自行顺序重放，无需该内存复用安排；它仍需完整403个检查点及前序归档。

## 此前检查：逐步延拓、四进制候选与危险域可达性（2026-09-21—22）

以下五阶段各自冻结输入、规则和来源。它们不是同一算法逐次相加的成功数。
从完整仓库根目录运行，使用Python 3.10+及现有Node；环境见第2节。
所有`my-`输出及检查点目录必须尚不存在，正式归档不覆盖。完整几何运行包含
离线oracle及有限赋值枚举，资源成本不同于只运行生产算法。

### A. 固定结构重启版的每次承诺检查

```text
python -X utf8 scripts/audit_commit_extendibility.py prepare --family guillotine --max-cuts 5 --assignment-limit 65536 --manifest outputs/my-guillotine-manifest.json
python -X utf8 scripts/audit_commit_extendibility.py run --manifest outputs/my-guillotine-manifest.json --output outputs/my-guillotine-audit.json.gz
python -X utf8 scripts/audit_commit_extendibility.py prepare --family grid-subsets --assignment-limit 65536 --manifest outputs/my-grid-manifest.json
python -X utf8 scripts/audit_commit_extendibility.py run --manifest outputs/my-grid-manifest.json --output outputs/my-grid-audit.json.gz
```

[正式结果](EXTENDIBILITY_RESULTS-2026-09-21.md)分别是357图/872次承诺和4,096图/6,114次承诺均可延拓。
前者穷举指定网格最多5刀的2,145条有序贯穿切分历史；后者穷举12条单位边的子集，
每个子集仅取一条代表顺序。独立求解器在候选运行后检查原始邻接及承诺，不反馈选色。

### B. 四进制候选原型的可靠性

```text
python -X utf8 scripts/validate_quaternary_contacts_v2.py prepare --manifest outputs/my-contact-manifest.json.gz
python -X utf8 scripts/validate_quaternary_contacts_v2.py run --manifest outputs/my-contact-manifest.json.gz --output outputs/my-contact-run.json.gz
python -X utf8 scripts/validate_quaternary_contacts_v2.py example --id two-neighbors-same-minimum --output outputs/my-contact-example.json
```

[41,847模型核查](QUATERNARY_CONTACT_RESULTS-2026-09-21.md)区分候选`0111={2,3,4}`与承诺2，
检查合法赋值保留，不把冲突/未决模型混成求解成功率。v1审计缺口与v2补强均保留；
当前复现使用v2入口。这个原型没有主动选色。

### C. 接入真实绘图几何

```text
python -X utf8 scripts/validate_quaternary_geometry.py map examples/structural-v2-failure-map-2026-09-21.json --output outputs/my-quaternary-map.json
python -X utf8 scripts/validate_quaternary_geometry.py run --manifest outputs/quaternary-geometry-manifest-2026-09-21.json.gz --output outputs/my-quaternary-geometry.json.gz --checkpoint-dir outputs/my-quaternary-geometry-parts
python -X utf8 scripts/check_quaternary_geometry_artifacts.py --manifest outputs/quaternary-geometry-manifest-2026-09-21.json.gz --report outputs/quaternary-geometry-2026-09-21.json.gz --checkpoint-dir outputs/quaternary-geometry-checkpoints-2026-09-21 --output outputs/my-quaternary-geometry-check.json
```

[正式结果](QUATERNARY_GEOMETRY_RESULTS-2026-09-22.md)覆盖4,144图、8,339场景。
该版本单锚全部未决，49份完整旧配色仅为往返证书；oracle见证不可冒充原型输出。
第三条核查保存的正式归档，与前一条新运行的`my-`输出分开；它不是再次生产求解。
真实桥、点触和虚拟连接的区别，及共享Node平面化的独立性边界见结果说明。

### D. 低色优先和提交前条件传播

```text
python -X utf8 scripts/validate_quaternary_low_color.py run --manifest outputs/quaternary-low-color-manifest-2026-09-22.json.gz --output outputs/my-low-color-run.json.gz --checkpoint-dir outputs/my-low-color-parts
python -X utf8 scripts/check_quaternary_low_color_artifacts.py --manifest outputs/quaternary-low-color-manifest-2026-09-22.json.gz --report outputs/quaternary-low-color-2026-09-22.json.gz --checkpoint-dir outputs/quaternary-low-color-checkpoints-2026-09-22 --output outputs/my-low-color-check.json
```

[4,272图对照](QUATERNARY_LOW_COLOR_RESULTS-2026-09-22.md)中，旧双锚完成数由plain的4,271
提高到guarded的4,272，单锚两版均完成。正式17,092次运行含4次具名诊断运行，
诊断重现同一旧失败不能另算修复。常规guarded有18,743次已核查安全提交；
后续发现的抽象顺序反例表明这不是普遍安全性证明。128个新输入两版均完成，无新增修复收益。

### E. 危险候选域是否能由实际流程产生

```text
python -X utf8 scripts/check_quaternary_reachability.py prepare --manifest outputs/my-reachability-manifest.json.gz
python -X utf8 scripts/check_quaternary_reachability.py run --manifest outputs/my-reachability-manifest.json.gz --output outputs/my-reachability-run.json.gz
python -X utf8 scripts/scan_low_color_obstruction_states.py --manifest outputs/quaternary-low-color-manifest-2026-09-22.json.gz --report outputs/quaternary-low-color-2026-09-22.json.gz --checkpoint-dir outputs/quaternary-low-color-checkpoints-2026-09-22 --output outputs/my-obstruction-scan.json
python -X utf8 scripts/check_quaternary_reachability_artifacts.py --manifest outputs/quaternary-reachability-manifest-2026-09-22.json.gz --report outputs/quaternary-reachability-2026-09-22.json.gz --scan outputs/quaternary-obstruction-state-scan-2026-09-22.json --output outputs/my-reachability-artifact-check.json
```

[正式结果](QUATERNARY_REACHABILITY_RESULTS-2026-09-22.md)的两个几何群体共314次运行、
763次可延拓承诺，0次拒绝候选；两群可能共享前缀，不称157张全局不同图。
六线段群覆盖全部720顺序，提升构造只覆盖4种表示的固定顺序、93个去重前缀。
同一报告另保留10顶点单锚抽象顺序下第4次提交A1的首错，完整解6→0；
相关11面实际母线轨迹先处理E，再传播固定A=E，未走到该危险状态。
第三条只读扫描上轮归档，第四条只复核保存证据；均不向生产策略提供候选或补救。
核查`passed`包括正确确认负结果，不表示被核查算法的每条路径都成功。

以上报告保留来源/输入哈希、完整证据及枚举与超限范围。后续改规则须另立版本再比较；
当前下一步是检查母线顺序的保护条件，另行评估共同三角形同名证书，而非把四进制本身当作证明。
发布与远端CI状态应查看实际提交及工作流，不能由这些本地研究记录预先推定。

## 已冻结主线：结构反证与整图重启（2026-09-21）

从完整仓库根目录执行以下命令；环境要求见第2节，所有输出与目录均须使用尚未占用的路径。
先重现旧 v2 唯一失败的真实 `frame/strokes` 几何：

```text
python -X utf8 scripts/name_structural_map.py examples/structural-v2-failure-map-2026-09-21.json --output outputs/my-structural-map.json
```

入口只把当前几何交给一次 `mother-peer-structural-reuse-v1` 命名与独立审计，输入中的旧名字等额外字段不参与选择。
但命令行仍读取正式旧 v2 报告核对来源，所以需要完整仓库证据，不能仅复制单个 Python 文件。
这份实例预期成功并保存 S1≠S10 的反证证书；成功退出码0，策略冲突退出码2，已有输出拒绝覆盖。
它保留母线、点到点几何、辅助层级和最小候选，只在当前复用提议被结构证书反驳时改变流程。
`inconclusive` 是未找到反证，不是当前提议已获可延伸保证。

重跑全部旧库，以及运行前固定的新种子双策略配对实验：

```text
python -X utf8 scripts/validate_structural_restart_full.py --workers 4 --batch-size 25 --output outputs/my-structural-full.json.gz --summary outputs/my-structural-summary.json --checkpoints outputs/my-structural-checkpoints
python -X utf8 scripts/validate_structural_restart_new_seeds.py --workers 4 --batch-size 25 --output outputs/my-structural-new-seeds.json.gz --summary outputs/my-structural-new-seeds-summary.json --checkpoints outputs/my-structural-new-seeds-evidence
```

第一条对7069张旧库去重几何各新跑一次候选规则，并逐次独立全审计；v2对照来自绑定哈希的旧归档。
第二条完整生成 `20262101..20262120` 共20条 guillotine 历史，每条24刀及初态，共500引用、481去重图；
每图旧 v2 和新规则各新跑一次，分别用已有独立核验器与结构证书审计器检查。
与旧库重叠2图、未见479图分别统计，全部前缀和最终图分别统计，不挑选成功前缀，不称独立图族。
两条命令的 `--limit` 只适合明确标注的小规模 smoke；正式成绩未使用该参数。
检查器验证原边、商图分区、强制合并、冲突证书、查询覆盖及无结论时的规则饱和，不能只读取成功总数。

正式结果为旧库7069/7069，新种子481/481，其中未见479/479；两批分别修复旧 v2 的1个失败，0退步。
在[成功保持命题](STRUCTURAL_RESTART_SUCCESS_PRESERVATION-2026-09-21.md)的明确前提下，旧成功轨迹必保留；
这不保证任意旧失败都能修复，也不保证资源开销不增加。完整解释见[冻结规则](STRUCTURAL_RESTART_RULES-2026-09-21.md)和[结果](STRUCTURAL_RESTART_RESULTS-2026-09-21.md)。

| 正式证据 | 作用 |
| --- | --- |
| [旧库完整 gzip](../outputs/structural-restart-full-2026-09-21.json.gz)及[摘要](../outputs/structural-restart-summary-2026-09-21.json) | 7069次新候选运行、完整审计统计、旧基线及逐图对照 |
| [旧库 checkpoints](../outputs/structural-restart-checkpoints-2026-09-21/) | 全部批次结果、来源与校验记录 |
| [新种子完整 gzip](../outputs/structural-restart-new-seeds-2026-09-21.json.gz)及[摘要](../outputs/structural-restart-new-seeds-summary-2026-09-21.json) | 481图两策略新运行、novel/overlap及历史口径配对统计 |
| [新种子 evidence](../outputs/structural-restart-new-seeds-2026-09-21-evidence/) | 全部配对批次、生成清单及校验记录 |
| [旧失败诊断](../outputs/v2-failure-diagnosis-2026-09-21.json) | 实际几何与可独立重放的结构证书 |

所有学习／失败案例保留完整执行记录；其余案例实际完整执行并审计后保存轨迹哈希及具体名字。
旧库与新种子分别核对31项、35项输入／源码起止哈希。主 gzip 的 SHA-256 分别是
`bc692056ee5395168bb39ceae9d3b24d5f5b2d289180bc3261a918c52c7daeca` 和
`62699d8f2953f77336e938f1ca4bde8be2fa65b4eb594b3bd19442e4b5efc49e`。
压缩文件本身、分片、源码清单及其独立审计承担不同核验职责，不能用一个摘要代替全部证据。

## 另一路线：Kempe 修复、重标成本与连续历史（2026-09-20—21）

这些程序研究“给定合法旧配色后加入一刀”的修复及成本，与上面的当前整图清空旧名重启分开。
固定160个首次受阻快照不是160条完整历史；最少 Kempe 操作数、最少净改旧侧数与累计成本也分开。

```text
python -X utf8 scripts/validate_kempe_split.py --output outputs/my-kempe-split.json
python -X utf8 scripts/validate_kempe_progress.py --output outputs/my-kempe-progress.json
python -X utf8 scripts/validate_recoloring_obstructions.py --output outputs/my-recoloring-obstructions.json
python -X utf8 scripts/validate_triangle_chain_replay.py --output outputs/my-triangle-chain-replay.json
python -X utf8 scripts/validate_kempe_history_continuation.py --output outputs/my-kempe-history-continuation.json.gz
python -X utf8 scripts/validate_triangle_chain_parent_rigidity.py --output outputs/my-parent-rigidity.json
```

各运行器默认读取它声明的正式归档输入；上面的 `my-` 输出不会自动成为下一条命令的输入。
应先阅读脚本的输入常量、源哈希与对应阶段文档。初次 `kempe-split-2026-09-20.json` 和
`kempe-progress-2026-09-20.json` 保留为历史记录；验证器及依赖清单补强后，当前源码复现使用
[split 的 `-v2` 报告](../outputs/kempe-split-2026-09-20-v2.json)与[progress 的 `-v2` 报告](../outputs/kempe-progress-2026-09-20-v2.json)，
不要把初次报告中已不匹配的旧源码哈希当成当前实现凭证。

[成本实验](KEMPE_SPLIT_COST-2026-09-20.md)保持95/160单次修复覆盖，降低已有成功的改名成本；
[多步实验](KEMPE_PROGRESS-2026-09-20.md)区分有界操作路径与精确终点成本；
[障碍构造](RECOLORING_OBSTRUCTIONS-2026-09-21.md)给出指定家族最后一刀至少改 `2m` 个旧侧的结论。
[连续修复](TRIANGLE_CHAIN_REPLAY-2026-09-21.md)的128条历史完成3712刀、1792次单 Kempe 后备修复；
每次后备的净旧侧成本最优不等于整条历史累计成本最优。
[父图刚性](TRIANGLE_CHAIN_PARENT_RIGIDITY-2026-09-21.md)把该家族最后一刀的 `2m` 下界推广到任意合法旧父图标色，
没有推广成任意图、任意历史或整图重启算法的下界。

完整证据包括[障碍 JSON](../outputs/recoloring-obstructions-2026-09-21.json)、
[对照重放 gzip](../outputs/triangle-chain-replay-2026-09-21.json.gz)、
[连续修复 gzip](../outputs/kempe-history-continuation-2026-09-21.json.gz)、
[父图刚性 JSON](../outputs/triangle-chain-parent-rigidity-2026-09-21.json)及[摘要](../outputs/replay-novelty-summary-2026-09-21.json)。
对照重放的约128MB明文文件不随本次归档发布；gzip 解压字节与该原始 JSON 完全相同。
**当前 `validate_kempe_history_continuation.py` 直接读取 gzip，无需解压。**
如历史代码要求旧 `.json` 路径，可用标准库显式恢复，先核对原始字节哈希，并以 `xb` 拒绝覆盖已有原件：

```text
python -X utf8 -c "import gzip, hashlib; from pathlib import Path; data = gzip.decompress(Path('outputs/triangle-chain-replay-2026-09-21.json.gz').read_bytes()); assert hashlib.sha256(data).hexdigest() == '727e72fe27de386c830fc2b4d5025b2a7d1ce7fe510d7d51efc710815e6e42b6'; stream = Path('outputs/triangle-chain-replay-2026-09-21.json').open('xb'); stream.write(data); stream.close()"
```

压缩文件自身 SHA-256 为 `ddccbc32f6c97f63fbb6df88278396d590aa77fcdf53ed80bd02d96c64e2a678`。
恢复出的明文用于兼容历史输入，不应再次提交为重复大文件。gzip 是完整证据压缩，不是删减版摘要。
上述代码中的断言必须开启，不能使用 `python -O`。

## 此前补充：有效旧操作与完整边界状态（2026-09-20）

[该阶段复核](PRIOR_OPERATIONS_RESULTS-2026-09-20.md)分别保存三种不同口径：
历史 7069 图的 v2/v3/v4 冻结结果、49 图 × 8 组合的 392 次新运行，以及原精确程序对 v4 九个失败的 9／9 求解。
新程序和证据已公开，旧报告中的“未上传”“未改网页”是各轮结束时的历史状态。

先复现一张图：以下精确入口接受**面邻接图 JSON**，不是画板的 `frame/strokes` 几何格式。
它保留完整边界状态并恢复见证，不使用旧配色或 v4 的贪心承诺。

```text
python -X utf8 scripts/solve_closed_interfaces.py --input examples/prior-v4-least-failure-graph.json --mode orbit --output outputs/my-prior-orbit.json
python -X utf8 scripts/check_prior_exact_failures.py --output outputs/my-prior-exact.json
python -X utf8 scripts/compare_prior_operations.py --output outputs/my-prior-operations.json.gz --summary outputs/my-prior-operations-summary.json
```

输出必须使用未占用的路径。第二条对同九图运行两个共享精确核心的入口，独立核验真实共边；
第三条运行预设的全部八组合，并检查旧基线的完整轨迹与传播哈希。
它不会按图选择最佳策略，也不是新的全库成绩或独立速度基准。

此前三轮的程序、数学边界和完整复现命令分别见：
[闭合接口／轨道压缩](CLOSED_INTERFACE_OPTIMIZATION-2026-09-20.md)、
[双接口推广](TWO_PORT_GENERALIZATION-2026-09-20.md)、
[联合边界过滤及负结果](JOINT_BOUNDARY_RESULTS-2026-09-20.md)。
该阶段保存的完整验证为 **674 项 Python 测试，0 失败、0 错误**；测试通过不表示所有贪心案例成功。

## 此前补充：内起点顺序与最少颜色控制（2026-09-20）

新增 [圈的 rank 与固定层补全](CIRCLE_RANK-2026-09-20.md)、
[圈层修复](CIRCLE_LAYER_REPAIR-2026-09-20.md) 和
[内外起点对照](INSIDE_OUT_EXPERIMENT-2026-09-20.md)。它们是独立研究模块，
不会替换下面的 v4 单图入口或改写其冻结成绩。

内外起点主实验固定四种可用色名；控制实验保持所有顺序不变，使用各图最少颜色。
63 图各做 1917 次运行。嵌套树的二色控制消除了状态数收益，边界宽度差异仍在。
完整命令如下，输出均须使用未占用的新文件名：

```text
python -X utf8 scripts/validate_inside_out.py --output outputs/my-inside-out.json
python -X utf8 scripts/validate_inside_out_palette.py --input outputs/my-inside-out.json --output outputs/my-inside-out-palette.json
```

这两条命令及其核心模块只使用标准库，需完整仓库中的原图报告作为输入。
若重新绘图，使用已安装的 Pillow 与本机可用的中文字体：

```text
python -X utf8 scripts/render_inside_out.py --input outputs/my-inside-out.json --palette-control outputs/my-inside-out-palette.json --output-dir docs/figures/my-inside-out --font /path/to/NotoSansCJK-Regular.ttc
```

本轮新增 17 项测试，合计 577 项 Python 测试及综合验证通过。完整代码、逐步状态、
最优连通宽度、负结果与来源哈希均随仓库发布；数字是有限实现核验，不是一般性能保证。

## 1. 先区分不同工作

| 工作 | 入口 | 能说明什么 |
| --- | --- | --- |
| 核查每次主动承诺是否有延拓 | `scripts/audit_commit_extendibility.py` | 指定小规模合法输入及固定结构规则；oracle只作离线核查 |
| 保留四进制候选及真实共边 | `scripts/validate_quaternary_geometry.py` | 几何/传播适配与证书；无主动选色版本可保持未决 |
| 同条件比较plain与guarded低色策略 | `scripts/validate_quaternary_low_color.py` | 固定4,272图及具名诊断，分别记录修复、退步和实际承诺 |
| 检查危险域的实际可达性 | `scripts/check_quaternary_reachability.py` | 真实母线有限运行与抽象顺序反例分开保存 |
| 只读复核可达性研究产物 | `scripts/check_quaternary_reachability_artifacts.py` | 已保存证据、输入覆盖与哈希；不重新运行生产器 |
| 按需结构反证后对当前整图重新命名 | `scripts/name_structural_map.py` | 当前候选一次运行、完整证书审计；反证无结论仍可能提交后受阻 |
| 新主线完整旧库实验 | `scripts/validate_structural_restart_full.py` | 固定规则在7069个去重输入上的新运行，旧 v2 为归档对照 |
| 预声明新种子配对实验 | `scripts/validate_structural_restart_new_seeds.py` | 每图两策略均新跑，分别统计重叠与未见几何、全前缀与终图 |
| 用精确边界程序求面邻接图配色 | `scripts/solve_closed_interfaces.py --mode orbit` | 完整状态与合法见证；成本取决于边界状态规模 |
| 研究画板几何的一次性贪心取色 | `scripts/name_peer_batch_map.py` | 固定 v4 规则的一次成功或冲突；它不是历史最强基线 |
| 对照此前初始化、调度与旧引理 | `scripts/compare_prior_operations.py` | 固定 49 图八组合，分别记录修复与退步 |
| 重新运行旧 v4 完整样本库 | `scripts/validate_peer_batches_full.py` | 固定旧 v4 在 7069 个去重输入上的实际结果 |
| 审计旧 v4 已存完整实验 | `scripts/audit_peer_batches_full.py` | 统计、输入、分片、色名与推导证书是否一致 |
| 浏览历史网页演示 | `npm run dev`、`npm run build` | 历史交互实现；并未接入最新 v4 或隐含异名模板 |

不要把“审计通过”理解为所有地图均标色成功。v4 正式记录是 **7060 成功、9 冲突**；
它修复旧 v3 的 4 个失败，同时产生 9 个新退步。软件测试允许并检验这些真实冲突。
单张图可由其他方法正确着色，不等于该候选的本次承诺路径成功。

## 2. 下载整个仓库与环境

应使用完整 Git checkout 或仓库源码归档，而不是仅安装 `fourcolor` Python 包。
测试和实验还需要 `scripts/`、`tests/`、`web/`、`examples/`、`docs/figures/` 与 `outputs/` 的公开证据。
记录所用提交：

```text
git rev-parse HEAD
python --version
node --version
```

必要环境：

- Python **3.10+**；核心 `fourcolor/` 使用标准库，不需要科学计算大套件。
- Node.js **20+**，且命令 `node` 在 PATH 上。许多 Python 测试会通过 Node 重新生成几何，因此只安装 Python 不够。
- Pillow：完整 Python 测试会导入绘图辅助模块；单图计算和核心算法本身不需要 Pillow。
- npm：用于执行网页测试与静态构建。当前网页没有第三方运行时依赖，仍保留 lockfile。

建议在本地虚拟环境安装研究／测试依赖，不改系统 Python。例如先运行 `python -m venv .venv`，
随后使用该环境的解释器安装：Windows 为 `.venv\Scripts\python -m pip install -r requirements-research.txt`，
Linux/macOS 为 `.venv/bin/python -m pip install -r requirements-research.txt`。
该文件仅声明 Pillow 的兼容范围；核心算法仍只使用标准库。
下面命令中的 `python` 应指向这个环境；也可用上述完整的环境内解释器路径替换。

2026-09-19 本地验证记录的环境为 Python 3.12.14、Node v24.14.0、Pillow 12.3.0。
这是原运行环境记录，不表示必须锁定这些版本，也不保证所有其他版本已实测。

不要用 `python -O`：部分独立证书检查依赖断言，正式运行器也会拒绝关闭断言的解释器。

## 3. 旧 v4 单图复现（历史对照）

从仓库根目录执行，输出使用一个尚不存在的文件名：

```text
python -X utf8 scripts/name_peer_batch_map.py examples/peer-batch-five-lines.json --output outputs/my-five-lines-run.json
```

输入对象只需 `strokes` 与可选的矩形 `frame`。例如：

```json
{
  "frame": {"width": 900, "height": 600},
  "strokes": [
    {"a": [300, 0], "b": [300, 600]},
    {"a": [600, 0], "b": [600, 600]},
    {"a": [0, 300], "b": [300, 300]}
  ]
}
```

位置使用原画板坐标，x 向右、y 向下。颜色不属于输入。
输出保存几何、每个整母线区间的左右侧身份及最终名字、主动取名记录和独立证书。
整母线不同位置可以具有不同的当前名字对，不能只留一个全局 `(a,b)`。

复现真实的最小新受阻图：

```text
python -X utf8 scripts/name_peer_batch_map.py docs/figures/peer-batches-2026-09-19/least-new-conflict-document.json --output outputs/my-known-conflict.json
```

这条命令预期保存冲突证书并返回退出码 **2**，不是程序崩溃；成功为 **0**。
重复使用已有输出名会被拒绝。此入口不读取归档配色报告，也没有旧算法后备。

## 4. 软件回归与有限数学检查

```text
npm ci
npm test
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/my-validation.json
```

`validate.py` 自身也执行完整 Python 单元测试，再做有限数学检查；
因此前一条独立 `unittest` 不是必要的重复工作，只是便于分开观察失败。
2026-09-19 研究快照记录为536项 Python 和107项 Node 测试通过；
9月21日连续修复阶段为786项 Python 与107项 Node；结构主线阶段为 **831项 Python及综合验证通过**。
后续研究检查点依次为逐步延拓869项、候选原型908项、真实几何940项、低色对照982项，
9月22日可达性研究为1,029项；后续顺序检查1,077项、三角形EQ 1,128项、奇环EQ 1,185项、
候选扫描1,224项，至9月26日全候选试排为 **1,274项Python测试及综合验证通过**，
详见[保存的综合验证](../outputs/validation-quaternary-all-candidate-2026-09-26.json)。
这些是各自保存的本地检查点，不是本次发布的远端CI成绩，也不等于各算法均已普遍安全。
结构阶段实际调用 Node 几何引擎，但未重跑整套网页测试。发布时另做的干净副本及远端检查以
[各次发布日志](PUBLICATION-2026-09-27.md)和实际工作流状态为准，不把前次记录当成本次 CI 结果。

完整测试导入 Pillow，但绘图单元测试用记录画布核对坐标，不实际加载 Windows 的 `msyh.ttc`。
仅跑软件测试不需要安装这个字体。真正重新生成 PNG 时才需要可用的中文字体。

部分有限数学单元测试使用小图枚举作为独立 oracle；不能据此说生产 v4 隐藏枚举了整张地图配色。

## 5. 旧 v4 完整运行与独立审计

下面的三个输出位置都必须是新名字：

```text
python -X utf8 scripts/validate_peer_batches_full.py --output outputs/my-peer-full.json.gz --summary outputs/my-peer-summary.json --checkpoints outputs/my-peer-parts --workers 4 --batch-size 25
python -X utf8 scripts/audit_peer_batches_full.py --report outputs/my-peer-full.json.gz --summary outputs/my-peer-summary.json --output outputs/my-peer-audit.json
```

完整运行包含 7069 张去重地图、363 条历史的 7678 个前缀引用和 302 份静态引用。
后两项合计是引用数，不是新的去重地图数。原四失败、后来发现的新失败与成功控制都不删掉。

正式运行对每个当前几何重新求解一次；旧 v3 只作为归档对照，不传入生产求解函数。
独立审计重新导出全部几何、核验所有已完成解，重放保存的全部失败与诊断证书，
并对声明的 55 个样本重新求解；**审计不是第二次 7069 张全量求解**。

默认 `--workers 4 --batch-size 25` 与原记录一致。可以减小 workers 适应机器；
若改变批次大小，一些较早版本的审计脚本对固定 283 分片有断言，不要套用到这些历史脚本。
运行时间受机器影响，报告中的原始耗时不是复杂度证明。

默认输入依赖公开的 `outputs/staged-levels-full-2026-09-19.json.gz`、固定诊断清单及其前序证据。
新运行器不会因为只下载了一个摘要，就自动补回缺失的历史输入。

## 6. 审计各阶段已有完整证据

以下命令采用仓库内正式输入，所有审计输出另存，避免覆盖旧结果。
它们检查的对象与重新求解规模并不完全相同；每份脚本首部和输出中的 `scope`/`limits` 说明具体边界。

```text
python -X utf8 scripts/audit_global_restart.py --output outputs/my-global-audit.json
python -X utf8 scripts/audit_frontier_report.py --output outputs/my-frontier-audit.json
python -X utf8 scripts/audit_relation_frontier_full.py --input outputs/relation-frontier-full-2026-09-19.json.gz --summary outputs/relation-frontier-full-summary-2026-09-19.json --output outputs/my-relation-audit.json
python -X utf8 scripts/audit_level_sides_full.py --output outputs/my-level-v1-audit.json
python -X utf8 scripts/audit_level_sides_peer_full.py --output outputs/my-level-v2-audit.json
python -X utf8 scripts/audit_staged_levels_full.py --output outputs/my-level-v3-audit.json
python -X utf8 scripts/audit_peer_batches_full.py --output outputs/my-batch-v4-audit.json
```

`audit_minimum_names.py` 的完整模式会重新运行原关系规则，并逐步检查它是否已经取最小名字，
不是单纯重算摘要，也不是执行一个改变后的求解器或宣称新的修复；应单独保存并解释：

```text
python -X utf8 scripts/audit_minimum_names.py --mode full --output outputs/my-minimum-full.json.gz --summary outputs/my-minimum-summary.json --parts outputs/my-minimum-parts --workers 4
```

重新定位 v4 的九个冲突与固定隐含异名模板覆盖：

```text
python -X utf8 scripts/diagnose_peer_batch_failures.py --input outputs/peer-batches-full-2026-09-19.json.gz --output outputs/my-peer-conflict-diagnosis.json
python -X utf8 scripts/check_implicit_inequality_failures.py --output outputs/my-implicit-coverage.json
python -X utf8 -m unittest tests.test_implicit_inequality -v
```

这里的旧合法见证只用于事后分析；模板覆盖原记录为 3/9，
不是“重新成功标色三张图”，更不能补进 v4 的 7060 个成功结果。

## 7. 哈希、分片和大文件：复现不可省略的部分

报告绑定原始文件字节与源码 SHA-256，既不是只比较 JSON 解析后的内容，也不是只比较配色数字。
请遵守以下规则：

- 保留发布提交的冻结源码；不要先重排导入、格式化或改注释，再要求旧源码哈希通过。
- 保留 `.gitattributes`；证据目录中某些 JSON 原始字节含 CRLF，自动转 LF、重新缩进或重新 gzip 都会改变档案哈希。
- 不改名正式输入及 `*-full-parts-2026-09-19/` 分片目录。完整审计还要查 `.sha256.json` sidecar 与 `manifest.json`，不是只有主 `.json.gz` 就足够。
- `outputs/peer-batches-full-parts-2026-09-19/` 等完整运行目录各有 283 个 gzip 分片与相应校验文件。源报告的 `execution.checkpoint_directory` 指向这些相对位置。
- 新结构主线的 `outputs/structural-restart-checkpoints-2026-09-21/` 与 `outputs/structural-restart-new-seeds-2026-09-21-evidence/` 也完整保留；不因主报告已压缩就省略这些执行证据。
- 文档中有几份较大的历史 JSON。网页不能预览全文时应克隆或下载 Raw 文件；不要把网页预览文本复制成替代输入。
- 大图 PNG 是便于阅读的预览，SVG 保留精确矢量线，图件 `manifest.json` 还保留输入、色名、坐标与哈希。

“字节不一致”首先意味着无法确认是原来那份证据，不等于发现了数学反例。
新运行的时间戳、计时和压缩文件哈希也不必与旧运行相同；需要匹配的是声明输入、规则、几何、决策与被检查结论。

Git checkout 还可检查当前索引是否逐字节保留证据及检查器声明的冻结源码：

```text
python -X utf8 scripts/check_publication_archive.py --output outputs/my-publication-check.json
```

此检查需要 Git 索引（不能仅有下载后解压的 ZIP），不重新求解数学问题，也不是秘密扫描。
它核对索引中的全部 `outputs/`、`docs/figures/` 和 v4 声明的源码；
自行修改或暂存新文件后应重新检查，不把先前报告当成新状态的保证。

历史结果按各次实验当时的规则和统计口径引用，具体复现与源码哈希核验范围依各 runner/audit 的声明。
部分历史同名脚本后来经过修订，当前 checkout 不保证能逐字节重算所有历史版本；
此前发布索引检查绑定 v4 的30份冻结源码及索引证据字节；新主线另按各运行器清单绑定31／35项来源。
发布索引检查的实际覆盖以脚本与新输出为准，不代表每个历史版本都已重新运行或其原源码哈希均与当前同名文件相同。

最新拟归档范围见[10月3日发布说明](PUBLICATION-2026-10-03.md)，此前范围仍见
[9月30日发布说明](PUBLICATION-2026-09-30.md)、[9月27日发布说明](PUBLICATION-2026-09-27.md)、
[9月21日发布说明](PUBLICATION-2026-09-21.md)与[9月22日发布说明](PUBLICATION-2026-09-22.md)：完整正式报告与分片保留，
结构 smoke、本地文本日志、重复大明文 JSON 和早期 inside-out 草图不发布；本地原件均保留。
旧报告里的“未上传”“未发布”是当时状态，不为本次归档改写，也不由本指南预先宣称远端推送或 CI 成功。

私人参考附件保存在被忽略的 `_local/`，不公开、不执行，也不是以上任何测试或计算的依赖。
私人机器路径、账号凭证、聊天记录与压缩附件不属于公开复现输入。

## 8. 重新生成准确图件

Pillow 与一个有权使用的中文字体即可生成图件；无需修改算法。Windows 默认字体为 `msyh.ttc`。
其他系统显式传入当地可用的 CJK 字体文件，例如安装了 Noto CJK 时使用它的真实路径：

```text
python -X utf8 scripts/render_peer_batches.py --input outputs/peer-batches-full-2026-09-19.json.gz --output-dir docs/figures/my-peer-rerender --font /path/to/NotoSansCJK-Regular.ttc
```

`/path/to/...` 是需替换的占位路径，不是仓库依赖。已有目标目录会被拒绝覆盖。
字体不同可能改变文字像素与图件哈希，但不能改变输入线坐标、实际配色或推导证书。
灰色虚线表示尚未激活的原始细分线，浅绿仅表示几何就绪，不是四色名字的一部分。

## 9. 网页与研究程序不混同

```text
npm run dev
npm run build
```

本地开发服务器默认在 `http://127.0.0.1:4173/`，根目录与 `rules.html` 是历史交互演示。
`model.html` 是既有理论解释页。构建产物放在 `dist/`，用于 GitHub Pages。

v4 的完整实验、负结果和固定隐含异名引理，以及最新结构反证主线，属于分别冻结的 Python 研究部分；
**此次整理公开研究材料，没有把网页默认命名器替换为这些研究策略。**
旧 v4 状态以其[结果报告](PEER_BATCH_RESULTS-2026-09-19.md)和[隐含异名引理](IMPLICIT_INEQUALITY-2026-09-19.md)为准；
结构重启主线以[结构重启结果](STRUCTURAL_RESTART_RESULTS-2026-09-21.md)及其单独命令行为准；
最新四进制分支以[三角饱和结果](QUATERNARY_TRIANGLE_SATURATION_RESULTS-2026-10-01.md)、
[支持普查](QUATERNARY_TRIANGLE_SATURATION_SUPPORT_RESULTS-2026-10-03.md)、
[预筛](QUATERNARY_TRIANGLE_SATURATION_PREFILTER_RESULTS-2026-10-03.md)、
[性能剖析](QUATERNARY_TRIANGLE_SATURATION_PROFILE_RESULTS-2026-10-03.md)及本指南顶部四轮入口为准，
未用该分支替换网页默认器，也不把其有限结果当作结构重启版的新成绩。
