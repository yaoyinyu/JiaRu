# Seed batch 工作区状态审计

版本：v1.0  
日期：2026-07-01

当一个真实 batch 已经开始执行后，这个脚本用来回答两个问题：

- 现在做到哪一步了？
- 下一步该跑什么命令？

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/audit-seed-batch-workspace.ts --root-dir "C:/path/to/seed-batch-001"
```

## 输出

- `seed-batch-workspace-status.json`

## 会检查的阶段

- 是否已经 bootstrapped
- 是否已有筛图记录
- 是否已有覆盖度审计
- 是否已生成 selected 批次
- 是否已准备初始标注

## nextStep 说明

脚本会给出一个 `nextStep`，例如：

- `batch-verify-nail-detection`
- `audit-screening-review`
- `build-reviewed-intake-batch`
- `prepare-reviewed-annotations`
- `manual-annotation-fix-or-import-reviewed-batch`

适合在真实批次推进时快速对状态做一次总览。
