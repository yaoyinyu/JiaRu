# 从本地图片目录启动真实 seed batch

版本：v1.0  
日期：2026-07-01

当你已经有一整个本地图片目录时，这一步可以直接把它转成 seed batch 工作区，而不是手工拷图、建目录、写 manifest。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir "C:/path/to/local-images" --root-dir "C:/path/to/seed-batch-001" --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
```

## 会生成什么

- `images/`：已复制进来的真实图片
- `debug/`
- `review/`
- `<sourceGroup>.manifest.json`
- `review/screening-review.csv`
- `review/failure-classification.csv`

## 适用场景

- 你已经下载好第一批真实美甲图
- 想马上把它们推进现有 Phase 1 流水线
- 不想手动创建 seed batch 目录结构
