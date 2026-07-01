# 第一批真实数据执行清单生成器

版本：v1.0  
日期：2026-07-01

这一步是在 `phase1-readiness.json` 和 `phase1-collection-plan.json` 之后补上的“最后一公里”工具。

它的目标不是再告诉你“还差多少”，而是直接生成一份首批真实数据执行清单，包含：

- 第一批建议做多少张
- 首批目录怎么命名
- 从图片目录到正式数据集要跑哪些命令
- 每一步的验收标准

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/generate-first-batch-checklist.ts
```

也可以带上你准备使用的真实目录：

```bash
node --no-warnings --experimental-strip-types model/training/generate-first-batch-checklist.ts --source-dir "C:/tmp/local-images" --root-dir "C:/tmp/seed-batch-001" --source-group seed-batch-001 --origin-type web --license "internal-test-only" --default-origin-ref "manual sourcing 2026-07-01"
```

## 输出

- `model/datasets/nail-texture-v1/metadata/first-batch-execution-checklist.json`

## 它会生成什么

- `firstBatchRecommendation`
  - 建议首批目标图数
  - 建议的 source mix
  - 预计还剩几个批次
- `sourceBatch`
  - 本批目录
  - 批次名
  - 来源类型
  - license / origin ref
- `steps`
  - 每一步标题
  - 要执行的命令
  - 每一步通过标准

## 推荐使用方式

1. 先跑：

```bash
node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts
node --no-warnings --experimental-strip-types model/training/plan-phase1-collection.ts
```

2. 再跑：

```bash
node --no-warnings --experimental-strip-types model/training/generate-first-batch-checklist.ts
```

3. 之后就按生成的 `steps` 顺序实际执行第一批导入。
