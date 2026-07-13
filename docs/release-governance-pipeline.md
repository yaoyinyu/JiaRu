# Release 治理流水线

版本：v1.4
日期：2026-07-04

`run-release-governance-pipeline.ts` 把 Phase 5 后半段的治理动作串成统一入口：

- `build-release-decision-report.ts`
- `promote-approved-release.ts`
- `build-release-trace-index.ts`
- `register-release-trace-index.ts`
- `audit-release-rollback.ts`

目标是把“候选模型是否可发布、是否晋升、证据如何追溯、是否能安全回滚”收口到同一条标准链路。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/run-release-governance-pipeline.ts --training-release-pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json --registry public/models/nail-texture-seg/release-registry.json --release-trace-draft model/exports/nail-texture-seg-v2/release-trace-draft.json --history-manifest model/exports/nail-texture-seg-v2/release-history-manifest.json
```

## 流水线步骤

1. 生成 `release-decision-report.json`。
2. 如果决策允许自动晋升，执行 `promote-approved-release.ts`。
3. promotion 成功后登记模型版本，并生成 registry 快照。
4. promotion 成功后执行 `audit-release-rollback.ts`，确认至少有一个可用回滚候选。
5. 不管 candidate 是否被放行，都生成 `release-trace-index.json`。
6. 只有 promotion 成功后，才把 trace 登记进 `release-history-manifest.json`。

这样可以覆盖两类场景：

- 放行 candidate：得到发布、registry、rollback audit、trace、history 闭环。
- 拦截 candidate：不发布，但仍保留 decision + trace，方便后续复盘。

## 关键参数

- `--training-release-pipeline-report <training-release-pipeline-report.json>`：必填，训练发布流水线报告。
- `--compare-summary <compare-summary.json>`：可选，A/B 对比结果。
- `--performance-report <performance-report.json>`：可选，桌面或手机识别性能门禁报告；失败时阻止 promotion。
- `--registry <release-registry.json>`：可选，模型 registry。
- `--rollback-audit-report <rollback-audit-report.json>`：可选，回滚审计输出路径。
- `--release-trace-draft <release-trace-draft.json>`：可选，把初始 draft 升级成正式 trace。
- `--reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>`：可选，直接从 reviewed batch import 链接 batch 来源。
- `--history-manifest <release-history-manifest.json>`：可选，指定历史台账。
- `--allow-manual-review true|false`：是否允许人工放行 `manual_review`。
- `--set-current true|false`：promotion 成功后是否切为 current version。
- `--promote true|false`：是否启用 promotion 步骤。

## 默认输出

默认在 `training-release-pipeline-report.json` 同一目录生成：

- `release-decision-report.json`
- `promotion-report.json`
- `rollback-audit-report.json`
- `release-trace-index.json`
- `trace-registration-report.json`
- `release-governance-pipeline-report.json`

## 重点输出字段

`release-governance-pipeline-report.json` 会汇总：

- `steps`
- `artifacts.releaseDecision`
- `artifacts.promotion`
- `artifacts.rollbackAudit`
- `artifacts.traceIndex`
- `artifacts.traceRegistration`
- `artifacts.historyManifest`

`artifacts.traceIndex.performance` 会保留发布决策使用的性能快照：

- `performance.ok`
- `performance.profile`
- `performance.maxElapsedMs`
- `performance.p95Ms`
- `performance.maxMs`
- `performance.slowSamples`
- `performance.performanceReportPath`

`artifacts.traceIndex.quality` 会保留发布决策使用的纹理质量快照：

- `quality.phase2ExtractionRateOk`
- `quality.directlyUsableRate`
- `quality.phase2ExtractionEvidenceOk`
- `quality.phase2ExtractionEvidenceScope`
- `quality.phase2RequiredUsableRate`，固定为 `0.8`
- `quality.phase4TextureQualityGateOk`
- `quality.contaminationRate`

如果候选版本因为性能超预算、提取率低于 80%、或证据不是 `release-test-split` 被拦截，trace 都会记录对应快照。旧决策报告缺少这些字段时写入 `null`，不会伪造通过状态。

## 自动回滚审计

当 `promote-approved-release.ts` 成功执行后，治理流水线会自动继续执行 `audit-release-rollback.ts`，并把结果写入默认的 `rollback-audit-report.json`。这一步会检查：

- 发布后 registry 是否仍然保留至少一个可用旧版本。
- 旧版本 manifest 快照和 ONNX 文件是否存在。
- registry 中的 `modelSizeBytes` 和 `sha256` 是否合法。
- ONNX 文件实际大小和 SHA-256 是否与 registry 完全一致。
- 当前 manifest 是否与 registry 的 `currentVersion` 一致。

如果 promotion 成功但回滚审计失败，`release-governance-pipeline-report.json` 会整体 `ok: false`，避免发布链路进入“已经升级但不可验证回滚”的危险状态。

治理总报告会包含：

- `paths.rollbackAuditReportPath`
- `artifacts.rollbackAudit`
- `steps[]` 中的 `audit-release-rollback`

## 成功与失败语义

- candidate 被批准并完成 promotion / rollback audit / trace / history 时，流水线整体 `ok: true`。
- candidate 被判定为 `hold_candidate` 时，流水线整体 `ok: false`。
- 即使 `ok: false`，仍应该能看到 decision 和 trace 产物，用于后续复盘。

## 推荐顺序

1. `run-training-release-pipeline.ts`
2. `compare-training-releases.ts`
3. `verify-recognition-performance.ts`
4. `run-release-governance-pipeline.ts`

完整链路为：训练发布产物 → 指标/性能对比 → 决策 → 安全晋升 → 回滚审计 → trace 建档 → history 入账。
## release-history active learning 摘要

`build-release-history-manifest.ts` 现在会从每个 `release-trace-index.json` 汇总 active-learning 信息，方便跨版本查看页面修正样本是否正在改善模型链路。

历史台账会保留：

- `totals.activeLearningTraceIndexes`
- `totals.activeLearningImportedSamples`
- `activeLearning.importedByPriority`
- `activeLearning.warningBreakdown`
- `activeLearning.backendBreakdown`
- `entries[].activeLearningImportedSampleCount`
- `entries[].activeLearningWarningBreakdown`
- `entries[].activeLearningReadinessTotals`

这样不用打开单个 trace，也能直接看到某个版本是否吸收过高优先级 debug sample，以及这些样本主要暴露的是模型运行时、fallback、后处理还是数据问题。
## active-learning warning manual_review 默认行为

当 `compare-summary.json` 中的 active-learning warning delta 增加时，`build-release-decision-report.ts` 会把候选版本判为 `manual_review`。`run-release-governance-pipeline.ts` 默认不会自动 promotion 这类候选，但仍会生成 `release-trace-index.json`，保留 decision、compare、active-learning warning delta 等证据，方便复盘。

如果人工确认这些 warning 可以接受，才显式使用：

```bash
--allow-manual-review true
```

这样 active-learning 回流暴露的新风险不会被静默发布，同时也不会丢失治理 trace。
## active-learning manual_review 人工放行

如果 active-learning warning delta 增加导致候选进入 `manual_review`，默认不会自动 promotion。只有人工确认风险可接受后，才使用：

```bash
--allow-manual-review true
```

此时治理流水线会继续执行 promotion、trace registration 和 rollback audit，并在 history manifest 中保留 `decisionStatus: "manual_review"`，表示该版本不是自动无风险放行，而是人工确认后放行。

## training release pipeline 中的 active-learning 人工放行

`run-training-release-pipeline.ts` 也会透传同一套治理参数。也就是说，一键训练发布流水线在读取 `compare-summary.json` 时，如果发现 `deltas.activeLearningWarnings` 有正向增量，会继承 release decision 的 `manual_review` 结果。

默认不加参数时，这类候选不会自动 promotion；只有显式传入：

```bash
--governance-allow-manual-review true
```

总流水线才会继续执行 `promote-approved-release`、trace registration、rollback audit 和 history manifest 登记。验收重点是：`training-release-pipeline-report.json` 里的 `artifacts.releaseGovernance.artifacts.releaseDecision.decision.status` 保留 `manual_review`，promotion 报告里的 `decisionStatus` 也保留 `manual_review`，避免把人工确认放行误读成普通自动通过。

## release-history performance summary

`build-release-history-manifest.ts` now summarizes performance evidence from every registered `release-trace-index.json`. The history manifest keeps per-entry performance fields and aggregate counters so reviewers can compare latency risk across candidate versions:

- `totals.performanceTraceIndexes`
- `totals.failedPerformanceTraceIndexes`
- `totals.performanceSlowSamples`
- `totals.performanceSlowClientOverheadSamples`
- `totals.performanceMissingWorkerTimingSamples`
- `performance.statusCounts`
- `performance.profileCounts`
- `performance.slowSamples`
- `performance.slowClientOverheadSamples`
- `performance.missingWorkerTimingSamples`

This extends the Phase 5 release history from promotion status tracking into performance-risk tracking, especially for client overhead regressions that are separate from Worker/model runtime cost.

## release-history quality summary

`build-release-history-manifest.ts` also summarizes texture-quality evidence from each release trace. The history manifest now keeps aggregate quality counters and per-entry quality fields so Phase 2/Phase 4 quality trends can be reviewed across candidate versions without opening each trace manually:

- `totals.qualityTraceIndexes`
- `totals.failedPhase2ExtractionTraceIndexes`
- `totals.failedTextureQualityTraceIndexes`
- `totals.averageDirectlyUsableRate`
- `totals.averageContaminationRate`
- `quality.phase2ExtractionStatusCounts`
- `quality.textureQualityStatusCounts`
- `quality.phase2EvidenceScopeCounts`

This keeps the version-history ledger aligned with the planning document's quality goals: usable texture extraction rate, release-test-split evidence, and contamination rate remain visible after trace registration.

## release-history failure summary

`build-release-trace-index.ts` now preserves the full final-audit failure summary from the training release pipeline instead of only keeping the two legacy counters. Each trace keeps:

- `release.failureCategoryCounts`
- `release.failureSummaryTotals`
- `release.derivedAnnotationFailures`
- `release.postprocessFailures`

`build-release-history-manifest.ts` then rolls these fields into cross-version history fields so review can quickly see whether failures are concentrated in postprocess, inferred-record, low-confidence, or other categories:

- `totals.failureTraceIndexes`
- `totals.failureCategoryTotal`
- `totals.failureSummaryCsvRows`
- `totals.failureSummaryInferredRecordFailures`
- `failureSummary.categoryBreakdown`
- `failureSummary.categoryTotal`
- `failureSummary.csvRows`
- `failureSummary.inferredRecordFailures`
- `failureSummary.derivedAnnotationFailures`
- `failureSummary.postprocessFailures`
- `entries[].failureCategoryCounts`
- `entries[].failureSummaryTotals`

This keeps Phase 5 release history useful even before real model training is resumed: every candidate can still explain what failed and which failure class is trending across versions.


## First-run visual evidence in release trace

`build-release-trace-index.ts` now preserves `release.firstRunOutputs` from the final audit report. This includes `recognitionMaskPath` when available, so a formal release trace can link a candidate version directly to the debug JSON, rectangle overlay, fallback masks, recognition mask overlay, model-output dump, and fixture evidence produced during the real-model first run.


## First-run visual evidence in release history

`build-release-history-manifest.ts` now keeps `entries[*].firstRunOutputs` and aggregate counters for visual evidence. `totals.visualEvidenceTraceIndexes` counts traces with first-run output evidence, while `totals.recognitionMaskEvidenceTraceIndexes` counts traces that include a non-empty `recognitionMaskPath`. This makes the version history useful for checking whether each candidate preserved mask-overlay evidence without opening every trace manually.


## Visual evidence in release comparison

`compare-training-releases.ts` now consumes the same `release.firstRunOutputs` evidence preserved by release trace and release history. During baseline/candidate comparison it reports visual-evidence snapshots for each side and warns if the candidate loses `recognitionMaskPath`. This makes the release governance chain continuous: first-run record -> final audit -> trace index -> history manifest -> A/B comparison.


## Visual evidence manual_review

Release governance now inherits visual-evidence deltas from the compare summary through `build-release-decision-report.ts`. If a candidate loses first-run output evidence or recognition-mask overlay evidence, the decision becomes `manual_review`; the governance pipeline will not auto-promote it unless `--allow-manual-review true` is used after explicit human review.


## Visual evidence manual_review acceptance

The governance pipeline now has explicit regression coverage for visual-evidence manual reviews:

- without `--allow-manual-review true`, a candidate with negative `deltas.firstRunVisualEvidence` or `deltas.recognitionMaskEvidence` keeps building the decision and trace index but skips promotion, trace registration, and rollback audit;
- with `--allow-manual-review true`, the same candidate can be promoted, while promotion, trace index, and release history still preserve `decisionStatus: "manual_review"`.

This proves the visual evidence risk follows the same explicit human-release path as active-learning warning reviews.


## MVP readiness visual-evidence governance audit

`audit-nail-texture-mvp-readiness.ts` now includes `release_visual_evidence_governance`. This check verifies that the visual-evidence risk path is present across compare, release decision, governance pipeline tests, training-release pipeline tests, and documentation. It prevents the MVP audit from passing with only generic release-governance files present while the first-run/recognition-mask manual-review path is missing.


## MVP readiness release-history evidence ledger audit

`audit-nail-texture-mvp-readiness.ts` also includes `release_history_evidence_ledger`. This check verifies that release history keeps the cross-version evidence ledger for performance, quality, failure taxonomy, active-learning imports, and first-run visual evidence. It prevents the readiness audit from passing if history only records version names while dropping the review signals needed to compare candidates safely before real training is resumed.
