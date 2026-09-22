# AGENTS.md

This is a reproducible mathematical research project about recursive edge-side
descriptions of plane-map four-coloring. The initiating idea belongs to Qinzi27.

- Write explanatory comments and docstrings in all scripts.
- Keep face identifiers, face colors, primal edges, dual edges, and split-history
  nodes distinct. A dangling edge does not split a face.
- A bridge has the same face on both sides and therefore color difference zero.
  Nowhere-zero flow statements require the explicitly stated bridgeless scope.
- Specify whether a closed walk belongs to the primal graph or the dual graph.
- Separate proved elementary/known results, conjectures, and finite experiments.
  Do not call this repository a new proof of the Four-Color Theorem.
- Preserve the original explanatory fragment and all user-authored work.
- Use Python 3.10+ and the standard library for the core; avoid unnecessary dependencies.
- Save reproducible generated validation reports in outputs/ and figures in docs/figures/.
- Keep random seeds, graph families, size bounds, and independent oracle results explicit.
- Before changing mathematical logic, explain the reason; keep changes small and reviewable.
- Run python -m unittest discover -s tests -v and python scripts/validate.py.
- Do not publish private machine paths, credentials, memory files, or conversation logs.
- Do not add or change a reuse license without the maintainer's authorization.

## 有限检验规范（2026-09-21，后续检验默认遵循）

有限检验用于核查方法的可靠性、可延拓性、适用范围和运行成本。按以下三层
分别设计实验与报告；不能用最终完成率替代中间推理的检查。

1. **规则可靠性（soundness）**：在预声明的小规模构形上枚举全部合法四名
   赋值，核对每条同名／异名推导及传播删减保留所有满足原约束与当前承诺的
   合法解。区分已证明的规则、规则实现的有限核验，以及尚未证明的完备性。
2. **每步可延拓性（extendibility）**：固定当前输入图 G，以 S 表示初始化
   锚点及累计落名承诺，E_G(S) 表示满足真实共边约束和 S 的全部合法四色解。
   先独立检查初始化是否有解；每次主动提交 v=c 前后检查
   `E_G(S) != empty => E_G(S union {v=c}) != empty`。优先定位第一次从有解
   变为无解的决定，记录选择依据、候选域、承诺前的完整解见证，以及承诺后
   的精确无解核查证据。未找到结构反证仅为 `inconclusive`，不能当作可延拓。
3. **完整流程**：冻结同一算法版本，在预声明的图族、规模及合法构造顺序上
   运行，检查完整配色、每条历史的全部前缀、终止与资源成本。编号、嵌入或
   历史变化的对照应保留算法要求的合法输入条件；超出范围的输入另列。

执行与证据要求：

- 独立精确求解器（oracle）只作离线核查，不向被测方法提供颜色、目标解、
  下一步选择或失败救援。独立检查直接依据原始真实邻接及承诺，避免复用被测
  推理核心造成共同错误；说明共享解析／几何代码及其独立核验范围。
- 区分穷举与抽样：声明穷举的有限对象、大小上限、完整生成依据、去重标准、
  颜色对称性处理及状态可达性。任意合法预着色与该算法实际可达状态分开；
  只发现前者的障碍，不能直接断言后者必失败。不可延拓的边界着色不否定
  整张图可四色；当前承诺导致的 `conflict` 也不否定整张图可四色。
- 在计算前固定输入清单、种子、策略和资源上限，保存源码／输入哈希、独立
  核查状态及可重放证据。超时、资源耗尽或核查未完成应记为未知／未完成，
  不能记作无解或通过。输出使用唯一新文件名，不覆盖冻结报告。
- 新失败保留原始输入，再缩减为仍符合声明范围的可重放实例；区分包含极小
  与全局最小。若只得到抽象约束反例，明确其几何／构造历史可实现性是否已证。
  修正规则后另立版本，分别报告修复、新退步、持续失败和未完成，不拼接版本
  成功集合。用失败实例改规则后，在未参与开发的输入上复核；同族新种子及
  相关历史前缀不能当作独立图族或普遍成功概率。失败结论限定到具体版本与
  规则，不直接等同于否定尚未完全形式化的研究思路。
- 经典 633 构形仅作为后续专项检验素材。接入前记录来源／版本／哈希，保留
  嵌入、度数、边界环及相关边界着色条件，明确与本项目面、线侧和母线历史的
  对应。仅对邻接子模块的检查不代表完整方法已通过；可约性也不等于任意边界
  配色都可原样延拓。通过全部构形不自动证明本算法完备，还需相应的覆盖性、
  操作正确性、状态衔接与终止论证。

近期优先顺序：固定当前结构重启版，先实施小规模合法输入的穷举与逐步
可延拓核查，寻找“未找到反证却提交错误颜色”的证据；再扩展不同生成家族
和规模，并评估经典构形的适配。具体执行入口与当轮状态见 `NEXT_STEP.md`。
