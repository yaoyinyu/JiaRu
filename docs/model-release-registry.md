# 模型版本 registry 与回滚

版本：v1.0  
日期：2026-07-01

这一步对应规划文档 Phase 5 里的：

- 增加模型版本 manifest
- 可回滚到上一个模型版本

## 设计

浏览器模型目录中保留：

- 当前活动版本：`manifest.json`
- 每个已登记版本的快照：`manifest.<version>.json`
- 版本登记表：`release-registry.json`

## 注册当前版本

```bash
node --no-warnings --experimental-strip-types scripts/register-model-release.ts --manifest public/models/nail-texture-seg/manifest.json
```

这一步会：

- 校验当前 manifest 对应的模型文件存在
- 生成 `manifest.<version>.json` 快照
- 把版本信息写入 `release-registry.json`
- 默认把当前版本标记为 active

## 切换 / 回滚到历史版本

```bash
node --no-warnings --experimental-strip-types scripts/switch-model-release.ts --version nail-texture-seg-v1
```

这一步会：

- 从 `release-registry.json` 中找到目标版本
- 把对应 `manifest.<version>.json` 复制回当前 `manifest.json`
- 更新 `currentVersion`

## 适用时机

- 已经有至少两版真实浏览器模型资产
- 需要保留 baseline 以便回滚
- 需要配合 `compare-training-releases.ts` 做发布决策
