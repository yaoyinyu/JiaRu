# 纹理可用率 / 污染率专项门禁

版本：v1.0  
日期：2026-07-03

这一步直接对应 `docs/nail-texture-recognition-model-plan.md` 里 Phase 4 的量化验收目标：

- 用户无需调整即可直接使用的样本比例 > 85%
- 纹理中明显皮肤 / 背景污染比例 < 10%

前面我们已经补了：

- 候选方向稳定化
- 低质量候选提示
- 透明裁剪与边缘羽化专项验收
- extraction diagnostics 的 UI 结构化展示

这次继续把这些信号收口成一份真正可执行的质量 gate。

## 当前实现位置

- `scripts/verify-texture-quality-gate.ts`
- `scripts/run-real-model-final-audit.ts`

## 这次补齐了什么

### 1. 新增独立的纹理质量 gate 脚本

新增：

- `scripts/verify-texture-quality-gate.ts`

它会读取 annotation debug 信息，统计：

- `directlyUsableCandidates`
- `contaminatedCandidates`
- `directlyUsableRate`
- `contaminationRate`

并输出结构化结论。

### 2. 当前门禁使用的判定口径

当前“可直接使用候选”要求同时满足：

- 没有 candidate warnings
- 没有 extraction quality warnings
- `extractionQualityOk !== false`
- `highlightRatio < 0.12`
- `highlightPixels < 8`

当前“污染候选”先按：

- `dirty_mask_crop`

来统计。

这意味着这份 gate 现在优先抓的是真正和“皮肤 / 背景混入”最贴近的污染信号，而不是把所有提取问题都混成污染。

### 3. final audit 现在会自动带出这份 gate

当你给 `run-real-model-final-audit.ts` 传入：

- `--annotation-dir`

它现在除了生成：

- `real-model-first-run-record.json`
- `failure-case-summary.json`

还会自动生成：

- `texture-quality-gate.json`

并把它写回最终 audit summary。

## 当前输出内容

gate 报告当前会包含：

- `thresholds`
- `totals`
- `rates`
- `warningBreakdown`
- `warnings`
- `nextSteps`

这样后续不只是知道“过 / 没过”，还知道到底是：

- 可直接使用率不够
- 还是污染率没有压下去
- 以及具体是哪类 warning 在拉低质量

## 为什么这一步重要

这一步让 Phase 4 从“有很多后处理质量信号”推进到了“有可量化的产品质量门禁”。

这样后面无论是：

- 真机最终审计
- 训练发布流水线
- 或版本对比

都可以开始吸收同一套质量指标，而不是只看主观描述。

## 自动化验收

本轮新增并通过：

- `tests/verify-texture-quality-gate.test.ts`
  - 验证门禁通过场景
  - 验证低可用率 / 高污染率失败场景
- `tests/run-real-model-final-audit.test.ts`
  - 验证 final audit 会带出 `texture-quality-gate.json`

并继续通过：

- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`
