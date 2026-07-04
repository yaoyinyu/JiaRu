# 模型评估可视化产物与门禁

版本：v1.0  
日期：2026-07-04

对应规划 Phase 2 的要求：

- 输出混淆样本
- 输出失败样本可视化
- 固定测试集评估结果可复查

## 生成方式

```powershell
python model/training/evaluate.py `
  --weights model/exports/nail-texture-seg-v1/nail-texture-seg-v1/weights/best.pt `
  --output model/exports/nail-texture-seg-v1/metrics.json `
  --artifacts-dir model/exports/nail-texture-seg-v1/evaluation-artifacts `
  --split test
```

评估脚本会启用 Ultralytics 的 `plots`、`save_json`、`save_txt` 和
`save_conf`，并在 `evaluation-artifacts/` 下保存混淆矩阵、PR 曲线、
预测与真值对照图、逐图预测标签和预测 JSON。

实际文件名由当前 Ultralytics 版本决定，`evaluation-artifacts.json`
会记录本次评估目录中的全部文件和分类计数。

## 独立验收

```powershell
node --no-warnings --experimental-strip-types scripts/verify-evaluation-artifacts.ts `
  --index model/exports/nail-texture-seg-v1/evaluation-artifacts/evaluation-artifacts.json `
  --require-split test
```

硬性条件：

- 索引结构版本为 `1`
- 使用要求的 split，正式发布默认为 `test`
- 至少存在一张混淆矩阵
- 至少存在一张 prediction 与 ground truth 对照图
- 索引中的每个文件必须真实存在、非空且为普通文件
- `artifacts_dir` 必须与索引所在目录一致
- 禁止绝对路径、`..` 越界路径和重复文件条目
- `total`、`plots`、`prediction_labels`、`json` 计数必须与索引内容一致

PR 曲线和逐图预测标签缺失会产生警告。负样本占比较高时，预测标签为空可能是正常情况，因此不直接作为硬失败。

## 发布流水线行为

`run-training-release-pipeline.ts` 在真实 `evaluate.py` 完成后自动执行
`verify-evaluation-artifacts.ts`。关键可视化缺失时，流水线立即失败，不继续导出或发布候选模型。

流水线报告同时提供：

- `paths.evaluationArtifactsDir`
- `paths.evaluationArtifactIndexPath`
- `artifacts.evaluationArtifacts`

dry-run 只验证参数和目标路径，不伪造可视化通过结果。
