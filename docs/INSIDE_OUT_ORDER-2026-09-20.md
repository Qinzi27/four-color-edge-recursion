# 从一个最内闭环向外计算：顺序优势与接口范围

2026-09-20。Qinzi27 澄清：提议改变的是计算起点与扩展顺序，先处理一个最内侧的可闭环系统，再向外推进；没有要求永久冻结内圈的颜色或层标记。不能用“冻结内圈失败”的反例代替检验这条顺序建议。

## 1. 顺序确实可能带来改善

考虑两组互不相交的嵌套双圈。O 是无界外面；L₂、R₂ 是两个最内面；L₁、R₁ 是各自的环带。面相邻图（对偶约束图）为

```text
L₂ — L₁ — O — R₁ — R₂
```

这是同一张最终地图。颜色固定为四个可重命名符号，算法每次加入一个相邻面，保留全部可行的当前边界状态，随后消去已经不再接触未处理面的变量。只改变起点与广度优先顺序：

| 起点与顺序 | 每步需保留的边界面数 | 峰值 | 实际边界赋值数峰值 | 整体换色后的状态类型峰值 |
|---|---|---:|---:|---:|
| 外面：O,L₁,R₁,L₂,R₂ | 1,2,2,1,0 | 2 | 16 | 2 |
| 一个最内面：L₂,L₁,O,R₁,R₂ | 1,1,1,1,0 | 1 | 4 | 1 |

外面起步同时打开左右两个方向，中途须记住 L₁、R₁ 同色或异色。最内面起步沿链前进，始终只把一个面交给下一步。这里的改善是实际边界宽度与状态数，不只是换了一套名称；最终都能完成，最少颜色数仍为 2。

这里“从一个最内面开始”表示选一个内侧起点沿邻接扩展。它不等于同时先处理所有最内面；后者也可能打开多个未完成接口。一般地图也可能分支、存在多个不可比内圈，不能假定都有唯一的线性内外顺序。

## 2. 保证来自完整接口，不来自方向本身

已处理面集为 P 时，定义

\[
B(P)=\{f\in P: f\text{ 邻接至少一个未处理面}\}.
\]

保留 B(P) 上所有能够扩张到已处理内部的合法赋色。加入下一个面时检验它与已处理邻面的不等色约束；随后将不再接触未处理部分的面投影消去。由于这些被消去的面不会再获得新邻接约束，内部可行性可由边界状态完整代表。

由逐步加入与投影的归纳，这个精确校验对任何处理顺序都完整；次序改变中间的最大边界宽度及状态数量，不改变最终图是否可着色。这是 [FOUNDATIONS.md §5](FOUNDATIONS.md#5-递归边界关系及粘合定理) 已有精确边界关系的顺序应用，不是新的四色存在性证明。

该小核验是诊断顺序影响的精确基线，未替换用户的线优先方法或网页规则。若只留下一个贪心状态，仍须另证它可向外延伸；不能从完整状态校验的保证推出单状态算法完整。

单独规定外面颜色为 1 或 0，只是全局色名的规范化，不强迫第一步处理外面。可先用最内面为参考，最后统一重命名。但旧算法若另外依赖外面邻接所有内部面的结构假设，这个假设不能作为色名规范化自动迁移。

## 3. 内圈可以保留什么

在两个嵌套圈加三条径向连接的例子中，内面可以一直保持颜色 1；三个环带扇区最终分别用 2、3、4。因此内圈的外侧描述从统一的 `(1,2)` 变为各段的 `(1,2)`、`(1,3)`、`(1,4)`。母线身份与内面颜色可保留，当前分段的外侧描述随新增面更新。

如果额外要求内圈所有边始终属于同一个二元层 A，则三角棱柱提供失败例；它只否定这个附加冻结条件，不否定本次顺序提议。直接枚举已确认：包含整个内圈的偶 A 只有“内圈”与“内外两圈”两种，两者均不能补第二层；但固定内面为 0、一个背景后代扇区为 1，仍有 `(内,外,S₀,S₁,S₂)=(0,0,1,2,3)` 与 `(0,0,1,3,2)` 两个合法解。

## 4. 更贴近线优先表示的小接口

也可以在原图上切开实际对外连接边，把它们作为有序端口。先处理桥的零色差；对于非零 `F₂²` 色差的合法内部解，所有端口标签 XOR 为 0。

| 非零端口数 | 总 XOR 为 0 的标签串数 | 整体置换三标签后的类型数 |
|---:|---:|---:|
| 1 | 0 | 0 |
| 2 | 3 | 1：aa |
| 3 | 6 | 1：abc |
| 4 | 21 | 4：aaaa、aabb、abab、abba |

因此，若两块已经各自存在合法内部解、全部共同接口恰是两条或三条切边，整体置换一块的三种非零色差就可对齐接口。这里允许整体换名或二元层组合，不能承诺第一层的边成员身份不变。这个条件数的是原图对外通道，不是圈的边数；也不保证所有图都能拆成这种小接口。

四端口开始，端口的同名关系不能只用一个总 XOR 或一个 rank 表示。三正则图中的相应接口状态与奇偶引理是已有 multipole 理论的一部分，见 Fiol & Vilaltella (2015), *Some results on the structure of multipoles in the study of snarks*, §2–3，[原文](https://www.combinatorics.org/ojs/index.php/eljc/article/download/v22i1p45/pdf/)。本文的流表述另由逐顶点 XOR 相加直接得到；不把非三正则图中的流说成 Tait 三边着色。

## 5. 一个必须区分的控制实验

另外测试了在完整最终图上只把初始 A 从外圈换为内圈，同时保持旧 q 修复规则不变：原八图、wheel 轮缘 3–9、prism 圈长 3–7，共 20 图、83 个初始 A、三种候选族，249 次运行均完成。在 189 个内外配对中，净改动相同 72 对、内起点更多 117 对、内起点更少 0 对。

这不是“从内向外逐层计算”的完整实现：q 从第一步就计算完整图上的全部外部奇点，候选也可立即选外圈。它只检验换初始圈，不公平代表用户澄清后的顺序。因此不将其作为否定内向外计算的证据。第 1 节才是保持同一状态算法、只改处理顺序的直接对照。

## 6. 小例子的可重复核验

本轮只做文档补充与只读计算，没有改动既有求解器。以下代码在仓库根目录执行，可复现第 1 节全部中间状态数；代码维护完整边界赋色，整体换名仅用于结果统计。

```python
from fourcolor.coloring import canonical_colors

vertices = tuple(range(5))  # L2, L1, O, R1, R2
edges = ((0, 1), (1, 2), (2, 3), (3, 4))
adj = {v: set() for v in vertices}
for a, b in edges:
    adj[a].add(b)
    adj[b].add(a)

def trace(order):
    """Keep all exposed-face states; forget only fully processed interfaces."""
    done, boundary, states = set(), (), {()}
    rows = []
    for v in order:
        # A processed neighbor of v must still be exposed before v is added.
        assert adj[v] & done <= set(boundary)
        next_done = done | {v}
        next_boundary = tuple(w for w in vertices
                              if w in next_done and adj[w] - next_done)
        next_states = set()
        for values in states:
            old = dict(zip(boundary, values))
            for color in range(4):
                if any(old[u] == color for u in adj[v] & done):
                    continue
                assignment = {**old, v: color}
                next_states.add(tuple(assignment[w] for w in next_boundary))
        rows.append((len(next_boundary), len(next_states),
                     len({canonical_colors(s) for s in next_states})))
        done, boundary, states = next_done, next_boundary, next_states
    return rows

print(trace((2, 1, 3, 0, 4)))  # (width, labeled states, rename classes)
print(trace((0, 1, 2, 3, 4)))
```

输出分别为 `[(1,4,1),(2,12,1),(2,16,2),(1,4,1),(0,1,1)]` 与 `[(1,4,1),(1,4,1),(1,4,1),(1,4,1),(0,1,1)]`。这只是一个精确正例，不是一般平均性能结论。

接下来可按相同地图、相同接口规则，成对比较外起点和各最内起点的最大活动边界、接口类型数、累计转移量与局部修复量。应把“内侧优先”当成待检验的顺序原则，将实际接口宽度作为评价量。

## English summary

The proposal changes the computation order, without requiring the innermost contour to remain permanently frozen. For the same map of two disjoint nested-circle pairs, an exact frontier computation starting at an innermost face reduces peak frontier size from two faces to one, labeled states from sixteen to four, and color-permutation classes from two to one. Complete boundary relations preserve final feasibility under either order, while intermediate complexity may differ. This supports testing inside-out orderings, but does not establish a universally superior ordering or a complete greedy coloring method.

论证审查工作流沿用 [上一轮说明](CIRCLE_LAYER_REPAIR-2026-09-20.md) 中记录的 Scientific Agent Skills 来源；它不是上述数学结论的证据。
