# 三色三角必要条件预筛：输出等价成立，稳定整体提速未成立（2026-10-03）

正式计算和最终保存复核均完成。新实现减少了三角组合枚举，但两轮完整生产
计时方向不一致，不能认定整体稳定提速。本轮成果保存在本地，未提交或推送。

## 1. 改了什么，为什么可以跳过

本轮新增 `quaternary-triangle-saturation-prefilter-v1`，保留原来的四进制候选
语义、低色优先、母线调度、条件EQ作用范围和完整数学证据格式。旧279项
冻结来源逐字节保留；新增5个脚本、5个测试文件和1份协议，共冻结290项来源。

对目标EQ类T、颜色q，旧三角饱和证书必须找到三个互异的真实邻接类，且
三个类的候选域都排除q。令这些候选邻居的集合为：

`N_q(T) = {U: U与T真实共边，且q不在D(U)中}`。

若 `|N_q(T)| < 3`，任何三个真实邻居都至少有一个不满足排除q的要求，
所以旧循环不可能产出证书。此时直接跳过组合枚举；条件足够时仍沿旧顺序
检查邻居三组合、三角内部真实边和最小原始边见证。这只是必要条件，邻居
数足够不代表三角证书一定存在。

预筛不要求q属于目标域，也不要求邻居域恰好有三个颜色；空域及EQ输入
验证沿用旧定义。逻辑NEQ不能充当真实共边。实现还把每个目标的邻居排序
移到颜色循环之外；本次计时比较整个新实现，不能单独归因于预筛门槛。
没有拓扑缓存、跨调用结果缓存或跨条件拼接域／EQ。

旧返回JSON逐字段兼容，包含旧 `triangles_examined` 参考循环计数。真实工作
量另存 `work_log`，实现版本在外部遥测和实验报告中标识；不把旧兼容计数
冒充新版实际枚举数。关闭遥测时仍执行相同预筛。

English scope: The necessary-condition prefilter preserves complete saved
outputs on the declared corpus and reduces actual triple enumeration. The two
paired repetitions do not establish a stable end-to-end runtime improvement.
This is an implementation optimization, not a new completeness result.

## 2. 比较范围与等价结果

计算前冻结6个直接归档输入：10月1日生产manifest／report／artifact-check，
以及10月3日支持扫描manifest／report／check。两组来源互相绑定；支持扫描
中的1,846份条件诊断拆为88个按图输入分片，最终逐正文与父归档比较。

| 检查对象 | 固定范围 | 本轮结果 |
|---|---:|---|
| 图记录 | 537，其中488准入 | 全部覆盖，保留49个旧几何排除 |
| 完整生产场景 | 975 | 新旧每次完整返回均等于已审计旧归档 |
| 条件诊断 | 1,846 | 新旧每次完整条件返回均等于旧归档 |
| 规则案例引用 | 6,120 | 完整证据等价，独立证书与工作量检查全部通过 |

49个旧排除仍为12个导出问题、37个几何审计问题，没有挑选更有利的输入。
975个场景包括相关历史前缀和锚点模式，不能当作975个独立图或新盲测样本。

比较覆盖阶段document、域、关系矩阵、条件EQ、证书、统计、事件、落名
承诺和最终颜色，不只比较终末结果。由完整相等继承旧归档的975完成、
4,067次安全实际提交以及当前状态支持普查结论；本轮没有新增oracle搜索，
也没有重跑旧完整生产轨迹审计或711,728份原始精确证据验证。

规则案例包括旧1,512项，加上K4和8个目标EQ提升构形，交叉4个q、8种邻居
排除掩码及16种目标域，新增4,608项。它穷举这组预声明的门槛／目标域模式，
不是任意图、任意域、任意EQ分区或全部可达状态；不同声明引用可以有相同
字面输入。共2,412个证书引用通过独立核验。本轮未新增全赋值延拓枚举。

## 3. 实际减少了多少工作

以下均为每项输入执行一次的等价工作量。计时重复和计时外遥测重放不重复
加入此分母。诊断1,846项中仅原有两项实际调用三角检测器，其余先被已有
条件传播识别为冲突。

| 范围 | 检测器调用 | 旧参考三组合 | 新实际三组合 | 跳过组合 | 减少比例 |
|---|---:|---:|---:|---:|---:|
| 975个完整生产场景 | 4,067 | 1,058,850 | 542,199 | 516,651 | 48.794% |
| 1,846个条件诊断 | 2 | 2,544 | 601 | 1,943 | 76.376% |
| 6,120个规则案例 | 6,120 | 73,236 | 2,552 | 70,684 | 96.515% |

各项均满足 `新实际枚举 + 跳过组合 = 旧参考枚举`。预筛也有自己的成本：

| 范围 | 进入预筛的颜色检查 | 预筛邻居membership检查 | 跳过的颜色检查 |
|---|---:|---:|---:|
| 完整生产 | 142,564 | 533,172 | 114,097 |
| 条件诊断 | 102 | 533 | 91 |
| 规则案例 | 92,052 | 243,900 | 89,500 |

membership只计新增预筛中的邻居域查询，不包含剩余三组合内的检查。
一次membership与一次组合尝试的成本不同，不能把次数直接相减成为时间。
本轮确认枚举减少，尚不能凭这些计数确定总时间瓶颈在哪里。

## 4. 配对计时：保留两轮相反方向

固定单worker，每个生产／条件输入做两次配对，按预声明索引奇偶选择AB或BA
起始，第二次反转。完整生产共3,900次计时调用，条件传播共7,384次；每次都
做完整归档等价比较。全项目测试先结束，正式计时期间没有并行本任务试验。

计时仅包含生产／传播调用，关闭work_log；哈希、完整比较、检查器、I/O、
遥测重放和前一次大对象释放在计时区间外。未另行预热；顺序平衡不能排除
操作系统、温度、缓存等全部影响。下表秒数是该重复内所有输入调用之和。

| 范围／重复 | 旧版秒 | 新版秒 | 新／旧 | 新版相对变化 |
|---|---:|---:|---:|---:|
| 完整生产，第1轮 | 65.612776 | 62.099838 | 0.946460 | -5.354% |
| 完整生产，第2轮 | 61.228765 | 62.960377 | 1.028281 | +2.828% |
| 条件诊断，第1轮 | 24.462987 | 24.555469 | 1.003781 | +0.378% |
| 条件诊断，第2轮 | 25.271907 | 24.987775 | 0.988757 | -1.124% |

先对每个输入取两次耗时中位数，再计算新／旧比值，最后跨输入取中位数：
完整生产为1.000369，条件诊断为0.998540，均接近不变。它与总耗时比值采用
不同权重，不能相互替代。合并两轮生产秒数得到0.985956，但此值会掩盖
重复间的相反方向，不用它宣称“稳定提速1.4%”。

因此，本轮是**输出等价且减少枚举的实现改进**，不是已经证实的整体速度
改进，也没有新增完成率、减少试探次数或数学推理覆盖的收益。

## 5. 长流程与核验边界

537个按图检查点和48个规则批次均已完成，共585个gzip文件、41,314,696字节。
正式run墙钟489.464秒（约8.16分钟），包含配对调用、比较、遥测／独立工作量
核验和分片写入；不含准备、全项目测试、最终check，也不是一次配色耗时。

沿用唯一临时文件与原子发布，不覆盖旧报告；恢复先完整重验已存图分片。
本次没有中断、恢复或失败文件，`resumed_drawings=0`。断点恢复、损坏拒绝、
失配记录由合成测试核验；没有做正式运行中断演习。中断发生在未完成图内时
仍需重做该图，不能声称做到每一步恢复。

48项新增专项测试通过。冻结版本全套 `unittest discover` 1,812项通过，
`scripts/validate.py` 同为1,812项通过，失败／错误／跳过均0。

独立清单复核不导入项目模块，重建6,120案例声明，核对290来源、6直接输入、
537图、975场景、88诊断分片及全部1,846条件项。最终标准check通过，保存
结果的等价、工作量、输入和覆盖标志均为true。工作检查器按原始真实边、EQ
类与域重建首个证书及组合排名，不调用生产器、传播器、检测器或oracle。

最终check的生产／传播／检测器重跑与oracle搜索全部为0；它校验保存的
时间字段、顺序和算术，不重新测量或证明历史时长。已有逐步可延拓与支持
证据由来源哈希和完整输出相等继承，不宣称本轮重新执行了这些精确搜索。

另一次仅使用标准库的独立汇总复核通过，未导入项目模块或运行算法：重新
构造6,120项规则声明并核对哈希，读取全部585检查点，核对975生产与1,846
条件完整输出身份、10,189条遥测记录和11,284份计时调用结果哈希，重算
report／check中的全部汇总字段，`issues=[]`。该复核不重复数学搜索或计时。

## 6. 复现入口与文件

从项目根目录，用Python 3.10+执行。首次复跑换用唯一新manifest和输出名，
避免覆盖冻结归档；下面给出新后缀示例。

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-quaternary-triangle-saturation-prefilter-rerun.json
python -X utf8 scripts/validate_quaternary_triangle_saturation_prefilter.py prepare --manifest outputs/quaternary-triangle-saturation-prefilter-manifest-rerun.json.gz
python -X utf8 scripts/validate_quaternary_triangle_saturation_prefilter.py run --manifest outputs/quaternary-triangle-saturation-prefilter-manifest-rerun.json.gz --output outputs/quaternary-triangle-saturation-prefilter-rerun.json.gz
python -X utf8 scripts/validate_quaternary_triangle_saturation_prefilter.py check --manifest outputs/quaternary-triangle-saturation-prefilter-manifest-rerun.json.gz --report outputs/quaternary-triangle-saturation-prefilter-rerun.json.gz --output outputs/quaternary-triangle-saturation-prefilter-check-rerun.json
```

重新check现有证据只需使用本轮manifest／report，并选择新的check输出名。
`run`未完成时用相同manifest和相同尚不存在的主report路径重启；已完成的
report拒绝覆盖。源文件变化会被哈希检查拒绝，需要另立冻结版本。

主要文件：

- 协议：`docs/QUATERNARY_TRIANGLE_SATURATION_PREFILTER_PROTOCOL-2026-10-03.md`
- 新实现：`scripts/quaternary_triangle_saturation_prefilter.py`、同前缀
  `contacts.py`、`low_color.py`。
- 独立检查器：`scripts/check_quaternary_triangle_saturation_prefilter.py`。
- 实验入口：`scripts/validate_quaternary_triangle_saturation_prefilter.py`。
- 冻结清单：`outputs/quaternary-triangle-saturation-prefilter-manifest-2026-10-03.json.gz`。
- 主报告：`outputs/quaternary-triangle-saturation-prefilter-2026-10-03.json.gz`。
- 最终检查、独立清单：同前缀 `check-2026-10-03.json`、`inventory-review-2026-10-03.json`。
- 独立汇总：同前缀 `summary-review-2026-10-03.json`。
- 综合验证：`outputs/validation-quaternary-triangle-saturation-prefilter-2026-10-03.json`。

| 文件简称 | SHA-256 |
|---|---|
| manifest | `3657ddd23afc353609aacf9c9522ecd944b7eca5944f85e8ff9ba50e434296b6` |
| report | `c915d3d643afc02f21797a92a8669828c4db05499834c18d5cb2089ded64b332` |
| check | `f54316e6d354e63e6a5940e33315a1647e5df301ee6e1994726f6e41e9f7f2f6` |
| inventory-review | `67879a9b175d5268ed39ad15a2705e969e3ea80c44e3e857d9a612ad697b702b` |
| summary-review | `a785f64a0aae06230b6cbd519d7327b2d3f20fdcf7cd2a89fc894940497ec6db` |
| 综合验证 | `de3758570becc90c7ae7654d18fde3a06bcb1e82bb92969edd81c79ab5ec005f` |

## 7. 下一步

优先做单独的性能剖析（profiling），先测完整生产调用中各组件的累计成本、
调用次数以及图规模分层。预声明样本和测量方式，保留未剖析的配对计时为
外部对照；剖析器本身有开销，不能将其时间直接混入当前速度比较。

根据实测占比再决定是否缓存拓扑、减少重复构造或继续优化三角检查。
这些目前都是候选方向，不能先假定某一组件是主要瓶颈。任何缓存须保留
真实邻接、side顺序、当前EQ分区及必要域／条件前提，重新冻结后比较完整
轨迹与实际耗时；不能只以省去某个循环为验收标准。

数学上，持久矩阵中的1,846项无联合支持色对仍在，但条件传播仍全部识别；
本轮没有学习新的持久禁配关系。一般安全落名、任意改选后的路径安全、
结构覆盖和完备性仍未证明。当前无需用户补图、手工运行或修复环境。
