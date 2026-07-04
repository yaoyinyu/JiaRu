# 模型版本 A/B 对比

版本：v1.1
日期：2026-07-04

这一步对应规划文档 Phase 5 里的：

- 增加模型 A/B 对比脚本

它用于把两版训练结果和浏览器模型产物放在一起比较，避免模型更新只看单次门禁，不看相对变化。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/compare-training-releases.ts --baseline-metrics model/exports/nail-texture-seg-v1/metrics.json --baseline-manifest public/models/nail-texture-seg-v1/manifest.json --candidate-metrics model/exports/nail-texture-seg-v2/metrics.json --candidate-manifest public/models/nail-texture-seg-v2/manifest.json --output model/exports/nail-texture-seg-v2/compare-summary.json
```

## 它会比较什么

- `seg_map50`
- `box_map50`
- `seg_map`
- `box_map`
- 模型文件大小
- `imgsz`
- `manifest inputSize`
- `backendPreferences`
- `labels`

## 输出

结构化 JSON 会输出到 stdout；传入 `--output` 时也会写入文件，方便后续 `build-release-decision-report.ts` 和 release governance 继续读取。内容包括：

- `baseline`
- `candidate`
- `deltas`
- `regressions`
- `improvements`
- `warnings`
- `nextSteps`

## 适用时机

- 已经有两版真实 `metrics.json`
- 已经有两版浏览器 manifest 和 ONNX
- 需要决定是否升级模型，或者是否保留上一版用于回滚
## 补充：把 failure summary 也纳入 A/B 对比

现在 `compare-training-releases.ts` 除了比较：

- `metrics.json`
- `manifest.json`
- `onnx` 文件大小

还支持可选比较两版 release 的失败摘要：

```bash
node --no-warnings --experimental-strip-types scripts/compare-training-releases.ts --baseline-metrics model/exports/nail-texture-seg-v1/metrics.json --baseline-manifest public/models/nail-texture-seg-v1/manifest.json --baseline-failure-summary model/exports/nail-texture-seg-v1/failure-case-summary.json --candidate-metrics model/exports/nail-texture-seg-v2/metrics.json --candidate-manifest public/models/nail-texture-seg-v2/manifest.json --candidate-failure-summary model/exports/nail-texture-seg-v2/failure-case-summary.json --output model/exports/nail-texture-seg-v2/compare-summary.json
```

当这两个参数都提供时，输出里还会多出：

- `baseline.failureSummary`
- `candidate.failureSummary`
- `deltas.postprocessFailures`
- `deltas.highlightHotspotFailures`

这样做版本决策时，就不只是看 mAP 是否涨跌，也能一起看到后处理失败画像有没有变差。
