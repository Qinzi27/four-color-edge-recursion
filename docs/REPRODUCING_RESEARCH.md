# 外部复现：算法、完整实验、证书与图件

本指南包含截至 2026-09-20 的研究记录。发起思路属于 Qinzi27。
这里公开的是可复现的候选方法、成功和负结果，不是一份新的四色定理证明。

## 最新补充：内起点顺序与最少颜色控制（2026-09-20）

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

## 1. 先区分四种工作

| 工作 | 入口 | 能说明什么 |
| --- | --- | --- |
| 给自己画的一张图标色 | `scripts/name_peer_batch_map.py` | 固定 v4 规则的一次成功或冲突 |
| 重新运行完整样本库 | `scripts/validate_peer_batches_full.py` | 同一规则在 7069 个去重输入上的实际结果 |
| 审计已存完整实验 | `scripts/audit_peer_batches_full.py` | 统计、输入、分片、色名与推导证书是否一致 |
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

## 3. 最短单图复现

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
2026-09-19 研究快照记录为 536 项 Python 测试和 107 项 Node 测试通过；
后续发布维护可能增加测试，应看当前实际输出，不硬编码这个数目。

完整测试导入 Pillow，但绘图单元测试用记录画布核对坐标，不实际加载 Windows 的 `msyh.ttc`。
仅跑软件测试不需要安装这个字体。真正重新生成 PNG 时才需要可用的中文字体。

部分有限数学单元测试使用小图枚举作为独立 oracle；不能据此说生产 v4 隐藏枚举了整张地图配色。

## 5. 新版完整运行与独立审计

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
- 文档中有几份较大的历史 JSON。网页不能预览全文时应克隆或下载 Raw 文件；不要把网页预览文本复制成替代输入。
- 大图 PNG 是便于阅读的预览，SVG 保留精确矢量线，图件 `manifest.json` 还保留输入、色名、坐标与哈希。

“字节不一致”首先意味着无法确认是原来那份证据，不等于发现了数学反例。
新运行的时间戳、计时和压缩文件哈希也不必与旧运行相同；需要匹配的是声明输入、规则、几何、决策与被检查结论。

Git checkout 还可检查当前索引是否逐字节保留证据及冻结的30份源码：

```text
python -X utf8 scripts/check_publication_archive.py --output outputs/my-publication-check.json
```

此检查需要 Git 索引（不能仅有下载后解压的 ZIP），不重新求解数学问题，也不是秘密扫描。
它核对索引中的全部 `outputs/`、`docs/figures/` 和 v4 声明的源码；
自行修改或暂存新文件后应重新检查，不把先前报告当成新状态的保证。

历史结果按各次实验当时的规则和统计口径引用，具体复现与源码哈希核验范围依各 runner/audit 的声明。
部分历史同名脚本后来经过修订，当前 checkout 不保证能逐字节重算所有历史版本；
最新发布索引检查仅绑定 v4 的 30 份冻结源码及索引证据字节，不代表每个历史版本都已重新运行或其原源码哈希均与当前同名文件相同。

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

最新 v4 的完整实验、负结果、独立证书和隐含异名引理属于 Python 研究部分；
**此次整理公开研究材料，不等于网页默认算法已经升级到 v4，也不等于隐含异名模板已经接入 v4。**
相关状态应以 [v4 结果报告](PEER_BATCH_RESULTS-2026-09-19.md)和[隐含异名引理](IMPLICIT_INEQUALITY-2026-09-19.md)为准。
