# 修正后批次回流正式数据集

版本：v1.0  
日期：2026-07-01

这一步把 `selected/annotations/raw-json` 里人工修正后的结果正式回流到数据集目录，并自动跑后续审计和转换。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/import-reviewed-batch.ts --root-dir "C:/path/to/seed-batch-001"
```

## 它会做什么

- 复制 `selected/images/*` 到 `model/datasets/nail-texture-v1/images/raw/`
- 复制 `selected/annotations/raw-json/*` 到 `model/datasets/nail-texture-v1/annotations/raw-json/`
- 自动运行：
  - `sync-sources-csv.ts`
  - `audit-sources-csv.ts`
  - `split-dataset.ts`
  - `audit-labels.ts`
  - `convert-annotations.ts`

## 输出

- `model/datasets/nail-texture-v1/metadata/reviewed-import-<sourceGroup>.report.json`

## 作用

这一步把首批 50 张修正样本真正纳入正式训练数据集，Phase 1 这条链路到这里才算从筛图、预标注、人工修正，走到了可训练数据资产。
