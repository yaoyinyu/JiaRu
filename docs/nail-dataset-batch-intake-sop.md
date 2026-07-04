# 美甲纹理首批样本批处理 SOP

版本：v1.1
日期：2026-07-04

这份 SOP 用来处理“拿到一整批图片之后，先预检，再导入”的场景。

## 1. 先准备两个东西

- 一个图片目录，例如 `C:/path/to/nail-batch-001`
- 一份批次清单，例如：[model/fixtures/nail-dataset-intake-batch.template.json](</E:/AI Project/Codex/JiaRu/model/fixtures/nail-dataset-intake-batch.template.json>)

## 2. 批次清单字段

- `sourceGroup`：这一批图片的统一批次名
- `originType`：来源类型
- `license`：授权/用途说明
- `defaultOriginRef`：默认来源说明
- `copyImagesToDataset`：后续是否复制到数据集目录
- `items[].fileName`：图片文件名
- `items[].originRef`：可选，单图覆盖默认来源
- `items[].notes`：可选备注

## 3. 先跑预检

```bash
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
```

预检会检查：

- manifest 结构是否正确
- `sourceGroup` / `originType` / `license` 是否齐
- 是否有重复文件名
- manifest 里声明的图片是否真的存在
- manifest 里声明的图片是否可以被解码，并且有有效宽高
- 图片目录里是否有“没写进 manifest”的文件

输出：

- `<manifest-name>.report.json`

报告里会包含：

- `missingFiles`：manifest 写了但磁盘不存在的图片
- `invalidImageFiles`：文件存在但无法作为有效图片解码的图片
- `unlistedFiles`：磁盘存在但 manifest 没写的文件
- `imageChecks`：每张已声明图片的解码结果、宽高、格式和通道数

`missingFiles` 和 `invalidImageFiles` 是 error，会阻止后续入库；`unlistedFiles` 是 warning，用来提醒你目录里可能混入了不属于本批的文件。

## 4. 预检通过后再导入

如果这批是参考图/商家图，可继续跑：

```bash
node --no-warnings --experimental-strip-types model/training/export-fallback-annotations.ts --copy-image --source-group seed-batch-001 --origin-type reference --origin-ref "Desktop album export 2026-07-01" --license "internal-test-only" C:/path/to/nail-batch-001/sample-001.jpg C:/path/to/nail-batch-001/sample-002.jpg
```

如果这批来自页面纠正样本，则走：

```bash
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images --copy-image --source-group user-corrections-2026-07-01 --origin-type user --origin-ref "authorized debug corrections" --license "user-authorized-internal-training"
```

## 5. 导入后的固定动作

```bash
node --no-warnings --experimental-strip-types model/training/sync-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/audit-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/split-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
node --no-warnings --experimental-strip-types model/training/convert-annotations.ts
```

## 6. 本阶段通过条件

- 预检 report 没有 error
- `sources.csv` 已生成或已更新
- `sources-audit.json` 没有 error
- `label-audit.csv` 已生成
- `split.json` 已生成

这样做的好处是：批次先验收，再导入，再审计，后面排查问题会轻很多。