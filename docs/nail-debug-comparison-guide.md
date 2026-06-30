# 美甲识别调试结果对比指南

这份文档用于在真实 ONNX 模型接入后，对比同一张参考图在不同识别后端或不同模型版本下的输出差异。

适用场景：

- 比较 `fallback` 与 `model`
- 比较模型 v1 与 v2
- 比较同一模型在改动前后的后处理效果

## 1. 先生成调试 JSON

对每个待比较版本，都先运行一次识别调试脚本：

```bash
node --no-warnings --experimental-strip-types scripts/verify-nail-detection.ts model/5188.jpg_wh860.jpg
```

脚本会生成：

- `nail-detection-debug.png`
- `nail-candidate-mask.png`
- `nail-skin-mask.png`
- `nail-detection-debug.json`

建议把不同版本的 JSON 另存为清晰文件名，例如：

```text
model/debug/fallback-5188.json
model/debug/model-v1-5188.json
model/debug/model-v2-5188.json
```

## 2. 运行对比脚本

```bash
node --no-warnings --experimental-strip-types scripts/compare-nail-debug.ts model/debug/fallback-5188.json model/debug/model-v1-5188.json
```

脚本会输出一份 JSON 摘要。

如果出现以下情况，脚本会返回非 0 退出码：

- 新版本候选数量少于基线
- 左到右配对后的最大中心偏差超过默认阈值 `35px`
- 新版本出现基线中没有的新 warning
- 基线中有候选无法完成配对

## 3. 输出字段怎么看

重点看这些字段：

| 字段 | 含义 |
| --- | --- |
| `ok` | 本次对比是否通过默认回归检查 |
| `baseline.backend` / `candidate.backend` | 基线和候选分别走的是 `fallback` 还是 `model` |
| `baseline.modelVersion` / `candidate.modelVersion` | 模型版本变化 |
| `countDelta` | 候选数量差值，候选减小通常要重点排查 |
| `matchedCount` | 按从左到右成功配对的候选数量 |
| `averageCenterDistance` | 平均中心偏差，越小越稳定 |
| `maxCenterDistance` | 最大中心偏差，默认超过 `35px` 视为回归 |
| `averageScoreDelta` | 候选平均分变化，正值代表整体分数更高 |
| `warningDiff.added` | 新增 warning |
| `maxCenterErrorDelta` | 如果两边都带标注真值，表示相对真值的最大中心误差变化 |
| `pairs[*]` | 每个配对候选的中心、长度、宽度、角度、分数变化 |
| `regressionReasons` | 未通过时的具体原因 |

## 4. 推荐验收方式

每次模型或后处理改动后，至少做下面这组检查：

1. 用同一张参考图分别生成基线和候选 JSON
2. 运行 `compare-nail-debug.ts`
3. 打开对应的 `nail-detection-debug.png` 肉眼确认候选框位置
4. 如果带有绿色标注图，再一起检查 `maxCenterErrorDelta`

建议最少保留三类样本：

- 标准四指参考图
- 强反光 / 金线 / 亮片图
- 复杂背景或无皮肤上下文图

## 5. 推荐判定标准

真实模型第一次接入时，至少满足：

- `ok === true`
- 候选数量不低于当前 fallback
- `maxCenterDistance <= 35`
- 没有新增致命 warning
- 如果有绿色标注真值，`maxCenterErrorDelta <= 0` 最理想；即使略有增加，也不应明显退化

## 6. 与当前流程的关系

这份对比不会替代：

- `scripts/verify-model-artifact.ts`
- `scripts/verify-nail-detection.ts`
- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`

它解决的是另一件事：判断“新模型结果是不是比旧结果更好、更稳”。
