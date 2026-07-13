# 美甲纹理端侧最终完成度审计

`audit-nail-texture-local-inference-completion.ts`把实施规范、进度标记、数据授权、候选精度、代表性测试集、桌面/移动设备、失败案例、Beta人工质量和生产模型资产汇总为一个机器可读总门。

## 执行

```powershell
npm.cmd run audit:nail-texture-completion
```

报告写入：

```text
model/reports/nail-texture-local-inference-completion-audit.json
```

未完成时命令返回退出码1并写出`decision=hold`。这是正确的阻断结果，不应通过忽略退出码、复制smoke模型或提前切换生产manifest规避。

## 审计范围

- 实施规范第16.1/16.2节全部勾选项；
- 进度文档所有标记及非PASS项；
- 正式数据集release授权和readiness；
- 当前最佳候选box/mask mAP50门；
- 100–200张来源隔离真实发布测试集下限；
- Windows桌面性能与重复运行内存门；
- Android手机、Android平板、iPhone和iPad真机性能/内存门；
- 用户典型失败案例；
- 至少100张代表性图片的Beta人工直接可用率；
- 生产manifest、ONNX大小和SHA-256一致性。

## 外部证据格式

无需手写下列JSON。先复制可填写模板：

```text
model/fixtures/nail-texture-beta-review.template.csv
model/fixtures/nail-texture-user-failure-cases.template.csv
```

将示例行替换为真实记录后，通过下面的构建器生成报告。CSV支持带引号和逗号的备注；文件名必须是安全的单层文件名，图片必须在指定本地目录真实存在。

移动设备每种设备一份报告，默认路径为`model/reports/nail-texture-device-<device>.json`：

```json
{
  "version": "nail-texture-device-acceptance/v1",
  "deviceFamily": "android",
  "ok": true,
  "decision": "pass",
  "performance": { "ok": true, "sampleCount": 20 },
  "memory": { "ok": true }
}
```

`deviceFamily`必须分别覆盖`android`、`android-tablet`、`iphone`和`ipad`。报告还应保留机型、系统、浏览器、后端、输入尺寸、P50/P95、主线程开销、峰值内存和连续增长统计；总门只读取上面的稳定契约字段。

```powershell
npm.cmd run build:nail-texture-device-acceptance -- --device-family android --device-name "vivo X100s Pro" --os "Android" --browser "Chrome" --backend webgpu --performance C:\path\performance.json --memory C:\path\memory.json --output model\reports\nail-texture-device-android.json
```

Android平板、iPhone和iPad分别把`--device-family`和输出文件改为`android-tablet`、`iphone`、`ipad`。性能和内存输入必须先通过现有验证器且各有至少20个样本；聚合器不会把失败的原始报告包装成PASS。

Beta质量报告默认路径为`model/reports/nail-texture-beta-quality-review.json`：

```json
{
  "version": "nail-texture-beta-quality-review/v1",
  "ok": true,
  "reviewedByUser": true,
  "sampleCount": 100,
  "directlyUsableRate": 0.85
}
```

构建命令：

```powershell
npm.cmd run build:nail-texture-beta-review -- --csv C:\path\beta-review.csv --image-dir C:\path\beta-images --reviewer "审核人" --output model\reports\nail-texture-beta-quality-review.json
```

CSV列固定为`fileName,sourceGroup,decision,correctionSeconds,notes`；`decision`只允许`directly_usable`、`needs_fix`、`unusable`。构建器校验100张下限、文件去重、图片存在、SHA-256、修正耗时和85%直接可用率。

典型失败案例报告默认路径为`model/reports/nail-texture-user-failure-cases.json`：

```json
{
  "version": "nail-texture-user-failure-cases/v1",
  "ok": true,
  "sampleCount": 1
}
```

构建命令：

```powershell
npm.cmd run build:nail-texture-failure-cases -- --csv C:\path\failure-cases.csv --image-dir C:\path\failure-images --output model\reports\nail-texture-user-failure-cases.json
```

CSV列固定为`fileName,sourceGroup,category,severity,notes`。类别只允许`occlusion`、`glare`、`complex_background`、`nonstandard_shape`、`partial_nail`、`decoration`、`other`；严重度只允许`low`、`medium`、`high`、`critical`。

图片本身仍留在本地数据盘，不加入Git；报告只记录数量、分类、审核结论、来源组和必要哈希。

## 发布顺序

外部证据全部通过后，先重新训练/评估或确认v6仍为最佳候选，再执行正式promotion、生产资产完整性验证和浏览器回归。只有审计最终返回`ok=true`、`decision=complete`，才能把实施目标标记为完成。
