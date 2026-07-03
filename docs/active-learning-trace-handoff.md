# Active Learning 追踪草稿与交接

版本：v1.0  
日期：2026-07-03

当页面修正样本开始通过主动学习流水线批量回流后，我们不仅需要“导进去了”，还需要正式记录：

- 导入了多少样本
- 这些样本的优先级分布
- 使用了什么 priority filter
- 这批回流后对 Phase 1 readiness 的当前状态是什么

这次新增了两份正式产物：

- `active-learning-release-trace-draft.json`
- `debug-sample-active-learning-handoff.json`

## 1. trace draft

由：

```text
scripts/build-active-learning-release-trace-draft.ts
```

生成。

它会把 active learning pipeline 里的关键信息沉淀进 `release trace` 风格的草稿结构中，当前重点包含：

- `activeLearning.pipelineReportPath`
- `activeLearning.priorityReportPath`
- `activeLearning.priorityFilters`
- `activeLearning.importedSampleCount`
- `activeLearning.importedByPriority`
- `activeLearning.readinessSnapshot`

这样后面如果我们要把“这批高优先修正样本”的影响继续串到训练发布或治理链路里，就已经有统一结构可用。

## 2. handoff

由：

```text
scripts/build-debug-sample-active-learning-handoff.ts
```

生成。

它的作用类似 reviewed batch handoff，只不过面向的是页面修正样本这条链路。当前会保留：

- active learning pipeline report 路径
- active learning release trace draft 路径
- 导入样本数量
- priority filter 信息

## 3. 它们如何产生

现在 `run-debug-sample-active-learning-pipeline.ts` 跑完后，会自动补出这两份产物，所以你通常不需要手工调用这两个脚本。

## 4. 对 release trace 的影响

`build-release-trace-index.ts` 现在已经可以读取 release trace draft 里的：

- `activeLearning.importedSampleCount`
- `activeLearning.importedByPriority`
- `activeLearning.priorityFilters`
- `activeLearning.readinessSnapshot`

这意味着后面 release trace 不再只知道：

- 这版模型来自哪一批 seed batch

也开始能知道：

- 这版模型前面是否吸收过高优先级页面修正样本
- 吸收的力度和当前 readiness 状态大概是什么
