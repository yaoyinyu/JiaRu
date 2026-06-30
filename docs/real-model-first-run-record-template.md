# 真实模型首轮联调记录模板

这份模板用于第一次把真实 ONNX 模型接进项目后，统一记录：

- 模型资产状态
- readiness 结果
- 单图验证结果
- 输出张量结构观察
- 是否通过首轮接入

模板文件：

```text
model/fixtures/real-model-first-run-record.template.json
```

## 推荐填写时机

按这个顺序：

1. 跑 `verify-real-model-readiness.ts`
2. 如果拿到了 `nail-model-output-dump.json`，补跑 fixture 验证链
3. 打开 `/ar-tryon` 做一次 UI 验收
4. 把结果整理进模板

## 至少要填的关键字段

- `model.artifactOk`
- `readiness.ok`
- `outputs.debugJsonPath`
- `outputs.modelOutputDumpPath`
- `observations.backend`
- `observations.candidateCount`
- `observations.outputNames`
- `observations.outputDims`
- `decision.status`
- `decision.summary`
- `decision.nextActions`

## 建议判定规则

- `pass`
  - 模型文件存在
  - readiness 通过
  - 单图验证候选数量不低于当前 fallback 基线
  - 输出张量结构可解释
  - UI 可正常回退、不阻塞

- `needs_adjustment`
  - 模型能跑，但候选位置、mask、score、输出布局还需要适配

- `blocked`
  - 缺少 ONNX 文件
  - session 根本无法初始化
  - 输出张量无法解析，且当前证据不足以继续定位

## 与现有脚本的关系

这份模板不替代脚本，它只负责“沉淀结果”。

建议把下面几类信息抄进来：

- `verify-model-artifact.ts` 的摘要
- `verify-real-model-readiness.ts` 的摘要
- `verify-nail-detection.ts` 生成的 debug JSON 路径
- `verify-model-output-fixture.ts` 的候选数量、输出维度和 failures
