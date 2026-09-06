# 美甲正式模型 Goal 与引用文档审计

日期：2026-09-05
范围：Goal 提示词、实施规范、实施进度、完成度审计及其实际脚本/机器报告
当前结论：Goal 方向正确，但原文存在发布证据复用、授权语义冲突和完成条件不可达等结构性问题，不应原样继续执行。

## 1. 直接结论

浏览器端使用单类别实例分割模型识别完整可见甲面，并在部署输入 512 下输出可映回原图的像素级 mask，这条主路线没有根本错误。当前应保留单阶段 YOLO segmentation、方形 letterbox 和产品去重，暂停继续投入 candidate53—57 这种“第二阶段只重新打分、最终仍使用第一阶段 polygon”的 ROI 路线。candidate57 在受保护 test100 中没有任何 stage2 晋级，说明这条 stage2 没有产生与训练和端侧复杂度相称的实际收益。

原 Goal 不能直接使用，至少有四个 P0：

1. 开头授予 standing 商业使用权，结尾又要求在精确训练授权和原子 freeze 时停下请求确认，前后矛盾。
2. 原文一边禁止复用已消费 holdout，一边要求下一候选继续用旧 val30 校准并通过旧 test100。旧 val30 已长期参与模型、阈值和组合选择，旧 test100 已被多轮候选使用并由 candidate57 消费，二者只能保留为历史回归证据。
3. 当前完成度脚本把进度文档中所有历史 FAIL、REJECT、HOLD 都当成当前失败。现有 523 个标记中有 51 个非 PASS；诚实保留历史失败时，`ok=true` 和 `decision=complete` 永远不可达。
4. 当前 evidence profile 仍绑定 candidate5 的质量证据，桌面证据来自 candidate6，最新候选状态却是 candidate57 TEST HOLD。正样本、负样本、ONNX、浏览器、真机、Beta 和回滚尚未绑定同一个不可变发布身份，存在跨候选拼接 PASS 的风险。

## 2. 当前事实基线

| 项目 | 当前事实 | 对 Goal 的影响 |
| --- | --- | --- |
| candidate57 | test100 为 531/554 匹配、479 完整 mask、23 漏甲、16 重复、5 背景误检、13 张图漏甲、59/100 图可直接提取；漏甲图片率 0.13、加权杂散率 0.04693141 失败 | 候选轨迹已经终止，不得重跑、反调、导出或部署 |
| 旧 val30 | 30 张、14 个来源组，已参与多轮候选、阈值、插值和组合选择 | 只能作受保护历史回归，不能继续充当下一发布候选的独立校准证据 |
| 旧 test100 | 已被多个候选反复评估，并已影响后续训练方向 | 只能作受保护历史回归，不能再声称是下一候选的一次性未见发布留出 |
| standing 授权 | `project-commercial-resource-authorization-v1.json` 已明确逐项授权、训练启动授权和满足证据门后的原子 freeze 授权均不再需要 | 精确清单、来源、许可、角色和 SHA-256 是机器追溯门，不是人工等待门 |
| 生产模型 | `public/models/nail-texture-seg/manifest.json` 存在，但仍是 640 占位 manifest，所指 ONNX 不存在 | 当前只有工程脚手架，没有批准生产模型 |
| 完成度审计 | 14 门中 4 门通过、10 门失败；profile 仍是 candidate5，进度历史造成永久阻断 | `decision=complete` 在 audit v3 修复前不能作为可信、可达的最终判据 |

## 3. 原 Goal 的具体问题与修改原则

| 优先级 | 原文问题 | 风险 | 修改原则 |
| --- | --- | --- | --- |
| P0 | standing 授权与末尾再次请求精确授权/freeze 矛盾 | Agent 会重复停顿，且与现有机器授权合同冲突 | 删除逐批、逐清单、训练启动和原子 freeze 人工确认；保留机器追溯与角色隔离 |
| P0 | 要求继续用旧 val30/test100 | 把已经自适应使用的数据冒充全新发布证据 | 旧集只读回归；新增 train 内开发折、全新校准集、全新一次性正样本发布留出 |
| P0 | 把当前 audit v2 的 `complete` 当可达终点 | 历史失败永久阻断，或诱导把失败篡改为 PASS | audit v3 只读取当前发布门；历史实验分开记录 lifecycle 与 outcome |
| P0 | 没有统一发布身份 | 可把 candidate5 的质量、candidate6 的性能和其他模型的资产拼成 PASS | 引入 `releaseIdentity`，绑定候选、运行时锁、全部模型 SHA、阈值/组合、预后处理和 manifest SHA |
| P1 | “持续迭代、全力推动、严禁原地打转”不可验证 | 容易继续同数据、同路线、小阈值和小插值循环 | 每轮预注册一个可证伪假设；train 内短测；失败关闭；每轮至多两个单变量实验 |
| P1 | “识别美甲”定义过宽 | 可能把框、椭圆或局部甲色区域当成功 | 每枚完整可见甲面恰好一个完整像素 mask；能映回原图并提取纹理 |
| P1 | “不复用 candidate5”语义过宽 | 可能误删或不再核验其拒绝证据 | 禁止部署/晋级其权重和复用其留出；保留拒绝报告、保护 registry 和只读回归证据 |
| P1 | 水印只写“需要注意” | 没有可执行审计，模型仍可能学习角标捷径 | 登记水印位置/类型；保留无水印层；做去除、遮挡、模糊和位置变化消融；水印不得进入甲面 mask |
| P1 | ONNX 只要求导出成功 | PT 指标可能与 ONNX、WebGPU/WASM 实际输出不一致 | 在同一冻结样本上验证 PT→ONNX→WebGPU/WASM 的候选、坐标和 mask 一致性 |
| P1 | 真机/Beta 未明确绑定同一模型 | 可用旧模型报告填新模型发布门 | 所有报告绑定同一 release identity；四类设备各至少 20 次，并记录后端、延迟、内存和失败 |
| P1 | 漏写桌面性能/内存和用户失败案例 | Goal 与当前 14 个正式门不一致 | 将 Windows 桌面性能、重复运行内存和真实用户失败案例纳入完成条件 |
| P1 | “两个独立批准版本”没有首发定义 | 首个版本无法同时拥有既有回滚版本 | 使用 bootstrap：先登记一个完整通过的非当前 fallback，再以另一个不同权重且完整通过的版本作为 current，并实际演练回滚 |

## 4. 建议直接替换的 Goal 提示词

```text
目标：交付可商用、在浏览器本地运行并接入 /ar-tryon 的正式美甲纹理识别模型。正式识别成功定义为：对每枚完整可见甲面输出且只输出一个完整像素级 mask，mask 能准确映回原图并提取纹理。裁边、严重模糊或无法确认完整轮廓的正图必须在源图门排除。模型不可用，或仅产生 MediaPipe/颜色/边界/矩形/椭圆等辅助区域时，必须明确显示“辅助定位、需要人工确认”，不得计入模型识别成功率或 Beta 直接可用率。

按 docs/nail-texture-local-inference-implementation-spec.md、docs/nail-texture-local-inference-implementation-progress.md、docs/nail-texture-completion-audit.md 和 docs/technical-whitepaper.md 持续推进；当文档互相冲突时，以当前可重放源码、机器报告和技术白皮书中的最新状态为准，并在同一任务中修正文档。

当前基线：candidate57 已在唯一一次有效受保护 test100 上因漏甲图片率 0.13 和加权杂散率 0.04693141 失败，固定为 TEST HOLD。不得重复评估、依据 test100 逐图结果调参、导出、登记、接入或部署 candidate57。旧 val30 和旧 test100 只保留为受保护历史回归证据，不再作为下一候选的独立校准或最终未见发布证据。生产 ONNX 尚不存在，产品继续 HOLD。

授权：用户已对本项目范围内由其提供或放置、且有权授权并可由 Codex 访问的图像资源，以及本机计算资源，授予持续商业模型开发使用权。标注、物化、训练启动、逐清单处理和满足机器证据门后的原子 freeze 无需再次请求逐批授权。系统仍必须记录精确文件清单、SHA-256、来源、许可声明、用途角色和冻结时间；这些记录用于追溯和角色隔离，不是人工批准等待点。该授权不改变 train/dev/calibration/test/holdout 的角色隔离，不允许任何已消费测试或留出及其派生物回流训练，也不替代第三方外部服务条款、付费云资源授权、Beta 人工判断或物理设备产生的真实证据。

首先修复完成度审计和三份引用文档：audit v3 必须把历史实验的 lifecycle 与质量 outcome 分开，只阻断当前 release requirements；历史 REJECT/HOLD 必须保留且不得改写为 PASS。建立单一不可变 releaseIdentity，至少绑定 candidateId、运行时选择锁、全部模型 SHA-256、输入尺寸、阈值、组合规则、预处理/后处理实现和生产 manifest SHA-256。正样本、困难负样本、ONNX、浏览器、桌面、四类真机、Beta、产品质量和回滚证据必须绑定同一 releaseIdentity，禁止跨候选或跨版本拼接。完成度审计必须直接重放固定的逐实例正样本质量合同，而不能只依赖 mAP。

正式训练主线采用单阶段 YOLO 实例分割、部署一致的 512 方形 letterbox 和产品去重；暂停 candidate53—57 当前“stage2 只打分、最终仍用 stage1 polygon”的 ROI 路线。只有在新增独立来源数据后，边界仍被证明是主要瓶颈，才允许预注册并重建真正替换 mask 的 stage2，同时先补齐浏览器多模型 manifest、Worker、体积、延迟和真机合同。

每个研发循环必须预注册一个可证伪假设，并具备来源隔离的新 train 真值，或一项完全独立于旧 val/test 逐图结果的明确训练/架构改动。先在 train 内按 sourceGroup 建立互斥开发折，每轮至多进行两个短程单变量实验；失败即关闭分支。禁止同输入同算法原样重训、用正式发布集调参、连续微小阈值/插值爬坡，或让每个普通实验都占用正式 candidate 编号。每轮只有一个胜出方案可进入完整训练和发布候选治理链。

训练数据必须经过来源、许可记录、原分辨率视觉审核、完整甲面 mask、polygon 合法性、同图零交叠和角色隔离门。优先增加透明/低对比、相邻长甲、侧视、多手、复杂背景等独立父图和来源组，禁止用大量近重复 ROI 替代来源多样性。带水印图片可以进入 train，但水印不得进入甲面 mask；必须登记水印位置与类型，保留无水印对照层，并完成去除/遮挡/模糊、位置变化及非右下水印消融，证明模型没有把水印当作美甲或来源捷径。

配方锁定后，建立不少于 30 张、与 train 和发布留出来源隔离的全新校准集，只允许选择一次 scoreThreshold。随后冻结权重、512 预处理、阈值、后处理、候选 ID 和 releaseIdentity，再建立不少于 100 张全新来源隔离正样本发布留出；必须在推理前原子冻结并只进行一次正式评估。固定质量门至少为：实例召回率 >= 0.90、完整 mask 比例 >= 0.85、漏甲图片率 <= 0.10、加权杂散率 <= 0.02、每图均有可核验输出，并报告直接可提取率和来源组最差表现。评估后不得再修改该候选。

候选锁定后，另行建立不少于 100 张未被该候选或其前代输出筛选的全新未见困难负样本，自动绑定 standing 授权、精确清单与 SHA-256，完成原分辨率终审并原子冻结。在部署输入 512 下，原图、裁右下 12%、模糊右下角三种既有变体均须达到误检图片数=0、误检检测数=0、相对原图 delta=0；若水印位于其他位置，还必须增加针对实际水印区域的裁切/遮挡与模糊变体。失败留出禁止回流训练或再次冒充未见证据。

质量门通过后导出生产 ONNX，登记文件大小、SHA-256、导出配置和完整性证据，并在同一冻结样本上验证训练框架、ONNX、WebGPU 和 WASM 的候选数量、置信度、坐标和像素 mask 一致性。生产 manifest 必须与 releaseIdentity 一致。随后接入 Worker 和 /ar-tryon 的多纹理自动识别/像素 mask 提取流程；只有 backend=model、生产身份一致且每个候选都有有效 mask 时，才可表述为正式自动识别成功。

使用同一 releaseIdentity 完成真实浏览器回归、Windows 桌面性能与重复运行内存、真实用户失败案例、Android 手机、Android 平板、iPhone、iPad 真机验收；四类设备分别至少进行 20 次有效运行，记录浏览器、后端、P50/P95、峰值内存和失败。完成至少 100 张代表性 Beta 人工质量审核、正式产品质量报告，以及两个不同权重且各自完整批准版本的回滚 bootstrap 与实际演练。

只有修正后的完成度审计对同一 releaseIdentity 的全部当前正式门重放通过，并返回 ok=true、decision=complete，才允许解除产品 HOLD 和标记 Goal 完成。训练完成、开发折或校准集通过、ONNX 导出成功、网页加载模型都只是中间里程碑。

精确清单、训练启动和原子 freeze 不再向用户请求授权。只有 Beta 人工判断或连接物理设备确实需要用户提供真实外部输入时，先完成全部不依赖用户的准备工作，生成可直接执行的验收包，再一次性提出具体请求。未经用户明确要求，不执行 git commit 或 git push。
```

## 5. 三份引用文档的问题

### 5.1 `nail-texture-local-inference-implementation-spec.md`

1. **当前状态过期。** 第 3—5 行仍是 2026-07-11/v1.1/实施基线；第 90—101 行仍声称训练只有 dry-run、Worker 判断错误、动态 import、拉伸输入和输出协议未闭环，但同文档第 731—743 行已经将其中多项标为完成。应把顶部状态改成 candidate57 TEST HOLD、生产 ONNX 缺失和剩余发布门。
2. **正式角色定义过宽。** 第 437—443 行把授权真实图、负样本和历史失败笼统写成“可以进 test”；应要求每个稳定 sourceGroup 只能有一个角色。受保护 test/holdout 的失败只能回归，不能进入训练或选样。
3. **正训练覆盖与排除规则混在一起。** 第 453—456 行把甲片板、裁切不完整、运动模糊一起列为真实数据覆盖。完整可见手上甲面才可进入正训练；独立甲片、裁断和无法确认轮廓的图应进入独立压力测试、失败案例或排除。
4. **授权文字过期。** 第 487 行仍要求用户图逐次明确授权，第 725 行保留 candidate5 一次性授权，第 909 行仍要求停下请求精确授权；这些都应改成 standing 授权加机器清单/哈希追溯，并区分未来产品终端用户上传数据。
5. **质量门过旧。** 第 625—662 行仍以 mAP 为主且把甲面缺失写成未量化门槛。mAP 应保留为诊断；正式正样本门应明确 0.90/0.85/0.10/0.02 四项逐实例合同及不少于 100 张的一次性正样本发布留出。
6. **候选历史与规范混杂。** 第 23—50 节把大量 candidate 历史放进稳定技术规范，且第 233—268 行同时把两阶段写成可选、又把旧蒸馏链写成正式路线。应将候选流水迁到 progress/archive，规范只保留稳定合同和一个“当前活动路线”。
7. **旧 val30/test100 仍被当作下一候选发布依据。** 第 1319 行仍要求下一候选重新通过旧 val30 后获取旧 test100 资格。应改成 train 内开发折、全新校准集和全新一次性正样本发布留出。
8. **fallback 契约不统一。** 多处把规则候选写成正常识别路径，另一些位置又要求模型失败转人工。应统一成辅助定位，并与前端 UI、Beta 计数和像素 mask 要求一致。
9. **manifest/release identity 不闭环。** 规范要求 SHA 和大小，但当前运行时类型和加载器未强制校验，现有 manifest 也不能表达复合运行时。优先确定单模型正式路线；若恢复两阶段，必须先升级多模型 manifest、Worker 和 evidence profile。

### 5.2 `nail-texture-local-inference-implementation-progress.md`

1. 第 3、6 行仍停在 2026-08-24/candidate18；第 497、501 行的“当前总体验收”仍围绕 candidate6/7，尾部却已记录 candidate57。顶部 dashboard 应只展示一个当前事实源：candidate57 TEST HOLD、旧 val/test 降级、无批准生产候选。
2. 进度状态把过程完成和质量结果混在一个字段中，出现“PASS（拒绝候选）”“VAL REJECT”“计划已锁定”等无法稳定机器判定的语义。应拆成 `lifecycle=planned|running|closed`、`outcome=pass|rejected|hold|not-applicable`、`gateRole=current-release|historical|superseded`。
3. 已完成或被否决的旧计划仍保持非 PASS，当前脚本会永久阻断 Goal。历史终局必须保留，但不应进入 current-release 阻断集合。
4. 当前 completion profile 和用户支持表仍围绕 candidate5；应显示“当前无批准发布候选”，旧 test100 和旧困难负留出为历史回归，并增加全新校准、正样本发布留出和负样本留出的待办。
5. M1 的模型加载 PASS 只是 33KB smoke ONNX 工程链，不代表生产模型资产可用；dashboard 应显式区分 smoke engineering pass 与 production release pass。

### 5.3 `nail-texture-completion-audit.md` 与实际脚本

1. 文档第 3 行和脚本第 992—1000 行要求整份 progress 的每个 marker 都严格 PASS；现有 51 个历史非 PASS 使完成条件不可达。audit v3 必须只读取显式 current-release required markers。
2. 文档第 211 行写 13 个 gate，当前脚本和报告实际是 14 个，应由 schema 自动生成数量，避免手写漂移。
3. evidence profile 仍绑定 candidate5 的单权重和 0.5 阈值，桌面证据却来自 candidate6，无法表达 candidate57 的双模型、三阈值和组合规则。应改成统一 `releaseIdentity`，并在无批准候选时明确返回 `no_approved_release_candidate`。
4. 正式 gate 仍主要读取 box/mask mAP 和旧 `qualityGatePassed`，没有把 schema v2 的实例召回、完整 mask、漏甲图片率和加权杂散率作为独立强门。应直接调用 `build-positive-recognition-quality-report.py --verify-report` 并拒绝任何非规范阈值合同。
5. Beta、桌面、移动、生产资产和回滚报告没有全部绑定同一模型/manifest/runtime lock，可跨候选拼接。每一份报告都必须包含并重放同一 release identity。
6. 发布顺序不应在外部证据通过后再训练。正确顺序是训练与内部开发完成 → 校准一次 → 锁定 release identity → 一次性正样本发布留出 → 全新困难负样本 → ONNX/浏览器/桌面/真机/Beta/产品质量 → 回滚与最终晋级；任何绑定证据产生后修改模型或运行时都使后续证据失效。

## 6. 推荐修复顺序

1. 先实现 completion audit v3：active gate 范围、历史终局语义、统一 release identity、当前候选拒绝保护、逐实例正样本强门和新留出消费台账。
2. 同步重写 spec 的顶部当前状态、数据角色、standing 授权、正式质量门和当前活动路线；将 candidate 历史迁入 progress/archive。
3. 将 progress 改成短 dashboard 加结构化历史账本，避免自然语言状态驱动机器总门。
4. 修复前端 fallback 语义：没有生产模型和有效像素 mask 时只显示辅助定位/人工确认，不计正式成功。
5. 升级 manifest、运行时加载器和报告 schema，使训练权重、ONNX、WebGPU/WASM、设备、Beta、产品质量和回滚全部绑定同一 release identity。
6. 完成上述证据基础设施后再启动下一轮新数据和单阶段候选训练，避免新候选再次落入不可验证或不可晋级的旧合同。

## 7. 本次审计边界

本次建立问题清单和可直接替换的 Goal 文本，没有修改完成度脚本、模型、训练配置、数据角色、生产 manifest 或前端运行逻辑。当前 audit v2 仍会被历史 marker 阻断，也仍存在跨候选证据拼接；在 audit v3 落地并重放前，不应把当前 `ok=false` 简化为“只差训练”，也不应通过改写历史失败来制造 `complete`。

## 8. 2026-09-06整改状态

本审计指出的文档层问题已经直接写回三份引用文档：实施规范升级为v1.2并新增当前发布候选活动合同，实施进度新增candidate57 TEST HOLD dashboard和结构化当前发布要求，完成度说明升级为v1.3并登记audit v3与统一`releaseIdentity`合同。旧candidate1—57、旧val30/test100和旧两阶段计划仍保留原始事实，但已明确标为历史或被替代，不再被解释为下一候选的有效发布路线。

代码层问题尚未因此自动解决：`scripts/audit-nail-texture-local-inference-completion.ts`和`model/reports/nail-texture-completion-evidence-profile.json`仍是v2/candidate5历史结构，生产manifest仍无批准ONNX，前端fallback、真机、Beta和回滚证据仍待实现。后续必须按三份文档的新合同修改并重放机器审计，不能把本次文档同步当作模型或产品PASS。
