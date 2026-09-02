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

训练困难负样本的新批授权链现以schema v3落实上述standing授权：只有160/160机器进度完成时才能冻结候选ID、精确文件清单、`requestedItemsSha256`及standing授权文件SHA-256；不再要求逐项用户消息。该工程标记不增加正式发布门通过数，也不把生成候选变成训练可用；原分辨率正式终审、保护集合隔离、清单终结和规范物化仍必须各自通过。

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

## candidate24 真值扩充当前结论（2026-08-26）

`00251…_10`已作为第56张补强真值晋升，新增5个完整mask；v28索引为56张/384 mask且旧55张的图片SHA、标注SHA、来源组与mask数零漂移。该进展只扩大独立train角色真值，不改变candidate21冻结test100失败、生产ONNX、浏览器、真机、Beta、困难负样本或回滚门。

`00415…_5`九甲人工候选虽然多边形合法、零交叠且几何9/9通过，仍因原分辨率发现另一枚长甲漏标而被隔离；补回漏甲后的十甲终版才通过整图、逐甲2×、合法性、零交叠和几何10/10，并使v29达到57张/394 mask。完成度审计不得把中间版机器几何PASS视为正式训练真值，也不得在candidate24尚未物化、训练和通过val30前提升模型发布门。

同步后的机器重放读取448个进度标记，其中426个PASS、22个非PASS；14个正式门4通过、10失败，继续返回`ok=false`、`decision=hold`。报告SHA-256为`2e01860c1d3a65107470006c3bb2b03e2bae06479e650ebfc1bf48801f0fb3e4`；两个candidate24真值标记都只确认训练数据通过，不改变模型与发布门。

## candidate24/25验证与困难负样本扩充当前结论（2026-08-27）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| candidate24输入与训练 | PASS：train430/val30/test0，270张正样本/1629 mask、160张困难负样本，直接学生最佳权重`0c5feba7…a56` | 只证明训练输入与训练运行有效，不构成模型质量PASS |
| candidate24部署512 val30 | VAL REJECT：阈值0.25为128匹配、16漏检、27误检；相对candidate21保持召回但多8个误检 | 违反预注册严格替换规则，禁止test100、导出、登记或部署 |
| candidate25四点小步插值 | VAL REJECT：alpha0.05在阈值0.40最多与candidate21打平128/16/19，其余点均退化 | 没有严格改善，不建立选择锁，不消费test100 |
| 下一训练困难负样本快照 | 70/160通过、90缺失、0失败、0未知；四个softgel家族、`samara_dry_clusters`、`seed_pod_glossy_macro`、`seed_capsule_translucent`各10/10，报告`214abb69…b8bdb` | 只通过生成与源图质量工程门，正式终审/终结/物化前继续训练禁用 |

统一机器决策`model/training/candidate24-25-validation-decision-v1.json`明确candidate21仍是当前基线。candidate21既有冻结test100仍未通过完整mask比例、缺甲图片率和零重复/额外/无效门，因此正式模型、生产ONNX、浏览器、真机、Beta、独立困难负样本和回滚证据均不能晋升。冻结计划身份复核确认041—050为`samara_dry_clusters`、051—060为`seed_pod_glossy_macro`，本轮061—070 `seed_capsule_translucent`也已完成递归深验；原定从071继续扩充的安排已被下节2026-08-28“正样本识别优先”策略取代，且任何后续动作都不得使用冻结test100、已消费holdout或发布留出的逐图预测选样。

## candidate27/28策略调整与正样本增量结论（2026-08-28）

candidate27的三种候选复核器实现均止于val30：CNN、按父候选一对一标签的CNN和手工特征复核器都未能在保持128个匹配时把误检严格压到19以下，最好同召回点仍有32个误检。该分支未运行冻结test100，也没有导出、登记或部署，因此不增加任何正式门通过数。

训练策略随后改为“美甲完整识别优先”。固定160项新困难负样本计划暂停在70/160，余下90张不再是下一训练前置；现有批准困难负样本仅按来源平衡、与模型输出无关的确定性规则取满足正式下限的有限子集。该调整只限制训练侧负类权重，不放宽训练后全新独立困难负样本三变体零误检/零delta发布门。

`01138…_7`与`01130…_10`各五个原分辨率人工polygon均已通过整图和逐甲局部放大复核、几何5/5及同图零交叠；后者的修复/几何报告分别为`5a5c2203…1cef`、`d2290d04…10d4`，已消除旧SAM漏甲、同甲拆分及局部甲面问题。补强规范真值v32为62张/429 mask、13张返修、0冲突，摘要`29250bab…173`；相对v31只新增`01130…_10`且旧61张零漂移。完成度机器重放更新为459个进度标记/434个PASS，14个正式门仍为4通过/10失败，报告`cbe5e1e9…c2cb`为`ok=false`、`decision=hold`。candidate28尚未物化或训练；candidate21仍是失败状态的当前识别基线，正式完成度继续HOLD。

2026-08-29继续完成`01112…_10`六甲和`00167…_15`七甲贴边人工polygon；`00167`把旧计数10纠正为7枚完整可见甲面，三枚完全遮挡甲不计数，并排除皮肤、背景与外伸蝴蝶饰件。最终修复/几何报告`a98cce5b…097c`/`587adc86…e3fe`均为7/7通过、零交叠。教师审核v35为64张/442 mask、11排除、0返修，索引`72be31e9…99d3`、摘要`ecfe80ed…2f57`，旧63张零漂移。训练器已支持`mask_ratio=1`与`overlap_mask=false`的全分辨率独立实例边界监督；该真值已进入下述candidate28物化输入，但在val30严格替换门完成前不增加正式门PASS，产品继续HOLD。

candidate28训练输入现已按稳定图片身份物化为274张正样本/1652 mask、160张既有批准困难负样本和来源隔离val30，训练集共434图；输入审计v4为PASS、0 orphan，SHA-256为`4eca2deb…425`。v5固定640、100 epochs、全分辨率mask、独立实例、无mosaic训练并已越过epoch1；Windows 1455恢复只将DataLoader workers由8降为0，不降低边界监督。该里程碑仍不等于模型门通过：训练完成后必须用项目逐实例val30评估完整甲面匹配、漏检和误检，未严格优于candidate21即否决；冻结test100、独立困难负样本、三变体、浏览器、真机和Beta门均保持未通过。

2026-08-29起，逐实例正样本报告自身不再能通过自报contract放宽正式门：新schema v2报告固定不少于100图、召回不低于0.90、完整mask比例不低于0.85、缺甲图片率不高于0.10、加权伪实例率不高于0.02，CLI只允许收紧。`--verify-report`会在重建前应用同一正式边界，伪造较弱contract不能通过重放；新建schema v1被拒绝，历史v1仍可在验证器内部只读重放。该工程修复封闭了报告构建/自重放漏洞，但最终完成度审计把逐实例报告登记为独立正式gate的编排工作仍待完成，因此不增加发布门通过数。

同步schema v3 standing授权工程标记后的机器重放读取454个进度标记，其中430个PASS、24个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。审计报告SHA-256为`c302cfc879dd42b33d8d2275876ae924b213b23d6fdef9a36a9411e8cb65e56b`；新增授权标记只证明重复人工等待已移除且机器追溯有效，不改变70/160训练负样本数量、生产资产、移动设备、Beta、正式产品质量或回滚门。

## candidate30—34边界增强结论（2026-08-30）

candidate30全量ROI、candidate31小幅插值、candidate32平衡ROI、candidate33五信号同权重自蒸馏和candidate34保守插值均已完成来源隔离val30判断。candidate33在0.10/0.15保持128匹配、16漏检时仍有59/41误检；candidate34的alpha0.01—0.05全部只与candidate29打平128/16/16，alpha0.08退化为127/17/15。统一机器决定`candidate30-34-boundary-validation-decision-v1.json`拒绝全部候选，且明确`protectedTest100Used=false`、`exportAuthorized=false`、`deploymentAuthorized=false`。

同权重自蒸馏工程合同及GPU反向烟测通过只证明训练链路有效，不增加任何正式发布门PASS。candidate29仍是失败状态的当前识别基线；冻结test100、独立困难负样本、三变体、生产ONNX、浏览器、四类真机、Beta、正式产品质量和双版本回滚均未晋升，完成度必须继续`decision=hold`。

本轮总完成度机器重放读取464个进度标记，其中438个PASS、26个非PASS；14个正式门4通过、10失败，返回`ok=false`、`decision=hold`。报告`model/reports/nail-texture-local-inference-completion-audit.json`的SHA-256为`51374e260f060961c20979d4c6937552d25ecfc34a47ef269910042545515e0e`；该结果与candidate30—34全部止于val30、产品继续HOLD的结论一致。

## candidate35新来源边界难例结论（2026-08-31）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 新来源真值与输入审计 | 27张冻结候选经原分辨率终审只晋升4张/20 mask；合并输入为278正图/1672 mask、160负图、val30/test0，审计`93eb96a1…c28`PASS | 只证明数据与训练输入合格，不增加正式识别门PASS |
| candidate35训练 | 640全分辨率独立mask训练18轮早停，最佳第3轮，权重`1aabbc8c…107f` | 只证明训练运行有效，不构成可发布模型 |
| 部署512 val30 | 0.45为128匹配、16漏检、17误检；0.30为129/15/28，均未严格优于candidate29的128/16/16 | VAL REJECT；禁止test100、发布留出、导出、登记、前端接入和部署 |
| 剩余难例 | 22张返修、1张排除，所有返修项继续`trainingUse=prohibited`直到逐甲原分辨率终审 | 下一训练输入须扩大真实贴边真值，不能把SAM候选或计数相符当PASS |

candidate35没有改变正式模型、生产manifest、浏览器、真机、Beta、困难负样本发布测试或回滚门。candidate29仍为失败状态的当前识别基线；完成度继续保持`ok=false`、`decision=hold`。

同步后的机器重放读取466个进度标记，其中439个PASS、27个非PASS；14个正式门仍为4通过、10失败，正确返回`ok=false`、`decision=hold`。报告SHA-256为`95eb025f28aaa225768504d6bd0c84ab3747132f823c9551b6836b92693e64f1`，新增candidate35数据工程PASS没有掩盖其val30拒绝状态。

## candidate36/37扩展边界监督结论（2026-08-31）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 返修真值与输入 | 累计11张/59 mask通过原分辨率完整甲面审核；合并为285正图/1711 mask、160负图、val30/test0，审计`4c006bf4…d530`PASS | 只证明训练输入合格，不增加正式模型门PASS |
| candidate36训练与val30 | 35轮早停、最佳第20轮、权重`b86a9a0b…f145`；512/0.45为124/20/20，0.10为130/14/73 | VAL REJECT；低阈值召回增加不能抵消73个误检 |
| candidate37保守融合 | 预注册7个alpha；1%—5%只打平128/16/16，8%及以上退化 | VAL REJECT；没有严格替换candidate29 |
| 受保护证据 | test100与独立发布留出均未读取，未导出、登记、接入或部署 | 避免污染后续门，但发布状态不变 |

candidate36/37没有改变生产manifest、浏览器、真机、Beta、困难负样本三变体、正式产品质量或回滚门。candidate29仍是失败状态基线，最终完成度必须继续`ok=false`、`decision=hold`。

同步后的机器重放读取468个进度标记，其中439个PASS、29个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`998745a3ac88a523bf6bcb5e048385517cc0efbf263b579e0ed9693b03122171`；candidate36/37两个VAL REJECT标记被正确计入阻塞项，没有被数据工程PASS掩盖。

## candidate38—42硬边界训练与受保护回归结论（2026-08-31）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 硬边界损失与边界评估器 | PASS：训练器支持显式边界权重，原分辨率2px边界F1报告可重放 | 只证明训练与测量链路成立，不增加正式模型门PASS |
| candidate38/40 | VAL REJECT：直接硬边界训练均降低固定阈值识别匹配数 | 不运行其test100，不导出或部署 |
| candidate41 | TEST HOLD：val30保持128/16/16且边界F1=0.60596；test100为519匹配、466完整mask、35漏甲、16额外、13无效 | 完整mask仍低于candidate29，不能替换基线 |
| candidate42 | TEST HOLD：val30保持128/16/16且边界F1=0.61307；test100为517匹配、465完整mask、37漏甲、18额外、16无效 | 回归进一步退化，停止该插值轨迹 |

candidate41质量报告SHA-256为`1e2f7b28…d9f9`，candidate42为`ebc73d00…567d`，两者均返回`hold_positive_recognition_gate`。冻结test100结果不得用于继续修改alpha、阈值、模型、后处理或样本；当前下一步仅为扩大独立train角色的原分辨率完整边界真值。正式模型、生产ONNX、浏览器、真机、Beta、困难负样本三变体、正式产品质量与回滚门均未晋升，产品继续HOLD。

同步后的机器重放读取472个进度标记，其中440个PASS、32个非PASS；新增硬边界工程门正确记为PASS，candidate38—42三个质量失败标记均进入阻塞清单。14个正式门仍为4通过、10失败，报告返回`ok=false`、`decision=hold`，SHA-256为`a8de8b4a…be1d`。

## candidate43扩展真实边界真值结论（2026-09-01）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 隔离难例返修与输入 | candidate35难例真值由11张/59 mask扩至18张/104 mask；合并为292正图/1756 mask、160负图、val30/test0，输入审计`2df809bc…8613`PASS | 只证明新增训练真值和输入合格，不增加正式识别门PASS |
| candidate43训练 | 从candidate29初始化，640全分辨率独立mask训练25轮早停，最佳第13轮、权重`893945ce…4f05` | 只证明训练运行有效，不构成可发布模型 |
| 部署512 val30 | 0.35为130匹配/14漏检/22误检、边界F1=0.59038；0.45为124/20/17、边界F1=0.60695 | VAL REJECT；召回、误检和边界不能在同一阈值同时过门 |
| 受保护证据 | test100与独立发布留出均未读取，未导出、登记、接入或部署 | 保持后续证据隔离，但产品发布状态不变 |

`candidate43-boundary-validation-decision-v1.json`明确通用校准器的0.35不能覆盖预注册严格替换规则。剩余5张难例继续训练禁用；candidate29仍是失败状态基线，正式模型、生产ONNX、浏览器、真机、Beta、全新困难负样本三变体和双版本回滚门均未晋升，产品继续HOLD。

同步后的机器重放读取474个进度标记，其中441个PASS、33个非PASS；14个正式门仍为4通过、10失败，正确返回`ok=false`、`decision=hold`。报告SHA-256为`ea23826662834358a5e7e6ddb95f78f86f1a27d4c719142d82756c9bddd76a5d`；新增真值工程PASS没有掩盖candidate43的VAL REJECT。

## candidate43后续边界真值增量（2026-09-01）

`00004`因立体装饰遮挡完整甲面而按源图门排除；`00201`按原图把预期10甲纠正为实际9枚完整可见甲面，9/9贴边polygon通过原分辨率视觉、合法性、零交叠和几何门。边界真值增至19张/113 mask、合并293张/1765 mask。该数据PASS发生在candidate43训练后，不可解释为candidate43质量改善，也不增加正式发布门PASS；剩余三张继续训练禁用，产品保持HOLD。

同步后的机器重放读取475个进度标记，其中442个PASS、33个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`dc11ed4da97d5889312a1be23d6460a7819a6492f589a1cb65c38ca61cdf4aae`。

## candidate44—46完整边界训练与冻结回归结论（2026-09-01）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 难例真值与candidate44输入 | `01063/01245`按遮挡或触边残缺整图排除，`01213`新增5个完整透明灰色长甲mask；边界真值20张/118 mask、合并294张/1770 mask，train454/val30/test0输入审计PASS | 只证明训练数据与输入合格，不增加正式模型质量门PASS |
| candidate44/45 | candidate44在0.35为128/16/22、0.45为126/18/16；candidate45四个粗插值点均为127匹配/17漏检 | 均在val30拒绝，未消费各自test100 |
| candidate46选择锁 | alpha0.025是三个预登记细点中唯一保持128/16/16且严格改善边界F1至0.603157的点；权重、512、0.45和后处理在test前哈希锁定 | 只通过val选择门，不等于发布模型 |
| candidate46冻结test100 | 519匹配、466完整mask、35漏甲、13重复、16额外、12无效；完整mask比例0.84116、缺甲图片率0.20、加权伪实例率0.11372 | 三项schema v2正式门失败，candidate46 TEST HOLD，停止本插值轨迹 |

candidate46相对candidate42确有小幅改善，但绝对发布门未通过，不能导出、登记、接入或部署。冻结test100已消费且不得用于继续修改alpha、阈值、后处理或样本；下一候选必须回到新的来源隔离训练/验证证据。同步后的机器重放读取480个进度标记，其中444个PASS、36个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`，报告SHA-256为`bed5040e5de2d13d40cb92ff0534e4c8f65469ade17676f9dc0bde49f681bd3d`。

## candidate47复用真值训练与candidate48首批标注结论（2026-09-01）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| candidate47输入 | 复验复用19张/110 mask，规范输入为313正图/1880 mask、160负图、val30/test0，输入审计`ea270da…65f8`PASS | 只证明训练输入合格，不增加正式模型门PASS |
| candidate47训练与val30 | 17轮早停、最佳第5轮、权重`7c408527…614d`；0.15为128/16/58，0.50为123/21/13 | VAL REJECT；未读取test100，不能导出、登记、接入或部署 |
| candidate48首批真值 | 11张/94候选中，首批`00664/00915`共2张/10 mask通过原分辨率终审，`00062`透明拇指局部mask返修 | 数据仍未物化，不能计作下一候选训练输入；另9张待返修 |

candidate47的训练完成不构成正式模型发布进展；正式质量门仍为失败状态。candidate48必须先完成剩余逐甲边界终审和规范物化，后续候选仍须依次通过val30、全新正样本发布留出、训练后独立困难负样本三变体、浏览器、真机、Beta和回滚门，产品继续HOLD。

同步后的机器重放读取483个进度标记，其中445个PASS、38个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`e338861654194780afa90b7e77e346d1bb3af19cb2557c4402e85a162e768f3d`；candidate47的VAL REJECT和candidate48的进行中标记均被正确保留，未被输入审计PASS掩盖。

## candidate48规范输入、训练与val30否决结论（2026-09-01）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| candidate48新真值 | `00664/00915/01051`共3张/20 mask通过原分辨率完整甲面终审；其余8张未通过项不计数 | 新增真值合格，但不单独增加正式模型门PASS |
| 规范输入 | 合并316正图/1900 mask、160负图、val30/test0；输入审计`3023b22d…55bb`、数据树`b32e524b…cf6d`PASS | 只证明训练输入和来源隔离合格 |
| candidate48训练与val30 | 18轮早停、最佳第6轮、权重`6c840ed1…b1c7`；0.35为128/16/28，0.45为126/18/21 | VAL REJECT；没有阈值满足128/16/16，未读取test100 |
| 后续发布链 | 未导出、登记、接入或部署；困难负样本三变体、浏览器、真机、Beta和回滚证据均未晋升 | 正式产品继续HOLD |

candidate48的训练完成和输入PASS不能替代正式识别质量门。该候选在val30即被否决，受保护test100保持未读取；下一步继续处理余下8张全新候选，不能围绕candidate48调阈值或复用其拒绝权重。

同步后的机器重放读取485个进度标记，其中446个PASS、39个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`114d4c2801303e1976d0fa04316f438ddf34968103a628bb2c58626b8a421a8a`；candidate48规范输入PASS与VAL REJECT均被正确计入，训练完成没有被误报为正式模型完成。

## candidate49剩余难例收口与规范输入结论（2026-09-01）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 余下8张终审 | `00623/01243/00228`等7张按漏甲污染、重复交叠、饰品误识别、裁甲或不可确认边界排除；只接受`00901`一张/10 mask | candidate48标注池由进行中更新为PASS，但不增加正式模型质量门PASS |
| `00901`真值 | 去除1个重复候选并修平3个装饰假凹口；10/10合法、零交叠、几何及原分辨率视觉审核PASS | 新增训练真值合格，不代表模型可用 |
| candidate49输入 | 317正图/1910 mask、160负图、val30/144、test0；数据树`4c1d392b…0f25`、输入审计`0161f28f…1556`PASS | 只增加数据/工程证据；未训练、未读取test100 |
| 训练触发 | 当前有效增量仅1张/10 mask，继续积累来源隔离高质量边界真值 | candidate49训练仍为等待状态，产品HOLD |

同步后的机器重放读取489个进度标记，其中450个PASS、39个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`4de391447f269e6aef6fe176d2fab5a89557f38d04ccf3b94c589107b9ffed26`；标注池收口没有被误报为正式模型完成。

## candidate50严格复核、训练与val选择结论（2026-09-02）

| 证据 | 结论 | 完成度影响 |
| --- | --- | --- |
| 当前合同复核 | 15张旧批准真值中只复用4张/25 mask，其余11张返修或排除 | 防止历史宽松边界污染新训练，不直接增加发布门PASS |
| candidate50输入 | 321正图/1935 mask、160负图、val30/144、test0；数据树`120013b0…b6e8`、输入审计`b84d4ff5…070e`PASS | 数据与工程证据通过 |
| 直接训练 | 24轮早停、最佳第12轮，权重`a0f603a6…aeec`；512 val30为125/19/16 | 直接权重VAL REJECT |
| 预登记融合 | alpha0.03在512/0.45保持128/16/16，边界F1从0.6011289提高到0.6025056；权重`58e5006c…0106`已锁定 | val选择门PASS，但不构成发布PASS |
| 受保护test100 | 519/554匹配、467完整mask、35漏甲、13重复、16额外、12无效、20图漏甲、55图可直接提取；报告`c65e8b35…eb22`深验一致 | 实例召回通过；完整率0.84296、缺甲图率0.20、加权杂散率0.11372失败，TEST HOLD |
| 发布链 | 新train证据、全新正样本发布留出、全新困难负样本三变体、ONNX、浏览器/Worker、真机、Beta100、产品质量与双版本回滚仍未通过 | 完成度保持HOLD，不得解除产品HOLD |

candidate50的val30边界严格改善没有在受保护test100转化为足量完整mask：相对candidate46只增加1枚完整mask和1张可直接提取图，漏甲、重复、额外和无效实例均未下降。该候选及其插值轨迹终止；test100结果不得反向进入选样、损失、阈值或后处理。OpenAI `gpt-image-2`只负责来源隔离训练候选生成，API不提供本地YOLO知识蒸馏需要的logit、特征层或边界张量；已实现的YOLO11m→YOLO11n多信号蒸馏candidate16已在val30否决，故当前加速主线是新增来源隔离真实难例完整polygon，而不是重复蒸馏。

candidate51冻结的5张/4来源组新源图已完成终结：`00710/00225/00624/00846`共4张/26 mask通过原分辨率整图/逐甲终审、polygon合法性与零交叠门，`00625`因必要甲面相互遮挡、隐藏边界不可确认而整图排除。最终索引v5为325张/1961 mask/109来源组，索引SHA-256 `d040d11fbe3fe92f8b3d686945ba36f606c03bdaeeba77d36237b9e36221c8f8`、规范条目SHA-256 `2b4c7d54b939056c1f6a57731ae44470c2647594ea65e90bb81157daf1cb4b88`，零冲突/冗余。物化为485张训练图（325正样本+160困难负样本）及val30/144 mask，test=0、孤儿文件=0；物化与正式合同深重放均PASS，candidate51唯一直接监督训练已启动。OpenAI `gpt-image-2`仍没有本地可微蒸馏运行、软信号或学生权重证据，candidate16本地蒸馏已被val30否决；不重复该支线。训练启动只是中间里程碑，尚未通过val30、受保护test100或发布门。最新重放为498标记/457 PASS、14门4通过/10失败，`ok=false`、`decision=hold`，报告SHA-256 `bcf2888651f263ab7c72d1b1c7b1a69a41d099f142b6cdfb52718efd88a5a7cf`；产品继续HOLD。

candidate51随后完成16轮训练，最佳权重`403e24ca…322`。正式512 val30在0.46为129匹配/15漏检/17误检，在0.465为127/17/17，不存在同时满足128/16/16识别非退化门的阈值，故决定`reject_candidate51_on_isolated_val30_recognition_non_regression`。边界晋级、test100、插值、导出、登记和部署均未执行；该失败不能以总体mAP或放宽阈值覆盖。OpenAI `gpt-image-2`蒸馏仍无实际产物，下一轮不得重复该支线或在相同输入上盲调。

同步后的完成度机器重放读取499个进度标记，其中458个PASS、41个非PASS；14个正式门仍为4通过、10失败，`ok=false`、`decision=hold`。报告SHA-256为`c92ae1944f3d4e7d222518ea77647c5163be68cb5c182724939d42c1e142a5ff`；candidate51训练完成PASS与val30 FAIL被分别保留，没有误晋升test、生产或发布门。

正式权重到达前的非生产浏览器替换链已完成：smoke ONNX完整性、16项Worker/运行时契约和33项相关测试通过；真实Chromium经Worker/WebGPU返回带mask候选并完成手指分配、像素纹理提取和AR槽位写回，控制台0错误。该标记只关闭工程接入未知项，生产ONNX仍不存在，candidate51仍为val拒绝，真实浏览器正式权重回归、四类真机和Beta门继续未完成。

同步后的完成度机器重放读取500个进度标记，其中459个PASS、41个非PASS；14个正式门仍为4通过、10失败，`ok=false`、`decision=hold`。报告SHA-256为`537cef2f15d84ab95e2289c10ce66ae7a3e6987726ff73d33afdb0bb37b27395`；新增非生产工程PASS没有覆盖生产模型、真机、Beta或候选质量失败。

同步后的机器重放读取494个进度标记，其中454个PASS、40个非PASS；14个正式门仍为4通过、10失败，返回`ok=false`、`decision=hold`。报告SHA-256为`a3f27779dc17586f99b9d5d257b778d1a83b001f72f50c928134f859fa7f42b9`；candidate50的val选择PASS和test100失败标记被分别保留，没有把总体mAP或中间里程碑误报为发布完成。

## 上线加速与OpenAI image2角色复核（2026-09-02）

candidate51的0.46点为129匹配/15漏检/17误检，说明当前失败处于召回—误检边界，但仍没有资格越过128/16/16正式val合同。下一候选新增的train内来源组隔离影子开发流程只能减少无效完整训练次数：最多两项短程单变量比较、胜出后一个正式候选、一次正式val30；它不增加任何正式门PASS，也不允许读取test100或发布留出选配方。

磁盘证据仍不存在OpenAI `gpt-image-2`产生的YOLO内部张量或学生权重，因此“OpenAI蒸馏”完成度保持为未发生；图像生成/编辑候选即使通过后续审核，也只能计入数据覆盖，不能计入蒸馏完成。生产模型、真机、Beta和发布门均未变化，完成度必须继续保持HOLD。

同步后的机器重放读取502个进度标记，其中460个PASS、42个非PASS；14个正式门仍为4通过、10失败，`ok=false`、`decision=hold`。报告SHA-256为`deae3faf976c82a2cb7fe633875eb675b80a862c04f01c26ef913d8f9d85f87b`；影子开发计划和OpenAI角色审计没有被误报为生产模型质量或发布完成。

## candidate52库存止损与生成源图状态（2026-09-02）

既有真实素材按candidate51当前训练索引重放后只余10张/8来源组，且全部被原分辨率质量事实排除；该止损只关闭重复审核循环，不增加模型质量门PASS。OpenAI内置图像生成新增3张/3来源组/预计20甲并完成源图初筛，但精确模型ID不可核验、完整mask尚未制作，故只能登记为候选源图且`trainingUse=prohibited`，不能计作OpenAI知识蒸馏、训练完成或模型晋级。

同步后的机器重放读取504个进度标记，其中462个PASS、42个非PASS；14个正式门仍为4通过、10失败，`ok=false`、`decision=hold`。报告SHA-256为`b02de70bd2000112bf9c21c0850b225ad927f7430c85f7273378844e20a52113`；新增两项数据治理PASS没有覆盖candidate51 val失败、生产模型、真机、Beta或发布门。
