# 本地图片目录到人工修正前的一键流水线

版本：v1.1
日期：2026-07-04

如果你已经有一整个本地图片目录，这条流水线可以直接完成 fixture 导入、fallback overlay 预检，并推进到人工修正前。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-local-batch-bootstrap-pipeline.ts --source-dir "C:/path/to/local-images" --root-dir "C:/path/to/seed-batch-001" --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-04" --fixture-dir "C:/path/to/fixtures"
```

没有 fixture 时可以省略 `--fixture-dir`，流水线仍会执行普通 fallback overlay 预检。

## 会自动串起来的步骤

- `bootstrap-seed-batch.ts`：复制 fixture，并从来源图清单排除 fixture 引用的绿圈标注图
- `batch-verify-nail-detection.ts`：生成逐图 overlay 和 debug 报告，作为硬性预检
- `run-seed-batch-prep-pipeline.ts`：审计筛选表并准备待人工修正标注
- `audit-seed-batch-workspace.ts`：输出工作区状态和下一步命令

预检报告返回 `ok=false` 时，流水线立即停止，不会在缺少有效 overlay 的情况下继续准备标注。

## 结果

执行成功后，工作区会至少具备：

- `images/`：只包含实际来源图，不包含 fixture 引用的标注图
- `fixtures/`
- `debug/*-batch-verify-report.json` 和逐图 overlay/debug 产物
- `review/screening-review.csv`
- `selected/images/`
- `selected/annotations/raw-json/*.json`
- `seed-batch-workspace-status.json`

适合把“我有一批本地图片”稳定推进到可人工修正的阶段。
