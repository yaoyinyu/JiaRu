# 首批种子集工作区脚手架

版本：v1.0  
日期：2026-07-01

这一步把“新建一个首批批次目录，并放好后续命令入口”变成一条命令，适合开始收集 `seed-batch-001`、`seed-batch-002` 这类首批种子集时使用。

## 命令

```bash
node --no-warnings --experimental-strip-types model/training/scaffold-seed-batch.ts --root-dir "C:/path/to/seed-batch-001" --source-group seed-batch-001 --origin-type web --default-origin-ref "manual web sourcing 2026-07-01"
```

## 生成内容

会生成：

- `images/`
- `debug/`
- `review/`
- `seed-batch-001.manifest.json`
- `README.md`
- `review/screening-review.csv`
- `review/failure-classification.csv`

其中：

- `images/` 用来放原始图片
- `debug/` 用来放批量 fallback overlay 结果
- `review/` 用来放人工筛图备注或额外清单
- `review/screening-review.csv` 用来记录 keep / drop / needs manual fix
- `review/failure-classification.csv` 用来记录失败样本属于 data / model / postprocess / ui 哪一类
- manifest 是可直接修改的批次模板
- README 会把后续命令直接写好

## 推荐流程

```text
scaffold-seed-batch.ts
  -> 往 images/ 放图
  -> batch-verify-nail-detection.ts
  -> 人工筛图
  -> init-intake-batch.ts
  -> validate-intake-batch.ts
  -> run-phase1-intake-pipeline.ts
```

## 作用

它不替代标注或训练，但能把“首批种子集的工作目录怎么起、后续命令怎么接”固定下来，减少每批数据重新搭目录和找命令的重复工作。
