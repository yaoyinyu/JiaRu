# 训练结果与导出产物验收

版本：v1.1
日期：2026-07-04

这一步用于把一版训练结果和浏览器端导出产物放在一起验收。

它关注两类问题：

- 指标是否达到 Phase 2 的最低门槛
- 导出的 manifest / ONNX 是否和训练配置一致，并且能安全用于浏览器加载

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/verify-training-release.ts --metrics model/exports/nail-texture-seg-v1/metrics.json --manifest public/models/nail-texture-seg/manifest.json
```

也可以只检查浏览器模型目录中的 manifest / ONNX：

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-artifact.ts public/models/nail-texture-seg/manifest.json
```


完整训练发布流水线会在真实训练前默认执行训练数据总门禁：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --source-authorization-dataset-root model/datasets/nail-texture-v1
```

这一步会调用 `model/training/verify-training-dataset-readiness.ts`，串联 `sources.csv` 磁盘一致性审计、`audit-training-source-authorization.ts --mode release` 和 Phase 1 readiness 审计，并把报告写入 `model/exports/<version>/training-dataset-readiness-release.json`。如果只是验证已经存在的旧产物，或在受控调试场景下临时跳过该门禁，可以显式追加 `--skip-source-authorization`；正式训练不建议跳过。
## 默认门槛

- `seg_map50 >= 0.75`
- `box_map50 >= 0.85`
- `model size <= 15MB` and `model size >= 256KB`; the lower bound prevents tiny placeholder ONNX files from passing release verification. The ideal browser target remains `<= 8MB`, reported through `sizeTier`.

## 检查内容

训练发布检查会确认：

- `metrics.json` 不是 dry-run 输出
- `metrics.split` 是否为 `test`
- `metrics.imgsz` 是否和 manifest `inputSize` 一致
- `seg_map50` / `box_map50` 是否达标
- 模型文件是否存在
- ONNX 大小是否超出 15MB、是否低于 256KB 占位阈值，以及是否超过 8MB 理想目标
- manifest label 是否包含 `nail_texture`

模型 artifact 检查还会确认：

- `manifest.task` 必须是 `segment`
- `manifest.modelFile` 必须是当前 manifest 目录下的基础文件名，不能是绝对路径或子目录路径
- `manifest.modelFile` 必须指向 `.onnx`
- `manifest.backendPreferences` 只能包含当前支持的浏览器后端：`webgpu` / `wasm`
- `manifest.labels[0]` 必须是 `nail_texture`，保证类别索引和后处理逻辑一致

## 输出

脚本会打印结构化 JSON：

- `ok`
- `metrics`
- `artifact`
- `errors`
- `warnings`
- `nextSteps`

## 适用时机

- 一轮训练完成并且已经生成 `metrics.json`
- 已经把 ONNX 和 manifest 导出到浏览器目录
- 想在接入前先做一次“发布门禁”

## 发布治理中的训练数据硬闸门

`training-release-pipeline-report.json` 会保存 `artifacts.trainingDatasetReadiness`。正式治理脚本读取该字段：

- 当字段明确存在且 `ok: false` 时，`build-release-decision-report.ts` 必须输出 `hold_candidate`；即使训练流水线和最终模型审计其余部分通过，也不得晋级。
- 决策报告的 `inputs.trainingDatasetReadinessOk` 和 `artifacts.trainingDatasetReadiness` 保留判定证据。
- `build-release-trace-index.ts` 将联合审计结果规范化为 `trainingReadiness`，记录来源审计、发布授权、Phase 1 规模/质量门禁、图片与有效 mask 数量及失败步骤。
- 历史旧报告没有该字段时保持兼容；“缺失”不会伪装成“通过”，但也不会单独改变旧报告的决策。

因此，正式发布至少需要联合数据就绪审计明确通过，不能依靠跳过审计得到的空字段证明数据合规。

## Model artifact integrity metadata

`model/training/export-onnx.py` writes two integrity fields into `manifest.json` after copying the exported ONNX file:

- `modelSizeBytes`: exact byte size of the referenced ONNX file.
- `sha256`: SHA-256 digest of the referenced ONNX file.

`verify-model-artifact.ts` verifies these fields whenever they are present. `verify-training-release.ts` runs artifact verification with `--require-integrity`, so release candidates must include both fields and they must match the ONNX file on disk. This prevents a model file from being replaced without updating the manifest evidence.
