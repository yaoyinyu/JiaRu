# 发布决策汇总报告

版本：v1.1  
日期：2026-07-03

这一步把训练发布链路末端已经生成的关键产物汇总成一份可直接用于“是否放行 candidate”的决策报告：

- `training-release-pipeline-report.json`
- 可选的 `compare-summary.json`
- 可选的 `release-registry.json`

现在它除了汇总 final audit 和 compare 结果，也会同步消费 `texture-quality-gate.json` 已经回写到 training release pipeline report 里的纹理质量门禁结果。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v1/training-release-pipeline-report.json
```

如果已经有 A/B 对比结果和 registry，也可以一起传入：

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --registry public/models/nail-texture-seg/release-registry.json
```

## 它解决什么问题

在进入发布决策前，我们通常已经有：

- training release pipeline 报告
- final audit 报告
- failure summary
- texture quality gate
- A/B compare 结果
- release registry

这些信息之前是分散的，人工判断时需要来回翻多份 JSON。  
这条命令会把它们收束成一份 `release-decision-report.json`，重点回答：

- 当前 candidate 是否通过核心 gate
- final audit 是 `pass / needs_adjustment / blocked`
- compare 是否存在回退
- 当前 registry 的 active version 是谁
- texture quality gate 是否通过
- 纹理裁剪是否已经达到“可直接用于后续贴图识别”的质量水平
- 当前更适合：
  - 直接放行
  - 暂缓发布
  - 进入人工复核

## 决策规则补充

当前决策分三档：

- `approve_candidate`
- `manual_review`
- `hold_candidate`

其中：

- 训练发布链路失败、final audit 为 `blocked`、或 compare 出现回退时，会进入 `hold_candidate`
- 如果核心 gate 都通过，但仍有剩余风险信号，会进入 `manual_review`

现在新增了一条剩余风险信号：

- `finalAuditTextureQualityGate.ok === false`

也就是说，哪怕模型训练、导出、final audit 和 compare 都通过了，只要纹理质量门禁显示：

- 可直接使用率偏低，或
- 污染率偏高

这版 candidate 也不会被直接标成 `approve_candidate`，而是进入 `manual_review`，要求先人工检查纹理裁剪质量。

## 输出

默认输出到与 pipeline report 同目录下的：

```text
release-decision-report.json
```

主要字段包括：

- `decision.status`
  - `approve_candidate`
  - `manual_review`
  - `hold_candidate`
- `decision.summary`
- `decision.reasons`
- `decision.nextActions`
- `inputs.pipelineOk`
- `inputs.finalAuditStatus`
- `inputs.compareOk`
- `inputs.derivedAnnotationFailures`
- `inputs.postprocessFailures`
- `inputs.textureQualityGateOk`
- `inputs.directlyUsableRate`
- `inputs.contaminationRate`
- `artifacts.finalAuditFailureSummary`
- `artifacts.finalAuditTextureQualityGate`
- `artifacts.compareSummary`
- `artifacts.registry`

## 推荐用法

建议顺序：

1. 先跑 `run-training-release-pipeline.ts`
2. 如有 baseline/candidate，对比跑 `compare-training-releases.ts`
3. 最后跑 `build-release-decision-report.ts`

如果 training release pipeline 已经接入了 final audit 的 texture quality gate，这一步就会把“模型是否能跑”和“纹理是否够干净、够可用”一起纳入发布判断。
