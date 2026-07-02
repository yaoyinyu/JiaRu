# Release 治理流水线

版本：v1.0  
日期：2026-07-02

这条流水线把原本分散的几个 Phase 5 脚本串成一个统一入口：

- `build-release-decision-report.ts`
- `promote-approved-release.ts`
- `build-release-trace-index.ts`
- `register-release-trace-index.ts`

目标是把“训练发布产物已经准备好”之后的治理动作变成一条标准顺序，而不是每次手工记忆执行步骤。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/run-release-governance-pipeline.ts --training-release-pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --registry public/models/nail-texture-seg/release-registry.json --release-trace-draft model/exports/nail-texture-seg-v2/release-trace-draft.json --history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

## 它会做什么

1. 先生成 `release-decision-report.json`
2. 如果决策允许自动晋升，再执行 `promote-approved-release.ts`
3. 不管 candidate 是否被放行，都会继续生成 `release-trace-index.json`
4. 只有在 promotion 真实成功后，才会把 trace 自动登记进 `release-history-manifest.json`

这样我们可以同时覆盖两类场景：

- 放行 candidate：得到完整的发布、trace、history 闭环
- 拦截 candidate：虽然不会发布，但仍然保留这次 candidate 的 decision + trace 记录

## 关键参数

- `--training-release-pipeline-report <training-release-pipeline-report.json>`：必填，训练发布流水线报告
- `--compare-summary <compare-summary.json>`：可选，A/B 对比结果
- `--registry <release-registry.json>`：可选，模型 registry
- `--release-trace-draft <release-trace-draft.json>`：可选，把初始 draft 升级成正式 trace
- `--reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>`：可选，直接从 reviewed batch import 链接 batch 来源
- `--history-manifest <release-history-manifest.json>`：可选，指定历史台账
- `--allow-manual-review true|false`：是否允许人工放行 `manual_review`
- `--set-current true|false`：promotion 成功后是否切为 current version
- `--promote true|false`：是否启用 promotion 步骤

## 默认输出

默认和 `training-release-pipeline-report.json` 放在同一目录：

- `release-decision-report.json`
- `promotion-report.json`
- `release-trace-index.json`
- `trace-registration-report.json`
- `release-governance-pipeline-report.json`

## 输出含义

总报告 `release-governance-pipeline-report.json` 会汇总：

- 输入参数
- 各步骤执行结果
- decision / promotion / trace / history 的最终产物

重点看：

- `steps`
- `artifacts.releaseDecision`
- `artifacts.promotion`
- `artifacts.traceIndex`
- `artifacts.traceRegistration`
- `artifacts.historyManifest`

## 成功与失败语义

- 当 candidate 被批准并完成 promotion / trace / history 时，流水线整体 `ok: true`
- 当 candidate 被判定为 `hold_candidate` 时，流水线整体 `ok: false`
- 即使 `ok: false`，仍然应该能看到 decision 和 trace 产物，用于后续复盘

## 推荐顺序

建议完整顺序：

1. `run-training-release-pipeline.ts`
2. `compare-training-releases.ts`
3. `run-release-governance-pipeline.ts`

这样就把 Phase 5 后半段真正收口成：

训练发布产物 → 决策 → 安全晋升 → trace 建档 → history 入账
