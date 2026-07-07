# 浏览器模型接入验收

版本：v1.0  
日期：2026-07-01

这一步用于验证“真实模型接进浏览器链路”之前，仓库里的接线是否完整。

它会同时看三类东西：

- 模型资产是否健康
- 可选的训练结果 / 后处理 fixture 是否健康
- `NailArtPicker`、client worker、worker、runtime 之间的关键接线是否存在

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --manifest public/models/nail-texture-seg/manifest.json
```

如果已经有训练结果和真实模型输出 fixture，也可以一起带上：

```bash
node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --manifest public/models/nail-texture-seg/manifest.json --metrics model/exports/nail-texture-seg-v1/metrics.json --fixture model/fixtures/nail-texture-model-output-sample.json
```

## 检查内容

- `verify-model-artifact.ts`
- 可选 `verify-training-release.ts`
- 可选 `verify-model-output-fixture.ts`
- `NailArtPicker` 是否走 worker 识别入口
- `NailArtPicker` 是否把 `AbortController.signal` 传入识别，并让“跳过识别”和“关闭”都先触发 abort
- `NailArtPicker` 是否同时保留端到端 `elapsedMs` 和 Worker 内部 `workerElapsedMs`
- `NailArtPicker` 是否在 `getImageData` 前把检测画布最长边限制到 800，并把候选坐标映射回原图
- `client-worker.ts` 是否传递 `preferModel` / `manifestUrl`
- worker 是否调用识别逻辑并回传响应
- client worker 是否避免 `Array.from(source.data)` 这类像素展开；`Uint8ClampedArray` 主路径必须零复制复用
- 取消请求时 client worker 是否真正终止推理 Worker，而不只是丢弃返回值
- Worker 是否在像素复制后关闭已转移的 `ImageBitmap`
- runtime 是否负责 manifest 加载和 execution provider 选择

## 输出

结构化 JSON：

- `artifact`
- `trainingRelease`
- `fixtureVerify`
- `contractChecks`
- `errors`
- `warnings`

## 适用时机

- 模型还没最终接入 UI，但想先确认浏览器侧接线完整
- 模型刚接进来，想在 `/ar-tryon` 手工验收前先跑一遍静态/动态门禁

## ONNX Runtime Web 依赖门禁

`verify-browser-integration.ts` 会同时读取 `package.json`，确认 `onnxruntime-web` 已声明为依赖。这样可以避免代码里存在动态 `import("onnxruntime-web")`，但真实浏览器构建时缺少运行时包的情况。
## Worker timeout fallback

`recognizeNailTexturesInWorker()` supports `workerTimeoutMs`. The default timeout is 15000ms. If the Worker does not answer in time, the client terminates that Worker instance and resolves through the existing main-thread fallback path with `worker_timeout_used_main_thread` in `warnings`.

This keeps the browser integration aligned with the Phase 3 non-blocking requirement: model or Worker hangs should not leave the multi-texture extraction flow waiting forever. Pass `workerTimeoutMs: 0` only for debugging cases where timeout behavior should be disabled deliberately.
## Browser integration timeout contract

`verify-browser-integration.ts` now includes `client_worker_times_out_to_fallback`. This static gate checks that the client worker still contains the timeout wiring, Worker termination, main-thread fallback call, and `worker_timeout_used_main_thread` warning marker.

This is intentionally a contract check rather than a real model run: it protects the Phase 3 non-blocking behavior before a real ONNX model is available.
## Picker-level timeout policy

`NailArtPicker` explicitly passes `workerTimeoutMs` when it calls `recognizeNailTexturesInWorker()`. The current UI policy is 15000ms, matching the client-worker default while making the product-level budget visible in the picker code.

The browser integration gate checks this through `picker_uses_worker_recognition`, so future picker rewrites must keep the timeout policy wired instead of relying on an implicit default. The picker warning presenter also maps `worker_timeout_used_main_thread` to a user-facing fallback message.
## Worker recognition option contract

`workerTimeoutMs` is now part of the browser Worker request contract. The UI still owns the timeout budget, and `client-worker.ts` still performs the actual timeout fallback, but the request sent to `nail-texture-recognition.worker.ts` also carries the normalized value. The Worker forwards it into `recognizeNailTextures()` so static browser-integration checks can verify that recognition options are consistent across the UI, client-worker, and worker boundary.

This is mainly a traceability and regression-safety contract: real model training is still out of scope for this step, while the browser integration can already prove that timeout policy is not silently dropped during refactors.
