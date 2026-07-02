# 开发日志 - 2026-07-02

## 本次补充

今天继续往下推进，把 reviewed batch import 和 training release 主链之间正式补了一层标准 handoff 文件。

本次核心改动：

- `scripts/build-reviewed-batch-release-handoff.ts`
- `model/training/run-reviewed-batch-import-pipeline.ts`
- `scripts/run-training-release-pipeline.ts`
- `tests/run-reviewed-batch-import-pipeline.test.ts`
- `tests/run-training-release-pipeline.test.ts`

## 这次具体做了什么

### 1. 新增标准 handoff 文件

新增脚本：

- `scripts/build-reviewed-batch-release-handoff.ts`

它会把 reviewed batch import 阶段已经产出的几个关键上下文收敛成一份：

- `reviewed-batch-release-handoff.json`

这份 handoff 里主要记录：

- `rootDir`
- `reviewedBatchImportPipelineReportPath`
- `releaseTraceDraftPath`
- `sourceGroup`
- `datasetRoot`
- `reviewedImportReportPath`
- `importedFileCount`

### 2. reviewed batch import 流水线自动产出 handoff

`run-reviewed-batch-import-pipeline.ts` 现在在：

- `build-initial-release-trace-draft`

之后，会继续自动生成：

- `build-reviewed-batch-release-handoff`

也就是说 reviewed batch 这条线结束后，已经天然具备交给 training release 主链的标准交接文件。

### 3. training release 主链优先消费 handoff

`run-training-release-pipeline.ts` 现在新增支持：

- `--governance-reviewed-batch-release-handoff`

当提供这份 handoff 后，主链会优先从中恢复：

- reviewed batch root dir
- reviewed batch import pipeline report
- release trace draft

这样对主链来说，reviewed batch 交接已经从“多路径拼装”变成了“单入口恢复”。

## 自动化测试

这次新增验证了两条关键路径：

- reviewed batch import 流水线会成功生成 handoff
- training release 主链可以优先消费 handoff 并继续跑 governance

## 验证结果

本次改动完成后，已执行并通过：

- `npm.cmd test -- tests/run-reviewed-batch-import-pipeline.test.ts tests/run-training-release-pipeline.test.ts tests/run-release-governance-pipeline.test.ts`

后续还会继续执行：

- `npm.cmd run lint`
- `npm.cmd run build`

## 当前效果

到这里，reviewed batch → training release 的接力又减少了一层手工耦合。

现在不是：

- import 流水线给你几个路径
- 你再手工一条条传给 training release

而是：

- import 流水线直接产出 handoff
- training release 主链优先读 handoff

这让整条 Phase 5 主链更接近真正连续的流水线形态。
