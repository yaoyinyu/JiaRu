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
- `build-independent-hard-negative-review-workspace.py`：从A授权和机器审计构建逐图原分辨率审核工作区；生成1:1像素审核页，并在审核前证明与train、val、冻结test零身份重合
- `record-training-hard-negative-authorization.py`：为候选训练负样本建立精确逐文件授权和机器审计；只接受权威受保护registry，固定新批training命名、768像素最短边、SHA-256、规范sourceIdentity与dHash256隔离，输出始终保持`trainingUse=prohibited`
- `record-independent-hard-negative-authorization.py`：在任何候选模型推理前原子冻结100张以上新来源困难负样本；固定拒绝精确/感知近重复、符号链接和宽泛授权，并把候选权重及规范val阈值深验报告一起锁定
- `finalize-independent-hard-negative-review.py`：重放授权、图片、审核页、受保护角色和逐图决定，输出候选清单；任何原图或证据漂移都会拒绝
- `finalize-reviewed-hard-negative-manifest.py`：把一个或多个已完成原分辨率审核的hard negative候选批次终结为schema v2清单；不足100张时只输出不可训练HOLD，达到门槛后才输出可供规范物化器消费的批准清单
- `finalize-reviewed-independent-hard-negative-holdout.py`：独立留出专用终结器；深度重放冻结与逐图终审，达到100张后只开放发布评估/长期回归，始终保持`trainingUse=prohibited`
- `audit-phase1-readiness.ts`：检查是否达到 Phase 1 的数据量与测试覆盖门槛
- `plan-phase1-collection.ts`：把 Phase 1 readiness 缺口翻译成下一批补样本计划
- `generate-first-batch-checklist.ts`：把当前 readiness/collection 结果翻译成首批真实数据执行清单
- `dataset.yaml`：训练/验证/测试数据集入口配置
- `train-yolo-seg.py`：训练 YOLO segmentation 模型
- `evaluate.py`：输出验证/测试指标
- `export-onnx.py`：导出浏览器端 ONNX 和 manifest
- `quantize-onnx-int8.py`：生成隔离的 QDQ INT8 评估候选；默认禁止 promotion，必须继续通过精度和浏览器门禁
- `assess-model-metrics.py`：比较输入尺寸或量化候选与 FP32 基线，自动拒绝超过允许退化幅度的候选
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
python model/training/record-training-hard-negative-authorization.py --verify-protected-registry E:/path/to/protected-hard-negative-registry-v1.json
python model/training/record-training-hard-negative-authorization.py --source-root C:/path/to/candidate3-training-v1 --user-authorization C:/path/to/candidate3-exact-authorization.json --output-dir C:/path/to/candidate3-training-authorization-v1 --protected-hard-negative-registry E:/path/to/protected-hard-negative-registry-v1.json --batch-date 20260726 --sequence-start 1 --sequence-end 160
python model/training/record-training-hard-negative-authorization.py --verify-authorization C:/path/to/candidate3-training-authorization-v1/authorization-record-A-v1.json
python model/training/build-independent-hard-negative-review-workspace.py --authorization C:/path/to/candidate3-training-authorization-v1/authorization-record-A-v1.json --machine-audit C:/path/to/candidate3-training-authorization-v1/machine-audit-v1.json --train-index C:/path/to/training-truth-index-v1.json --val-index C:/path/to/validation-truth-index-v1.json --frozen-test-manifest C:/path/to/frozen-test-manifest.json --output-dir C:/path/to/candidate3-training-review-workspace
python model/training/record-independent-hard-negative-authorization.py --source-root C:/path/to/post-train-holdout --user-authorization C:/path/to/pre-existing-user-authorization.json --candidate-weights C:/path/to/best.pt --candidate-threshold-report C:/path/to/formal-val-threshold.json --expected-candidate-weights-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef --expected-score-threshold 0.50 --protected-hard-negative-registry E:/path/to/current-protected-hard-negative-registry.json --batch-date 20260724 --sequence-start 161 --sequence-end 270
python model/training/record-independent-hard-negative-authorization.py --verify-freeze C:/path/to/post-train-holdout/_independent_holdout_freeze_v1/freeze-manifest-v1.json
python model/training/build-independent-hard-negative-review-workspace.py --authorization C:/path/to/post-train-holdout/_independent_holdout_freeze_v1/authorization-record-A-v1.json --machine-audit C:/path/to/post-train-holdout/_independent_holdout_freeze_v1/machine-audit-v1.json --freeze-manifest C:/path/to/post-train-holdout/_independent_holdout_freeze_v1/freeze-manifest-v1.json --train-index C:/path/to/training-truth-index-v1.json --val-index C:/path/to/validation-truth-index-v1.json --frozen-test-manifest C:/path/to/frozen-test-manifest.json --output-dir C:/path/to/hard-negative-review-workspace
python model/training/finalize-independent-hard-negative-review.py --workspace C:/path/to/hard-negative-review-workspace/review-workspace-v1.json --decisions C:/path/to/review-decisions-completed-v1.csv --output-dir C:/path/to/hard-negative-review-finalized
python model/training/finalize-reviewed-hard-negative-manifest.py --candidate-manifest C:/path/to/hard-negative-candidate-manifest.json --output C:/path/to/hard-negative-formalization.json
python model/training/finalize-reviewed-hard-negative-manifest.py --verify-report C:/path/to/approved-hard-negative-manifest.json
python model/training/finalize-reviewed-independent-hard-negative-holdout.py --candidate-manifest C:/path/to/hard-negative-candidate-manifest.json --output C:/path/to/approved-independent-holdout.json
python model/training/finalize-reviewed-independent-hard-negative-holdout.py --verify-report C:/path/to/approved-independent-holdout.json
python model/training/audit-hard-negative-watermark-shortcut.py --weights C:/path/to/best.pt --hard-negative-manifest C:/path/to/approved-independent-holdout.json --output C:/path/to/independent-holdout-audit.json --artifacts-dir C:/path/to/independent-holdout-artifacts --dataset-role independent-holdout --deployment-confidence 0.45
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

### Hard negative 正式终结门

第三候选训练负样本与训练后独立留出是两种不同角色，不能共用授权记录：

1. 训练负样本先由`record-training-hard-negative-authorization.py`建账。用户授权必须精确列出最终批次的相对路径，并明确允许商业模型训练与长期回归、排除独立发布测试；目录级宽泛授权不能替代逐文件白名单。
2. `--protected-hard-negative-registry`是唯一受保护集合入口。registry固定每份历史training/holdout manifest的路径、SHA-256和角色；记录器会深验全部manifest，并把完全一致的历史重复证据规范去重。后续新增任何受保护manifest时必须先更新并重新冻结registry，禁止调用方只传有利子集。
   - 使用`update-protected-hard-negative-registry.py`做单调追加；旧entries必须保持不可变前缀，工具拒绝删除、替换、改序、角色漂移、重复身份和manifest字节漂移，并支持`--verify-registry`深度重放。
3. 新批文件必须使用`hard_negative_training_YYYYMMDD_NNN_family_VV`，序号在声明区间内连续，最短边不少于768像素。旧`hard_negative_ai_*`、`hard_negative_independent_*`或`nail_*`命名只允许在registry绑定的历史受保护清单中兼容，不能用于新训练批次。
   - 生成阶段先固定160项计划，再用`audit-training-hard-negative-generation-progress.py`记录可恢复快照。允许缺图时输出诚实`HOLD`与下一缺口；补图时绑定`--previous-report`可增长但不可修改既有图片。即使160/160机器通过，也只会进入“可请求精确用户授权”，不会自动授予训练资格。
   - 若上一候选由独立困难负样本审计否决，先用`build-candidate5-hard-negative-generation-plan.py`深验拒绝报告与当前受保护registry，固定160项新训练候选及失败类型简报。该工具只生成计划；必须先把刚冻结的失败独立留出单调追加到registry，计划才会把它作为受保护证据，绝不允许回流训练。
4. 授权记录和机器清单不会直接赋予训练资格；两者始终为candidate-only、`trainingUse=prohibited`。审核工作区会调用记录器做只读深度重放，并采用staging与原子替换，防止半成品或旧页面混入。
5. 每张图仍须通过原分辨率视觉终审；AI来源不降低清晰度、完整主体、真人甲面排除、无水印捷径和目标域标准。达到100张批准项后，才可由`finalize-reviewed-hard-negative-manifest.py`生成训练可消费的schema v2清单。

独立AI困难负样本必须先完成冻结、逐图审核和角色专用终结：

1. `record-independent-hard-negative-authorization.py`先在任何候选模型推理前冻结不少于100张的精确批次身份；授权文件必须预先存在且`sourceRoot`精确等于批次根，并强制提供当前受保护hard-negative registry。正式下限、dHash256距离12近重复门、固定证据目录、日期和连续序号均不可由CLI降低或改写；命名、完整解码、最短边、精确/感知重复、符号链接、当前SHA-256任一失败均不会留下最终证据。新留出还会按精确SHA-256、规范sourceIdentity和dHash256≤12拒绝与历史training/holdout全集重合；候选权重、规范val阈值报告与registry在同一次原子冻结中深度重放并锁定。正式候选调用还应同时传`--expected-candidate-weights-sha256`与`--expected-score-threshold`，把阶段计划中的目标权重和阈值作为显式防误用断言；二者与实际深验结果不一致时不得留下冻结证据。
2. `build-independent-hard-negative-review-workspace.py`逐文件复验A授权、机器审计、图片SHA-256、尺寸与完整解码，并与当前train、val、冻结test证据按文件名、图片SHA-256和`sourceGroup`复核零重合。
3. 审核人员只能在绑定的1:1像素审核页和原图上填写另一份完成版CSV；禁止覆盖工作区中的空白模板，因为模板SHA-256属于工作区契约。
4. `finalize-independent-hard-negative-review.py`再次重放所有输入和审核页哈希。`pass`必须有审核说明且不得带缺陷码；`exclude`必须给出受控缺陷码。输出仍为候选、`trainingUse=prohibited`。
5. 训练负样本使用`finalize-reviewed-hard-negative-manifest.py`；独立留出必须使用`finalize-reviewed-independent-hard-negative-holdout.py`。后者达到100张才生成schema v2独立留出清单，只允许发布评估与长期回归，始终禁止训练。
6. `audit-hard-negative-watermark-shortcut.py --dataset-role independent-holdout`会再次深验留出清单、冻结证据、权重和预冻结阈值；正式门固定要求三种变体零误检、零检测数差异，CLI不能放宽。

若某批图片已经被当前模型用于误检筛选，并且筛选结果将影响训练选择或返修，该批只能进入训练/诊断角色，不能继续作为下一候选的未见独立发布留出。下一版发布留出必须在训练方案与样本角色冻结后从新来源另建。

`finalize-reviewed-hard-negative-manifest.py`不会把候选清单的外层`PASS`直接当作训练授权。它会重放候选清单、逐图审核决定、A授权、图片SHA-256、尺寸和解码结果，并要求所有候选清晰、无有效真人美甲甲面、非裁断/拼图/模板/独立甲片。正式下限固定为100张，`--minimum-images`只能提高、不能降低。

- 少于100张：输出`status=HOLD`、`trainingUse=prohibited`和`candidateItems`，不输出可消费的正式`items`。
- 达到100张：输出schema v2 `approved_hard_negative_manifest`；角色隔离、候选数据物化和训练输入审计会调用`verify_approved_report()`从当前审核、授权与图片字节重新验证。
- 图片必须由Pillow完成`verify()`与完整像素`load()`，最短边不少于320像素，审核记录宽高必须与当前文件一致。
- 可解码图片的真实格式若与扩展名不一致，源文件不改，正式清单使用匹配真实格式的物化文件名；文本、损坏文件或不支持格式直接拒绝。
- 物化后的hard negative在GPU前输入审计中再次解码，标签必须严格为零字节。

## 评估可视化产物

`evaluate.py` 会在 `metrics.json` 同级生成 `evaluation-artifacts/`，保存混淆矩阵、预测对照图、逐图预测标签和统一索引。正式训练发布流水线会自动执行可视化产物门禁。详细说明见 `docs/model-evaluation-artifacts.md`。

## Training environment preflight

Before a real non-dry-run training starts, run:

```bash
python model/training/check-training-environment.py --require-local-model
```

This command does not train or access the network. It checks the materialized train/val/test image counts, Python version, Ultralytics/Torch availability, and whether the requested checkpoint is already local. If `yolo11n-seg.pt` is not present locally, the first real Ultralytics training run may download it.
