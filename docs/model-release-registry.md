# 模型版本 registry 与回滚

版本：v1.2
日期：2026-07-04

这一页对应 `nail-texture-recognition-model-plan.md` Phase 5 的模型版本治理：发布后必须能定位当前版本、保留旧版本快照，并在需要时安全回滚。

## 目录结构

浏览器模型目录中保留三类文件：

- 当前活动版本：`manifest.json`
- 每个已登记版本的快照：`manifest.<version>.json`
- 版本登记表：`release-registry.json`

`release-registry.json` 里的每个 release 条目必须记录：

- `version`
- `manifestSnapshotPath`
- `modelFile`
- `modelPath`
- `inputSize / task / backendPreferences / labels`
- `modelSizeBytes`
- `modelSizeMb`
- `sha256`
- `registeredAt`

其中 `modelSizeBytes` 和 `sha256` 是回滚安全的核心字段：它们证明 registry 指向的 ONNX 文件没有在发布后被替换或损坏。

## 注册当前版本

```bash
node --no-warnings --experimental-strip-types scripts/register-model-release.ts --manifest public/models/nail-texture-seg/manifest.json
```

这一步会：

- 读取当前 manifest 对应的 ONNX 文件。
- 计算模型文件的精确字节数 `modelSizeBytes`。
- 计算模型文件 SHA-256。
- 生成 `manifest.<version>.json` 快照。
- 把版本信息写入 `release-registry.json`。
- 默认把该版本设置为 `currentVersion`。

## 切换 / 回滚到历史版本

```bash
node --no-warnings --experimental-strip-types scripts/switch-model-release.ts --version nail-texture-seg-v1
```

这一步会：

- 从 `release-registry.json` 找到目标版本。
- 检查目标版本的 manifest 快照存在。
- 检查目标版本的 ONNX 文件存在。
- 重新计算 ONNX 的 `modelSizeBytes` 和 `sha256`。
- 只有实际文件与 registry 完全一致时，才把 `manifest.<version>.json` 复制回当前 `manifest.json`。
- 更新 `currentVersion`。

如果模型文件被替换、损坏、截断，切换会失败，不会污染当前 manifest。

## 回滚审计门禁

```bash
node --no-warnings --experimental-strip-types scripts/audit-release-rollback.ts --registry public/models/nail-texture-seg/release-registry.json --manifest public/models/nail-texture-seg/manifest.json
```

审计会检查：

- `currentVersion` 是否存在，并且能在 `releases` 中找到。
- registry 是否至少保留一个非当前版本作为回滚候选。
- 每个版本的 manifest 快照和 ONNX 文件是否仍在磁盘上。
- manifest 快照里的 `version / modelFile / inputSize / task / backendPreferences / labels` 是否和 registry 条目一致。
- registry 条目是否包含合法的 `modelSizeBytes` 和 `sha256`。
- ONNX 文件的实际大小和 SHA-256 是否和 registry 一致。
- 如果 manifest 快照也包含 `modelSizeBytes / sha256`，它们是否和 registry 一致。
- 当前 `manifest.json` 的版本是否和 registry 的 `currentVersion` 一致。

这让“可回滚到上一版模型”不只是文件存在，而是能被发布前审计证明：目标文件仍然是当时登记的那个模型。

## 适用时机

- 已经有至少两版真实浏览器模型资产。
- 需要保留 baseline，方便快速回滚。
- 需要配合 `compare-training-releases.ts` 做发布决策。
- 需要在 `run-release-governance-pipeline.ts` 中自动证明发布后仍可安全回滚。

## 和 release governance 的关系

`run-release-governance-pipeline.ts` 在 promotion 成功后会自动调用 `audit-release-rollback.ts`。这意味着 registry 不能只包含版本号，还必须由 `register-model-release.ts` 生成完整条目、manifest 快照、模型大小和 SHA-256。否则即使模型文件复制成功，治理总报告也会因为“不可验证回滚”而失败。