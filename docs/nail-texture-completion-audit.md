# 美甲纹理端侧最终完成度审计

`audit-nail-texture-local-inference-completion.ts` v2把实施规范、全部进度标记、数据授权、候选精度、代表性测试集、桌面/移动设备、失败案例、Beta人工质量、正式发布产品质量、生产模型资产和回滚完整性汇总为一个机器可读总门。任一进度标记不是严格的`PASS`，都作为正式失败门参与`decision`，不再只出现在摘要中。

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
- 进度文档所有标记及非PASS项；非PASS项正式参与总门，不是仅供查看的统计；
- 正式数据集release授权和readiness；
- 当前最佳候选box/mask mAP50门；
- 100–200张来源隔离真实发布测试集下限；
- Windows桌面性能与重复运行内存门；
- Android手机、Android平板、iPhone和iPad真机性能/内存门；
- 用户典型失败案例；
- 至少100张代表性图片的Beta人工直接可用率；
- 与冻结发布测试快照绑定的正式产品质量：直接可用率、污染实例率、像素泄漏率、粗糙矩形化、甲面缺失率和场景分组退化；
- 生产manifest、ONNX大小和SHA-256一致性。
- 当前版本以及至少一个历史版本的回滚注册、模型完整性和审计结果。

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

## 正式发布产品质量证据

默认路径为`model/reports/nail-texture-release-product-quality.json`，也可使用`--release-product-quality <json>`指定。报告必须由冻结发布测试快照、逐实例人工审核CSV和场景回归CSV构建，不得从训练或验证集拼接样本，也不得手写外层`ok=true`。

逐实例CSV固定表头如下；`instanceIndex`从1开始，并且必须完整覆盖快照内每个`items[].maskCount`。每行的`fileName`、`sourceGroup`、`imageSha256`必须与快照逐项一致：

```csv
fileName,sourceGroup,imageSha256,instanceIndex,decision,contaminated,roughRectangle,predictedPixels,outsideGtPixels,gtPixels,missedGtPixels
```

`decision`只允许`directly_usable`、`needs_fix`、`unusable`；两个布尔字段只允许`true`或`false`。四个像素计数必须是非负整数，且`outsideGtPixels<=predictedPixels`、`missedGtPixels<=gtPixels`。

场景回归CSV固定表头如下：

```csv
dimension,name,sampleCount,baselineBoxMap50,candidateBoxMap50,baselineMaskMap50,candidateMaskMap50
```

`dimension`必须覆盖`skin-tone`、`nail-color`、`reflectivity`、`occlusion`、`orientation`、`nail-count`、`background`、`device-backend`八维；每行`sampleCount`必须为正整数，四项mAP50必须位于`[0,1]`。构建命令示例：

```powershell
npm.cmd run build:nail-texture-release-product-quality -- --snapshot "辅助材料/real-release-test-2026-07-13/frozen-reviewed-candidate-v1/manifest.json" --instances-csv "<逐实例审核.csv>" --scenarios-csv "<场景回归.csv>" --reviewer "<审核人>" --output "model/reports/nail-texture-release-product-quality.json"
```

构建器先使用与冻结工具相同的`sort_keys + compact + UTF-8` canonical JSON算法重算`itemsSha256`，并要求快照`decision=frozen_reviewed_candidate_not_release_ready`、`trainingUse=prohibited`以及`representativeReleaseGate={required:100,actual:图片数,ok:true}`；`fileName`和`imageSha256`均必须逐图唯一，禁止以不同文件名复用同一图片哈希膨胀代表性数量，`sourceGroup`允许同源多图重复。因此当前67图快照即使聚合指标达标也只能HOLD。每个场景行的`sampleCount`不得超过冻结图片数。随后固定重算直接可用率、污染实例率、粗糙矩形率、像素泄漏率（`sum(outsideGtPixels)/sum(predictedPixels)`）和缺失率（`sum(missedGtPixels)/sum(gtPixels)`），并将快照与两份CSV的绝对路径、当前SHA-256写入报告。复验器`verifyApprovedReleaseProductQualityReport(reportPath, expectedSnapshotPath)`会从报告绑定路径重新读取三份原始证据、重新对账和计算，并强制报告绑定的快照路径与完成度审计CLI的`--release-test-snapshot`完全一致；另一份即使内容合法的快照也不能换绑。完成度审计正式调用该复验器，不再独立信任外层聚合字段，并独立拒绝冻结快照中的重复图片哈希。任一原始文件写后漂移、实例漏项/重复、身份漂移或手写聚合PASS都会失效。输出路径不得覆盖任一输入证据文件。

完成度审计的`--output`还会在写入前保护全部直接输入，以及当前可解析的传递证据：产品质量绑定的快照和两份CSV、回滚注册表中的manifest快照与模型、生产模型、移动设备性能/内存验证及其原始输入。路径比较采用Windows大小写归一化、真实路径和已存在文件身份，已有硬链接/目录别名也不能绕过保护。

```json
{
  "version": "nail-texture-release-product-quality/v1",
  "ok": true,
  "reviewedByUser": true,
  "trainingUse": "prohibited",
  "snapshot": { "itemsSha256": "64位冻结清单SHA-256" },
  "sampleImages": 100,
  "sampleInstances": 500,
  "directlyUsableRate": 0.85,
  "contaminationInstanceRate": 0.09,
  "roughRectangleRate": 0.15,
  "pixelLeakageRate": 0.02,
  "missingRate": 0.08,
  "frozenMaximumMissingRate": 0.1,
  "minimumAllowedDelta": -0.02,
  "scenarioGroups": [
    {
      "name": "light-to-dark skin",
      "dimension": "skin-tone",
      "sampleCount": 100,
      "ok": true,
      "boxMap50Delta": -0.01,
      "maskMap50Delta": -0.02
    },
    { "name": "light-to-dark nail color", "dimension": "nail-color", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.01, "maskMap50Delta": -0.01 },
    { "name": "matte-to-mirror", "dimension": "reflectivity", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.02, "maskMap50Delta": -0.02 },
    { "name": "visible-to-occluded", "dimension": "occlusion", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.01, "maskMap50Delta": -0.02 },
    { "name": "portrait-landscape-rotated", "dimension": "orientation", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.01, "maskMap50Delta": -0.01 },
    { "name": "single-to-multiple nails", "dimension": "nail-count", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.02, "maskMap50Delta": -0.02 },
    { "name": "simple-to-complex background", "dimension": "background", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.01, "maskMap50Delta": -0.02 },
    { "name": "webgpu-and-wasm", "dimension": "device-backend", "sampleCount": 100, "ok": true, "boxMap50Delta": -0.02, "maskMap50Delta": -0.02 }
  ],
  "errors": []
}
```

v2会重放以下条件：版本固定；用户已审核；训练用途禁止；`snapshot.itemsSha256`与冻结清单完全一致；`sampleImages`等于冻结图片数且不少于100；`sampleInstances`等于冻结mask数；直接可用率不低于0.85；污染实例率严格低于0.10；粗糙矩形化不高于0.15；像素泄漏率必须显式报告且位于`[0,1]`；缺失率不得高于同一报告冻结的有效上限，且`frozenMaximumMissingRate`固定为0.10；`minimumAllowedDelta`固定为`-0.02`，与部署`maximumRegression=0.02`一致。每个场景组必须有正样本、`ok=true`，box/mask退化均不得低于该门槛；`dimension`只允许上述八维并且各至少出现一个有效组。`errors`必须为空。任一字段缺失、非有限数、原始证据缺失或漂移、维度缺失、场景失败均保持HOLD。

## 回滚证据

默认报告路径为`model/reports/nail-texture-release-rollback.json`，注册表默认路径为`public/models/nail-texture-seg/release-registry.json`；也可分别使用`--rollback-audit <json>`和`--release-registry <json>`指定。报告必须直接由回滚审计器生成：

```powershell
node --no-warnings --experimental-strip-types scripts/audit-release-rollback.ts --registry public/models/nail-texture-seg/release-registry.json --manifest public/models/nail-texture-seg/manifest.json --output model/reports/nail-texture-release-rollback.json
```

回滚报告版本为`nail-texture-release-rollback-audit/v2`，会绑定注册表与当前生产manifest的绝对路径和SHA-256。生成报告时逐版本读取注册表记录，重新检查manifest快照、快照字段、模型文件大小与SHA-256；当前版本还会核对生产manifest的`version`、`inputSize`、`task`、`backendPreferences`、`labels`、`modelFile`、`modelSizeBytes`和`sha256`，并确认它实际指向注册表中的当前模型。

完成度审计不会信任报告里手写的`releases[].ok`或`integrityOk`。每次运行都会使用`--release-registry`与生产manifest重新执行同一套当前状态深验，并要求重放结果与已保存的v2报告逐字段一致。因此，即使把报告内部字段全部手写成PASS，只要缺少真实注册表、快照或模型文件就会拒绝；报告生成后任一注册表、manifest、快照或模型字节发生漂移也会拒绝，必须修复证据并重新生成回滚报告。

## 发布顺序

外部证据全部通过后，先重新训练/评估并确认候选通过冻结快照和正式产品质量门，再执行promotion、生产资产完整性验证、回滚审计和浏览器回归。只有v2的13个正式gate全部通过、全部进度标记均为PASS，且最终返回`ok=true`、`decision=complete`，才能把实施目标标记为完成。
