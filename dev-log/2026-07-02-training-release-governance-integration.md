# 开发日志 - 2026-07-02

## 本次补充

今天继续沿着 `docs/nail-texture-recognition-model-plan.md` 推进，把刚完成的 release governance 流水线接回了 training release 主链。

这次改动的核心文件：

- `scripts/run-training-release-pipeline.ts`
- `tests/run-training-release-pipeline.test.ts`
- `docs/training-release-pipeline.md`

## 这次具体做了什么

### 1. training release 流水线新增可选 governance 入口

`run-training-release-pipeline.ts` 现在新增支持：

- `--run-governance`
- `--governance-compare-summary`
- `--governance-registry`
- `--governance-release-trace-draft`
- `--governance-reviewed-batch-import-pipeline-report`
- `--governance-history-manifest`
- `--governance-allow-manual-review`
- `--governance-set-current`
- `--governance-promote`

这意味着现在 training release 在生成完自己的报告后，可以继续自动调用：

- `run-release-governance-pipeline.ts`

不需要后面再手工拼接第二条治理命令。

### 2. 主链行为保持兼容

这次不是强制改行为，而是做成“默认不变、按需开启”：

- 不加 `--run-governance`：行为和以前一致
- 加了 `--run-governance`：训练发布报告写完后，继续跑 release governance

这样老的训练/验收习惯不会被破坏，但新的闭环已经能直接开启。

### 3. 报告里补上 governance 产物

当启用 governance 后，`training-release-pipeline-report.json` 现在会额外包含：

- `paths.governanceReportPath`
- `options.runGovernance`
- `options.governance*`
- `artifacts.releaseGovernance`

这样后面查看一份 training release 报告，就能同时知道：

- 训练 / 导出 / 验收有没有通过
- 最终审计是否通过
- release decision 是什么
- candidate 有没有被晋升
- trace / history 有没有完成建档

## 自动化测试

这次新增了主链级别的集成验证：

- 训练发布链可继续进入 release governance
- governance 产物会被回写到 training release 报告

## 验证结果

本次改动完成后，已执行并通过：

- `npm.cmd test -- tests/run-training-release-pipeline.test.ts tests/run-release-governance-pipeline.test.ts`

后续还会继续执行：

- `npm.cmd run lint`
- `npm.cmd run build`

## 当前效果

到这里，training release 主链已经从：

训练 → 导出 → 验收 → final audit

继续推进到了：

训练 → 导出 → 验收 → final audit → decision → promotion → trace → history

也就是说，现在真正开始有了“从模型训练到治理入账”的连续主线，而不是只靠多个独立脚本手工串接。
