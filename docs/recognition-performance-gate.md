# 识别性能门禁

版本：v1.2  
日期：2026-07-04

这一步对应 `docs/nail-texture-recognition-model-plan.md` Phase 3 的性能验收：

- 桌面浏览器单图总耗时 < 800ms。
- 中端手机单图总耗时 < 1500ms。

当前真实 ONNX 还没落地，所以该门禁先固定报告格式和验收口径。等真实模型 final audit 或 UI debug sample 产出后，可以直接读取其中的 `elapsedMs`，并把性能报告接入发布决策。

`elapsedMs` 现在是端到端时间：从调用 `recognizeNailTexturesInWorker()` 开始，覆盖像素准备、`createImageBitmap`、Worker 排队/传输、推理和后处理。`workerElapsedMs` 保留 Worker 内部识别时间；发布门禁始终使用更贴近用户体验的 `elapsedMs`。

## 命令

桌面预算：

```bash
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts --profile desktop --sample-dir C:/path/to/debug-samples --output C:/path/to/performance-report.desktop.json
```

手机预算：

```bash
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts --profile mobile --sample-dir C:/path/to/debug-samples --output C:/path/to/performance-report.mobile.json
```

也可以直接传入单个或多个 JSON：

```bash
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts C:/path/to/nail-detection-debug.json C:/path/to/local-debug-sample.json
```

## 输入来源

脚本会读取 JSON 根字段里的：

- `elapsedMs`
- `backend`
- `modelVersion`
- `imageId` 或 `input`

当前支持两类产物：

- `NailArtPicker` 导出的 debug sample。
- `verify-nail-detection.ts` 生成的 detection debug JSON。

没有 `elapsedMs` 的 JSON 会被跳过，并在报告里列入 `skippedFiles`。

## 输出

报告包含：

- `ok`
- `profile`
- `thresholds.maxElapsedMs`
- `thresholds.minSamples`
- `totals.samples`
- `totals.slowSamples`
- `stats.averageMs / p50Ms / p95Ms / maxMs`（端到端）
- `stats.averageWorkerMs / averageClientOverheadMs`（有 `workerElapsedMs` 时）
- `slowSamples`
- `errors`
- `nextSteps`

## 发布链路集成

`build-release-decision-report.ts` 支持传入性能报告：

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json
```

`run-release-governance-pipeline.ts` 也支持同一个参数：

```bash
node --no-warnings --experimental-strip-types scripts/run-release-governance-pipeline.ts --training-release-pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json
```

如果性能报告 `ok === false`，候选模型会进入 `hold_candidate`，不会被自动 promotion。正式 `release-trace-index.json` 会保留：

- `performance.ok`
- `performance.profile`
- `performance.maxElapsedMs`
- `performance.p95Ms`
- `performance.maxMs`
- `performance.slowSamples`
- `performance.performanceReportPath`

这样 Phase 3 的性能目标不再只停留在文档描述，而是会进入 release decision 和 trace 证据链。
## Worker input preparation guard

Browser integration verification also checks that worker input preparation does not expand RGBA pixels through `Array.from(source.data)`. The normal `ImageData.data` path reuses its `Uint8ClampedArray` directly; generic array-like inputs use native typed-array `set` only after RGBA length validation.

A controlled 1920x1080 benchmark on 2026-07-04 measured the removed `Array.from + set` path at 168.91 ms versus 0.0053 ms for buffer reuse. This microbenchmark is diagnostic evidence, not a replacement for the desktop/mobile end-to-end performance report.

Before `getImageData`, `NailArtPicker` now caps the detection canvas to an 800-pixel longest edge and remaps candidate geometry to original-image coordinates. An 8000x6000 input therefore uses at most an 800x600 (1.92 MB) detection RGBA buffer instead of a 192 MB full-resolution buffer. The model mask remains a normalized full-image grid and is reused when extracting from the original image.