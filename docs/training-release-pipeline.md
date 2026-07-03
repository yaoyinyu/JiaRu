# 训练发布流水线

版本：v1.2  
日期：2026-07-03

这条流水线把 Phase 2 到 Phase 5 之间的关键动作串成一个统一入口：

- `train-yolo-seg.py`
- `evaluate.py`
- `export-onnx.py`
- `verify-training-release.ts`
- 可选的 `run-real-model-final-audit.ts`
- 可选的 `run-release-governance-pipeline.ts`

目标是把“训练一版模型并进入发布治理”变成一条可重复、可追踪的主链。

## 基本命令

Dry run：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --dry-run
```

真实跑：

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
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-release-trace-draft model/exports/nail-texture-seg-v2/release-trace-draft.json --governance-history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

## governance 相关参数

- `--run-governance`
- `--governance-compare-summary`
- `--governance-registry`
- `--governance-release-trace-draft`
- `--governance-reviewed-batch-import-pipeline-report`
- `--governance-reviewed-batch-root-dir`
- `--governance-reviewed-batch-release-handoff`
- `--governance-active-learning-handoff`
- `--governance-history-manifest`
- `--governance-allow-manual-review true|false`
- `--governance-set-current true|false`
- `--governance-promote true|false`

## reviewed batch 接力

如果你不想手工分别传：

- `release-trace-draft.json`
- `reviewed-batch-import-pipeline-report.json`

现在可以直接给：

- `--governance-reviewed-batch-root-dir`

或者更标准一点，直接给：

- `--governance-reviewed-batch-release-handoff <reviewed-batch-release-handoff.json>`

主链会优先从 handoff 中恢复：

- `reviewedBatchRootDir`
- `reviewedBatchImportPipelineReportPath`
- `releaseTraceDraftPath`

## active learning 接力

如果训练前的数据增强主要来自页面修正样本回流，现在也可以直接给：

- `--governance-active-learning-handoff <debug-sample-active-learning-handoff.json>`

例如：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v5/compare-summary.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-active-learning-handoff C:/path/to/active-learning/debug-sample-active-learning-handoff.json --governance-history-manifest model/exports/nail-texture-seg-v5/release-history-manifest.json
```

这时主链会优先从 handoff 中恢复：

- `activeLearningReleaseTraceDraftPath`

然后继续跑 governance，并把 active learning trace 字段带进：

- `release-trace-index.json`
- `training-release-pipeline-report.json` 里的 `artifacts.releaseGovernance`

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

同理，部分 governance 路径也会按默认模板补齐：

```text
compare summary   -> <train-output-dir>/compare-summary.json
registry          -> <browser-model-dir>/release-registry.json
history manifest  -> <train-output-dir>/release-history-manifest.json
```

## 输出

流水线会生成：

```text
model/exports/<version>/training-release-pipeline-report.json
```

报告里会包含：

- 每一步是否通过
- 实际命令
- 训练 / 指标 / manifest 产物摘要
- final audit 摘要
- release governance 摘要
- governance 输入上下文恢复结果

关键字段重点看：

- `paths.*`
- `options.*`
- `steps`
- `artifacts.metrics`
- `artifacts.manifest`
- `artifacts.finalAudit`
- `artifacts.finalAuditFailureSummary`
- `artifacts.finalAuditTextureQualityGate`
- `artifacts.releaseGovernance`
