# 开发日志 - 2026-07-02

## 本次补充

今天继续沿着 `docs/nail-texture-recognition-model-plan.md` 往下推进，把“正式 release trace 自动登记进历史台账”接到了安全晋升入口里。

这次落地的重点是：

- 更新 `scripts/promote-approved-release.ts`
- 复用 `scripts/register-release-trace-index.ts`
- 增加 `tests/promote-approved-release.test.ts`

## 这次具体做了什么

### 1. 在 promotion 成功后自动登记正式 trace

`promote-approved-release.ts` 现在新增支持：

- `--trace-index`
- `--history-manifest`
- `--trace-registration-output`

当本次 decision 允许晋升，且 `register-model-release.ts` 成功后：

1. 先完成模型 registry 注册
2. 再自动调用 `register-release-trace-index.ts`
3. 把本次 `release-trace-index.json` 合并进 `release-history-manifest.json`

这样后面不需要再手工补一遍 trace 历史登记。

### 2. 把 trace 登记结果写回 promotion 报告

`promotion-report.json` 现在除了原本的：

- `registerSummary`

还会额外带上：

- `traceRegistrationSummary`

这样后面查看一次 promotion 报告，就能同时知道：

- 模型有没有成功注册
- 正式 trace 有没有成功进入历史台账

### 3. 补充自动化测试

新增验证场景：

- `approve_candidate` 正常晋升
- 晋升成功后自动登记正式 trace
- `hold_candidate` 被阻止
- `manual_review` 在显式授权后允许继续

## 验证结果

本次改动完成后，已执行并通过：

- `npm.cmd test -- tests/promote-approved-release.test.ts tests/register-release-trace-index.test.ts`
- `npm.cmd run lint`
- `npm.cmd run build`

## 当前效果

到这里，release 闭环又少了一步手工操作：

1. 训练 / 审计 / 决策完成
2. 执行安全晋升
3. registry 更新
4. release trace 自动进入历史 manifest

也就是说，后面我们回看某个版本时，不只是知道“它有没有被发布”，还可以直接从历史台账一路追到：

- 它来自哪一批数据
- 当时的 audit 结果是什么
- decision 是怎么做出来的
- 最终有没有被正式晋升
