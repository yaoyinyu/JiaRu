# Phase 1 补样本计划器

版本：v1.0  
日期：2026-07-01

这一步是在 `audit-phase1-readiness.ts` 之后补上的执行层输出。

readiness gate 会告诉你“还差多少”，而这个脚本会进一步把差距翻译成：

- 当前最该补哪一类样本
- 下一批建议准备多少张图
- 还大概剩几个批次
- 下一步直接可执行的命令

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/plan-phase1-collection.ts
```

默认读取：

- `model/datasets/nail-texture-v1/annotations/raw-json/`
- `model/datasets/nail-texture-v1/metadata/split.json`
- `model/datasets/nail-texture-v1/metadata/sources.csv`

输出：

- `model/datasets/nail-texture-v1/metadata/phase1-collection-plan.json`

## 它会给出的内容

- 剩余还差多少图片
- 剩余还差多少有效 mask
- 按当前平均每图可产出多少有效指甲，估算还要补多少图
- 按每批 50 图以内，估算还剩几个批次
- 是否优先补：
  - negative 测试样本
  - complex background 测试样本
  - 现有 error 级标注修复

## 推荐使用方式

每次完成一批导入后直接运行：

```bash
node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir "C:/tmp/seed-batch-next"
```

现在这条流水线会自动继续生成：

- `phase1-readiness.json`
- `phase1-collection-plan.json`

也就是说，导完一批以后，你不需要自己读长 JSON 判断方向，直接看计划器输出的 `priorities` 和 `suggestedCommands` 即可。
