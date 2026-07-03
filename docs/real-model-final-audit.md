# 真实模型最终审计命令

版本：v1.0  
日期：2026-07-01

当真实 ONNX、参考图、可选 dump、UI review 都准备好后，用这条命令做最终审计。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/run-real-model-final-audit.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --output-dir model/debug/real-model-final-audit --debug-prefix real-model --ui-review model/fixtures/real-model-ui-review.template.json
```

如果想把已导入 annotation JSON 里的 `attributes.debug` 一起纳入失败归因汇总，可以额外传：

```bash
--annotation-dir model/datasets/nail-texture-v1/annotations/raw-json
```

如果已经有训练指标和 dump，也可以带上：

```bash
node --no-warnings --experimental-strip-types scripts/run-real-model-final-audit.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --output-dir model/debug/real-model-final-audit --debug-prefix real-model --metrics model/exports/nail-texture-seg-v1/metrics.json --dump model/debug/run-001/nail-model-output-dump.json --fixture-out model/fixtures/nail-texture-model-output-sample.generated.json --ui-review model/fixtures/real-model-ui-review.template.json
```

## 产物

- `real-model-first-run-record.json`
- `real-model-final-audit-report.json`
- `failure-case-summary.json`
- `texture-quality-gate.json`（当传入 `--annotation-dir` 时）
- 一组 debug 图片 / JSON / 可选 dump

其中 `failure-case-summary.json` 现在除了人工 `failure-classification.csv` / first-run record，也可以吸收 annotation debug 里的：

- `warnings`
- `extractionQualityWarnings`
- 高光热点派生信号

如果传入了：

```bash
--annotation-dir model/datasets/nail-texture-v1/annotations/raw-json
```

现在除了失败归因摘要，也会额外产出：

- `texture-quality-gate.json`

它会把 annotation debug 里的提取质量信号进一步汇总成：

- 可直接使用率
- 污染率
- warning breakdown

并一起写回 `real-model-final-audit-report.json`。

## 作用

这条命令本身不替代已有验证器，而是把它们的结果统一沉淀成一份最终交付前的审计结论。

现在它还会自动补一份失败归因摘要，帮助把 `blocked / needs_adjustment` 结果继续归到：

- `data`
- `model`
- `postprocess`
- `ui`
