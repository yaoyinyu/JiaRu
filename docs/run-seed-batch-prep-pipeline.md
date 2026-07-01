# Seed batch 预处理流水线

版本：v1.0  
日期：2026-07-01

这条流水线把一个真实 seed batch 从筛图记录自动推进到“人工修正前”。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-seed-batch-prep-pipeline.ts --root-dir "C:/path/to/seed-batch-001"
```

## 会自动串起来的步骤

- `audit-seed-batch-workspace.ts`
- `audit-screening-review.ts`
- `build-reviewed-intake-batch.ts`
- `prepare-reviewed-annotations.ts`

## 结果

执行成功后，工作区会至少具备：

- `selected/images/`
- `selected/<sourceGroup>.manifest.json`
- `selected/annotations/raw-json/*.json`
- `selected/reviewed-annotation-prep-report.json`

它适合在开始人工修正之前，先把可自动推进的步骤一次性跑完。
