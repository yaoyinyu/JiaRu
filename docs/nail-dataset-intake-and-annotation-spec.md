# 美甲纹理数据采集与标注执行规范

版本：v1.1
日期：2026-07-04

这份文档把 Phase 1 里“采集素材、补来源信息、做标注、跑审计”的执行口径固定下来，避免后续不同批次的数据混乱，影响训练和验收。

## 1. 适用范围

- 用户上传的美甲参考图
- 内部整理的美甲样图
- 商家展示图、授权样图、公开测试图
- 明确用于“非美甲/复杂背景误检抑制”的负样本图

## 2. 单批次最小执行单元

建议把每次采集当作一个 `sourceGroup` 批次，例如：

- `seed-batch-001`
- `merchant-red-series-a`
- `user-corrections-2026-07-01`
- `negative-background-set-001`

同一批次的图片尽量保持来源一致，这样 train/val/test 切分时更不容易发生同源泄漏。

## 3. `sources.csv` 必填口径

每条记录至少补齐以下信息：

| 字段 | 要求 |
| --- | --- |
| `imageId` | 稳定唯一 ID |
| `fileName` | 仅文件名，不带目录 |
| `sourceGroup` | 批次名，不能为空 |
| `originType` | `reference/web/user/merchant/negative/other` |
| `originRef` | 来源 URL、相册名、商家名、用户授权备注或批次说明 |
| `license` | 授权状态、内部测试用途、可商用说明等 |
| `negative` | 是否为负样本 |
| `annotationPath` | `annotations/raw-json/<file>.json` |
| `imagePath` | `images/raw/<file>.jpg|png|jpeg|webp` |
| `annotationCount` | 当前标注出的 nail polygon 数量 |
| `createdAt` / `updatedAt` | ISO 时间戳 |

## 4. 标注执行规则

- 类别固定为 `nail_texture`
- 一块可独立提取纹理的甲面对应一个 polygon
- 只标甲面，不标手指皮肤、戒指、花瓣、桌面等背景
- 高光如果属于甲面视觉的一部分，可以保留在 polygon 内
- 遮挡严重但仍可提取的，只标可见区域
- `negative=true` 的图片不得含任何标注

推荐属性：

- `fingerHint`: `thumb/index/middle/ring/pinky/unknown`
- `shape`: `square/round/almond/coffin/stiletto/unknown`
- `quality`: 1-5
- `occluded`: `true/false`
- `artificialTip`: `true/false`

## 5. 采集与入库建议顺序

1. 图片放入 `images/raw/`，或通过导入脚本自动复制
2. 跑 fallback 导出初始标注
3. 人工修正 polygon
4. 跑 `sync-sources-csv.ts`
5. 跑 `audit-sources-csv.ts`
6. 跑 `audit-training-source-authorization.ts --mode release`，确认训练来源授权
7. 跑 `split-dataset.ts`
8. 跑 `audit-labels.ts`
9. 跑 `convert-annotations.ts`

## 6. 审计命令

```bash
node --no-warnings --experimental-strip-types model/training/audit-sources-csv.ts
node --no-warnings --experimental-strip-types model/training/audit-training-source-authorization.ts --mode release
node --no-warnings --experimental-strip-types model/training/audit-labels.ts
```

## 7. 审计结果解释

`audit-sources-csv.ts` 会输出：

- `metadata/sources-audit.json`

其中：

- `ok=true`：没有来源级 error
- warning：可以继续，但建议补齐
- error：本批次不应进入训练转换流程

重点错误类型：

- `missing_source_group`
- `invalid_origin_type`
- `invalid_annotation_path`
- `invalid_image_path`
- `invalid_annotation_count`
- `invalid_timestamp`
- `missing_source_image_file`
- `missing_source_annotation_file`
- `unreadable_source_annotation_file`
- `annotation_count_mismatch`

其中磁盘一致性错误用于拦截“sources.csv 记录存在，但图片或标注文件已经丢失/漂移”的情况。`annotation_count_mismatch` 表示 `sources.csv` 里的 `annotationCount` 和对应标注 JSON 的实际 `annotations.length` 不一致，需要先重新同步或修正后再进入训练转换。

重点警告类型：

- `missing_origin_ref`
- `missing_license`
- `negative_origin_mismatch`

`audit-training-source-authorization.ts` 会输出：

- `metadata/training-source-authorization-release.json`
- 或 `metadata/training-source-authorization-internal.json`

推荐口径：

- `--mode internal`：只用于内部验证、debug、算法回归；允许 `internal-test-only`，但仍会提示缺少来源或授权字段。
- `--mode release`：用于正式训练/候选模型发布前；会拦截网络采集图、`internal-test-only`、授权描述模糊、用户图未明确授权、商家图未明确授权。

正式训练建议使用以下授权描述：

- `user-authorized-internal-training`
- `merchant-authorized-commercial-training`
- `licensed-commercial-training`
- `cc0` / `public-domain`
- `owner-authorized-training`

如果是网上下载的美甲素材，默认只能进入 `internal` 验证，不应直接进入 `release` 训练，除非已经拿到可训练/可商用/可二次使用的明确授权，并把 `originType` 与 `license` 重新记录清楚。

## 8. 本阶段验收标准

- 能导入/生成原始标注
- `sources.csv` 可同步成功
- `sources-audit.json` 可生成
- `label-audit.csv` 可生成
- `split.json` 可生成
- 转换脚本能产出 YOLO segmentation 标签

这份规范的作用不是替代训练脚本，而是把“素材进入训练前”的规则固定下来，让后面每一批数据都能复用同一套流程。
