# Phase 1 数据集 readiness gate

版本：v1.1
日期：2026-07-04

这一步把规划文档里 Phase 1 的验收门槛变成一个可执行 gate。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts
```

默认读取：

- `model/datasets/nail-texture-v1/annotations/raw-json/`
- `model/datasets/nail-texture-v1/metadata/split.json`
- `model/datasets/nail-texture-v1/metadata/sources.csv`

输出：

- `model/datasets/nail-texture-v1/metadata/phase1-readiness.json`

## 当前 gate 检查项

- 图片总数是否达到 `200`
- 有效 nail mask 是否达到 `800`
- label audit 是否没有 error 级问题
- split 是否完整：每个 annotation document 必须且只能出现在一个 split 中，split 不能引用不存在的图片
- test split 是否包含负样本
- test split 是否包含复杂背景样本

## split 完整性判定

报告中的 `splitIntegrity` 会列出三类问题：

- `missingFromSplit`：有 annotation document，但没有进入 `train/val/test` 任一 split
- `unknownInSplit`：`split.json` 引用了不存在的图片
- `duplicateInSplit`：同一图片在 split 中出现超过一次

这类问题会让 `gates.splitIntegrityPass.ok=false`，需要先重新运行 `split-dataset.ts` 或修正 `split.json`，再进入训练转换和模型训练。

## 复杂背景判定

当前实现会优先从 `sources.csv` 的 `notes` 标签里读：

- `reason=complex_background`
- `reason=background_confusion`
- `background=dark`
- `background=mixed`

所以前面的筛图和回流步骤里保留这些标签是有价值的。

## 如何解读

- `ok=true`：当前数据集已经满足 Phase 1 的最小验收门槛
- `ok=false`：报告会明确告诉你还差图片、还差 mask、split 是否不完整，还是 test split 覆盖没齐