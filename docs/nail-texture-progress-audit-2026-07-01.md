# 美甲纹理识别专项模型进度审计（2026-07-01）

对应规划文档：

- `docs/nail-texture-recognition-model-plan.md`

本文档只做一件事：把当前仓库的真实状态，对照规划文档逐项审计，区分：

- 哪些能力已经代码落地
- 哪些验收已经有自动化证据
- 哪些阶段仍然被真实数据、真实模型资产或人工验收卡住

## 一、当前总体结论

当前项目已经明显完成了以下骨架建设：

- Phase 0 的识别类型统一、fallback 适配、模型识别入口、Worker 接入、`NailArtPicker` 对接
- Phase 1 的数据采集 / 筛选 / 预标注 / 导入 / split / 审计 / readiness / 补样本计划工具链
- Phase 2 的训练 / 评估 / 导出 / 发布校验 / 训练发布流水线
- Phase 3 的浏览器端模型加载、Worker 推理、fallback 保留、浏览器接入门禁、真实模型最终审计脚本

但是，按规划文档的“真实完成”标准看，项目还没有完成 MVP，原因非常明确：

1. 正式数据集当前仍是空集  
   - `audit-phase1-readiness.ts` 当前输出：`images=0`、`validMasks=0`
2. 浏览器模型目录当前只有 manifest，没有真实 ONNX  
   - `verify-model-artifact.ts` 当前输出：`modelExists=false`
3. 因为没有真实训练产物，所以：
   - Phase 2 指标门禁还不能真实通过
   - Phase 3 的真实模型浏览器集成还不能以真实模型资产验收
   - MVP 验收清单中的“可在浏览器加载的模型文件”仍未满足

一句话总结：

> 代码链路已经从 Phase 0 一直铺到了 Phase 3，但当前最大的阻塞点已经不是“功能没写”，而是“真实数据集和真实模型资产还没落地”。

## 二、按阶段审计

### Phase 0：现状固化

规划要求：

- 统一 `NailTextureCandidate`
- 把 `nail-image-detection.ts` 包装成 `fallback-adapter.ts`
- 参考图绿圈真值测试升级为通用 fixture 机制
- 修复文档和源码中的编码显示问题

当前证据：

- `src/lib/nail-texture-recognition/types.ts`
- `src/lib/nail-texture-recognition/fallback-adapter.ts`
- `src/lib/nail-texture-recognition/index.ts`
- `src/lib/nail-texture-recognition/recognize.ts`
- `tests/nail-image-detection.test.ts`
- `tests/nail-texture-model-runtime.test.ts`

结论：

- 代码能力：已基本落地
- 自动化验收：已具备
- 仍未完全闭环的点：
  - “编码显示问题已全面清理”这一项没有单独形成强证据，只能认为已做过多轮修复，但不是完全可证明的闭项

阶段判断：

- Phase 0：代码层面基本完成，验收基本通过

### Phase 1：数据与标注工具链

规划要求：

- 定义标注规范
- 收集 200 张种子图
- fallback 生成候选，人工修正为 mask
- 完成 `convert-annotations.ts` 和 `audit-labels.ts`
- 建立 train/val/test split

当前证据：

- 标注/批次/采集规范文档：
  - `docs/nail-dataset-intake-and-annotation-spec.md`
  - `docs/nail-seed-dataset-collection-checklist.md`
  - `docs/run-reviewed-batch-import-pipeline.md`
  - `docs/phase1-readiness-gate.md`
  - `docs/phase1-collection-plan.md`
- 工具脚本：
  - `model/training/init-intake-batch.ts`
  - `model/training/validate-intake-batch.ts`
  - `model/training/scaffold-seed-batch.ts`
  - `model/training/bootstrap-seed-batch.ts`
  - `model/training/build-reviewed-intake-batch.ts`
  - `model/training/prepare-reviewed-annotations.ts`
  - `model/training/import-reviewed-batch.ts`
  - `model/training/sync-sources-csv.ts`
  - `model/training/split-dataset.ts`
  - `model/training/audit-labels.ts`
  - `model/training/convert-annotations.ts`
  - `model/training/audit-phase1-readiness.ts`
  - `model/training/plan-phase1-collection.ts`
  - `model/training/run-reviewed-batch-import-pipeline.ts`
- 自动化测试：
  - `tests/audit-phase1-readiness.test.ts`
  - `tests/plan-phase1-collection.test.ts`
  - `tests/run-reviewed-batch-import-pipeline.test.ts`

当前真实资产状态：

- 运行 `model/training/audit-phase1-readiness.ts` 的当前结果：
  - `images=0`
  - `validMasks=0`
  - `train/val/test=0/0/0`
  - 缺少负样本 test coverage
  - 缺少复杂背景 test coverage

结论：

- 工具链：已大体建成
- 自动化验收：已具备
- 真实阶段目标：未完成

阻塞原因不是脚本，而是数据资产：

- 200 张种子图：未达到
- 800 个有效 mask：未达到
- test split 负样本：未达到
- test split 复杂背景：未达到

阶段判断：

- Phase 1：代码已基本落地，但真实数据集目标仍未完成

### Phase 2：第一版模型

规划要求：

- 训练轻量 segmentation 模型
- 输出 `metrics.json`、混淆样本、失败样本可视化
- 导出 ONNX
- 写 Node 端验证脚本，对固定样本集跑推理

当前证据：

- 训练/评估/导出：
  - `model/training/train-yolo-seg.py`
  - `model/training/evaluate.py`
  - `model/training/export-onnx.py`
- 发布门禁与流水线：
  - `scripts/verify-training-release.ts`
  - `scripts/run-training-release-pipeline.ts`
- 配套文档：
  - `docs/training-release-verification.md`
  - `docs/training-release-pipeline.md`
- 自动化测试：
  - `tests/model-training-python-scripts.test.ts`
  - `tests/verify-training-release.test.ts`
  - `tests/run-training-release-pipeline.test.ts`

当前真实资产状态：

- `model/exports/nail-texture-seg-v1/` 当前没有真实训练产物
- 因此不存在可用于真实 Phase 2 门禁的 `metrics.json`
- 也不存在真实 `best.pt`

结论：

- Phase 2 的代码链路已经可跑 dry-run，也支持真实发布门禁
- 但“第一版模型已训练完成”这件事目前没有真实证据

规划验收中这些项目前仍未被真实满足：

- `mask mAP50 >= 0.75`
- 测试集可用纹理提取率 >= 80%
- ONNX 模型小于 15MB（没有真实导出文件可验）

阶段判断：

- Phase 2：工程脚手架和门禁已落地，但真实模型训练结果尚未产生

### Phase 3：浏览器集成

规划要求：

- 增加 `onnxruntime-web`
- 实现模型 manifest 和懒加载
- 实现 Worker 推理
- 实现模型结果映射到 `NailArtPicker`
- 保留 fallback

当前证据：

- 浏览器识别模块：
  - `src/lib/nail-texture-recognition/model-runtime.ts`
  - `src/lib/nail-texture-recognition/client-worker.ts`
  - `src/workers/nail-texture-recognition.worker.ts`
  - `src/lib/nail-texture-recognition/postprocess.ts`
  - `src/lib/nail-texture-recognition/quality.ts`
  - `src/components/NailArtPicker.tsx`
- 浏览器/真实模型门禁：
  - `scripts/verify-browser-integration.ts`
  - `scripts/verify-real-model-readiness.ts`
  - `scripts/build-real-model-first-run-record.ts`
  - `scripts/run-real-model-final-audit.ts`
- 自动化测试：
  - `tests/verify-browser-integration.test.ts`
  - `tests/verify-real-model-readiness.test.ts`
  - `tests/build-real-model-first-run-record.test.ts`
  - `tests/run-real-model-final-audit.test.ts`

当前真实资产状态：

- `public/models/nail-texture-seg/manifest.json` 已存在
- 但 `public/models/nail-texture-seg/nail-texture-seg-v1.onnx` 当前不存在
- `verify-model-artifact.ts` 当前结论：
  - `modelExists=false`
  - `ok=false`

结论：

- 浏览器侧代码集成和验收脚本已经基本具备
- 但“模型在浏览器本地真实可用”仍不能被证明

原因很直接：

- 真实 ONNX 不存在
- 真实模型推理性能也就无法做桌面 / 手机耗时验收

阶段判断：

- Phase 3：代码接线已完成大半，真实模型资产缺失导致实机能力未闭环

### Phase 4：质量优化

规划要求：

- mask 边缘羽化
- 高光保护
- 透明背景输出
- 低质量候选提示
- 候选方向稳定化

当前证据：

- 已有部分基础能力：
  - `src/lib/nail-texture-recognition/quality.ts`
  - `src/lib/nail-texture-recognition/postprocess.ts`
- 但没有看到完整的 Phase 4 专项实现与专项验收文档

结论：

- 只能认为“局部前置能力已存在”
- 不能认为 Phase 4 已完成

阶段判断：

- Phase 4：未完成

### Phase 5：数据闭环与版本管理

规划要求：

- 模型版本 manifest
- debug 样本导出
- 模型 A/B 对比脚本
- 失败样本分类表

当前证据：

- 已部分具备：
  - 模型 manifest 机制已存在
  - debug 样本与首轮审计记录已存在
  - 失败样本分类相关文档/表格已有部分基础
- 但当前没有明确看到“模型 A/B 对比脚本”已独立落地
- 也没有真实多版本模型资产可做回滚/对比证明

结论：

- Phase 5 只能算部分铺底

阶段判断：

- Phase 5：未完成

## 三、对 MVP 验收清单的逐项审计

规划文档第 14 节要求：

### 1. 有 200 张以上训练图片和独立 test split

当前状态：

- 未满足

证据：

- `audit-phase1-readiness.ts` 当前输出 `images=0`

### 2. 有可复现训练脚本和导出脚本

当前状态：

- 已满足

证据：

- `train-yolo-seg.py`
- `evaluate.py`
- `export-onnx.py`
- `run-training-release-pipeline.ts`
- 对应测试均已通过

### 3. 有一个可在浏览器加载的模型文件

当前状态：

- 未满足

证据：

- `verify-model-artifact.ts` 当前输出 `modelExists=false`

### 4. `NailArtPicker` 可以从模型结果显示候选

当前状态：

- 代码层面已满足
- 真实模型资产层面未完全证明

证据：

- `src/components/NailArtPicker.tsx`
- `src/lib/nail-texture-recognition/client-worker.ts`
- `src/workers/nail-texture-recognition.worker.ts`
- `verify-browser-integration.test.ts`

### 5. 模型失败时现有 fallback 继续可用

当前状态：

- 已满足（代码和自动化门禁层面）

证据：

- `fallback-adapter.ts`
- `recognize.ts`
- `nail-texture-model-runtime.test.ts`
- 浏览器集成门禁与真实模型最终审计脚本均保留 fallback 路径

### 6. 参考图流程继续通过：上传图 -> 自动候选 -> 完成分配 -> 生成纹理

当前状态：

- 代码层面与既有基线路径保持
- 但没有新的真实 UI 运行证据证明“当前这一次仓库状态下完整手工流程已重新实测”

结论：

- 可判定为“代码验收通过，真机/UI 证据仍偏弱”

### 7. `npm.cmd test`、`npm.cmd run lint`、`npm.cmd run build` 通过

当前状态：

- 已满足

最近证据：

- `npm.cmd test`：91 passed / 0 failed / 1 skipped
- `npm.cmd run lint`：通过
- `npm.cmd run build`：通过

## 四、当前真正的阻塞点

到今天这个阶段，项目最核心的阻塞点只有三类：

### A. 数据资产阻塞

- 正式数据集为 0
- 缺 200 张训练图
- 缺 800 个有效 mask
- 缺 test split 负样本
- 缺 test split 复杂背景样本

### B. 模型资产阻塞

- 没有真实 `best.pt`
- 没有真实 `metrics.json`
- 没有真实 `nail-texture-seg-v1.onnx`

### C. 真实 UI / 性能证据阻塞

- 缺桌面浏览器单图耗时实测证据
- 缺中端手机单图耗时实测证据
- 缺真实模型条件下的完整 `/ar-tryon` 手工验收记录

## 五、建议的下一步顺序

如果目标是尽快让规划中的 MVP 真正往完成态推进，优先级建议如下：

1. 先补第一批真实训练数据  
   - 不是继续扩代码，而是按 `run-reviewed-batch-import-pipeline.ts` 把首批样本真正导入正式数据集

2. 持续跑 `audit-phase1-readiness.ts` 和 `plan-phase1-collection.ts`  
   - 直到 Phase 1 的 `200 / 800 / test coverage` 真实通过

3. 然后再跑真实训练发布流水线  
   - `scripts/run-training-release-pipeline.ts`

4. 产出真实 ONNX 后，再跑真实模型最终审计  
   - `scripts/run-real-model-final-audit.ts`

## 六、当前审计结论

截至 2026-07-01，项目状态更准确的描述应当是：

- Phase 0：基本完成
- Phase 1：工具链完成，真实数据未完成
- Phase 2：训练发布链完成，真实模型未完成
- Phase 3：浏览器接线与门禁完成，真实模型资产未完成
- Phase 4：未完成
- Phase 5：部分铺底，未完成

如果只看代码工程进度，这个项目已经走得很远。

如果按规划文档的最终交付标准看，它现在仍然处于：

> “工程骨架已基本铺开，但真实数据集与真实模型资产仍是决定性阻塞项”的状态。
