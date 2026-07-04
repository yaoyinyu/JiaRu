# 发布决策汇总报告

版本：v1.4
日期：2026-07-04

`build-release-decision-report.ts` 会把训练发布链路末端生成的关键产物汇总成一份可用于判断“是否放行候选模型”的报告：

- `training-release-pipeline-report.json`
- 可选的 `compare-summary.json`
- 可选的 `performance-report.*.json`
- 可选的 `release-registry.json`

它会同时消费 final audit、训练数据 readiness、A/B 对比、识别性能门禁、纹理质量门禁和发布证据代表性信息。

## 命令

基础命令：

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v1/training-release-pipeline-report.json
```

带 A/B 对比、性能报告和 registry：

```bash
node --no-warnings --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report model/exports/nail-texture-seg-v2/training-release-pipeline-report.json --compare-summary model/exports/nail-texture-seg-v2/compare-summary.json --performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json --registry public/models/nail-texture-seg/release-registry.json
```

也兼容从 `training-release-pipeline-report.json` 的 `artifacts.recognitionPerformance` 读取性能报告。

## 决策状态

- `approve_candidate`：核心发布门禁全部通过，可以进入自动 promotion。
- `manual_review`：核心门禁通过，但仍有剩余质量风险，需要人工复核。
- `hold_candidate`：候选不能发布。

## 硬阻断规则

以下任一情况会进入 `hold_candidate`：

- training release pipeline 未通过。
- final audit 为 `blocked`。
- compare 出现回退。
- recognition performance 明确失败，例如桌面或手机样本超过耗时预算。
- training dataset readiness 明确失败。
- Phase 2 可用纹理提取率低于 `0.80`。
- 已有纹理质量门禁结果，但其发布证据不是 release-test-split，或样本量证据不通过。

性能门禁的原则是：如果你把性能报告交给发布决策，它就会被当成硬证据。`ok === false` 时候选不能晋升，因为 Phase 3 明确要求浏览器端本地推理不能拖垮 UI。

纹理质量证据也必须配套：

```json
{
  "evidence": {
    "ok": true,
    "scope": "release-test-split",
    "representativeTestSplit": true
  }
}
```

否则该结果只能算本地调试信号，不能当作发布证据。

## 人工复核规则

以下情况通常进入 `manual_review`：

- Phase 2 可用纹理提取率达到 `0.80`，但 Phase 4 质量门禁仍失败。
- final audit 虽未 blocked，但还有 postprocess 或 derived annotation 风险信号。

## 输出字段

默认输出到 pipeline report 同目录下：

```text
release-decision-report.json
```

主要字段包括：

- `decision.status`
- `decision.summary`
- `decision.reasons`
- `decision.nextActions`
- `inputs.pipelineOk`
- `inputs.trainingDatasetReadinessOk`
- `inputs.finalAuditStatus`
- `inputs.compareOk`
- `inputs.recognitionPerformanceOk`
- `inputs.recognitionPerformanceProfile`
- `inputs.recognitionPerformanceMaxElapsedMs`
- `inputs.recognitionPerformanceP95Ms`
- `inputs.recognitionPerformanceMaxMs`
- `inputs.recognitionPerformanceSlowSamples`
- `inputs.derivedAnnotationFailures`
- `inputs.postprocessFailures`
- `inputs.textureQualityGateOk`
- `inputs.phase2ExtractionRateOk`
- `inputs.phase2ExtractionEvidenceOk`
- `inputs.phase2ExtractionEvidenceScope`
- `inputs.directlyUsableRate`
- `inputs.contaminationRate`
- `artifacts.recognitionPerformance`
- `artifacts.finalAuditFailureSummary`
- `artifacts.finalAuditTextureQualityGate`
- `artifacts.compareSummary`
- `artifacts.registry`

## 推荐使用顺序

1. 跑 `run-training-release-pipeline.ts`。
2. 如有 baseline/candidate，跑 `compare-training-releases.ts`。
3. 从真实 debug sample 或 final audit 产物跑 `verify-recognition-performance.ts`。
4. 跑 `build-release-decision-report.ts`。
5. 如果需要一键串联 promotion、trace、history，继续跑 `run-release-governance-pipeline.ts`。