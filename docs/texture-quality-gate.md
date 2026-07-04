# 纹理可用率 / 污染率 / 形状保真质量门禁

版本：v1.2
日期：2026-07-04

这一步对应 `docs/nail-texture-recognition-model-plan.md` 中 Phase 4 的量化验收目标：

- 用户无需调整即可直接使用的纹理样本比例 > 85%。
- 纹理中明显皮肤 / 背景污染比例 < 10%。
- 异形甲、圆甲、长甲不能被批量退化成粗糙矩形裁剪。
- 发布候选模型必须说明质量证据来自独立发布测试集，而不是少量本地 debug 样本。

## 实现位置

- `scripts/verify-texture-quality-gate.ts`
- `scripts/run-real-model-final-audit.ts`

## 检查内容

### 1. 可直接使用率

报告字段：

- `totals.directlyUsableCandidates`
- `rates.directlyUsableRate`

一个候选纹理被算作“可直接使用”需要同时满足：

- 没有 candidate warnings。
- 没有 extraction quality warnings。
- `extractionQualityOk !== false`。
- `highlightRatio < 0.12`。
- `highlightPixels < 8`。

默认门槛：`directlyUsableRate >= 0.85`。

### 2. 污染率

报告字段：

- `totals.contaminatedCandidates`
- `rates.contaminationRate`

当前污染候选先按 `dirty_mask_crop` 统计，用来捕捉皮肤或背景混入纹理裁剪的核心风险。

默认门槛：`contaminationRate < 0.1`。

### 3. 形状保真 / 粗糙矩形率

报告字段：

- `totals.candidatesWithPolygon`
- `totals.roughRectangleCandidates`
- `rates.roughRectangleRate`

粗糙矩形判定口径：

- polygon 点数少于 `minPolygonPointsForShapePreserved`，默认 `5`；或
- polygon 面积 / 外接 bounds 面积大于等于 `maxPolygonBoundsFillRatio`，默认 `0.96`。

默认门槛：`roughRectangleRate <= 0.15`。

### 4. 发布证据代表性

报告字段：

- `evidence.scope`
- `evidence.ok`
- `evidence.representativeTestSplit`
- `evidence.minDocuments`
- `evidence.minCandidatesWithDebug`
- `evidence.minCandidatesWithPolygon`

本地调试默认使用 `--evidence-scope local-debug`。如果结果要作为发布候选证据，必须使用：

```bash
--evidence-scope release-test-split
```

并配置足够的样本量门槛，例如：

```bash
--min-documents 50 --min-candidates-with-debug 200 --min-candidates-with-polygon 200
```

发布决策层会硬性要求 `evidence.scope === "release-test-split"` 且 `evidence.ok === true`。也就是说，即使 1 张图跑出 100% 可用率，也不能作为模型发布证据。

## 常用命令

本地调试：

```bash
node --no-warnings --experimental-strip-types scripts/verify-texture-quality-gate.ts --annotation-dir C:/path/to/annotations --output C:/path/to/texture-quality-gate.json
```

发布测试集验收：

```bash
node --no-warnings --experimental-strip-types scripts/verify-texture-quality-gate.ts --annotation-dir C:/path/to/test-annotations --output C:/path/to/texture-quality-gate.json --evidence-scope release-test-split --min-documents 50 --min-candidates-with-debug 200 --min-candidates-with-polygon 200
```

可调参数：

- `--min-usable-rate 0.85`
- `--max-contamination-rate 0.1`
- `--min-documents 1`
- `--min-candidates-with-debug 1`
- `--min-candidates-with-polygon 1`
- `--max-highlight-ratio-for-usable 0.12`
- `--max-highlight-pixels-for-usable 8`
- `--max-rough-rectangle-rate 0.15`
- `--min-polygon-points-for-shape-preserved 5`
- `--max-polygon-bounds-fill-ratio 0.96`

## 输出内容

`texture-quality-gate.json` 包含：

- `ok`
- `annotationDirPath`
- `thresholds`
- `evidence`
- `totals`
- `rates`
- `warningBreakdown`
- `warnings`
- `nextSteps`

这样后续不只知道“过 / 没过”，还知道问题来自：可用率不足、污染率过高、polygon 粗糙矩形化，还是验收样本证据不足。

## 自动化验收

覆盖测试：

- `tests/verify-texture-quality-gate.test.ts`
  - 可用率 / 污染率 / 形状保真通过场景。
  - 低可用率 / 高污染率 / 粗糙矩形 polygon 失败场景。
  - 发布测试集样本量不足时失败。
- `tests/run-real-model-final-audit.test.ts`
  - final audit 会带出 `texture-quality-gate.json`。