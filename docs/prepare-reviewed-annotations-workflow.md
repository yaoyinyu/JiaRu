# 筛后样本初始标注准备

版本：v1.0  
日期：2026-07-01

这一步服务于“首批 50 张筛完 -> 开始人工修正”。

它会在 `selected/` 工作区里：

- 批量生成 fallback 初始标注 JSON
- 统计这批样本的 polygon 数和 manual-fix 数量
- 给人工修正前留下一份批次准备报告

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/prepare-reviewed-annotations.ts --root-dir "C:/path/to/seed-batch-001"
```

## 输出

- `selected/annotations/raw-json/*.json`
- `selected/reviewed-annotation-prep-report.json`

## 作用

这一步不会直接写入正式数据集目录，而是在筛后工作区内准备好人工修正所需的初始标注。

这样做的好处是：

- 先在局部工作区里确认这批样本是否值得继续修正
- 不会过早污染正式 `model/datasets/nail-texture-v1/`
- 可以在修正前先看到这批样本的初始 polygon 数量和 manual-fix 压力
