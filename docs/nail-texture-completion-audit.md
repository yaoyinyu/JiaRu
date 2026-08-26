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

自2026-08-23起，candidate9后续采用强教师到端侧小模型的受控标注/蒸馏策略：GPT-5.6 Sol负责原分辨率语义审核，轻量候选负责高召回定位，SAM2.1 large负责像素候选，端侧学生负责最终浏览器部署。该策略不是新增的旁路PASS：完成度审计仍只接受已物化、来源隔离且审核通过的训练真值，以及学生模型独立产生的val30、冻结test100、全新困难负样本、浏览器、真机、Beta和回滚证据；教师输出、软标签或伪标签本身不得填写任何正式gate。第二轮教师审核已形成21张/130 mask，candidate11虽在val30锁定阈值0.50与同甲后处理0.60/0.85/0.12，冻结test100仍只有493/554匹配、436完整mask、61漏甲、19重复、30额外和22无效预测mask，完整mask比例0.78700、37%图片漏甲，继续HOLD。该结果只允许驱动train角色新真值课程和val30上的容量比较，禁止test100回流或反向调参。

本轮调整后的Goal执行策略也受本审计约束：产品第一目标是正确识别并提取每枚完整美甲，执行优先级为完整甲面召回、同甲唯一实例、边界无污染、端侧性能。大模型教师必须输出可追溯的难例分类、返修路由或审核决定；只有原分辨率终审通过的polygon才能成为学生真值。每个新学生候选必须相对上一轮具备可核验的真值增量、训练策略改动或后处理改动，禁止同输入原样重训后重复消费评测。水印素材允许训练，但完成度审计不得把水印相关特征当作识别证据，困难负样本水印/遮挡消融和无水印泛化证据仍须保留。

同甲唯一性后处理的代码存在或合成单测通过不构成完成门。candidate9后续候选必须在来源隔离val30上锁定mask-IoU、较小mask包含率和完整mask替换分数容差，并保存参数与源码/权重/val预测哈希；冻结test100只允许在参数锁定后作一次诊断，禁止用其选择参数。完成度审计只有在固定学生候选分别产出val30、冻结test100、全新未见困难负样本、浏览器和Beta证据后才读取正式结果；当前0.60/0.85/0.12实现的18/18专项回归只登记为算法增量，正式gate仍保持HOLD。

candidate12已完成同一输入下的容量对照：YOLO11s-seg低学习率冻结骨干训练虽正常结束，但部署512的val30没有阈值满足联合约束，因此不得进入冻结test100。该失败把下一轮策略限定为扩充train角色的高质量难例真值，而不是继续在相同231张正样本上排列模型容量、学习率或冻结层数；任何后续学生仍须重新通过val30，只有val优胜候选才可消费一次冻结test100。

教师真值现已扩展至30张/180 mask；原分辨率视觉门排除了`00451…_6`侧视污染整图和`01126`吞入黑色背景的错误人工v2。candidate13输入为240张/1390 mask正样本、160训练负样本、val30/test0，物化和输入深审均通过。candidate13重训与candidate14从candidate11最优检查点继续训练虽分别提高了部分mAP指标，但在正式512 val30阈值0.50都只有121/144匹配、23漏检和26误检，低于candidate11的122匹配、22漏检。因此完成度审计将二者记录为val阶段否决：不得为其创建选择锁、运行冻结test100、导出、登记或部署。下一轮只有在按val30抽象漏检类型增加来源隔离train真值后才可启动；不得继续对同一输入排列超参，也不得读取冻结test100图片、预测、标签或派生物选样。

candidate15把上述策略落实为匿名失败画像和可核验真值增量：val30画像只保留完整漏检、定位失败、宽/侧视、小面积、贴边和狭长等聚合类别，不含图片身份且明确`trainingUse=prohibited`；教师真值扩展至37张/234 mask，训练输入为247张/1444 mask正样本、160负样本、val30/test0并通过深审。candidate15在部署512、阈值0.50的val30达到124/144匹配、20漏检、29误检，按“完整甲面召回优先”超过candidate11后才锁定并消费一次冻结test100。固定参数结果虽改善到496/554匹配、441完整mask和58漏甲，但仍有21重复、33额外、25无效预测，37%图片漏甲且仅40%图片可直接提取，因此正式门继续HOLD。下一轮不得读取或披露test100逐图身份来选样，不得把其预测、标签或派生物回流训练；只能继续依据val30匿名类别扩充来源隔离train真值，再产生新的val优胜学生。

candidate16采用新的五段教师链路：GPT-5.6 Sol负责语义审查，OpenAI官方`gpt-image-2`只负责生成/编辑来源隔离的train候选，SAM2.1 large负责像素候选，通过部署512 val30资格门的本地较大YOLO负责可微软目标，YOLO11n负责浏览器部署。OpenAI图像生成结果、SAM候选、教师logit或特征本身都不能填写发布PASS；只有原分辨率终审硬真值和最终候选独立生成的val30、冻结test100、全新困难负样本、浏览器、真机、Beta与回滚证据可进入正式gate。官方YOLO11m-seg干净基座训练得到的权重在512 val30阈值0.50达到127/144匹配、17漏检、28误检；首版多信号YOLO11n学生没有阈值满足同一val30联合约束，因此candidate16保持FAIL。该YOLO11m权重本身由批准硬真值直接训练并可独立推理，故candidate17另以哈希绑定选择锁将其登记为直接部署候选，而非把“教师PASS”转换成“蒸馏PASS”；冻结test100虽以503/554匹配、0.90794实例召回首次通过召回子门，但完整mask、缺甲图片、重复、额外候选及无效mask门仍失败。审计固定：教师不是训练或网页前置条件，较大直接模型仍必须独立通过浏览器体积、延迟、内存和全部发布门。

2026-08-24完成candidate17直接中型模型冻结test100验证后，机器重放确认门禁继续生效：总计440个进度标记、424个PASS、16个非PASS，14个正式门中4个通过/10个失败；`M2-T3-CANDIDATE16-MULTI-SIGNAL-DISTILLATION-001`继续记录蒸馏学生val30失败，新增`M2-T3-CANDIDATE17-DIRECT-MEDIUM-001`记录直接模型只通过实例召回子门、完整性与唯一性门仍失败。报告SHA-256为`0e46dd55549d55d080fc51b183e24bbc3ae8a1539da399db663bd9240472cc7e`，`ok=false`、`decision=hold`符合预期，既没有把教师资格PASS错误晋升为蒸馏PASS，也没有把candidate17的召回子门PASS误写成正式发布PASS。

candidate18继续沿直接训练主线推进：43张/287 mask补强真值合并后形成train413/val30/test0深审输入，YOLO11m从candidate17权重直接微调且`distillation=null`。val30在召回不低于0.88的主约束下锁定512/0.30，为128/144匹配、16漏检、21误检；冻结test100一次诊断为515/554匹配、461完整mask、39漏甲、14重复、25额外、22无效，22图漏甲、50图可直接提取。完成度审计必须把`M2-T3-CANDIDATE18-HARDCASE-DIRECT-001`保持为非PASS：0.92960实例召回只通过子门，0.83213完整mask比例、0.22缺甲图率和零重复/额外/无效门仍失败；不得因相对candidate17改善而导出、登记或部署。

2026-08-25收口重放共读取441个进度标记、424个PASS和17个非PASS，14个正式门仍为4通过/10失败，`ok=false`、`decision=hold`；报告SHA-256为`5f42f0912f236992c76b228134292375042f201c030081e3660c011daf5d31e7`。该结果确认candidate18提升未绕过独立困难负样本、移动真机、Beta、生产资产和回滚门。

自2026-08-22起，项目范围内图像与本机计算资源由`model/training/project-commercial-resource-authorization-v1.json`提供standing商业授权，完成度审计不再把“逐批等待用户确认”作为独立发布门。该变化只移除人工暂停：数据集readiness与用途角色仍须由机器证据判定，val、冻结test、已消费holdout及其派生物/父来源仍禁止训练；原分辨率完整甲面、独立未见留出、三变体零误检、浏览器、真机、Beta、产品质量与回滚门继续全部要求真实PASS。

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

## candidate19—21 当前完成度结论（2026-08-25）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| candidate19输入深审 | PASS：train420/val30/test0，260张正样本/1551 mask、160张困难负样本，角色与冻结test100来源隔离 | 只证明候选训练输入合格，不解除发布门 |
| candidate19/20 val30 | 两者均为`no_threshold_meets_validation_constraints`，未运行test100 | 正确在val阶段淘汰，不计正式识别PASS |
| candidate21 val30选择锁 | PASS：alpha0.60单学生权重`1eea8742…fae7`，512/0.40为128匹配、16漏检、19误检；锁禁止test反调 | 允许一次冻结test100诊断，不允许导出/部署 |
| candidate21冻结test100 | FAIL：519/554匹配、466完整mask、35漏甲、13重复、18额外、17无效、20图漏甲；召回0.93682通过，完整率0.84116、缺甲图率0.20和唯一性门失败 | `M2-T3-CANDIDATE21-INTERPOLATED-STUDENT-001`保持非PASS；正式模型、生产资产、浏览器、真机、Beta和回滚门均不得晋升 |

candidate21冻结测试已经消费。完成度审计不得把相对candidate18的聚合改善解释为正式识别通过，也不得用逐图测试结果驱动下一训练集、阈值或后处理。当前Goal继续保持`ok=false`、`decision=hold`，只有后续独立train真值迭代通过全部正式门才可变更。

## candidate22—23 当前完成度结论（2026-08-26）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| candidate22输入深审 | PASS：train425/val30/test0，265张正样本/1589 mask、160张困难负样本，0 orphan | 只证明候选训练输入合格，不解除发布门 |
| candidate22训练 | PASS：直接学生、`distillation=null`、45轮早停，最佳权重`ec6aad80…25dc` | 只证明训练完成，不等于候选质量通过 |
| candidate22 val30 | VAL REJECT：512/0.25为127匹配、17漏检、22误检，未超过candidate21的128/16/19 | 禁止建立选择锁、运行test100、导出或部署 |
| candidate23四点插值 | VAL REJECT：alpha0.20保持128匹配但误检29；alpha0.40/0.60/0.80无合格阈值 | 预注册替换规则未满足；冻结test100保持未触碰 |

candidate21仍是当前基线但其既有冻结test100质量门失败，产品继续HOLD。candidate22/23没有改变正式模型、生产manifest、浏览器、真机、Beta、困难负样本、ONNX或回滚门状态；完成度仍必须由机器审计返回`ok=true`且`decision=complete`才能解除。

本阶段同步后的机器重放读取446个进度标记，其中424个PASS、22个非PASS；14个正式门4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`b68211e7c8575432edd0fab3f06be982375486e4ac8e2956b764cd5e449f0e02`，与candidate22/23均在val阶段淘汰的结论一致。
