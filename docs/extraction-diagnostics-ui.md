# 提取诊断信息的 UI 结构化展示

版本：v1.0  
日期：2026-07-02

这一步对应 `docs/nail-texture-recognition-model-plan.md` 里 Phase 4 的“低质量候选提示”和“透明裁剪结果可解释性”继续收口。

前面我们已经把：

- 候选 warning
- 候选置信度

透出到了 `NailArtPicker`。这次继续把：

- `extractionDiagnostics.quality`
- `extractionDiagnostics.highlightRepair`

整理成结构化摘要，直接展示给用户。

## 当前实现位置

- `src/components/nail-art-picker-quality.ts`
- `src/components/NailArtPicker.tsx`

## 这次补齐了什么

### 1. 新增 extraction diagnostics 摘要层

新增：

- `summarizeExtractionDiagnostics()`

它会把提取后的诊断信息整理成：

- `severity`
- `title`
- `stats`
- `messages`

而不是让 UI 自己去拼：

- `quality.ok`
- `highlightPixels`
- `repairedPixels`

这些底层字段。

### 2. UI 现在会把提取结果显示成“状态 + 数据 + 建议”

当前候选如果已经完成 mask 纹理提取，底部会显示一个单独的信息块，包含：

- 当前纹理提取结果是否稳定
- 高光像素数量
- 已修复像素数量
- 质量或高光相关的具体说明

这比之前只显示一行：

```text
quality=... · highlight=... · repaired=...
```

更适合用户理解，也更适合后续继续扩展。

### 3. 高光修复状态现在也能被用户感知

如果检测到高光：

- 且修复成功，会提示“已对可修复部分做轻微修复”
- 如果没有足够上下文完成修复，也会明确告诉用户

这样用户看到的不是抽象计数，而是可判断的结果说明。

## 为什么这一步重要

到这一步，Phase 4 的 UI 已经不只是告诉用户“这个候选可能不稳”，而是开始告诉用户：

- 纹理提取本身是否稳定
- 高光问题有没有被处理
- 边界和透明裁剪有没有明显风险

这会直接降低“用户看不懂结果，只能盲试”的成本。

## 自动化验收

本轮新增覆盖：

- `tests/nail-art-picker-quality.test.ts`
  - 验证 `summarizeExtractionDiagnostics()` 的摘要结构和文案

并继续通过：

- `tests/nail-texture-mask-pipeline.test.ts`
- `tests/nail-texture-mask-extract.test.ts`
- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`
