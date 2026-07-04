# 失败样本分类表审计

版本：v1.0  
日期：2026-07-04

这一步对应 `docs/nail-texture-recognition-model-plan.md` Phase 5 的闭环目标：失败样本能被归类到数据、模型、后处理或 UI 问题。

## 为什么需要这个门禁

`failure-classification.csv` 之前已经由 seed batch 脚手架生成，也能被 `summarize-failure-cases.ts` 汇总。但如果表里只有模板行、分类枚举写错、关键字段为空，汇总结果就不能作为发布或回流依据。

`audit-failure-classification.ts` 用来检查这张表本身是否已经具备可用证据。

## 命令

```bash
node --no-warnings --experimental-strip-types scripts/audit-failure-classification.ts --failure-csv C:/path/to/review/failure-classification.csv --output C:/path/to/review/failure-classification-audit.json
```

可选参数：

- `--min-classified-rows 1`：至少需要多少条真实分类行，默认 1

## 当前检查项

脚本会验证：

- 表头必须是 `fileName,stage,category,subcategory,severity,action,notes`
- `category` 必须是 `data / model / postprocess / ui`
- `severity` 必须是 `low / medium / high / critical / derived`
- `fileName / stage / category / subcategory / severity / action` 必填
- 脚手架模板行不会计入真实分类证据
- 重复的 `fileName + stage + category + subcategory` 会给出 warning

## 输出重点

报告会包含：

- `totals.classifiedRows`
- `totals.templateRows`
- `categoryCounts`
- `coverage.hasData / hasModel / hasPostprocess / hasUi`
- `errors`
- `warnings`
- `nextSteps`

## 和汇总脚本的关系

推荐顺序：

1. 人工填写 `failure-classification.csv`
2. 运行 `audit-failure-classification.ts`
3. 通过后再运行 `summarize-failure-cases.ts`
4. 把汇总结果接入 final audit / release trace

这样 Phase 5 的失败分类不会只停留在“有表格”，而是能成为可验收、可追踪的闭环证据。