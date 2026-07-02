# 开发日志 - 2026-07-02

## 本次补充

今天继续沿着 `docs/nail-texture-recognition-model-plan.md` 往下推进，把 handoff 再往前用了一层：让 training release 主链基于 handoff 和 `modelVersion` 自动补更多默认路径。

本次核心改动：

- `scripts/run-training-release-pipeline.ts`
- `tests/run-training-release-pipeline.test.ts`
- `docs/training-release-pipeline.md`
- `docs/reviewed-batch-release-handoff.md`

## 这次具体做了什么

### 1. `modelVersion` 现在会自动对齐默认 `runName` 和 `trainOutputDir`

之前如果手工传了：

- `--model-version nail-texture-seg-v9`

但没传：

- `--run-name`
- `--train-output-dir`

主链可能仍然落在旧的默认目录里。

现在主链会自动对齐成：

- `runName = nail-texture-seg-v9`
- `trainOutputDir = model/exports/nail-texture-seg-v9`

这样版本号和输出目录更一致。

### 2. governance 默认路径开始自动补齐

现在当启用：

- `--run-governance`

且没有手工传某些治理路径时，主链会自动补：

- `compare-summary.json` -> `<train-output-dir>/compare-summary.json`
- `release-registry.json` -> `<browser-model-dir>/release-registry.json`
- `release-history-manifest.json` -> `<train-output-dir>/release-history-manifest.json`

这意味着治理链条的手工参数又少了一层。

### 3. handoff 从“上下文索引”升级成“默认路径入口”

之前 handoff 主要解决的是：

- reviewed batch root dir
- reviewed batch import report
- release trace draft

现在它的意义更强了：

- 主链先从 handoff 恢复 reviewed batch 上下文
- 再结合 `modelVersion` / `trainOutputDir` / `browserModelDir`
- 自动补全 governance 相关默认路径

也就是说，handoff 已经开始承担真正的主链配置入口角色，而不只是单纯存几个文件路径。

## 自动化测试

这次新增验证了两条关键行为：

- `modelVersion` 会自动对齐默认 `runName` / `trainOutputDir`
- handoff 场景下，governance 默认路径会自动补齐并成功跑通

## 验证结果

本次改动完成后，已执行并通过：

- `npm.cmd test -- tests/run-training-release-pipeline.test.ts tests/run-reviewed-batch-import-pipeline.test.ts tests/run-release-governance-pipeline.test.ts`

后续还会继续执行：

- `npm.cmd run lint`
- `npm.cmd run build`

## 当前效果

到这里，training release 主链又少了几项必须手工指定的路径。

现在从使用体验上，已经更接近：

1. reviewed batch import 产出 handoff
2. training release 主链读取 handoff
3. 主链自动补齐训练/治理默认目录
4. final audit + governance 继续顺流而下

这让整条链越来越像真正连续的流水线，而不是一组功能存在但需要人工小心拼接的脚本。
