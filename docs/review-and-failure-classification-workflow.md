# 首批筛图与失败样本分类工作流

版本：v1.0  
日期：2026-07-01

这份文档把两件事固定下来：

- 首批 50 张参考图怎么做人工筛图记录
- 后续失败样本怎么归类到数据、模型、后处理或 UI

这同时服务于：

- Phase 1 的首批种子集筛选
- Phase 5 的失败样本分类闭环

## 1. 脚手架会自动生成什么

运行：

```bash
node --no-warnings --experimental-strip-types model/training/scaffold-seed-batch.ts --root-dir "C:/path/to/seed-batch-001" --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
```

后，`review/` 下会自动生成：

- `screening-review.csv`
- `failure-classification.csv`

## 2. screening-review.csv 用来干什么

它用于首批人工筛图，决定每张图：

- 是否进入训练
- 是否需要人工修正
- 更适合 train / val / test 哪一类
- 放弃的原因是什么

推荐决策值：

- `keep`
- `drop`
- `needs_manual_fix`
- `reserve_for_test`

常见 reasonCode：

- `good_detection`
- `low_resolution`
- `heavy_occlusion`
- `strong_reflection`
- `background_confusion`
- `duplicate_image`
- `not_nail_texture`

建议额外补充这些覆盖字段：

- `sampleKind`：`reference / merchant / negative / other`
- `backgroundTone`：`dark / light / mixed / unknown`
- `colorFamily`：`red / black / nude / light / other`
- `effectTags`：用 `|` 分隔多个标签，例如 `highlight|gold_line`

## 3. failure-classification.csv 用来干什么

它用于把失败样本长期归类，方便后续优化时知道问题主要在哪一层。

推荐 category：

- `data`
- `model`
- `postprocess`
- `ui`

常见 subcategory 示例：

- `data / strong_reflection`
- `data / insufficient_negative_samples`
- `model / missed_small_nails`
- `model / overdetect_background`
- `postprocess / unstable_angle`
- `postprocess / dirty_mask_crop`
- `ui / confusing_assignment`
- `ui / manual_fix_too_slow`

## 4. 什么时候写哪一张表

建议顺序：

1. 批量跑 fallback overlay
2. 先写 `screening-review.csv`
3. 对明显复杂或失败的样本，再补 `failure-classification.csv`
4. 保留适合训练的图，再进入 intake manifest 和 Phase 1 流水线

## 5. 为什么这一步现在就值得做

虽然“失败样本分类表”在规划文档里属于更后面的闭环任务，但现在就建立模板有两个直接好处：

- 首批 50 张不会只停留在“看过了”，而是能留下可复盘记录
- 到 200 张和第一版模型训练后，可以直接复用同一套问题分类口径

## 6. 验收标准

这一步完成后，至少要满足：

- 每个 seed batch 工作区都能自动带出 review 模板
- 人工筛图和失败归类不需要另起格式
- 后续能把问题归到 `data / model / postprocess / ui`

这就让 Phase 1 的筛图动作和 Phase 5 的闭环动作，从第一批数据开始共用同一套记录方式。
