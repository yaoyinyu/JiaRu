# 修正后 batch 回流流水线

版本：v1.0  
日期：2026-07-01

这条流水线把人工修正完成后的 seed batch 一次性推进到正式数据集，并立即跑 Phase 1 gate。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir "C:/path/to/seed-batch-001"
```

## 会自动串起来的步骤

- `audit-seed-batch-workspace.ts`
- `import-reviewed-batch.ts`
- `audit-phase1-readiness.ts`
- `plan-phase1-collection.ts`
- `generate-first-batch-checklist.ts`

## 说明

- `import-reviewed-batch.ts` 必须成功
- `audit-phase1-readiness.ts` 是软检查：即使当前还没达到 `200 / 800` 门槛，也会保留报告并继续返回流水线成功
- `plan-phase1-collection.ts` 会把缺口翻译成下一批补样本方向
- `generate-first-batch-checklist.ts` 会同步刷新首批/下一批的执行清单

适合在人工修正完成后，快速看这批样本导入后对正式数据集的实际提升。
