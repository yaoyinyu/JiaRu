# 真实模型接入 SOP

这份 SOP 用于把真实 `ONNX` 模型放进项目后，按固定步骤完成一次端到端接入验收。

## 第 0 步：准备文件

把下面两个文件放到：

```text
public/models/nail-texture-seg/
```

需要存在：

- `manifest.json`
- `nail-texture-seg-v1.onnx`（或 manifest 中声明的其他文件名）

## 第 1 步：检查 manifest 和模型文件是否自洽

在项目根目录运行：

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-artifact.ts
```

预期：

- `ok: true`
- `modelExists: true`
- 没有 `errors`

如果失败，先不要继续往下走，先修：

- manifest 路径
- `modelFile` 文件名
- 模型大小是否超过限制

## 第 2 步：跑参考图识别调试

```bash
node --no-warnings --experimental-strip-types scripts/verify-nail-detection.ts model/5188.jpg_wh860.jpg
```

这条命令现在会同时产出：

- `nail-detection-debug.png`
- `nail-candidate-mask.png`
- `nail-skin-mask.png`
- `nail-detection-debug.json`

重点打开：

- 终端输出 JSON
- `nail-detection-debug.json`
- `nail-detection-debug.png`

## 第 3 步：先看是不是还在走 fallback

在 `nail-detection-debug.json` 里先看：

- `backend`
- `warnings`
- `modelInfo`

判断：

- 如果 `backend === "fallback"`：
  - 优先看 `warnings`
  - 常见值：
    - `onnx_runtime_not_loaded`
    - `onnx_session_init_failed:*`
    - `model_outputs_empty_used_fallback`

- 如果 `backend === "model"`：
  - 说明 session 至少成功初始化过
  - 继续往下看输出张量结构

## 第 4 步：检查输入输出名字

查看：

- `modelInfo.inputNames`
- `modelInfo.outputNames`

目标：

- 确认当前代码喂给 session 的输入名和模型实际输入名一致
- 确认模型输出张量名是否符合预期

如果输出名和你想象的不一样，不用先改大逻辑，先记录真实名字。

## 第 5 步：检查输出张量摘要

查看：

- `debugOutputs[*].name`
- `debugOutputs[*].dims`
- `debugOutputs[*].sample`

目标：

- 确认哪个张量像 detection tensor
- 确认哪个张量像 prototype tensor
- 确认 sample 值是否合理，不是全 0 / 全 NaN / 全常数

## 第 6 步：检查候选结果

查看：

- `count`
- `regions`
- `maxCenterError`（如果带了绿圈标注）

最低目标：

- 当前参考图仍然至少产出 4 个候选
- `maxCenterError` 不明显退化

## 第 7 步：打开网页做 UI 验收

启动项目后进入：

```text
/ar-tryon
```

然后上传参考图，确认：

- 页面不会卡死
- 可以取消
- `NailArtPicker` 仍能打开
- 顶部能看到“模型识别”或“回退识别”
- 如模型失败，会自动回退而不是直接不可用

## 第 8 步：跑完整静态验收

```bash
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

必须同时通过。

## 第 9 步：如果出问题，按优先级排查

1. 模型文件不存在 / 路径不对
2. session 初始化失败
3. input name 不对
4. output name / dims 和当前 postprocess 假设不一致
5. detection/prototype 张量识别错位
6. score threshold 太高
7. mask decode 参数不匹配

## 第 10 步：接入完成的最低完成线

满足以下几点，才算真实模型初步接入成功：

- 资产校验通过
- 参考图脚本能跑完
- 输出张量摘要可读
- 页面里可以触发模型路径
- 模型失败时 fallback 仍然可用
- `npm.cmd test` / `lint` / `build` 全通过
