# Nail Texture Dataset v1

这个目录用于沉淀“用户上传美甲纹理参考图”的训练数据工作区。

目标：

- 统一原始图片、标注文件、YOLO segmentation 标签和元数据结构
- 让 fallback 自动候选、人工修正和后续模型训练能够串起来
- 在正式收集 200 张种子图之前，先把目录与工具链固定下来

目录结构：

```text
model/datasets/nail-texture-v1/
  README.md
  images/
    raw/          # 原始采集图片；默认不建议直接提交大批量素材
    train/
    val/
    test/
  annotations/
    raw-json/     # 人工修正后的原始 polygon 标注
  labels-yolo-seg/
    train/
    val/
    test/
  metadata/
    sources.csv
    split.json
    label-audit.csv
```

`sources.csv` 建议至少维护这些字段：

- `imageId`
- `fileName`
- `sourceGroup`
- `originType`
- `originRef`
- `license`
- `notes`
- `negative`
- `annotationPath`
- `imagePath`
- `annotationCount`
- `createdAt`
- `updatedAt`

建议在每次批量导入或人工补录后运行：

```bash
node --no-warnings --experimental-strip-types model/training/audit-sources-csv.ts
```

它会生成 `metadata/sources-audit.json`，重点检查：
- `originType` 是否合法
- `originRef` / `license` 是否缺失
- `annotationPath` / `imagePath` 是否符合约定目录
- `createdAt` / `updatedAt` 是否为有效时间戳
- 负样本是否被标成 `originType=negative`

## 标注 JSON 格式

每张图对应一个 `.json` 文件，结构如下：

```json
{
  "version": "nail-texture-dataset/v1",
  "image": {
    "id": "sample-001",
    "fileName": "sample-001.jpg",
    "width": 860,
    "height": 645,
    "sourceGroup": "merchant-set-a",
    "negative": false
  },
  "annotations": [
    {
      "id": "n1",
      "label": "nail_texture",
      "polygon": [
        { "x": 120, "y": 80 },
        { "x": 148, "y": 72 },
        { "x": 166, "y": 132 },
        { "x": 126, "y": 145 }
      ],
      "attributes": {
        "fingerHint": "index",
        "shape": "almond",
        "quality": 4,
        "occluded": false,
        "artificialTip": true
      }
    }
  ]
}
```

约束：

- `version` 固定为 `nail-texture-dataset/v1`
- `label` 当前只允许 `nail_texture`
- `polygon` 至少 3 个点，且点必须落在图片范围内
- `negative=true` 的负样本不能包含任何 `annotations`
- `sourceGroup` 用于切分 train/val/test 时做同源聚合，避免相似图泄漏

## 数据流程

1. 原始图片放入 `images/raw/`，或者通过导出脚本自动复制
2. 运行 fallback 导出脚本生成初始标注 JSON
3. 人工修正 `annotations/raw-json/`，或从页面导出的修正样本 JSON 通过 `import-debug-sample.ts` 导入
4. 运行 `sync-sources-csv.ts` 同步 `metadata/sources.csv`
5. 运行 `audit-sources-csv.ts` 输出 `metadata/sources-audit.json`
6. 运行 split 脚本生成 `metadata/split.json`
7. 运行 audit 脚本输出 `metadata/label-audit.csv`
8. 运行转换脚本生成 `labels-yolo-seg/`
9. 再根据 split 结果把图片/标签组织到 `train` / `val` / `test`

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/export-fallback-annotations.ts --copy-image --source-group seed-batch-001 model/5188.jpg_wh860.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --source-group user-corrections-001 local-debug-2026-06-30.json C:/path/to/original-image.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
node --no-warnings --experimental-strip-types model/training/sync-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/split-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
node --no-warnings --experimental-strip-types model/training/convert-annotations.ts
```

## Git 建议

- `README.md`、脚本和少量 fixture 可以进 Git
- 批量原始图片、批量标注、训练产物默认不要直接进 Git
- 如果要保留目录结构，可在空目录中放 `.gitkeep`
