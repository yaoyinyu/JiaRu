# 开发日志 - 2026-07-02

## 本次补充

今天继续沿着 `docs/nail-texture-recognition-model-plan.md` 的 Phase 5 往下推进，把 release 治理相关脚本收口成一条统一流水线。

这次新增：

- `scripts/run-release-governance-pipeline.ts`
- `tests/run-release-governance-pipeline.test.ts`
- `docs/release-governance-pipeline.md`

## 这次具体做了什么

### 1. 增加统一的 release governance 入口

原本我们已经有：

- release decision
- promotion
- release trace index
- trace history register

但这些能力还是分散的，需要人工按顺序调用。

这次新脚本把它们串成：

1. `build-release-decision-report.ts`
2. `promote-approved-release.ts`
3. `build-release-trace-index.ts`
4. `register-release-trace-index.ts`

这样后面执行 candidate 治理时，不需要再靠人工记忆顺序。

### 2. 明确了“放行”和“拦截”两条分支

新的流水线行为是：

- 如果 decision 允许自动晋升，就继续做 promotion
- 如果 decision 是 `hold_candidate`，就不做 promotion
- 不管 candidate 是否被拦截，都会继续生成 `release-trace-index.json`
- 只有 promotion 真实成功后，才会把正式 trace 写入 history manifest

这意味着：

- 放行版本：得到完整发布闭环
- 拦截版本：也保留 decision + trace 证据，方便后续复盘

### 3. 把 report 语义补稳定

这轮中间顺手修了两个治理层的小口径问题：

- `promotion` 被跳过时，`skipped` 字段现在会正确标记为 `true`
- 后续 trace history registration 现在要求 “promotion 真正执行且成功”，不再把“被跳过但 ok=true”误判成已发布

## 自动化测试

新增覆盖了两条关键路径：

- candidate 被批准后，一次完成 decision / promotion / trace / history
- candidate 被拦截后，整体失败，但仍然保留 decision 和 trace

## 验证结果

本次改动完成后，已执行并通过：

- `npm.cmd test -- tests/run-release-governance-pipeline.test.ts tests/promote-approved-release.test.ts tests/build-release-decision-report.test.ts tests/build-release-trace-index.test.ts tests/register-release-trace-index.test.ts`

后续还会继续执行：

- `npm.cmd run lint`
- `npm.cmd run build`

## 当前效果

到这里，Phase 5 的治理链又往前收了一步。

现在不是只有单个脚本都存在，而是已经有一条真正可执行的总控入口，把：

- 决策
- 发布
- trace
- history

连成一条稳定顺序。
