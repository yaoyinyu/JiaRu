# 运行时半径平滑接入方案（2026-11-17）

状态：**S1—S5、S7 已执行；S6 部分执行**（2026-11-17）。已落地代码默认关闭，生产 manifest 未声明该字段。S6 的构建 + 重启 + 部署校验通过；首次实测新增耗时 P95 4.72ms 超 3ms 预算（L3 不通过）。已按「质量最高」原则采纳 §10 的 C+（闭式 RMS 只剪枝、真实卷积裁决，不做单调性假设）：复测 **P95 2.20ms 达标**，mask 结果与优化前逐位相同。开关仍默认关闭，生产 manifest 未声明该字段。L1／L2 已通过；实际 fixture 由 32 枚改为 16 枚（188,653 字节，符合 §9 风险 9 的备选口径）。

## 1. 目标与非目标

**目标**
- 把循环093已验证的算子（RMS 有界循环高斯 + 面积补偿）落到浏览器运行时，使模型路径的输出 mask 与 Python 侧复现一致（训练域 248→420）。
- 全部改动**默认关闭**：manifest 未声明 `radiusSmoothing` 时，输出与当前版本逐位一致。

**非目标**
- 不改权重、不训练、不导出 ONNX、不动 Stage A/B 模型文件。
- 不改生产 manifest（属发布身份变更，受 PRODUCT HOLD 约束）。
- 不改门、不改真值、不改评测口径。
- 不做独立来源重标定（用户表示新图后补）。

## 2. 事实基础（已核）

| 项 | 位置/事实 |
|---|---|
| 解码 | `src/lib/nail-texture-recognition/radial-field.ts:160` `radialMaskLogits`：`logits[i] = fround(radius[bins[i]] − distance[i])`，阈值 0 |
| 调用点 | `src/lib/nail-texture-recognition/radial-refine.ts:439` `const logits = radialMaskLogits(radiusValues, ...)`；`:489` `radialCoverageAlpha(radiusValues, ...)` 复用同一半径向量 |
| 配置 | `src/lib/nail-texture-recognition/types.ts:150` `NailTextureStage2Manifest`（可选字段，缺省即旧行为） |
| 配置来源 | `recognize.ts:136` `stage2Config: manifest.stage2` |
| 现有关键测试 | `tests/nail-texture-radial-field.test.ts`、`tests/nail-texture-radial-fixture.test.ts`、`tests/nail-texture-model-runtime.test.ts`、`tests/nail-texture-mask-pipeline.test.ts` |
| 证据 | `model/reports/cycle093-bias-neutral-smoothing-v1/report.json`（`710201aa…`）：`adaptive0.7+ac` = 420 甲，meanMaskIoU 0.98804、meanF1 0.99004、面积偏置相对对照 +0.034 |

## 3. 实施步骤

| 步 | 内容 | 产物 | 审批 |
|---|---|---|---|
| S0 | 冻结基线：记录当前 `BUILD_ID`、`git rev-parse HEAD`、现网 8 页面状态、`radial-refine` 现有单测通过数 | 基线快照写入 dev-log | 本方案批准 |
| S1 | 新增纯函数 `smoothRadiusVector(radius, bins, distance, options)`：RMS 有界选核（网格 0.5—8px 弧长，τ=0.7）、面积补偿（目标=平滑前 `logits≥0` 计数，`δ=(A_target−A)/P` 后重解一次） | `src/lib/nail-texture-recognition/radial-smoothing.ts`（新文件，无副作用、可单测） | 本方案批准 |
| S2 | `radial-refine.ts` 接入：`radiusValues` → `smoothRadiusVector` → 复用平滑后的向量给 `radialMaskLogits` 与 `radialCoverageAlpha`（两者必须同源，否则 mask 与覆盖率不一致） | 修改 1 处调用链 | 本方案批准（默认关） |
| S3 | 类型与配置：`NailTextureStage2Manifest` 增可选 `radiusSmoothing`（`mode: "none" | "rms-bounded-gaussian"`、`deviationRmsArcPixels`、`gridArcPixels`、`areaCompensation`）；缺省=旧行为 | `types.ts` + 校验/默认值 | 本方案批准 |
| S4 | 单测：常数半径不变；面积补偿后面积相对误差 <0.5%；τ 界内选核单调；2048 bin 循环边界；`mode:"none"` 与旧实现逐位一致 | `tests/nail-texture-radius-smoothing.test.ts` | 本方案批准 |
| S5 | 跨语言对拍：从 634 冻结 mask 导出 32 枚代表性半径向量 + Python 参考 mask 指纹（≤300KB fixture），TS 解码须与其**逐位一致** | `tests/fixtures/` + `tests/nail-texture-radius-smoothing-parity.test.ts` | 本方案批准 |
| S6 | 端到端：本地 `next build --webpack` + 12 图走 NailArtPicker，开关开/关各一次；记录 mask 差异、耗时 P95 增量、内存 | 验证记录（dev-log） | **已批准并部分执行（2026-11-17）**：构建 + 重启 + 部署校验通过；**图像级开/关对比未做**（需在 `public/models/**` 写入含 `radiusSmoothing` 的 manifest，属 §5 禁写）；新增耗时 P95 4.72ms **超 3ms 预算**，见 §8 L3 |
| S7 | 文档：白皮书登记可选接口（不改版本号除非实质变更）；dev-log 记录；`docs/agent-rules` 无需改 | 文档 | 本方案批准 |

## 4. 影响范围

**代码**：新增 1 文件、修改 2 文件（`radial-refine.ts`、`types.ts`）、新增 2 测试 1 fixture。
**运行时行为**：`mode` 缺省 → 逐位不变；仅当 manifest 显式声明时改变 mask 与 coverage alpha。
**消费者**：`NailArtPicker`（模型路径）、`device-benchmark`。`/ar-tryon` 不消费该链路（已核：识别引擎引用数为 0），不受影响。
**数据**：只读冻结证据；不写 `model/reviews/`、不改真值、不产生新标注。
**发布身份**：不动 `public/models/nail-texture-seg/manifest.json`；若未来要开，属新 releaseIdentity，须另立合同并走完整发布门。
**性能**：新增 2048 点循环卷积（O(bins×kernel)）+ 一次 ROI 重解码（roiSide² 比较）。预估单实例 +1—3ms（CPU/WASM）。
**环境**：S1—S5 只需 Node；S6 需重建 `.next`（必须先把旧 `.next` 改名移开，Turbopack 仍不可用）与重启 `next start`。

## 5. 所需权限与受控边界

- 允许写：`src/lib/nail-texture-recognition/`（新增 + 2 处修改）、`tests/`、`docs/`、`dev-log/`。
- 禁止：`public/models/**`、`model/reviews/**`、任何真值/标注目录、`.env.local` 之外的配置、`deploy/`。
- 不执行：训练、ONNX 导出、云端部署、git push（除非另行指示）。

## 6. 回滚

| 级别 | 触发 | 动作 | 恢复时间 |
|---|---|---|---|
| R1 配置级 | 端到端发现问题 | manifest/测试 manifest 里 `radiusSmoothing.mode="none"` 或删除字段 | 立即，无需重建 |
| R2 代码级 | 单测/对拍失败 | `git revert` S1—S5 四个提交（或删除新文件 + 还原 2 处修改） | 分钟级 |
| R3 产物级 | S6 构建后异常 | 还原上一份 `.next`（S0 已备份 `BUILD_ID` 与目录）、重启 `next start` | 分钟级 |
| R4 环境级 | 服务不可用 | 现有 `jiaru.service`/隧道脚本未改；重启 `next start`，隧道域名不变 | 分钟级 |

## 7. 风险清单（逐项评估）

| # | 风险 | 触发 | 影响 | 探测 | 缓解/恢复 |
|---|---|---|---|---|---|
| 1 | mask 与 coverage alpha 不同源 | S2 只改 mask 未改 alpha | 边缘羽化与二值边界错位，出现重影 | S4 单测断言两者由同一向量产生；S6 目检边缘 | 同源复用同一 `smoothedRadius` 变量 |
| 2 | 面积补偿发散 | 周长解析式偏差大 | mask 膨胀/塌陷 | 单测断言面积误差 <0.5% 且 δ 有界（|δ|≤2px） | 补偿失败即回退不平滑 |
| 3 | float32 与 Python float64 不一致 | 卷积在 JS 用 fround | 个别像素翻转 | S5 逐位对拍 | 卷积与补偿显式 `Math.fround`，以 fixture 为准 |
| 4 | 算子默认开启误伤 | 缺省值写错 | 全量用户输出变化 | `mode` 缺省分支单测 + 快照对比 | 默认 `none`，显式声明才生效 |
| 5 | 性能回归 | ROI 重解码 | 端侧 P95 上升 | S6 计时 | δ≈0 时跳过重解码；单实例预算 3ms 内 |
| 6 | 训练域参数外推 | τ/网格来自 634 训练域 | 新来源上过平滑 | 仅在 12 图上看形态 | 明确标注“独立来源未标定”，发布前必须重标定 |
| 7 | 构建污染仓库 | Turbopack 失败/`tsconfig` 被改写 | 脏工作区 | 构建后 `git diff` | 按既有流程：旧 `.next` 改名、`--webpack`、构建后还原并 diff 确认 |
| 8 | 误当发布资格 | 报告数字被当成质量门通过 | 违反 PRODUCT HOLD | 文档写明 | 白皮书与 dev-log 均登记“非候选、非发布证据” |
| 9 | fixture 体积膨胀 | 32×2048 float | 仓库变大 | 提交前核对体积 | 上限 300KB，超出改存 16 枚 |

## 8. 验证门与停止条件

- **L1 单测**：`node --no-warnings --experimental-strip-types --test` 指定文件全绿；`typecheck` 与 `typecheck:tests` 0 错误；局部 ESLint 无 error。
  **实测通过**：新增 7 项 + 对拍 3 项；回归 `radial-field`/`radial-fixture`/`model-runtime`/`mask-pipeline` 共 48 项全绿；双 tsconfig 0 错误；ESLint 4 文件 0 error。
- **L2 跨语言对拍**：fixture 的 TS 解码 mask 与 Python 参考**逐位一致**（差异 0）；若不为 0 即停止，不进入 S6。
  **实测通过**：`tests/fixtures/radius-smoothing-parity-v1.json`（16 例，按面积四分层取样，15 例触发平滑，`5185773f…`，188,653 字节）；解码指纹（sha256）、核宽、面积 16/16 零差；`minReconstructionIoU=0.99705`、`maxConventionMismatchPixels=0`。
  另用 093 模块自带 `adaptive_vector`/`compensate_area` 复算同 16 例排除循环自证：`sigmaMismatch=0`、面积逐例相同。
  **执行中发现的口径坑**：审计 `contour_radius` 的 bin 原点为 `floor((θ+π)/2π·N)%N`，运行时 `computeRadialLattice` 为 `floor(wrapped·N/2π)`，相差 N/2=1024 bin；直接复用审计向量会让 mask 旋转 180°。fixture 因此按运行时原点重拟合。
- **L3 端到端**：开关关 = 输出与 S0 基线逐图一致；开关开 = 12 图目检无破形、P95 增量 ≤3ms。
  **实测（2026-11-17）**：构建 `next build --webpack` 46s 通过（BUILD_ID `zXr-z6jr0n8UXDBKikQTb`，新代码进 `.next/static/chunks/5163-*.js`），`next start` 重启后 8 页面 200、`/api/me` 401；线上 manifest 的 `stage2` 键无 `radiusSmoothing` → 开关关闭，行为与基线一致。
  **开关开的量化**（不跑 ONNX，只覆盖本次改动的解码链；16 枚真实 Stage B 半径向量）：mask 变更均值 0.52% 像素、开/关 IoU 0.99017、面积基本不变（补偿生效，如 50948→50936）。
  **耗时：P50 3.36ms、P95 4.72ms、max 6.10ms → 超 ≤3ms 预算，L3 不通过**。拆解：升序网格逐个卷积取最后一个通过者 = 每甲约 10 次卷积；单次卷积 0.30ms、单点网格（固定 σ）全流程 1.24ms，全网格 3.28ms（2.65×）。内存无泄漏（堆用量回落）。
  **结论：暂停接入**。Δ 约 +13—16ms/图（4—5 指）相对整图约 1.68s 约 +0.8%，但未满足自定门；优化方案见 §10。
- **L4 全量**：634 甲在浏览器侧复现 420 需批量harness；若不可得，则记录为**未闭合项**，不得口头宣称已复现。
- 任一 L 级失败即停止后续步骤，保留现场，写 dev-log。

## 9. 成本与顺序

S1—S5 约 1 轮会话（纯代码与测试，不重建）；S6 需二次批准（构建 + 重启，约 5 分钟）；S7 文档随代码一起。

## 10. S6 后的待批优化（未执行）

L3 未通过的主因是核宽扫描把 10 个候选全卷积一遍。三条候选路径，按风险从低到高：

| 选项 | 做法 | 预期耗时 | 数值影响 | 需要 |
|---|---|---|---|---|
| A 单调性早退 | 网格降序扫描，第一个满足 RMS 界即选定 | ≈2.1ms（平均约 5 次卷积） | 依赖 RMS 随 σ 单调（16 例可验，parity 测试会兜底） | 改 `radial-smoothing.ts` + 复跑 L1/L2 |
| B 二分查找 | 在 10 个候选上二分（约 3—4 次卷积） | ≈1.6ms，P95≈2.2ms | 同上，依赖单调性 | 同上 |
| C 先判后算 | 用循环自相关一次性算出各 σ 的 RMS，只对选中 σ 做 1 次真卷积 | ≈1.3ms | RMS 闭式与卷积有末位差，可能改变临界选择；须 16 例零差验证 | 新数值实现 + 重新对拍 |
| **C+ 已采纳** | 闭式 RMS **只做剪枝**（`rms > τ+1e-6` 才跳过），**降序找第一个用真实卷积满足界的核宽** —— 等价于「取满足界的最大核宽」，不需要单调性假设；短向量自动回退全扫 | 实测 P95 **2.20ms**（P50 1.89、max 3.85） | 与全扫参考同值：16 例指纹/σ/面积零差，另加 ±1e-9/±1e-8/±1e-6 阈值扫描对拍 | 已实现并验证，见下 |

另有两处可顺带补：①`public/models` 之外要跑「开关开」的图像级端到端，需要一份含 `radiusSmoothing` 的测试 manifest（当前 §5 禁写，需单独批准文件范围）；②`validateNailTextureModelManifest` 目前不校验 `radiusSmoothing`（非法值会静默降级为不平滑），建议随下一次改动补上校验。

### 10.1 C+ 落地结果（2026-11-17）

- 实现：`chooseSigma` 改为「`circularAutocorrelation` 一次 → 每个候选闭式 RMS → 降序扫，`rms > τ+1e-6` 才跳过 → 命中者用 `circularConvolve` + `rmsDelta` 真实裁决」。`fullScanSelection` 保留为短向量（`2·half > ⌊N/2⌋`）回退路径。
- 为何这是质量最高的做法：不做任何单调性假设（降序「第一个通过」= 定义上的最大通过核宽）；凡有通过可能的候选都用真实卷积裁决，闭式只可能让它**多算**而非**算错**。
- 新增 `tests/nail-texture-radius-smoothing-selection.test.ts`（3 项）：①10 组随机向量（含 2048/512/256/64 bin、τ=1e-6 与 1e9 极端）与全扫参考 σ/applied 逐例一致；②τ 设在每个候选真实 RMS 的 ±1e-9/±1e-8/±1e-6 上做阈值扫描，全部一致（同时把「闭式与真卷积之差 ≤1e-9」变成可验证事实）；③面积补偿后相对变化 <0.5%。
- 复测（同一脚本、同一 16 枚真实向量）：P50 3.36→**1.89ms**、P95 4.72→**2.20ms**、max 6.10→3.85ms；mask 变更像素总数 5517、开/关 IoU 0.99017 —— **与优化前逐位相同**，即只提速不改结果。L3 的 P95 ≤3ms 达标。
- 回归：`radius-smoothing`(7) + `parity`(3) + `selection`(3) + `radial-field` + `radial-fixture` + `model-runtime` + `mask-pipeline` 共 **54 项全绿**；双 tsconfig typecheck 0 错误。

## 11. 原生半径复测：代理指标不迁移（2026-11-17，决定保持关闭）

**问题**：093 的 420 是在「从预测 mask 重拟合出的轮廓半径」上测的。运行时平滑的是 Stage B 原生 `radius` 输出，两者不是同一个向量（重拟合会外扩约 0.5px，重建 IoU 仅 0.998）。

**审计 094**（`model/training/audit-development-cycle-094-native-radius-smoothing.py`，证据 `model/reports/cycle094-native-radius-smoothing-v1/report.json`）：

- 保真门全部通过：原生解码与评估存下的 `masksPacked` **逐像素零差**（0 mismatch）、基线严格联合**精确复现 248**、634 甲/2 项无真值跳过。
- 结果：`τ=0.7` 时仅 **3/634** 触发平滑，严格联合 **248→248，增益 0**（+0/−0），meanMaskIoU 0.98467→0.98468。
- 根因量化：原生半径**相邻 bin 抖动约 3.47px**（中位），连最小核（σ=0.5px）都会造成 **2.17px** 的 RMS 位移 → 远超 0.7 的界，算子几乎恒等于不生效。这也解释了用户此前看到的边缘锯齿：模型半径头本身就抖。

**审计 095 τ 扫描**（`audit-development-cycle-095-native-radius-tau-sweep.py`，证据 `cycle095-native-radius-tau-sweep-v1/report.json`）：

| τ | 触发 | 严格联合 | 增/失 | meanMaskIoU | meanBoundaryIoU | meanBoundaryF1 |
|---|---|---|---|---|---|---|
| 基线 | — | 248 | — | 0.98467 | 0.72466 | 0.98880 |
| 0.7（当前默认） | 3 | 248 | 0/+0 | 0.98468 | 0.72483 | 0.98880 |
| 1.0 | 18 | 251 | +3/−0 | 0.98471 | 0.72547 | 0.98872 |
| 1.5 | 79 | 261 | +14/−1 | 0.98490 | 0.72763 | 0.98792 |
| **2.0** | 274 | **281** | **+47/−14** | **0.98553** | **0.73080** | 0.98505 |
| 2.5 | 520 | 273 | +95/−70 | 0.98587 | 0.72854 | 0.98275 |
| 3.0 | 618 | 278 | +127/−97 | 0.98547 | 0.72186 | 0.98303 |
| ≥4.0 | 634 | 241 | +129/−136 | 0.98370 | 0.70085 | 0.97915 |

配对显著性（不一致对二项检验）：τ=2.0 的 47/14 双侧 **p=2.7e-5**；τ=1.5 的 14/1 为 p=9.8e-4；τ=2.5、3.0 分别 p=0.061、0.052（不显著，且翻转对数翻倍）。

**处置**：代码保持 `mode` 缺省关闭、`DEFAULT_OPTIONS` 保持 τ=0.7（当前配置对真实输出等价于不生效，既无增益也无害）。若要启用，应按 **τ=2.0** 重标定，并接受「+33 甲净增、boundaryF1 −0.0038、14 甲退化」这一权衡；仍远低于 539 门。是否重标定属产品决策，需另行批准。
