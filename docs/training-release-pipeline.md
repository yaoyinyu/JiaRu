# 训练发布流水线

版本：v1.0  
日期：2026-07-01

这一步把 Phase 2 里原本分散的几个动作串起来：

- `train-yolo-seg.py`
- `evaluate.py`
- `export-onnx.py`
- `verify-training-release.ts`

目标是把“训练一版模型并做发布门禁”变成一条可复现的流水线。

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

## 它解决的两个真实问题

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

3. 当你已经准备好真实参考图时，流水线可以继续追加：

- `run-real-model-final-audit.ts`

也就是训练发布门禁通过后，直接进入真实模型首轮审计，而不是再手工拼下一条命令。

## 输出

流水线会生成：

- `model/exports/nail-texture-seg-v1/training-release-pipeline-report.json`

报告里会包含：

- 每一步是否通过
- 实际命令
- 训练 / 指标 / manifest 的产物摘要
- 如果触发了真实模型最终审计，也会把最终审计结果摘要写进同一份报告
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
