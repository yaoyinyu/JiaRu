# 真实模型联调报告流程

版本：v1.0  
日期：2026-07-01

这条流程用于在真实 ONNX 到位后，把三类证据汇总成一份统一联调记录：

- readiness 结果
- browser integration gate 结果
- 手工 UI 验收记录

## 需要准备

- 真实模型 manifest / onnx
- 一张联调用参考图
- 可选的模型原始输出 dump / fixture
- 一份 UI 手工验收记录：
  [model/fixtures/real-model-ui-review.template.json](E:/AI%20Project/Codex/JiaRu/model/fixtures/real-model-ui-review.template.json)

## 生成首轮联调记录

```bash
node --no-warnings --experimental-strip-types scripts/build-real-model-first-run-record.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --output model/fixtures/real-model-first-run-record.generated.json --debug-output-dir model/debug/real-model-first-run --debug-prefix real-model --ui-review model/fixtures/real-model-ui-review.template.json
```

如果已经有训练指标和 dump，也可以带上：

```bash
node --no-warnings --experimental-strip-types scripts/build-real-model-first-run-record.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --metrics model/exports/nail-texture-seg-v1/metrics.json --dump model/debug/run-001/nail-model-output-dump.json --fixture-out model/fixtures/nail-texture-model-output-sample.generated.json --ui-review model/fixtures/real-model-ui-review.template.json
```

## 输出

- 统一的首轮联调记录 JSON
- `decision.status`
  - `pass`
  - `needs_adjustment`
  - `blocked`

## 作用

这一步不是替代已有脚本，而是把已有脚本的结果沉淀成一份最终可留档的联调结论。
