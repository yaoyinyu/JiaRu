# 安全发布入口：先审再发

版本：v1.1  
日期：2026-07-02

这个脚本把：

- `build-release-decision-report.ts`
- `register-model-release.ts`

串成一个更安全的发布入口，避免在还没确认 release decision 的情况下，直接把 candidate 注册成当前版本。

## 命令

当 `release-decision-report.json` 的结论是 `approve_candidate` 时：

```bash
node --no-warnings --experimental-strip-types scripts/promote-approved-release.ts --decision-report model/exports/nail-texture-seg-v2/release-decision-report.json
```

如果这次发布已经生成正式 trace，希望在晋升成功后自动登记进历史台账：

```bash
node --no-warnings --experimental-strip-types scripts/promote-approved-release.ts --decision-report model/exports/nail-texture-seg-v2/release-decision-report.json --trace-index model/exports/nail-texture-seg-v2/release-trace-index.json
```

## 它会做什么

1. 读取 `release-decision-report.json`
2. 找到其中对应的 `pipelineReportPath`
3. 从 pipeline report 里拿到 `paths.manifestPath`
4. 检查决策状态是否允许发布
5. 只有通过后，才继续调用 `register-model-release.ts`
6. 如果提供了 `--trace-index`，则在发布成功后继续调用 `register-release-trace-index.ts`

## 默认规则

- `approve_candidate`：允许发布
- `manual_review`：默认不允许
- `hold_candidate`：禁止发布

## 如果你已经做完人工确认

对于 `manual_review`，只有在你明确授权时才允许继续：

```bash
node --no-warnings --experimental-strip-types scripts/promote-approved-release.ts --decision-report model/exports/nail-texture-seg-v2/release-decision-report.json --allow-manual-review true
```

## 可选参数

- `--registry <release-registry.json>`：指定要写入的 registry
- `--trace-index <release-trace-index.json>`：发布成功后，把这次正式 trace 自动登记进历史 manifest
- `--history-manifest <release-history-manifest.json>`：指定历史台账输出位置
- `--trace-registration-output <trace-registration-report.json>`：指定 trace 自动登记报告输出位置
- `--output <promotion-report.json>`：指定 promotion 报告输出位置
- `--set-current true|false`：是否把当前 candidate 设为 current version
- `--allow-manual-review true|false`：是否允许人工放行 `manual_review`

## 输出

默认会在 decision report 同目录生成：

```text
promotion-report.json
```

其中会记录：

- `decisionStatus`
- `candidateVersion`
- `manifestPath`
- `registerSummary`
- `traceRegistrationSummary`
- 如果被拦下，则记录 `reason` 和 `nextActions`

当启用了 `--trace-index` 时，还会额外得到：

```text
trace-registration-report.json
```

里面会记录：

- `traceIndexPath`
- `historyManifestPath`
- `traceIndexCount`
- `includedTraceIndexes`

## 推荐顺序

建议完整顺序：

1. `run-training-release-pipeline.ts`
2. `compare-training-releases.ts`
3. `build-release-decision-report.ts`
4. `promote-approved-release.ts`

如果需要追踪历史台账，则在第 4 步传入 `--trace-index`。

这样 Phase 5 的发布闭环会变成：

训练产物 → 最终审计 → 失败归因 → A/B 对比 → 决策报告 → 安全晋升 → trace 历史登记
