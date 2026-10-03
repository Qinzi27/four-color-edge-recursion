# 完整生产性能剖析：优先检查嵌套证据深复制（2026-10-03）

全量剖析、标准保存复核与独立汇总审查均已完成。当前明确的优化目标是传播结果的重复深复制；
本轮没有修改配色算法，也没有宣称获得新的加速或数学推理能力。成果本地保存，
未提交或推送。

## 1. 主要发现

在全部975个生产场景中，标准库 `copy.py` 的自身耗时合计167.431秒，占
剖析函数自身总量296.514秒的 **56.47%**。关系运算模块
`fourcolor/relation_names.py` 自身耗时49.637秒，占 **16.74%**。

三角预筛入口 `find_triangle_saturations_prefilter` 的自身耗时0.419秒，
包含子调用的累计耗时3.810秒，仅占同一剖析总量的 **1.28%**。上一轮减少
48.8%三角枚举却未呈现稳定整体提速，与这里观察到的较小时间占比相符；
这是一项支持性解释，不是对上一轮时间波动的因果证明。

本轮未开启剖析的生产调用合计103.730秒，开启剖析为296.569秒，比值2.859。
剖析器对高频小调用有明显扰动，因此下述剖析占比不能直接当作普通运行
占比，更不能承诺删除某段代码后会加速相同百分比。本轮与上一轮的计时
并非同一次受控新旧对照，不据此认定预筛版变快或变慢。

English scope: Full-corpus profiling identifies nested evidence copying as
the leading diagnostic hotspot. Profiled proportions are not unprofiled
runtime shares or promised speedups. No producer logic was changed in this run.

## 2. 冻结对象与结果一致性

- 旧290项源码与协议逐字节保留，新增剖析统计模块／测试、实验入口／测试、
  协议共5项，冻结295项来源及3个直接归档输入。
- 537条图记录、488条准入、975个生产场景全部覆盖；49项旧几何排除仍为
  12项导出失败、37项几何审计失败，不赋予虚构的生产时间。
- 每场景同一预筛实现普通调用与剖析调用各一次，共1,950次完整生产调用。
  按全局scene index奇偶换序，普通先488场景、剖析先487场景，没有另行预热。
- 两次完整返回均逐字段等于对应旧归档，含输入、学习、阶段、矩阵、域、
  证书、事件、承诺及最终颜色；无输出差异、执行错误或未完成项。
- 新oracle搜索为0。固定原图、初始化和承诺序列的既有安全证据由完整输出
  相等继承，本轮没有重新核验711,728份原始精确记录，也没有重跑1,846个
  条件诊断或6,120个规则案例。一般可延拓性与完备性结论不变。

运行环境为CPython 3.12.14、Windows AMD64。`cProfile` 开启subcalls与builtins，
使用默认timer；外部wall time使用 `perf_counter`。输入复制、上一输出释放、
比较、摘要计算、统计导出和I/O均在生产计时外。算法内部已有复制仍属于被测
生产成本。剖析wall包含极小的enable／disable控制成本。

## 3. 按原始side规模分层

side范围为2–28，直接取 `original_input.sides`，不是EQ合并后的类数。
抽象控制的side不另称几何面。同图锚点场景与历史前缀有关联，不作为独立
图样本，也不计算普遍性能置信区间。

| 原始side数 | 图记录 | 场景 | 普通调用秒 | 剖析调用秒 | 剖析／普通 |
|---|---:|---:|---:|---:|---:|
| 1–4 | 207 | 414 | 4.503094 | 14.198310 | 3.1530 |
| 5–8 | 155 | 310 | 12.317152 | 42.869476 | 3.4805 |
| 9–12 | 81 | 161 | 28.555212 | 89.800930 | 3.1448 |
| 13+ | 45 | 90 | 58.354808 | 149.699818 | 2.5653 |
| 合计 | 488 | 975 | 103.730265 | 296.568534 | 2.8590 |

13+层仅90场景，占9.23%，却占本轮普通生产调用总时间的56.26%。因此后续
优化必须分别看大规模层与小规模层，不能只报告全体平均值。

## 4. 自身时间与累计时间分开解释

下面是互不重叠的模块自身时间，分母为全部导出函数自身时间296.513605秒。
内建函数单列；其中一部分由复制或关系操作调用，不应再重复加入其他模块
的累计时间来构造“总占比”。

| 模块 | 自身秒 | 自身占比 |
|---|---:|---:|
| 标准库copy.py | 167.43115 | 56.47% |
| 内建函数 | 57.02921 | 19.23% |
| fourcolor/relation_names.py | 49.63738 | 16.74% |
| scripts/quaternary_contact_model.py | 6.75098 | 2.28% |
| fourcolor/structural_name_relations.py | 4.00911 | 1.35% |
| scripts/quaternary_logical_neq_contacts.py | 3.72987 | 1.26% |

copy模块自身占比在四个规模层分别为65.12%、64.21%、61.88%、50.18%；
relation_names模块分别为2.34%、6.80%、9.83%、25.10%。复制在各层都突出，
关系运算的相对成本在较大规模层更明显。

函数层面的关键记录：

| 函数 | primitive calls | total calls | 自身秒 | 累计秒 |
|---|---:|---:|---:|---:|
| copy.deepcopy | 262,302 | 139,510,407 | 106.847988 | 217.773659 |
| relation_names.compose | 19,578,298 | 19,578,298 | 34.281962 | 34.281962 |
| relation_names.relation_closure | 5,046 | 5,046 | 4.111887 | 48.551177 |
| find_triangle_saturations_prefilter | 4,067 | 4,067 | 0.419378 | 3.809532 |

primitive calls排除递归重入，total calls包含递归；不能把139,510,407次复制
函数调用解释成同数量的图、状态或完整对象副本。全部函数调用合计944,010,240，
同样只是剖析器记录的Python／内建调用计数。deepcopy的累计秒包括它调用的
dict/list复制及内建操作，与这些函数的累计秒重叠，不能相加。

保留了全部函数和caller边。cProfile函数总表采用 `(cc,nc,tt,ct)`，caller边
前两项实际相反，为 `(nc,cc,tt,ct)`；真实递归合成测试确认了这一点。
每场景另存剖析器snapshot的函数数、总调用数、primitive调用数与total_tt，
与导出行逐项核对，防止漏记函数后仍通过。时间和允许1e-9相对／绝对浮点
容差，自身和不得超过对应wall加1e-6秒；这些只核算术，不证明历史时钟值。

## 5. 定位到可改动的具体位置

按deepcopy的直接调用者看，较大累计成本分别来自：

| 直接调用者 | deepcopy直接调用数 | 该调用边累计秒 |
|---|---:|---:|
| propagate_prefilter_contacts | 25,210 | 113.965722 |
| propagate_diamond_contacts | 25,234 | 56.416565 |
| propagate_wheel_contacts | 5,046 | 28.048438 |

这是函数级caller记录，不是行级剖析。预筛层113.966秒涵盖其各个deepcopy
调用点，不能全部归因于某一行，亦不能直接作为下一次优化可节省的时间。

源码中可见多层相似模式：取得下层完整结果base，深复制一份存入rounds，
再深复制最后一轮结果作为顶层outcome。结果内还嵌套下层轮次和证据，因此
外层复制需要再次遍历已经很大的嵌套对象。

下一轮优先只试一个小变体：在
`scripts/quaternary_triangle_saturation_prefilter_contacts.py:40` 保存本轮
历史时接管刚返回且随后只读的base，省去 `deepcopy(base)`。本层在该点
之后只读取base的域，修改的是独立work；下轮获得另一个新base。

必须保留：

1. 原始输入与工作副本的隔离，以及每轮document快照。
2. 最后顶层outcome与rounds内结果之间的独立副本。
3. 跨轮、跨阶段、跨运行及外部调用者之间的可变对象隔离。

这不是把所有deepcopy换成浅拷贝。首轮先不同时修改diamond层、wheel层或
关系compose，便于把收益和退步归于一个明确变化。新版本须先通过别名／
快照污染测试，再冻结并比较全部975生产、1,846条件诊断、规则回归与完整
返回，同时重新做无剖析器的配对计时。实际节省仍未知，不能预报56%提速。

最后那次复制尤其不能直接删掉：若顶层outcome就是最后一轮对象，再把包含
该对象的rounds装入outcome，会形成循环引用。改成浅复制虽避开这层循环，
仍可能让顶层域、关系和历史快照共享可变对象。下一轮测试必须覆盖这些区别。

## 6. 验证、文件与复现

21项专项测试通过。冻结源码的全套1,833项单元测试通过（215.750秒），
综合验证同为1,833项通过（210.971秒），失败／错误／跳过均0。开发期间
为补齐统计覆盖校验而中断的较早测试日志保留，不计为一次通过。

独立清单审计通过：标准库逐项检查295来源、旧290继承、3直接输入、537
父检查点、975原始输入／结果哈希、geometry逐值一致及scene index 0–974。
标准保存check通过，所有完整输出相等、剖析算术与覆盖标志均为true；
生产与oracle重跑数为0。

另一次不导入项目模块的标准库独立汇总审查也通过：核对537新检查点、975
完整envelope、1,950份计时调用输出哈希与975份snapshot总量；逐项解析
184,793条函数行及401,583条caller边，重算全局及四个规模层的全部函数、
调用边、模块分组与排名，均与主报告一致，issues为空。未运行算法或剖析，
未重测历史时钟，未重验旧oracle。

537份按图检查点共30,464,336压缩字节。正式run主循环墙钟584.919秒，包含
两种生产调用、完整比较、统计导出／检查及I/O；不含入口的来源核验、准备、
全项目测试或最终check。无中断、恢复或失败文件，resumed_drawings=0。
恢复与损坏拒绝通过合成测试核验，没有进行正式中断演习。

主要文件均使用 `quaternary-triangle-saturation-profile` 前缀：

- 协议：`docs/QUATERNARY_TRIANGLE_SATURATION_PROFILE_PROTOCOL-2026-10-03.md`。
- 剖析数据转换：`scripts/quaternary_profile_stats.py`。
- 入口：`scripts/validate_quaternary_triangle_saturation_profile.py`。
- 冻结：`outputs/quaternary-triangle-saturation-profile-manifest-2026-10-03.json.gz`。
- 主报告：`outputs/quaternary-triangle-saturation-profile-2026-10-03.json.gz`。
- 保存check与独立清单：同前缀 `check-2026-10-03.json`、
  `inventory-review-2026-10-03.json`。
- 独立汇总：同前缀 `summary-review-2026-10-03.json`。
- 综合验证：`outputs/validation-quaternary-triangle-saturation-profile-final-2026-10-03.json`。

| 文件 | SHA-256 |
|---|---|
| manifest | `bbd3e39556880cea8080527865fcfaa262ae4917969750b8fa1e3fadf6929bc5` |
| report | `62e9f3f953fbf3812c4232b68aea372022681ff0cb32e604b7ac8437787e936d` |
| check | `218e4e6751d170ebf8a80f0bdb5158c26afe188b3a1fb6854ca43e9b2e1f5026` |
| inventory-review | `6ba6fb97838b5c73fe0ebeb0b0caea0f4dec2d3fa4f98d7490eb962685f2694a` |
| summary-review | `67ad420a6039a642e8fd545971c7b80390ce98db1b45fb3150b23b67c9d0e826` |

在项目根目录使用Python 3.10+。复跑须选唯一新输出名，示例后缀不能覆盖
已经存在的文件：

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/validate.py --output outputs/validation-profile-rerun.json
python -X utf8 scripts/validate_quaternary_triangle_saturation_profile.py prepare --manifest outputs/profile-manifest-rerun.json.gz
python -X utf8 scripts/validate_quaternary_triangle_saturation_profile.py run --manifest outputs/profile-manifest-rerun.json.gz --output outputs/profile-rerun.json.gz
python -X utf8 scripts/validate_quaternary_triangle_saturation_profile.py check --manifest outputs/profile-manifest-rerun.json.gz --report outputs/profile-rerun.json.gz --output outputs/profile-check-rerun.json
```

对现有结果做保存复核时，用本轮manifest／report与一个新的check文件名即可。
剖析函数标识已去除私有机器路径；没有发布包含本地路径的原始二进制profile。
