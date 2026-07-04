# 训练发布流水线

版本：v1.3
日期：2026-07-04

`run-training-release-pipeline.ts` 把 Phase 2 到 Phase 5 之间的关键动作串成统一入口：

- `train-yolo-seg.py`
- `evaluate.py`
- `verify-evaluation-artifacts.ts`
- `export-onnx.py`
- `verify-training-release.ts`
- 可选的 `run-real-model-final-audit.ts`
- 可选的 `run-release-governance-pipeline.ts`

目标是把“训练一版模型并进入发布治理”变成一条可重复、可追溯的主链。

## 基本命令

Dry run：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --dry-run
```

真实运行：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts
```

如果已经有现成的 `metrics.json` 和浏览器模型目录，只想重跑发布门禁：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export
```

## 可选：继续跑 final audit

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json
```

如果还想把 annotation debug 一起带进 final audit：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --final-audit-annotation-dir model/datasets/nail-texture-v1/annotations/raw-json
```

## 可选：继续跑 release governance

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --governance-performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-release-trace-draft model/exports/nail-texture-seg-v2/release-trace-draft.json --governance-history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

## governance 相关参数

- `--run-governance`
- `--governance-compare-summary <compare-summary.json>`
- `--governance-performance-report <performance-report.json>`
- `--governance-registry <release-registry.json>`
- `--governance-release-trace-draft <release-trace-draft.json>`
- `--governance-reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>`
- `--governance-reviewed-batch-root-dir <seed-batch-dir>`
- `--governance-reviewed-batch-release-handoff <reviewed-batch-release-handoff.json>`
- `--governance-active-learning-handoff <debug-sample-active-learning-handoff.json>`
- `--governance-history-manifest <release-history-manifest.json>`
- `--governance-allow-manual-review true|false`
- `--governance-set-current true|false`
- `--governance-promote true|false`

`--governance-performance-report` 会透传给 `run-release-governance-pipeline.ts`。如果性能报告 `ok === false`，候选模型会被 `hold_candidate`，不会自动 promotion。流水线总报告也会把该报告读入 `artifacts.recognitionPerformance`。

## reviewed batch 接力

如果不想手工分别传：

- `release-trace-draft.json`
- `reviewed-batch-import-pipeline-report.json`

可以直接给：

- `--governance-reviewed-batch-root-dir`

或者更标准地给：

- `--governance-reviewed-batch-release-handoff <reviewed-batch-release-handoff.json>`

主链会优先从 handoff 中恢复：

- `reviewedBatchRootDir`
- `reviewedBatchImportPipelineReportPath`
- `releaseTraceDraftPath`

## active learning 接力

如果训练前的数据增强主要来自页面修正样本回流，可以直接给：

- `--governance-active-learning-handoff <debug-sample-active-learning-handoff.json>`

例如：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v5/compare-summary.json --governance-performance-report model/exports/nail-texture-seg-v5/performance-report.mobile.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-active-learning-handoff C:/path/to/active-learning/debug-sample-active-learning-handoff.json --governance-history-manifest model/exports/nail-texture-seg-v5/release-history-manifest.json
```

此时主链会优先从 handoff 中恢复 `activeLearningReleaseTraceDraftPath`，并把 active learning trace 字段带进：

- `release-trace-index.json`
- `training-release-pipeline-report.json` 的 `artifacts.releaseGovernance`

## 默认路径

如果显式传了：

```bash
--model-version nail-texture-seg-v9
```

但没有再手工指定：

- `--run-name`
- `--train-output-dir`

主链会自动对齐默认值：

```text
runName = nail-texture-seg-v9
trainOutputDir = model/exports/nail-texture-seg-v9
```

部分 governance 路径也会按默认模板补齐：

```text
compare summary      -> <train-output-dir>/compare-summary.json
performance report   -> <train-output-dir>/performance-report.mobile.json
registry             -> <browser-model-dir>/release-registry.json
history manifest     -> <train-output-dir>/release-history-manifest.json
```

## 输出

流水线会生成：

```text
model/exports/<version>/training-release-pipeline-report.json
```

报告包含：

- 每一步是否通过
- 实际命令
- 训练 / 指标 / manifest 产物摘要
- evaluation artifacts 摘要
- recognition performance 摘要
- final audit 摘要
- release governance 摘要
- governance 输入上下文恢复结果

关键字段：

- `paths.*`
- `options.*`
- `steps`
- `artifacts.metrics`
- `artifacts.recognitionPerformance`
- `artifacts.evaluationArtifacts`
- `artifacts.manifest`
- `artifacts.finalAudit`
- `artifacts.finalAuditFailureSummary`
- `artifacts.finalAuditTextureQualityGate`
- `artifacts.releaseGovernance`

## Phase 2 评估可视化门禁

真实评估会生成 `evaluation-artifacts/evaluation-artifacts.json`，并由 `verify-evaluation-artifacts.ts` 检查测试集混淆矩阵和预测 / 真值对照图。门禁失败时流水线不会继续导出和发布。路径及索引内容会写入训练发布报告；详见 `docs/model-evaluation-artifacts.md`。
## governance 后置回滚审计

当 `--run-governance` 开启且候选模型被 promotion 成功后，`run-release-governance-pipeline.ts` 会自动追加回滚审计。训练发布总报告中的 `artifacts.releaseGovernance` 会包含 `artifacts.rollbackAudit`，用于确认新版本发布后仍然可以切回旧版本。

因此，真实发布前需要保证 `--governance-registry` 指向的是已经通过 `register-model-release.ts` 登记过至少一个旧版本的 registry；只有手写 `{ version }` 的 registry 不足以通过回滚审计。
