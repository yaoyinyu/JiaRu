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