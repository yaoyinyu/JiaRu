# Nail Texture Model Training

这个目录用于放训练前的数据准备脚本，以及后续模型训练与导出脚本。

当前已落地：

- `export-fallback-annotations.ts`：把 fallback 检测结果导出成待人工修正的初始标注 JSON
- `import-debug-sample.ts`：把 `NailArtPicker` 导出的修正样本 JSON 转成训练用原始标注 JSON
  - 支持单文件导入
  - 也支持 `--sample-dir + --image-dir` 批量导入
- `sync-sources-csv.ts`：根据现有标注回填或修复 `metadata/sources.csv`
- `audit-sources-csv.ts`：校验 `metadata/sources.csv` 的来源字段、路径、时间戳和负样本元数据
- `split-dataset.ts`：按 `sourceGroup` 稳定划分 train / val / test
- `audit-labels.ts`：检查标注质量并输出 CSV
- `convert-annotations.ts`：把原始 polygon JSON 转成 YOLO segmentation 标签
- `dataset.yaml`：训练/验证/测试数据集入口配置
- `train-yolo-seg.py`：训练 YOLO segmentation 模型
- `evaluate.py`：输出验证/测试指标
- `export-onnx.py`：导出浏览器端 ONNX 和 manifest

推荐流程：

1. 准备参考图或种子图
2. 运行 `export-fallback-annotations.ts` 生成初始标注
3. 人工修正 `model/datasets/nail-texture-v1/annotations/raw-json/*.json`
4. 如果修正发生在页面交互里，可先导出修正样本 JSON，再运行 `import-debug-sample.ts`
5. 运行 `sync-sources-csv.ts` 检查并修复 `metadata/sources.csv`
6. 运行 `audit-sources-csv.ts` 生成 `metadata/sources-audit.json`
7. 运行 `split-dataset.ts` 生成 `metadata/split.json`
8. 运行 `audit-labels.ts` 生成 `metadata/label-audit.csv`
9. 运行 `convert-annotations.ts` 生成 `labels-yolo-seg/{train,val,test}`

示例命令：

```bash
node --no-warnings --experimental-strip-types model/training/scaffold-seed-batch.ts --root-dir C:/path/to/seed-batch-001 --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts --image-dir C:/path/to/nail-batch-001 --source-group seed-batch-001 --origin-type web --license "internal-test-only" --default-origin-ref "manual web sourcing 2026-07-01"
node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir C:/path/to/nail-batch-001 --output-dir C:/path/to/nail-batch-001-debug --prefix seed-batch-001
node --no-warnings --experimental-strip-types model/training/export-fallback-annotations.ts --copy-image --source-group seed-batch-001 model/5188.jpg_wh860.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --source-group user-corrections-001 local-debug-2026-06-30.json C:/path/to/original-image.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images
node --no-warnings --experimental-strip-types model/training/sync-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/audit-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/split-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
node --no-warnings --experimental-strip-types model/training/convert-annotations.ts
python model/training/train-yolo-seg.py --dry-run
python model/training/evaluate.py --dry-run
python model/training/export-onnx.py --dry-run
node --no-warnings --experimental-strip-types scripts/verify-training-release.ts --metrics model/exports/nail-texture-seg-v1/metrics.json --manifest public/models/nail-texture-seg/manifest.json
node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --manifest public/models/nail-texture-seg/manifest.json
```

批量图片先预检时，可额外运行：

```bash
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts --image-dir C:/path/to/nail-batch-001 --source-group seed-batch-001 --origin-type web --license "internal-test-only" --default-origin-ref "manual web sourcing 2026-07-01" --output C:/path/to/nail-batch-001/seed-batch-001.manifest.json
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
```

`import-debug-sample.ts` 的作用是把页面里调整过的候选框结果，转换成和 `annotations/raw-json/*.json` 同一格式的训练样本。当前它需要两份输入：

- 导出的修正样本 JSON
- 对应原图文件路径

如果加上 `--copy-image`，脚本会同时把原图复制到 `images/raw/`。

批量模式下：

- 使用 `--sample-dir <dir> --image-dir <dir>`
- 当前约定样本文件和图片文件使用相同 stem
- 会自动匹配常见后缀：`.png`、`.jpg`、`.jpeg`、`.webp`
- 例如 `batch-001.json` 可以对应 `batch-001.png` 或 `batch-001.jpg`

后续待补：

- `scripts/verify-nail-detection.ts` 的模型推理 overlay 扩展
- 真实训练依赖安装说明与训练机环境约束
