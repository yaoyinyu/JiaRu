# Debug Sample 主动学习导入流水线

版本：v1.0  
日期：2026-07-03

这条流水线把页面修正样本的主动学习闭环收口成一个统一入口：

- 先给 debug sample 排优先级
- 再按优先级筛选并导入
- 然后继续跑数据集审计、split、标签转换和 Phase 1 readiness

新增脚本：

```text
model/training/run-debug-sample-active-learning-pipeline.ts
```

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-debug-sample-active-learning-pipeline.ts --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images --copy-image --origin-type user --origin-ref "authorized debug corrections" --license "user-authorized-internal-training"
```

如果只想先导入高价值样本：

```bash
node --no-warnings --experimental-strip-types model/training/run-debug-sample-active-learning-pipeline.ts --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images --copy-image --min-priority medium --top 20 --origin-type user --origin-ref "authorized debug corrections" --license "user-authorized-internal-training"
```

## 它会自动串起哪些步骤

1. `prioritize-debug-samples.ts`
2. `import-debug-sample.ts`
3. `sync-sources-csv.ts`
4. `audit-sources-csv.ts`
5. `split-dataset.ts`
6. `audit-labels.ts`
7. `convert-annotations.ts`
8. `audit-phase1-readiness.ts`
9. `plan-phase1-collection.ts`
10. `generate-first-batch-checklist.ts`

## 输出

默认会生成两份文件：

- `prioritized-debug-samples.json`
- `debug-sample-active-learning-pipeline-report.json`

默认位置都在 `--sample-dir` 下，也可以自己通过参数改掉。

## 适用场景

这条流水线适合：

- 页面里已经导出了一批 debug sample
- 不想人工翻每份 JSON 再逐个导入
- 希望先吃掉高价值修正样本
- 希望导入后立刻看到对正式数据集 readiness 的真实影响

## 和 reviewed batch pipeline 的关系

- `run-reviewed-batch-import-pipeline.ts`：适合参考图 / 商家图 / seed batch
- `run-debug-sample-active-learning-pipeline.ts`：适合页面修正样本 / 用户纠正样本

两条链路现在分别覆盖了：

- 批量采集导入
- 页面纠正回流

这样 Phase 1 到 Phase 5 之间的数据闭环会更完整。
## warningBreakdown 输出

`prioritized-debug-samples.json` 还会包含 `warningBreakdown`，用于汇总这批样本中的运行时 warning，例如模型清单错误、ONNX session 初始化失败、模型输出为空后回退等。后续 release trace / handoff 会保留这个字段，方便在不立即训练真实模型的阶段先判断问题集中在哪条链路。

## Debug sample recognition options

页面导出的 debug sample 现在会保留 UI 识别配置：`recognitionOptions.maxCandidates` 与 `recognitionOptions.workerTimeoutMs`。`import-debug-sample.ts` 会把这些字段透传到 annotation 的 `image.debug.recognitionOptions`，方便后续回放某个样本时确认它是在什么候选数和 Worker 超时策略下产生的。

`worker_timeout_used_main_thread` 已归类为模型运行时 warning。这样即使当前阶段不训练真实模型，active-learning 优先级和 release review 仍能把 Worker 超时回退视为需要复盘的运行时风险。

## Debug low-score option handoff

Debug samples and imported annotations now preserve `recognitionOptions.includeLowConfidenceCandidates` when the low-score candidate review mode was explicitly enabled. Normal samples omit the field, while debug-retained low-score candidate samples can be replayed with the same candidate visibility policy.
