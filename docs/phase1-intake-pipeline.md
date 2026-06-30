# Phase 1 数据入库流水线

版本：v1.0  
日期：2026-07-01

这条流水线把首批样本入库的常用步骤串成一条命令：

- batch manifest 预检
- fallback 初始标注导出
- `sources.csv` 同步
- `sources-audit.json` 审计
- `split.json` 生成
- `label-audit.csv` 生成
- YOLO segmentation 标签转换

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest C:/path/to/batch-manifest.json --image-dir C:/path/to/nail-batch-001
```

## 输入

- `--manifest`：批次清单
- `--image-dir`：图片目录

## 输出

流水线会写入：

- `model/datasets/nail-texture-v1/metadata/phase1-intake-<sourceGroup>.report.json`

这个报告里会记录每一步是否成功，以及各脚本的 JSON 摘要。

## 适用场景

- 一批参考图刚收集完，准备进入数据集
- 想把 Phase 1 流程一次性跑完，减少手动漏步骤
- 想留下一份可回看的入库执行记录

## 注意

- 如果 manifest 预检失败，流水线会在导出前停止
- 如果 `audit-labels.ts` 或 `audit-sources-csv.ts` 报 error，流水线会失败并保留报告
- 这条流水线适合“参考图/商家图批量入库”；页面纠正样本仍然优先走 `import-debug-sample.ts`
