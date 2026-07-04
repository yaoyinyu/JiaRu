# 修正后 batch 回流流水线

版本：v1.1
日期：2026-07-04

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
- `build-initial-release-trace-draft.ts`
- `build-reviewed-batch-release-handoff.ts`

## 说明

- `import-reviewed-batch.ts` 必须成功
- `import-reviewed-batch.ts` 的导入报告会写入 `readinessSnapshot`，单独运行 import 时也能看到 Phase 1 差距
- `import-reviewed-batch.ts` 还会写入 `trainingDatasetReadinessSnapshot`，它串联来源文件一致性、正式训练授权和 Phase 1 readiness，更接近“现在能不能启动正式训练”的结论
- `audit-phase1-readiness.ts` 是软检查：即使当前还没达到 `200 / 800` 门槛，也会保留报告并继续返回流水线成功
- `plan-phase1-collection.ts` 会把缺口翻译成下一批补样本方向
- `generate-first-batch-checklist.ts` 会同步刷新首批/下一批的执行清单
- `build-initial-release-trace-draft.ts` 和 `build-reviewed-batch-release-handoff.ts` 会给后续模型训练发布链路留下治理交接文件

## 成功语义

流水线 `ok=true` 表示这批已修正样本已经成功导入正式数据集，并且下游审计、切分、标签转换和交接产物都生成成功。

它不表示 Phase 1 已经完成。是否达到 Phase 1 的 200 张图片、800 个有效 mask、test split 负样本和复杂背景覆盖，要看导入报告或 gate 报告里的 `readinessSnapshot.ok` / `ok`。是否可以进入正式训练，还要看 `trainingDatasetReadinessSnapshot.ok`；小批量导入时它通常会是 `false`，但会列出剩余差距和授权/来源问题。

适合在人工修正完成后，快速看这批样本导入后对正式数据集的实际提升。