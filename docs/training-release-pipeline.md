# 训练发布流水线

版本：v1.1  
日期：2026-07-02

这一步把 Phase 2 里原本分散的几个动作串起来：

- `train-yolo-seg.py`
- `evaluate.py`
- `export-onnx.py`
- `verify-training-release.ts`

现在它还能在需要时继续往后衔接：

- `run-real-model-final-audit.ts`
- `run-release-governance-pipeline.ts`

目标是把“训练出一版模型并做发布门禁”变成一条可复现的流水线，并且在你准备好后继续把 release 治理闭环也接上。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --dry-run
```

真实跑时：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts
```

如果已经有参考图，并且想在训练发布通过后顺手进入真实模型最终审计：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json
```

如果已经有现成的 `metrics.json` 和浏览器模型目录，只想重跑发布门禁：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export
```

## 它解决的几个真实问题

1. 统一训练产物里的 `best.pt` 默认路径  
   现在训练、评估、导出都会默认使用：

```text
<train-output-dir>/<run-name>/weights/best.pt
```

2. 导出的浏览器 `manifest.json` 与后续验收口径一致  
   现在导出脚本会写入：

- `backendPreferences`
- `labels`
- `modelFile`
- `inputSize`
- `version`
- `task`

这样后面的 `verify-model-artifact.ts` / `verify-training-release.ts` 才能真正接上。

3. 当你已经准备好真实参考图时，流水线可以继续追到：

- `run-real-model-final-audit.ts`

也就是训练发布门禁通过后，直接进入真实模型首轮审计，而不是再手工拼下一条命令。

4. 当你准备好 compare / registry / trace draft 这些治理输入时，流水线还能继续追到：

- `run-release-governance-pipeline.ts`

也就是 training release 报告生成后，直接继续完成：

- release decision
- promotion
- release trace index
- history manifest

## 输出

流水线会生成：

- `model/exports/<version>/training-release-pipeline-report.json`

报告里会包含：

- 每一步是否通过
- 实际命令
- 训练 / 指标 / manifest 的产物摘要
- 如果触发了真实模型最终审计，也会把最终审计结果摘要写进同一份报告
- 如果触发了 release governance，也会把治理总报告摘要写进同一份报告
- 如果是 dry-run，会明确标注发布门禁被跳过

## 补充：把 annotation debug 一起带进发布流水线

如果你已经把页面修正样本或 reviewed annotation 导入到了：

```text
model/datasets/nail-texture-v1/annotations/raw-json
```

现在可以直接在训练发布流水线里透传给 final audit：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --final-audit-annotation-dir model/datasets/nail-texture-v1/annotations/raw-json
```

这样最终生成的 `training-release-pipeline-report.json` 会额外包含：

- `options.finalAuditAnnotationDir`
- `artifacts.finalAudit.annotationDirPath`
- `artifacts.finalAuditFailureSummary`

也就是发布流水线一级就能直接看到 annotation debug 派生出来的后处理失败汇总。

## 补充：把 release governance 自动接回主链

如果你希望 training release 成功后直接继续进入 release 治理闭环，可以加：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-release-trace-draft model/exports/nail-texture-seg-v2/release-trace-draft.json --governance-history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

关键参数包括：

- `--run-governance`
- `--governance-compare-summary`
- `--governance-registry`
- `--governance-release-trace-draft`
- `--governance-reviewed-batch-import-pipeline-report`
- `--governance-reviewed-batch-root-dir`
- `--governance-history-manifest`
- `--governance-allow-manual-review true|false`
- `--governance-set-current true|false`
- `--governance-promote true|false`

如果你不想手工分别传：

- `release-trace-draft.json`
- `reviewed-batch-import-pipeline-report.json`

现在可以只传 reviewed batch 根目录：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-reviewed-batch-root-dir C:/path/to/seed-batch-020 --governance-history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

这时主链会自动尝试从该目录解析：

- `release-trace-draft.json`
- `reviewed-batch-import-pipeline-report.json`

如果你只给了其中一个文件路径，主链也会继续尝试从对应的 `rootDir` 反推另一个文件。

## 补充：优先使用 reviewed batch release handoff

现在 reviewed batch import 流水线还会额外产出一份标准 handoff：

```text
reviewed-batch-release-handoff.json
```

如果你希望 training release 主链优先按这份标准接力文件来解析上下文，可以直接传：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --governance-registry public/models/nail-texture-seg/release-registry.json --governance-reviewed-batch-release-handoff C:/path/to/seed-batch-020/reviewed-batch-release-handoff.json --governance-history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

这时主链会优先从 handoff 中读取：

- `reviewedBatchRootDir`
- `reviewedBatchImportPipelineReportPath`
- `releaseTraceDraftPath`

然后再继续跑 governance。

对使用者来说，这样就把 reviewed batch → training release 的交接收敛成了一个标准入口文件。

启用后，`training-release-pipeline-report.json` 还会额外记录：

- `paths.governanceReportPath`
- `options.runGovernance`
- `artifacts.releaseGovernance`

这样 training release 主链就不只停在“训练产物通过门禁”，而是可以继续把发布治理闭环也跑完。

## 补充：默认路径现在会自动跟随 `modelVersion`

如果你显式传了：

```bash
--model-version nail-texture-seg-v9
```

但没有再手工指定：

- `--run-name`
- `--train-output-dir`

主链现在会自动对齐默认值：

```text
runName = nail-texture-seg-v9
trainOutputDir = model/exports/nail-texture-seg-v9
```

这样可以避免出现“模型版本已经变了，但训练输出目录还停在旧版本目录”的不一致。

## 补充：handoff 驱动的治理默认路径模板

当你已经提供：

- `--run-governance`
- `--governance-reviewed-batch-release-handoff`

即使不再手工传这些路径：

- `--governance-compare-summary`
- `--governance-registry`
- `--governance-history-manifest`

主链现在也会自动补齐默认路径：

```text
compare summary   -> <train-output-dir>/compare-summary.json
registry          -> <browser-model-dir>/release-registry.json
history manifest  -> <train-output-dir>/release-history-manifest.json
```

也就是说，handoff 不只是帮助主链恢复 reviewed batch 上下文，现在也开始承担“治理路径模板”的默认来源。
