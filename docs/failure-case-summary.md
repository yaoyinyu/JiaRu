# 失败样本分类汇总

版本：v1.0  
日期：2026-07-01

这一步是在 `failure-classification.csv` 模板的基础上，再往前走一步：

- 不只记录失败样本
- 还能自动汇总当前失败主要堆在哪一层

它对应规划文档 Phase 5 里的：

- 建立失败样本分类表
- 失败样本能被归类到数据、模型、后处理或 UI 问题

## 命令

只汇总 `failure-classification.csv`：

```bash
node --no-warnings --experimental-strip-types scripts/summarize-failure-cases.ts --failure-csv C:/path/to/failure-classification.csv
```

只根据真实模型首轮记录推断：

```bash
node --no-warnings --experimental-strip-types scripts/summarize-failure-cases.ts --first-run-record C:/path/to/real-model-first-run-record.json
```

也可以两者一起输入：

```bash
node --no-warnings --experimental-strip-types scripts/summarize-failure-cases.ts --failure-csv C:/path/to/failure-classification.csv --first-run-record C:/path/to/real-model-first-run-record.json
```

也可以直接从 annotation JSON 里的 `attributes.debug` 派生后处理失败项：

```bash
node --no-warnings --experimental-strip-types scripts/summarize-failure-cases.ts --annotation-dir model/datasets/nail-texture-v1/annotations/raw-json
```

当前会自动纳入的信号包括：

- `debug.warnings[]`
- `debug.extractionQualityWarnings[]`
- 当 `highlightRatio >= 0.12` 或 `highlightPixels >= 8` 时派生 `highlight_hotspots`

## 输出

结构化 JSON，包括：

- `categoryCounts`
- `dominantCategories`
- `csvBreakdown`
- `inferredFromFirstRunRecord`
- `nextSteps`

## 适用时机

- 首批 seed batch 筛图之后，想知道失败主要集中在哪一层
- 真实模型首轮审计之后，想把 blocked / needs_adjustment 结果沉淀成分类线索
