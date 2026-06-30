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
- `client-worker.ts` 是否传递 `preferModel` / `manifestUrl`
- worker 是否调用识别逻辑并回传响应
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
