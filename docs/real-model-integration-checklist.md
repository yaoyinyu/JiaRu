# 真实 ONNX 模型接入检查清单

这份清单用于把训练产出的真实 ONNX 模型接到浏览器端识别链路里，并在接入后快速确认问题落点。

## 1. 放置模型资产

需要至少准备：

- `public/models/nail-texture-seg/manifest.json`
- `public/models/nail-texture-seg/<your-model>.onnx`

manifest 当前至少包含：

```json
{
  "version": "nail-texture-seg-v1",
  "inputSize": 640,
  "task": "segment",
  "backendPreferences": ["webgpu", "wasm"],
  "modelFile": "nail-texture-seg-v1.onnx",
  "labels": ["nail_texture"]
}
```

## 2. 先跑资产自检

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-artifact.ts
```

重点确认：

- manifest 能读取
- `modelFile` 路径正确
- ONNX 文件真实存在
- 模型大小没有超出浏览器目标上限（默认 15MB）

## 3. 再跑识别调试脚本

```bash
node --no-warnings --experimental-strip-types scripts/verify-nail-detection.ts model/5188.jpg_wh860.jpg
```

关注输出里的这些字段：

- `backend`
- `modelVersion`
- `modelInfo.inputNames`
- `modelInfo.outputNames`
- `debugOutputs[*].name`
- `debugOutputs[*].dims`
- `debugOutputs[*].sample`
- `warnings`

## 4. 如果还是走 fallback

优先检查：

1. `warnings` 是否包含 `onnx_runtime_not_loaded`
2. `warnings` 是否包含 `onnx_session_init_failed:*`
3. manifest 里的 `backendPreferences` 是否和浏览器能力匹配
4. Worker / runtime 是否实际拿到了模型文件 URL

## 5. 如果模型 session 成功但结果为空

优先检查：

1. `modelInfo.inputNames` 是否和模型实际输入一致
2. `debugOutputs[*].dims` 是否符合预期
3. detection tensor 和 prototype tensor 是否被正确识别
4. 输出 row 的布局是否真的是 `[cx, cy, w, h, score, ...coeffs]`
5. `scoreThreshold` 是否过高

## 6. 如果候选位置不对

优先检查：

1. `inputSize` 是否和训练导出时一致
2. preprocess 缩放映射是否正确
3. `cx/cy/width/length` 是不是已经归一化或单位不同
4. 后处理里 `scaleX/scaleY` 的还原是否需要按真实模型改

## 7. 如果 mask 有但裁切效果不好

优先检查：

1. prototype tensor 的维度顺序
2. coefficients 对应的 channel 数量
3. mask threshold 是否过高/过低
4. mask 的 `scale/origin` 是否需要按真实模型输出修正

## 8. 接入完成后的最小验收

至少要重新执行：

- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`
- `node --no-warnings --experimental-strip-types scripts/verify-model-artifact.ts`
- `node --no-warnings --experimental-strip-types scripts/verify-nail-detection.ts model/5188.jpg_wh860.jpg`

并确认：

- 参考图仍能识别出 4 个候选
- fallback 仍可用
- 模型输出名 / 维度 / sample 可读
- `NailArtPicker` 不会因为模型失败而卡死
