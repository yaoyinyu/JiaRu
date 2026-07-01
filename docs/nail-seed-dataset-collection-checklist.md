# 美甲素材首批采集执行清单

版本：v1.0  
日期：2026-07-01

这份清单对应 `docs/nail-texture-recognition-model-plan.md` 里 Phase 1 的“先做高质量种子集，再扩大采集量”。目标不是先堆数量，而是先做出一批足够干净、足够多样、可以直接进入训练流水线的首批素材。

## 1. 什么时候开始搜集素材

当下面三个条件都成立时，就应该开始：

- 已经确定识别目标是 `nail_texture`
- 已经有现成的 intake / 标注 / 审计脚本
- 下一步需要为专用识别模型准备训练数据

当前仓库已经满足这三个条件，所以现在确实可以开始搜集素材。

## 2. 第一批不要追求“大而全”

建议第一批先做 `50~100` 张，分成四类：

| 类别 | 建议数量 | 目的 |
| --- | ---: | --- |
| 已验证参考图 | 20~30 | 先跑通标注和训练流程 |
| 公开美甲展示图 | 20~30 | 补花色、角度、背景变化 |
| 商家/样板图 | 10~20 | 增加贴图风格密度 |
| 负样本图 | 10~20 | 压低误检 |

第一批重点不是“覆盖互联网所有款式”，而是先覆盖这几种情况：

- 深色背景 / 浅色背景
- 红色、黑色、裸色、浅色甲面
- 有高光、金线、亮片、猫眼效果
- 近景特写 / 多指同框 / 单指贴图样板
- 手部、饰品、花瓣、桌面等容易误检的干扰场景

## 3. 哪些图该收，哪些图先别收

优先收：

- 甲面边界清晰
- 纹理细节清楚
- 分辨率足够
- 指甲主体无遮挡或仅轻度遮挡
- 同一张图里能稳定看出 1~5 个可提取甲面区域

先别收：

- 整张图严重糊掉
- 指甲被大面积手指、道具、文字水印挡住
- 甲面过曝或反光到看不见纹理
- 构图太远，指甲区域很小
- 同一套图几乎完全重复，只是轻微裁切

## 4. 素材来源记录要从第一天开始做

即使只是内部技术验证，也建议从第一批开始记录：

- 来源类型：`reference / web / merchant / user / negative / other`
- 来源说明：URL、相册名、商家名或授权备注
- 许可说明：例如 `internal-test-only`
- 批次名：例如 `seed-batch-001`

这样后面跑 `sources.csv`、审计、切分训练集时不会乱。

## 5. 推荐执行顺序

### 第一步：先把图片放到一个批次目录

例如：

```text
C:/path/to/nail-batch-001/
  sample-001.jpg
  sample-002.jpg
  sample-003.png
```

### 第二步：自动生成 manifest 草稿

```bash
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts --image-dir C:/path/to/nail-batch-001 --source-group seed-batch-001 --origin-type web --license "internal-test-only" --default-origin-ref "manual web sourcing 2026-07-01"
```

默认会在图片目录里生成：

```text
C:/path/to/nail-batch-001/seed-batch-001.manifest.json
```

这个脚本会：

- 扫描目录里的 `jpg/jpeg/png/webp`
- 按文件名排序写入 `items`
- 生成一份可直接进入预检的 batch manifest

### 第三步：跑预检

```bash
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts --manifest C:/path/to/nail-batch-001/seed-batch-001.manifest.json --image-dir C:/path/to/nail-batch-001
```

### 第四步：通过后进入 Phase 1 流水线

```bash
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest C:/path/to/nail-batch-001/seed-batch-001.manifest.json --image-dir C:/path/to/nail-batch-001
```

## 6. 第一批的验收标准

第一批素材通过的标准不是“数量足够多”，而是：

- manifest 能自动生成
- `validate-intake-batch.ts` 预检通过
- 流水线能产出初始标注和 metadata
- `sources.csv`、`split.json`、`label-audit.csv` 能生成
- 标注样本足够支撑第一轮 MVP 训练

## 7. 结论

所以答案是：现在可以开始搜集素材，但建议按“首批种子集”的方式做，而不是一上来就无差别大量下载。当前仓库已经有预检和入库流水线，现在新增的 `init-intake-batch.ts` 可以把“收完图之后怎么开始”这一步直接落地。
