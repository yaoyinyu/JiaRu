# 真实模型最终审计命令

版本：v1.0  
日期：2026-07-01

当真实 ONNX、参考图、可选 dump、UI review 都准备好后，用这条命令做最终审计。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/run-real-model-final-audit.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --output-dir model/debug/real-model-final-audit --debug-prefix real-model --ui-review model/fixtures/real-model-ui-review.template.json
```

如果已经有训练指标和 dump，也可以带上：

```bash
node --no-warnings --experimental-strip-types scripts/run-real-model-final-audit.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --output-dir model/debug/real-model-final-audit --debug-prefix real-model --metrics model/exports/nail-texture-seg-v1/metrics.json --dump model/debug/run-001/nail-model-output-dump.json --fixture-out model/fixtures/nail-texture-model-output-sample.generated.json --ui-review model/fixtures/real-model-ui-review.template.json
```

## 产物

- `real-model-first-run-record.json`
- `real-model-final-audit-report.json`
- 一组 debug 图片 / JSON / 可选 dump

## 作用

这条命令本身不替代已有验证器，而是把它们的结果统一沉淀成一份最终交付前的审计结论。
