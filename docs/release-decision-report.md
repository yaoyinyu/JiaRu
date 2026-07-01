# 发布决策汇总报告

版本：v1.0  
日期：2026-07-01

这一步把 Phase 5 里已经拆开的几条链路汇总成一份可直接用于发布判断的报告：

- `training-release-pipeline-report.json`
- 可选 `compare-training-releases.ts` 输出
- 可选 `release-registry.json`

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v1/training-release-pipeline-report.json
```

如果已经有 A/B 对比结果和 registry，也可以一起带上：

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --registry public/models/nail-texture-seg/release-registry.json
```

## 它解决什么问题

之前我们已经有：

- 训练发布流水线报告
- final audit 报告
- failure summary
- A/B 对比结果
- release registry

但做最终发布判断时，仍然需要人工来回打开几份 JSON。

这条命令把它们汇总成一份 `release-decision-report.json`，重点回答：

- 当前 candidate 是否通过核心 gate
- final audit 是 `pass / needs_adjustment / blocked`
- A/B 对比是否存在回退
- 当前 registry active 版本是谁
- 是否建议直接发布、暂缓发布，还是进入人工复核

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
- `artifacts.finalAuditFailureSummary`
- `artifacts.compareSummary`
- `artifacts.registry`

## 推荐用法

建议顺序：

1. 先跑 `run-training-release-pipeline.ts`
2. 如有 baseline/candidate，对比跑 `compare-training-releases.ts`
3. 最后跑 `build-release-decision-report.ts`

这样最终发布判断会稳定落在同一份汇总报告里。
