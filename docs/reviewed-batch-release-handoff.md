# Reviewed batch release handoff

版本：v1.1
日期：2026-07-04

这份 handoff 文件是给 reviewed batch import 流水线和 training release 主链之间做交接用的。

它的定位不是新的训练或发布报告，而是一份很轻的“衔接上下文索引”，帮助后面的主链少传路径、少靠人工拼参数。

## 产物位置

当你执行：

```bash
node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir C:/path/to/seed-batch-020
```

流水线现在除了已有的：

- `reviewed-batch-import-pipeline-report.json`
- `release-trace-draft.json`

还会新增：

- `reviewed-batch-release-handoff.json`

默认就放在同一个 `rootDir` 下。

## 它里面有什么

这份 JSON 主要记录三类信息：

1. reviewed batch 根目录
2. reviewed batch import 流水线报告路径
3. release trace draft 路径

同时还会附带批次摘要，例如：

- `sourceGroup`
- `datasetRoot`
- `reviewedImportReportPath`
- `importedFileCount`
同时会新增 `trainingReadiness` 摘要：

- `ok`：整个数据集当前是否可进入正式训练
- `reportPath`：训练数据总门禁报告路径
- `authorizationMode`：通常为 `release`
- `gates.sourceAudit`：来源记录和磁盘文件是否一致
- `gates.sourceAuthorization`：素材授权是否满足正式训练要求
- `gates.phase1Readiness`：200 张图片、800 个有效 mask、split 和测试覆盖是否通过
- `totals.images` / `totals.validMasks`：当前数据量
- `failingSteps`：仍未通过的子门禁

同样的 `trainingReadiness` 摘要也会写入 `release-trace-draft.json`。后续训练和治理链路只读取 handoff/trace 就能判断数据是否准备好，不需要再回头拼接多个审计文件。

## 用法

training release 主链现在可以直接消费它：

```bash
node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts --skip-train --skip-evaluate --skip-export --final-audit-image model/5188.jpg_wh860.jpg --final-audit-ui-review model/fixtures/real-model-ui-review.template.json --run-governance --governance-reviewed-batch-release-handoff C:/path/to/seed-batch-020/reviewed-batch-release-handoff.json
```

这样主链会自动拿到：

- reviewed batch root dir
- reviewed batch import pipeline report
- release trace draft
- 以及后续治理默认路径模板所需的上下文入口

不需要你再把这些路径逐个传进去。

## 为什么要有这层

之前的方式是：

- reviewed batch import 产出多个文件
- training release 主链需要分别知道这些文件的位置

现在通过 handoff，我们把“多文件交接”变成了“单文件交接”。

这让：

- 手工命令更短
- 主链接力更稳定
- 后续如果 handoff 想再加新字段，也更容易扩展

## 和 training release 默认路径的关系

现在 handoff 的作用已经不只是一份“路径索引”。

当 training release 主链收到 handoff 后，它会优先恢复：

- `reviewedBatchRootDir`
- `reviewedBatchImportPipelineReportPath`
- `releaseTraceDraftPath`

并继续结合主链自己的：

- `modelVersion`
- `trainOutputDir`
- `browserModelDir`

自动补齐治理默认路径，例如：

- `compare-summary.json`
- `release-registry.json`
- `release-history-manifest.json`

这让 reviewed batch → training release → governance 之间的接力更加连续。
