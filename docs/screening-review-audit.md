# 首批筛图覆盖度审计

版本：v1.0  
日期：2026-07-01

这一步用于回答一个更实际的问题：首批 50 张筛图之后，我们是不是已经有一批足够平衡、值得继续扩到 200 张的数据。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/audit-screening-review.ts --root-dir "C:/path/to/seed-batch-001"
```

输出：

- `review/screening-review-audit.json`

## screening-review.csv 现在建议补的字段

- `sampleKind`：`reference / merchant / negative / other`
- `backgroundTone`：`dark / light / mixed / unknown`
- `colorFamily`：如 `red / black / nude / light / other`
- `effectTags`：用 `|` 分隔，如 `highlight|gold_line|glitter`

## 报告会检查什么

当前会检查：

- 保留样本是否达到首批建议量 50
- 是否同时覆盖深色背景和浅色背景
- 是否包含负样本
- 是否包含商家/样板类样本
- 是否有预留 test 样本
- 是否覆盖高光、金线、亮片或猫眼效果

## 如何解读

- `ok=true`：当前这批筛图在基础覆盖维度上达标
- `ok=false`：还存在明显缺口，应先补样本再继续扩批或训练

## 作用

这一步把“感觉这批图差不多了”变成了结构化判断，更贴近规划文档里“先做 50 张验证，再扩到 200 张”的节奏。
