# 首批筛图结果转入库工作流

版本：v1.0  
日期：2026-07-01

这一步把 `review/screening-review.csv` 里的人工决策真正转成下一步可执行结果：

- 复制保留图片到干净目录
- 生成筛后 manifest
- 产出筛图统计报告

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir "C:/path/to/seed-batch-001"
```

默认会生成：

- `selected/images/`
- `selected/<sourceGroup>.manifest.json`
- `selected/reviewed-intake-report.json`

## 保留规则

脚本会保留：

- `keepForTraining=true`
- 或 `decision=reserve_for_test`

脚本会排除：

- `decision=drop`

这样可以把训练样本和保留测试样本一起整理出来，而明显不合格的图不会继续流入 intake。

## 典型流程

```text
batch-verify-nail-detection.ts
  -> screening-review.csv
  -> build-reviewed-intake-batch.ts
  -> validate-intake-batch.ts
  -> run-phase1-intake-pipeline.ts
```

## 价值

这一步的意义是：首批 50 张筛图结果不再停留在表格里，而是直接变成后续数据流水线的输入。
