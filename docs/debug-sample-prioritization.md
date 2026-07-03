# Debug Sample 主动学习优先级

版本：v1.0  
日期：2026-07-03

这一步把规划文档第 11.2 节里的“优先回收哪些用户修正样本”落成了一条可执行工具链。

新增脚本：

```text
model/training/prioritize-debug-samples.ts
```

它的作用不是直接导入样本，而是先回答一个更实际的问题：

哪些 debug sample 最值得优先进入人工复核、数据集修正和下一轮训练。

## 命令

按目录扫描：

```bash
node --no-warnings --experimental-strip-types model/training/prioritize-debug-samples.ts --sample-dir C:/path/to/debug-samples
```

按多个文件扫描：

```bash
node --no-warnings --experimental-strip-types model/training/prioritize-debug-samples.ts C:/path/to/debug-samples/sample-001.json C:/path/to/debug-samples/sample-002.json
```

只看优先级最高的前几条：

```bash
node --no-warnings --experimental-strip-types model/training/prioritize-debug-samples.ts --sample-dir C:/path/to/debug-samples --top 10
```

## 它如何打分

脚本会读取每份 debug sample 里的：

- `backend`
- `warnings`
- `originalCandidates`
- `correctedCandidates`
- 候选级 `confidence`
- 候选级 `warnings`
- `extractionDiagnostics`

然后按规划里的主动学习线索打分并排序。

当前优先关注这些模式：

1. 低置信候选被用户修正成可用结果  
   - 对应：模型有犹豫，但用户能修正成功

2. 高置信候选被用户删除  
   - 对应：模型“很自信但其实错了”

3. 用户手动新增候选  
   - 对应：模型或 fallback 漏检了可用甲面

4. 用户做了大幅 move / scale 修正  
   - 对应：初始候选几何位置偏差较大

5. fallback 处理成功或出现模型运行警告  
   - 对应：模型可用性、浏览器 runtime、fallback 覆盖差异需要补齐

6. 纹理提取仍带有污染 / 高光 / 边缘问题  
   - 对应：这类样本对后续纹理质量优化更有价值

## 输出

脚本输出一份 JSON 报告，包含：

- `totals.highPriority / mediumPriority / lowPriority`
- `reasonBreakdown`
- `ranked[]`

其中每个 `ranked[]` 条目都会包含：

- `priorityScore`
- `priorityTier`
- `reasons`
- `summary`

## 怎么用

推荐顺序：

1. 先从开发环境导出 debug sample
2. 跑 `prioritize-debug-samples.ts`
3. 先处理 `high priority`
4. 再把确认过的样本喂给 `import-debug-sample.ts`
5. 最后继续走 `split-dataset.ts` / `audit-labels.ts` / `convert-annotations.ts`

这样做的好处是，我们不需要把所有用户修正样本一股脑全部导入，而是先把：

- 高置信误检
- 明显漏检
- 纹理质量差但又很有代表性的样本

优先回收到训练闭环里。

## 直接接入导入脚本

现在 `import-debug-sample.ts` 的 batch 模式已经可以直接消费这份 priority report：

```bash
node --no-warnings --experimental-strip-types model/training/import-debug-sample.ts --sample-dir C:/path/to/debug-samples --image-dir C:/path/to/original-images --priority-report C:/path/to/prioritized-debug-samples.json --min-priority medium --top 20 --copy-image
```

可选参数：

- `--priority-report <json>`：使用 `prioritize-debug-samples.ts` 生成的排序结果
- `--min-priority <high|medium|low>`：只导入不低于该等级的样本
- `--top <n>`：只取排序最前面的前 n 条

这样就把“排序”和“入库”接成了同一条实用链路：

priority report  
→ 只挑高价值样本  
→ `import-debug-sample.ts` 批量导入  
→ 进入正式数据集
