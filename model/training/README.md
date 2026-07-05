# Nail Texture Model Training

这个目录用于放训练前的数据准备脚本，以及后续模型训练与导出脚本。

当前已落地：

- `export-fallback-annotations.ts`：把 fallback 检测结果导出成待人工修正的初始标注 JSON
- `import-debug-sample.ts`：把 `NailArtPicker` 导出的修正样本 JSON 转成训练用原始标注 JSON
  - 支持单文件导入
  - 也支持 `--sample-dir + --image-dir` 批量导入
- `prioritize-debug-samples.ts`：给 debug sample 做主动学习优先级排序
- `run-debug-sample-active-learning-pipeline.ts`：把 priority、debug sample 导入、sources 审计、split、label convert、readiness 串成一条流水线
- `sync-sources-csv.ts`：根据现有标注回填或修复 `metadata/sources.csv`
- `audit-sources-csv.ts`：校验 `metadata/sources.csv` 的来源字段、路径、时间戳和负样本元数据
- `audit-training-source-authorization.ts`：区分内部验证素材和正式训练素材，拦截未授权/模糊授权来源
- `verify-training-dataset-readiness.ts`：训练前总门禁，串联 sources 审计、授权审计和 Phase 1 readiness
- `split-dataset.ts`：按 `sourceGroup` 稳定划分 train / val / test
- `audit-labels.ts`：检查标注质量并输出 CSV
- `convert-annotations.ts`：把原始 polygon JSON 转成 YOLO segmentation 标签
- `materialize-training-dataset.ts`：把 raw 图片和转换后的标签物化为 Ultralytics 标准 train / val / test 目录
- `audit-phase1-readiness.ts`：检查是否达到 Phase 1 的数据量与测试覆盖门槛
- `plan-phase1-collection.ts`：把 Phase 1 readiness 缺口翻译成下一批补样本计划
- `generate-first-batch-checklist.ts`：把当前 readiness/collection 结果翻译成首批真实数据执行清单
- `dataset.yaml`：训练/验证/测试数据集入口配置
- `train-yolo-seg.py`：训练 YOLO segmentation 模型
- `evaluate.py`：输出验证/测试指标
- `export-onnx.py`：导出浏览器端 ONNX 和 manifest
- `../scripts/run-training-release-pipeline.ts`：把训练、评估、导出、发布门禁串成一条流水线

推荐流程：

1. 准备参考图或种子图
2. 运行 `export-fallback-annotations.ts` 生成初始标注
3. 人工修正 `model/datasets/nail-texture-v1/annotations/raw-json/*.json`
4. 如果修正发生在页面交互里，可先导出修正样本 JSON，再运行 `import-debug-sample.ts`
   - 如果想先吃高价值样本，优先走 `run-debug-sample-active-learning-pipeline.ts`
5. 运行 `sync-sources-csv.ts` 检查并修复 `metadata/sources.csv`
6. 运行 `audit-sources-csv.ts` 生成 `metadata/sources-audit.json`
7. 运行 `audit-training-source-authorization.ts --mode release` 生成正式训练授权审计
8. 运行 `split-dataset.ts` 生成 `metadata/split.json`
9. 运行 `audit-labels.ts` 生成 `metadata/label-audit.csv`
10. 运行 `convert-annotations.ts` 生成 `labels-yolo-seg/{train,val,test}`
11. 运行 `audit-phase1-readiness.ts` 看是否通过 `200 / 800 / test coverage`
12. 运行 `plan-phase1-collection.ts` 得到下一批补样本建议
13. 运行 `generate-first-batch-checklist.ts` 得到首批真实数据执行清单

示例命令：

```bash
node --no-warnings --experimental-strip-types model/training/scaffold-seed-batch.ts --root-dir C:/path/to/seed-batch-001 --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts --image-dir C:/path/to/nail-batch-001 --source-group seed-batch-001 --origin-type web --license "internal-test-only" --default-origin-ref "manual web sourcing 2026-07-01"
node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir C:/path/to/nail-batch-001 --output-dir C:/path/to/nail-batch-001-debug --prefix seed-batch-001 --fixture-dir C:/path/to/seed-batch-001/fixtures
node --no-warnings --experimental-strip-types model/training/export-fallback-annotations.ts --copy-image --source-group seed-batch-001 model/5188.jpg_wh860.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --source-group user-corrections-001 local-debug-2026-06-30.json C:/path/to/original-image.jpg
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --copy-image --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images
node --no-warnings --experimental-strip-types model/training/prioritize-debug-samples.ts --sample-dir C:/path/to/debug-samples --top 20
node --no-warnings --experimental-strip-types model/training/run-debug-sample-active-learning-pipeline.ts --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images --copy-image --min-priority medium --top 20 --origin-type user --origin-ref "authorized debug corrections" --license "user-authorized-internal-training"
node --no-warnings --experimental-strip-types model/training/sync-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/audit-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/audit-training-source-authorization.ts --mode release
node --no-warnings --experimental-strip-types model/training/audit-training-source-authorization.ts --mode internal
node --no-warnings --experimental-strip-types model/training/verify-training-dataset-readiness.ts --dataset-root model/datasets/nail-texture-v1
node --no-warnings --experimental-strip-types model/training/split-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
node --no-warnings --experimental-strip-types model/training/convert-annotations.ts
node --no-warnings --experimental-strip-types model/training/materialize-training-dataset.ts
node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts
node --no-warnings --experimental-strip-types model/training/plan-phase1-collection.ts
node --no-warnings --experimental-strip-types model/training/generate-first-batch-checklist.ts
python model/training/train-yolo-seg.py --dry-run
python model/training/evaluate.py --dry-run
python model/training/export-onnx.py --dry-run
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --dry-run
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --source-authorization-dataset-root model/datasets/nail-texture-v1 --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json
node --no-warnings --experimental-strip-types scripts/verify-training-release.ts --metrics model/exports/nail-texture-seg-v1/metrics.json --manifest public/models/nail-texture-seg/manifest.json
node --no-warnings --experimental-strip-types scripts/compare-training-releases.ts --baseline-metrics model/exports/nail-texture-seg-v1/metrics.json --baseline-manifest public/models/nail-texture-seg-v1/manifest.json --candidate-metrics model/exports/nail-texture-seg-v2/metrics.json --candidate-manifest public/models/nail-texture-seg-v2/manifest.json
node --no-warnings --experimental-strip-types scripts/register-model-release.ts --manifest public/models/nail-texture-seg/manifest.json
node --no-warnings --experimental-strip-types scripts/switch-model-release.ts --version nail-texture-seg-v1
node --no-warnings --experimental-strip-types scripts/audit-release-rollback.ts --registry public/models/nail-texture-seg/release-registry.json --manifest public/models/nail-texture-seg/manifest.json
node --no-warnings --experimental-strip-types scripts/audit-failure-classification.ts --failure-csv C:/path/to/review/failure-classification.csv --output C:/path/to/review/failure-classification-audit.json
node --no-warnings --experimental-strip-types scripts/summarize-failure-cases.ts --failure-csv C:/path/to/failure-classification.csv --first-run-record C:/path/to/real-model-first-run-record.json
node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --manifest public/models/nail-texture-seg/manifest.json
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts --profile desktop --sample-dir C:/path/to/debug-samples --output C:/path/to/performance-report.desktop.json
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts --profile mobile --sample-dir C:/path/to/debug-samples --output model/exports/nail-texture-seg-v2/performance-report.mobile.json
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --run-governance --governance-performance-report model/exports/nail-texture-seg-v2/performance-report.mobile.json
```


授权审计口径：

- `--mode internal`：内部验证/回归测试素材可用，适合网上搜集图、debug 样本、算法预检。
- `--mode release`：正式训练或候选模型发布前必须通过；会拦截 `web` 来源、`internal-test-only`、用户/商家未明确授权和模糊 license。
- 正式可训练素材建议用 `user-authorized-internal-training`、`merchant-authorized-commercial-training`、`licensed-commercial-training`、`cc0`、`public-domain`、`owner-authorized-training` 这类明确 wording。
- `run-training-release-pipeline.ts` 在真实训练且未 `--skip-train` 时，会先执行 `verify-training-dataset-readiness.ts`，同时检查来源文件一致性、正式训练授权和 Phase 1 数据量/质量门槛；只有验证旧产物或受控调试时才建议显式使用 `--skip-source-authorization`。

种子批次工作区固定包含 `fixtures/`。已有绿圈真值时将 fixture JSON 放入该目录；批量预检会自动匹配，并跳过 fixture 引用的标注图。

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
- 如果已经先跑过 `prioritize-debug-samples.ts`，还可以加：
  - `--priority-report <json>`
  - `--min-priority <high|medium|low>`
  - `--top <n>`

后续待补：

- `scripts/verify-nail-detection.ts` 的模型推理 overlay 扩展
- 真实训练依赖安装说明与训练机环境约束

## 评估可视化产物

`evaluate.py` 会在 `metrics.json` 同级生成 `evaluation-artifacts/`，保存混淆矩阵、预测对照图、逐图预测标签和统一索引。正式训练发布流水线会自动执行可视化产物门禁。详细说明见 `docs/model-evaluation-artifacts.md`。

## Training environment preflight

Before a real non-dry-run training starts, run:

```bash
python model/training/check-training-environment.py --require-local-model
```

This command does not train or access the network. It checks the materialized train/val/test image counts, Python version, Ultralytics/Torch availability, and whether the requested checkpoint is already local. If `yolo11n-seg.pt` is not present locally, the first real Ultralytics training run may download it.
