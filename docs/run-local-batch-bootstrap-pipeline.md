# 本地图片目录到人工修正前的一键流水线

版本：v1.0  
日期：2026-07-01

如果你已经有一整个本地图片目录，这条流水线可以直接把它推进到人工修正前。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-local-batch-bootstrap-pipeline.ts --source-dir "C:/path/to/local-images" --root-dir "C:/path/to/seed-batch-001" --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
```

## 会自动串起来的步骤

- `bootstrap-seed-batch.ts`
- `run-seed-batch-prep-pipeline.ts`
- `audit-seed-batch-workspace.ts`

## 结果

执行成功后，工作区会至少具备：

- `images/`
- `review/screening-review.csv`
- `selected/images/`
- `selected/annotations/raw-json/*.json`
- `seed-batch-workspace-status.json`

适合把“我有一批本地图片”尽快推进到可人工修正的阶段。
