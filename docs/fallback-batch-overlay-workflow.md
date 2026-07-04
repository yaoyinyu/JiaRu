# 首批 50 张参考图 fallback overlay 工作流

版本：v1.0  
日期：2026-07-01

这一步对应 `docs/nail-texture-recognition-model-plan.md` 里的第一批任务建议第 4 步：先选一批参考图，用当前 fallback 自动生成候选 overlay，再进入人工修正。

## 1. 适用场景

适合下面这类准备动作：

- 刚收完第一批 50~200 张美甲参考图
- 想先快速看哪些图能被当前 fallback 稳定检出
- 想把 overlay、mask、debug JSON 一次性导出来给人工标注前筛图

## 2. 批量命令

```bash
node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "C:/path/to/nail-batch-001" --output-dir "C:/path/to/nail-batch-001-debug" --prefix seed-batch-001 --fixture-dir "C:/path/to/seed-batch-001/fixtures"
```

如果某些图片已经有绿圈真值 fixture，把 JSON 放进批次的 `fixtures/`。脚本会按图片文件名或 stem 自动匹配 fixture，并自动跳过 fixture 引用的标注图；没有 fixture 的图片仍按普通 fallback 预检。

## 3. 输出内容

每张图都会生成：

- overlay PNG
- candidate mask PNG
- skin mask PNG
- debug JSON

同时还会生成一份批量报告：

```text
C:/path/to/nail-batch-001-debug/seed-batch-001-batch-verify-report.json
```

报告里会记录：

- 每张图是否成功
- 候选数量
- 使用的是哪个 backend
- 是否有 warning
- 每个调试产物的路径

## 4. 推荐用法

建议顺序是：

1. 收集一批参考图
2. 跑批量 overlay
3. 先剔除明显不适合做训练样本的图
4. 再把保留下来的图生成 intake manifest
5. 再进入初始标注导出和人工修正

也就是：

```text
收图
  -> 批量 fallback overlay
  -> 人工筛图
  -> init-intake-batch.ts
  -> validate-intake-batch.ts
  -> run-phase1-intake-pipeline.ts
```

## 5. 什么时候判定这一批通过

这一批的通过标准不是“所有图都完美检出”，而是：

- 能稳定批量导出 overlay 和 debug 产物
- 可以快速看出哪些图适合进入标注
- 可以把失败样本和复杂样本提前分组
- 为后续人工修正节省大量逐张检查时间

## 6. 结论

`scripts/batch-verify-nail-detection.ts` 的作用不是替代标注，而是把“首批 50 张先跑一遍候选 overlay”这件事变成一个可复用的批处理步骤，让后面的种子集筛选和标注更顺。
