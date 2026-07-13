# 审核图片区域提取

## 用途

`model/training/extract-reviewed-image-regions.py` 用于从截图或拼图素材中提取单一真实照片区域，去除界面文字、装饰排版和重复缩略图。输出仍是待审核候选，不会自动进入正式训练集。

适用前提：

- 父图来源与训练授权已经明确；
- 裁剪区域只包含一个需要继续标注的真实照片视图；
- 同一父图产生的所有裁剪必须保持在同一个数据 split；
- 裁剪后仍需逐甲标注和原分辨率 overlay 审核。

## 清单格式

```json
{
  "version": "nail-texture-region-extraction/v1",
  "sourceGroupPrefix": "real-reference-crops-v1",
  "regions": [
    {
      "parentFileName": "source.jpg",
      "regionId": "main-hand",
      "box": [0.1, 0.2, 0.8, 0.9]
    }
  ]
}
```

`box` 为 `[x1, y1, x2, y2]` 归一化坐标，必须全部位于 `[0, 1]` 内。`regionId` 只允许小写字母、数字、短横线和下划线。

## 执行

```powershell
python model/training/extract-reviewed-image-regions.py `
  --manifest "辅助材料/real-material-review-2026-07-12/review/xhs-main-photo-regions-v1.json" `
  --image-dir "辅助材料/real-material-review-2026-07-12/selected/images" `
  --output-dir "辅助材料/real-material-review-2026-07-12/selected/xhs-main-photo-crops-v1" `
  --report "辅助材料/real-material-review-2026-07-12/review/xhs-main-photo-regions-v1-report.json" `
  --min-side 192
```

报告为每个派生图记录：

- 父文件名、父图 SHA-256 和原始尺寸；
- 归一化框、像素框和区域 ID；
- 派生文件名、SHA-256 和尺寸；
- 由父文件名稳定生成的 `sourceGroup`；
- `reviewRequired=true`。

同一父图的所有区域共享 `sourceGroup` 中的 `parent-<hash>` 键，后续导入时必须沿用该值，避免父图派生样本跨 train/val/test 泄漏。

## 当前验证

2026-07-13 对9张小红书截图各提取1个主照片区域：9/9成功，尺寸范围为356×454至799×810，联系表确认已移除页面文字和圆形重复图。v6在这些派生图上以1024/conf=0.10生成92个候选，但仍有重复框和少量误检，因此只用于下一轮SAM2提示与人工审核，没有进入正式训练集。

Windows PowerShell可能使用GBK控制台；脚本将stdout中的非ASCII字符转义，同时磁盘报告继续使用UTF-8原文，避免Unicode文件名导致任务在打印阶段失败。
