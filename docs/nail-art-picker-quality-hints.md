# NailArtPicker 低质量候选提示

版本：v1.0  
日期：2026-07-02

这一步对应 `docs/nail-texture-recognition-model-plan.md` 里 Phase 4 的“低质量候选提示”。

目标不是新增识别算法，而是把识别链已经产出的：

- `confidence`
- `warnings`
- `extractionDiagnostics.quality`

真正透出给 `NailArtPicker` 用户界面，让用户在确认贴图前知道哪些候选值得复核。

## 当前实现位置

- `src/components/nail-art-picker-quality.ts`
- `src/components/NailArtPicker.tsx`

## 这次补齐了什么

### 1. warning 代码不再直接裸露给用户

现在新增了一层展示映射：

- `presentRecognitionWarning()`
- `summarizeRegionQuality()`
- `regionNeedsReview()`

它把内部 warning code 翻译成更可理解的提示语，例如：

- `angle_defaulted_vertical`
- `highlight_hotspots`
- `mask_crop_touches_edge`
- `worker_unavailable_used_main_thread`

不再直接原样显示在 UI 上。

### 2. 候选是否需要复核现在有统一规则

当前只要满足任一条件，就会认为候选需要复核：

- `confidence === "low"`
- 存在候选级 `warnings`
- 存在提取后质量问题 `extractionDiagnostics.quality.ok === false`

这意味着 UI 的：

- 顶部状态提醒
- 候选标签 `⚠`
- 底部当前候选质量面板

都不再各自发散判断，而是共用同一套口径。

### 3. 当前候选会显示结构化质量面板

以前底部只会直接输出原始 warning 列表。

现在选中某个候选时，会显示：

- `当前候选质量正常`
或
- `建议复核当前候选`

并列出用户可理解的具体原因。

这样用户能更快知道：

- 是角度不稳
- 是裁剪贴边
- 是高光过强
- 还是当前候选整体置信度偏低

## 这一步的价值

它把 Phase 4 从“后处理内部知道有风险”推进到“用户确认前就能看到风险”。

这对后续两件事都重要：

1. 减少无提示情况下的错误确认
2. 让 debug sample 导出的人工修正更有针对性

## 自动化验收

本轮新增了：

- `tests/nail-art-picker-quality.test.ts`

覆盖：

- 识别 warning 的用户文案映射
- `regionNeedsReview()` 统一判定
- `summarizeRegionQuality()` 去重与汇总逻辑

并额外通过：

- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`
