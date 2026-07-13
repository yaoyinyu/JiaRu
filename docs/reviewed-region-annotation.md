# 派生照片逐甲标注与审计

截图或拼图先通过 `extract-reviewed-image-regions.py` 提取单一真实照片区域，再使用人工视觉紧框与 `sam-assisted-nail-annotation.py` 生成候选多边形。SAM2推理成功不代表审核通过，必须查看原分辨率叠加图，并确保所有完整露出的甲面均已标注、轮廓没有皮肤或背景泄漏；触及裁剪边界的不完整甲面不标注。

提示文档可在每个 `images[]` 项上设置 `sourceGroup`。脚本优先使用逐图值，缺省时才使用文档级值；这样同批派生图仍按父截图保持稳定分组，避免父子样本跨split。

审核清单使用 `nail-texture-region-annotation-review/v1`。执行审计：

```powershell
node --no-warnings --experimental-strip-types model/training/verify-reviewed-region-annotations.ts `
  --manifest 辅助材料/real-material-review-2026-07-12/review/xhs-main-photo-crops-v1-annotation-review.json `
  --report 辅助材料/real-material-review-2026-07-12/review/xhs-main-photo-crops-v1-annotation-audit-report.json
```

审计器要求区域提取报告中的每个派生图都有唯一决定，并校验派生图SHA-256、尺寸、父图稳定`sourceGroup`、标注数量、标签、多边形边界和最小面积。只有`pass`项允许进入后续导入流程；`rework`和`drop`项的`acceptedMaskCount`必须为0。

2026-07-13首批结果：9张全部完成审核，7张/41个mask通过，2张返修，审计0错误。通过项尚未导入正式数据集。
