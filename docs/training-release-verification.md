# 训练结果与导出产物验收

版本：v1.0  
日期：2026-07-01

这一步用于把一版训练结果和浏览器端导出产物放在一起验收。

它关注两类问题：

- 指标是否达到 Phase 2 的最低门槛
- 导出的 manifest / ONNX 是否和训练配置一致

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/verify-training-release.ts --metrics model/exports/nail-texture-seg-v1/metrics.json --manifest public/models/nail-texture-seg/manifest.json
```

## 默认门槛

- `seg_map50 >= 0.75`
- `box_map50 >= 0.85`
- `model size <= 15MB`

## 检查内容

- `metrics.json` 不是 dry-run 输出
- `metrics.split` 是否为 `test`
- `metrics.imgsz` 是否和 manifest `inputSize` 一致
- `seg_map50` / `box_map50` 是否达标
- 模型文件是否存在
- ONNX 大小是否超标
- manifest label 是否包含 `nail_texture`

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
