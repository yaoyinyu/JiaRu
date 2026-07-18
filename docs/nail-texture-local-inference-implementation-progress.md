# 美甲纹理端侧实施进度与审核标记

更新日期：2026-07-18
依据：`docs/nail-texture-local-inference-implementation-spec.md`

## 标记规则

- `✅ PASS`：实现完成，自动审核通过，可以推进下一项。
- `🟡 IN PROGRESS`：正在实现，尚未形成完成证据。
- `⏭ USER INPUT`：需要用户材料或真机，暂时跳过，不阻塞其他任务。
- `🟠 PARTIAL`：用户已提供部分材料或确认，但还不足以通过该阶段门禁。
- `⬜ PENDING`：尚未开始。
- `🔴 HOLD`：审核失败，修复前不能推进依赖项。

## 里程碑 1：真实模型端侧冒烟

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `M1-T1-RUNTIME` | Worker 环境识别与 ONNX Runtime 显式加载 | ✅ PASS | Worker 无 `window` 环境测试通过；WebGPU→WASM 重试测试通过；Turbopack 生产构建通过；浏览器集成契约 15/15 通过 |
| `M1-T2-CONTRACT` | 固定 manifest 输入输出协议并接入真实 ONNX smoke artifact | ✅ PASS | 真实 ONNX、SHA-256、输出 dump 与 fixture 均通过审核；离线后处理得到 2 个带 mask 候选 |
| `M1-T2-SCORE-THRESHOLD` | 模型级候选置信度阈值契约 | ✅ PASS | manifest可选`scoreThreshold`经0—1开区间严格校验，导出器与制品验证器同步；运行时将有效阈值传入原始候选及质量排序两道过滤，旧manifest继续使用0.35；0.30候选在模型阈值0.25下的浏览器识别路径测试通过 |
| `M1-T3-BROWSER` | 浏览器内真实 Worker 推理与 UI 后端显示 | ✅ PASS | Chromium 实测 Worker + WebGPU；manifest 与 ONNX 均由本地 URL 加载；2 个候选；控制台 0 错误、0 警告 |
| `M1-T4-FALLBACK` | WebGPU、WASM、超时、取消和规则回退端到端审核 | ✅ PASS | WebGPU 浏览器实测；WebGPU→WASM、超时→规则回退、取消重置及 Worker 能力不足→主线程均有自动测试 |
| `M1-T5-UPLOAD-GATE` | 本地图片MIME、大小、分辨率和解码门禁 | ✅ PASS | 编辑器与AR共用JPG/PNG/WebP、10MB、320–4096像素及解码校验；4项边界测试通过，Playwright验证非法文件内联提示、合法1024 PNG进入编辑器且控制台0错误0警告 |

### `M1-T1-RUNTIME` 审核记录

实现结果：

- Worker 不再因为缺少 `window` 被误判为服务端。
- 相对 manifest/model URL 可以使用 Worker 自身 `location` 解析。
- 移除了 `new Function()` 隐藏动态导入。
- 使用构建器可分析的 `import("onnxruntime-web/webgpu")` 与 `import("onnxruntime-web/wasm")`。
- WebGPU Session 初始化失败时按 manifest 偏好继续尝试 WASM。
- runtime cache 仍按 manifest URL 隔离。

审核命令与结果：

```text
node --no-warnings --experimental-strip-types --test tests/nail-texture-model-runtime.test.ts
结果：16/16 PASS

node --no-warnings --experimental-strip-types --test tests/verify-browser-integration.test.ts
结果：4/4 PASS

node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --skip-model-artifact
结果：ok=true，contractChecks 15/15 PASS

npm.cmd run build
结果：Next.js 16.2.9 Turbopack 编译、TypeScript、静态页面生成全部 PASS
```

审核结论：

> `M1-T1-RUNTIME` 已通过。现有证据证明 Worker 运行环境和 ORT 模块加载路径已具备生产构建条件；真实 ONNX 文件及浏览器实际推理属于下一标记，不在本标记中提前宣称完成。

### `M1-T2-CONTRACT`、`M1-T3-BROWSER` 与 `M1-T4-FALLBACK` 审核记录

- smoke manifest 显式固定 `NCHW / RGB / zero_to_one / letterbox / ultralytics-seg-raw-v1`。
- ONNX 文件为可由 ONNX Runtime 实际执行的模型，不是伪造占位文件；大小 33518 字节，SHA-256 为 `3daa876fb529c3d21d87d731b609a30d8beab8ad9ea29ee45c30566c7692b5cf`。
- 输出 fixture 为 `[1,37,3]` 与 `[1,32,16,16]`，经过转置、Top-K、NMS、mask decode/crop 后得到 2 个候选。
- Chromium 页面实测显示 `model / webgpu`、`nail-texture-seg-smoke-v1`、2 个候选；端到端 491 ms，Worker 461 ms。
- 网络记录证明 manifest、ONNX、Worker chunk 与 ORT WASM/WebGPU 资源均从 `localhost` 加载；控制台 0 错误、0 警告。
- Worker 能力门禁显式要求 `Worker`、`createImageBitmap` 与 `OffscreenCanvas`；能力不足时使用主线程本地路径。

审核结果：专项测试 30/30 PASS；全量回归测试 289/289 PASS；ESLint PASS；Next.js 生产构建 PASS。

### `M1-T2-SCORE-THRESHOLD` 审核记录

- `NailTextureModelManifest` 与 `NailTextureModelInfo` 增加可选 `scoreThreshold`；manifest缺省时运行时明确落为`0.35`，因此旧制品兼容且调试信息可追溯实际生效值。
- manifest运行时校验和`verify-model-artifact.ts`均拒绝非有限数、`<=0`或`>=1`；`export-onnx.py --score-threshold`使用相同开区间约束并把校准值写入新manifest。
- 识别链路把同一有效阈值传给原始输出过滤和质量排序，消除第二道固定`0.35`造成的假配置；`includeLowConfidenceCandidates`仍只作为显式调试开关。
- 该标记只证明阈值契约真实生效，不证明`0.25`适合生产；v6冻结67张画像在0.25下误检上升，生产manifest与共享默认值均未修改。

审核结果：模型运行时、候选质量、ONNX导出和制品校验专项35/35 PASS；全量364/364、Python编译、ESLint、Next.js生产构建、359文件编码审计通过。完成度审计更新为93标记/80 PASS、2/10门并按预期保持HOLD。

## 里程碑 2：正确后处理与真实数据试验

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `M2-T1-PROTOCOL` | 统一 letterbox、输出布局、Top-K、NMS、mask crop 与坐标还原 | ✅ PASS | 横竖图 letterbox、逆映射、channel-major 输出、重复框抑制及 mask crop 单元测试通过；fixture 会逐候选核对 Python/TypeScript 几何、分数与 mask 前景像素 |
| `M2-T2-TEXTURE` | 原图 mask 采样、透明边缘与高光策略 | ✅ PASS | 默认保留高光且不改像素；修复仅在显式指定时启用；透明羽化、紧边界裁剪、诊断和 UI 提示测试通过 |
| `M2-T2-DATA-GATE` | 数据结构、来源授权、split 与训练环境门禁 | ✅ PASS | 正式有效集409图/2142个mask、409条来源记录，split=300/46/63；7张截图派生图按父图稳定分组，来源授权、标签、split比例、训练物化和readiness通过 |
| `M2-T3-SYNTHETIC-BASELINE` | 训练、评测并导出隔离的合成数据基线 | ✅ PASS | 300 张 AI 图逐 SHA-256 核对无缺失；88 epochs early stop；test box mAP50=0.522、mask mAP50=0.454；11.09MB ONNX 完整性与浏览器 WebGPU 通过；发布门禁按预期拒绝 |
| `M2-T3-REAL-DATA` | 导入授权真实图片并建立来源隔离测试集 | 🟠 PARTIAL | 新增113张已获商业训练与长期回归授权；80张原图/516 mask及7张截图派生图/41 mask正式导入，5张源图排除、28张原图继续返修。真实发布测试样本仍未达到100–200张代表性要求 |
| `M2-T3-VISION-ANNOTATION` | 识图提示 + SAM2/YOLO 辅助重建真实甲面多边形 | 🟡 IN PROGRESS | 正式集409图/2142 mask不变；外部首批train为100张唯一图片/521个完整mask。来源隔离val 30张完成首轮审核后已终审10张/44 mask，剩余20张返修；整套val尚未全通过，约100张hard negative及整批物化/来源隔离继续推进 |
| `M2-T3-VAL-ANNOTATION-WORKSPACE` | 来源隔离val专用标注工作区与自动候选链路 | ✅ PASS | 构建器新增显式`--selection-mode val`且保持默认first-train兼容；真实计划物化30张/7来源组/3分片/159枚预期甲面，30/30硬链接且来源组不拆分。YOLO部署512生成155候选，SAM2.1 large完成30图/155提示、0 fallback/0错误，几何112 pass/43 suspect；专项测试证明train/test不会混入val |
| `M2-T3-VAL-MASK-INITIAL-REVIEW` | val候选完整甲面原分辨率首轮审核 | ✅ PASS | 16页覆盖30张，逐图原分辨率复核为1 pass/29 rework/0 exclude；仅`nail_00456…_2`的2枚完整甲面直通，其余存在漏甲、重复或皮肤/非甲物体污染。四个分片以工作区、分片、页面和决策SHA-256终结；正式val真值仍0/30，返修清零前禁止校准或训练 |
| `M2-T3-VAL-TRUTH-ROLE-GATE` | val角色绑定终审与唯一索引 | ✅ PASS | 最终真值终结器新增`--truth-role val --role-manifest`，核对val角色、图片/来源/甲数和训练禁用；唯一索引支持validation前缀并与training报告隔离，同图冲突继续拒绝。默认train兼容，专项5/5通过 |
| `M2-T3-VAL-MASK-REPAIR-BATCH-001-004` | val低风险误检删除、紧框重建与人工polygon返修 | ✅ PASS | `00454/00457/00384`形成15个完整SAM polygon；`00829`两甲全人工重画，`00672`保留3甲并重画2甲；整图、逐甲2×、合法性、零交叠和几何均通过。`00455`SAM仍吸收皮肤，保持返修未晋级 |
| `M2-T3-VAL-TRUTH-006` | 首6张来源隔离验证真值候选唯一索引 | ✅ PASS | 6个批准报告归并为6张唯一图片/24 mask、0冗余、0冲突，索引SHA-256为`adac6dc3…33c7`；全部绑定val角色且trainingUse=prohibited，剩余24张清零前整套split仍禁止校准或训练 |
| `M2-T3-VAL-MASK-REPAIR-BATCH-005-006` | 透明长甲、立体装饰与横向甲完整轮廓返修 | ✅ PASS | `00946`删除眼睛/镜片/衣物/重复候选，SAM右侧拇指仍吸收面部后改用人工polygon，并在逐甲2×发现第2甲漏白色延长甲尖后再次重画；`00945`五甲全部紧框SAM，横向甲吸收指腹后两轮人工收紧至真实甲沟。终版2张/10 mask通过整图、全部逐甲2×、合法性、零交叠和几何10/10 |
| `M2-T3-VAL-TRUTH-008` | 首8张来源隔离验证真值候选唯一索引 | ✅ PASS | 8个批准报告归并为8张唯一图片/34 mask、0冗余、0冲突，索引SHA-256为`b080d9d1…fa69`；全部绑定val角色且trainingUse=prohibited，剩余22张清零前整套split仍禁止校准或训练 |
| `M2-T3-VAL-MASK-REPAIR-BATCH-007` | 同源透明长甲、横向甲与立体装饰完整轮廓返修 | ✅ PASS | `00944/00936`删除全部漏甲及眼睛、眼镜、头发、衣物或皮肤旧候选；SAM 2图/10提示、0 fallback、几何10/10，但视觉门拦截横向甲吸收面部/眼镜及拇指带入头发/皮肤。两轮人工复核最终保留5个已审polygon、重画5个问题polygon；整图、全部逐甲2×、合法性、零交叠和几何10/10通过 |
| `M2-T3-VAL-TRUTH-010` | 首10张来源隔离验证真值候选唯一索引 | ✅ PASS | 10个批准报告归并为10张唯一图片/44 mask、0冗余、0冲突，索引SHA-256为`f7f3c9f3…379c`；全部绑定val角色且trainingUse=prohibited，剩余20张清零前整套split仍禁止校准或训练 |
| `M2-T3-PROMPT-DIAGNOSTICS` | 辅助标注单甲失败精确定位 | ✅ PASS | FastSAM/SAM2空mask错误包含提示序号和模式，polygon转换错误包含提示序号；专项测试通过，实跑准确定位`prompt 6 (box)`及`prompt 9 (box-center)` |
| `M2-T3-REGION-EXTRACTION` | 从截图/拼图中提取受审计单照片区域 | ✅ PASS | 9张小红书截图主区域9/9提取成功；报告包含父子SHA-256、归一化/像素框、尺寸、reviewRequired和父图稳定sourceGroup；Windows Unicode控制台兼容及非法框/路径守卫测试通过 |
| `M2-T3-DERIVED-ANNOTATION` | 派生照片逐甲SAM2标注与父图稳定分组审计 | ✅ PASS | 9张派生图9/9有审核决策，7张/41 mask通过、2张返修；机器审计核对派生图哈希、尺寸、逐图sourceGroup、mask数、多边形边界与面积，0错误；2项专项测试通过 |
| `M2-T3-DERIVED-IMPORT` | 审核通过派生样本授权继承与安全入库 | ✅ PASS | 7张/41 mask已导入；逐图sourceGroup、父文件/哈希/裁剪框和原批次授权写入来源记录，409条来源、300/46/63 split、标签、物化及release readiness全部通过；专项测试10/10通过 |
| `M2-T3-RELEASE-TEST-INTAKE` | 新增真实发布测试素材统一命名、去重与用途隔离 | ✅ PASS | 101张统一为`real_release_20260713_001..101.jpg`并保留原名/来源/哈希映射；9张跨旧批次精确重复排除，92张按57核心/35压力图进入独立发布测试与长期回归，19个来源组且训练用途明确禁止 |
| `M2-T3-MATERIAL-NAMING` | 外部素材全集统一命名与可逆追溯 | ✅ PASS | 其余5批1435张统一为类型/来源/日期/四位序号命名，5份映射保留原名、新名、SHA-256和来源组；1435/1435哈希复核一致。101张已稳定引用的发布测试图保持原命名，外部素材共1536张纳入统一管理 |
| `M2-T3-RELEASE-TEST-STRESS-REGIONS` | 35张截图/拼图压力图主照片区域提取与来源继承 | ✅ PASS | 35/35区域提取成功，父图/派生SHA-256、裁剪框和父图稳定sourceGroup审计通过；派生intake强制父项为stress、每父图一个主区域并继承发布测试/长期回归授权，训练用途prohibited；专项测试2/2通过 |
| `M2-T3-RELEASE-TEST-ANNOTATION` | 新增真实发布测试素材逐甲标注与整图复核 | 🟡 IN PROGRESS | 冻结前拓扑门发现030的关节假阳性及13图无效polygon/交叠边界；返修并经原分辨率复核后，92张父图为67张/384 mask通过、0返修、25张源图裁断或遮挡排除。核心57张为45张/268 mask通过、0返修、12排除，压力35张为22张/116 mask通过、0返修、13排除；当前候选已冻结，但仍少33张才达到100张代表性下限 |
| `M2-T3-RELEASE-TEST-CANDIDATE-FREEZE` | 冻结受审核发布测试候选并校验可复现性 | ✅ PASS | 67张/384 mask按core 45张与stress 22张隔离复制；67个图片哈希、67个标注哈希、图片/标注联合哈希及清单聚合SHA-256独立复算0错误，18个父来源组，trainingUse固定prohibited。冻结只证明候选真值与规模证据，代表性门67/100未通过，v6质量指标仍来自历史13张/102 mask冻结test |
| `M2-T3-RELEASE-TEST-REPAIR-V2` | 返修提示keep/drop/add与父图级审核聚合 | ✅ PASS | 5张/25提示SAM2完成且几何25 pass/0 suspect；原分辨率4张/20 mask提升、1张返修。修复提示记录双清单SHA-256，审核叠加核对polygon数/来源组，聚合报告覆盖92/92父图并保持trainingUse=prohibited；专项5/5通过 |
| `M2-T3-RELEASE-TEST-REPAIR-V3` | 第二轮逐甲返修与原分辨率污染复核 | ✅ PASS | 6张/29提示SAM2完成且几何29 pass/0 suspect；原分辨率仅002、027两张/9 mask提升，001、051、052、091因皮肤污染继续返修。父图聚合为16张/98 mask暂通过、75张返修、1张排除，训练用途保持prohibited |
| `M2-T3-RELEASE-TEST-REPAIR-V4` | 逐新增框提示模式与第三轮高潜力返修 | ✅ PASS | 构建器支持逐框`box-center`并拒绝数量不匹配/非法模式；5张/24提示SAM2完成、0 fallback、几何24 pass/0 suspect，原分辨率5张/24 mask全部提升。父图聚合为21张/122 mask暂通过、70张返修、1张排除、9个来源组，训练用途保持prohibited |
| `M2-T3-RELEASE-TEST-REPAIR-V5` | 第四轮高置信候选返修与严格视觉拦截 | ✅ PASS | 6张/30提示SAM2完成、0 fallback、几何30 pass/0 suspect；原分辨率仅接受043/044/064共3张/15 mask，004/022/080继续返修。父图聚合为24张/137 mask暂通过、67张返修、1张排除、10个来源组，训练用途保持prohibited |
| `M2-T3-RELEASE-TEST-REPAIR-V6` | 第五轮负点提示返修与边缘裁断复核 | ✅ PASS | 7张/37提示采用`center-negative-corners`完成、0 fallback、几何37 pass/0 suspect；原分辨率仅接受033/045/048共3张/18 mask，4张继续返修；034/070因甲面被画面边缘截断转为排除。父图聚合为27张/155 mask暂通过、62张返修、3张排除、10个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V7` | 第六轮重复提示清理与完整甲面优先审核 | ✅ PASS | 6张/31提示完成、0 fallback、几何31 pass/0 suspect；原分辨率仅接受051/054/077共3张/16 mask，3张局部/重复/污染项继续返修；049因下边界裁断转为排除。父图聚合为30张/171 mask暂通过、58张返修、4张排除、11个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V8` | 第七轮全甲面复核与遮挡源图清退 | ✅ PASS | 6张/40提示完成、0 fallback、几何38 pass/2 suspect；原分辨率0张/0 mask新增通过，024/067/073/075继续返修，023/084及同期复核085/088按裁断或遮挡规则排除。父图聚合保持30张/171 mask暂通过，更新为54张返修、8张排除、11个来源组 |
| `M2-T3-SAM-MULTIPOINT` | 逐甲多正点/多负点提示契约与动态标签 | ✅ PASS | 构建器支持保留及新增逐框`positivePoints`/`negativePoints`，校验数量、结构和归一化边界并记录正负点数量；执行器独立校验并按实际点数生成标签，自定义负点替代默认角点。专项5/5通过 |
| `M2-T3-RELEASE-TEST-REPAIR-V9` | 第八轮透明延长甲多点定向返修 | ✅ PASS | 067以每甲两个正点覆盖有色基底和透明甲尖，定向负点压制袖口污染；5/5提示完成、0 fallback、几何5 pass/0 suspect，原分辨率接受1张/5个完整mask。父图聚合更新为31张/176 mask暂通过、53张返修、8张排除、11个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V10` | 第九轮长甲与低对比裸色甲完整轴向多点返修 | ✅ PASS | 024/075共10提示完成、0 fallback，几何9 pass/1 suspect；立体钻饰导致的中心点suspect经原图复核不构成漏甲，三次甲根负点收敛后原分辨率接受2张/10个完整mask。父图聚合更新为33张/186 mask暂通过、51张返修、8张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V11` | 第十轮双手相邻长甲完整轴向多点返修 | ✅ PASS | 073共9提示完成、0 fallback，几何9 pass/0 suspect；原分辨率确认上手带钻白色延长段和下手相邻三甲均完整分离，一甲一mask且无皮肤污染，接受1张/9 mask。父图聚合更新为34张/195 mask暂通过、50张返修、8张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V12` | 第十一轮同源长甲重建与严格拇指皮肤复核 | ✅ PASS | 025/026共10提示完成、0 fallback，几何10 pass/0 suspect；原分辨率仅接受025的1张/5 mask，026的拇指仍吸收矩形皮肤区域而继续返修。父图聚合更新为35张/200 mask暂通过、49张返修、8张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V13` | 第十二轮低对比裸色甲、透明侧向拇指与衣物污染复核 | ✅ PASS | 065/071共10提示完成、0 fallback，几何9 pass/1 suspect；原分辨率仅接受071的1张/5 mask，065拇指仍吸收牛仔布与皮肤而继续返修。父图聚合更新为36张/205 mask暂通过、48张返修、8张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V14` | 第十三轮低对比单手甲重建与右边界裁断复核 | ✅ PASS | 080/091共10提示完成、0 fallback，几何10 pass/0 suspect；原分辨率接受080的1张/5完整mask，091因最右侧小拇指甲被图片边界裁断转为排除。父图聚合更新为37张/210 mask暂通过、46张返修、9张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V15` | 第十四轮双手10甲、立体蝴蝶结与漏拇指完整重建 | ✅ PASS | 078共10提示完成、0 fallback，几何10 pass/0 suspect；原分辨率接受1张/10完整mask，两枚蝴蝶结甲不再拆分且下手拇指补齐；069按左边界裁断规则转排除。父图聚合更新为38张/220 mask暂通过、44张返修、10张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V16` | 第十五轮深色甲收紧、低对比摆件污染与遮挡源图清退 | ✅ PASS | 001/047共14提示完成、0 fallback，几何14 pass/0 suspect；原分辨率接受001的1张/5完整mask，047因最左低对比甲仍吸收白色摆件继续返修；081左边界裁断、083背景手甲面被遮挡转排除。父图聚合更新为39张/225 mask暂通过、41张返修、12张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V17` | 第十六轮深色拇指皮肤污染定点返修 | ✅ PASS | 004保留4个已通过完整甲面提示并收紧重建拇指，5/5提示完成、0 fallback，几何5 pass/0 suspect；原分辨率确认拇指不再吸收下方皮肤，接受1张/5完整mask。父图聚合更新为40张/230 mask暂通过、40张返修、12张排除、12个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V18` | 第十七轮长甲甲根皮肤污染定点返修 | ✅ PASS | 022保留4个完整甲面；右上长甲首跑虽几何通过但甲根皮肤外溢，收紧提示后5/5完成、0 fallback，几何5 pass/0 suspect；原分辨率接受1张/5完整mask。父图聚合更新为41张/235 mask暂通过、39张返修、12张排除、13个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V19` | 第十八轮拇指矩形皮肤污染定点返修 | ✅ PASS | 026保留4个完整手指甲面，以4个轴向正点和6个皮肤负点重建拇指；5/5完成、0 fallback，几何5 pass/0 suspect；原分辨率接受1张/5完整mask。父图聚合更新为42张/240 mask暂通过、38张返修、12张排除、13个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V20` | 第十九轮透明拇指牛仔布/皮肤污染定点返修 | ✅ PASS | 065保留4个完整手指甲面，以覆盖有色甲面/透明甲尖的4个轴向正点和6个污染区负点重建拇指；5/5完成、0 fallback，几何5 pass/0 suspect；原分辨率接受1张/5完整mask。父图聚合更新为43张/245 mask暂通过、37张返修、12张排除、14个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V21` | 第二十轮漏甲与重复mask联合返修 | ✅ PASS | 052保留3个完整甲面，将黑色蝴蝶结甲的两个重叠候选重建为单一完整mask，并补齐左下漏标拇指；5/5完成、0 fallback，几何5 pass/0 suspect；原分辨率接受1张/5完整mask。父图聚合更新为44张/250 mask暂通过、36张返修、12张排除、14个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V22` | 第二十一轮交叠甲与拇指皮肤污染返修 | ✅ PASS | 072保留7个完整mask，重建两枚交叠长甲和前景蝴蝶拇指；首跑几何10/10通过但视觉门拒绝拇指皮肤污染，收紧复跑后10/10完成、0 fallback、几何10 pass/0 suspect；原分辨率接受1张/10完整mask。父图聚合更新为45张/260 mask暂通过、35张返修、12张排除、14个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V23` | 第二十二轮低对比紫色甲与白色摆件分离返修 | ✅ PASS | 047保留8个完整mask，只重建最左低对比紫色甲；SAM2完成9/9、0 fallback、几何9 pass/0 suspect，原分辨率并排复核确认完整甲面且无白色摆件污染。父图聚合更新为46张/269 mask暂通过、34张返修、12张排除、14个来源组 |
| `M2-T3-RELEASE-TEST-REPAIR-V24` | 第二十三轮双手10甲与手掌/腕表误检清理 | ✅ PASS | 076保留9个完整mask，删除1个手掌和2个腕表误检，只重建上方拇指；SAM2完成10/10、0 fallback、几何9 pass/1 suspect，原分辨率确认10甲完整，suspect仅为下方斜向拇指提示中心关系。核心返修队列清零；父图聚合更新为47张/279 mask暂通过、33张返修、12张排除、14个来源组 |
| `M2-T3-RELEASE-TEST-STRESS-REPAIR-V2` | 第二十四轮暨压力派生图首批单手照片返修 | ✅ PASS | 3e9b/51a2/e826保留11个完整mask，删除1个黑背景误检并补4个漏甲；首跑几何15/15通过但视觉门拒绝皮肤/白布污染，三次收紧复跑后15/15完成、0 fallback、几何15 pass/0 suspect，原分辨率接受3张/15完整mask。父图聚合更新为50张/294 mask暂通过、30张返修、12张排除、16个来源组 |
| `M2-T3-RELEASE-TEST-STRESS-REPAIR-V3` | 第二十五轮暨压力派生图第二批返修、裁断清退与几何审计复现 | ✅ PASS | 新增几何审计脚本并逐行复现v2的15/15；0662两次收紧袖口相邻甲，d17a确认相邻polygon交集为0，最终10/10完成、0 fallback、几何10 pass/0 suspect，原分辨率接受2张/10完整mask。0c2b/6be4父主照片裁断转排除；4个选错局部区域项保留重提取。父图更新为52张/304 mask暂通过、26张返修、14张排除、16个来源组 |
| `M2-T3-RELEASE-TEST-STRESS-REGION-V2` | 第二十六轮压力错误区域重提取、稳定父组替换与透明长甲复核 | ✅ PASS | 4个父截图重提取主照片并移除3处相邻拼图半甲；新增按父图替换合并器，4/4父哈希、派生哈希、稳定来源组通过，35图聚合保持一父一派生。SAM2完成27/27、1 fallback、0错误，几何22 pass/5 suspect；原分辨率接受f8c5/bc6b/c541共3张/18完整mask，eac9相邻透明长甲仍合并皮肤/邻指继续返修。父图更新为55张/322 mask暂通过、23张返修、14张排除、17个来源组 |
| `M2-T3-RELEASE-TEST-STRESS-REGION-V3` | 第二十七轮压力错误小图/裁断区域重提取与视觉复核 | ✅ PASS | 007/037/094/095从父截图重取完整主照片，4/4父哈希、派生哈希和稳定来源组通过，聚合保持35父图/35派生。SAM2完成19/19、0 fallback、几何19 pass/0 suspect；原分辨率仅接受7a92的1张/5完整mask，另3张皮肤外溢继续返修。父图更新为56张/327 mask暂通过、22张返修、14张排除、17个来源组 |
| `M2-T3-RELEASE-TEST-STRESS-LARGE-REPAIR-V4` | 第二十八轮SAM2.1 large皮肤污染收紧与fallback逐提示诊断 | ✅ PASS | 86ac/956d/b1184共3张/14提示由SAM2.1 large完成、0 fallback，几何13 pass/1 suspect；原分辨率仅接受86ac/956d的2张/10完整mask，b1184第1—3甲仍有甲根皮肤而返修。后续v5/v6证明b1184提示2/3初始均返回0 mask并退化为box-only；执行器新增逐文件、提示序号、模式和初始mask数诊断，并保留多mask按正负点/框包含率选择能力。压力集更新为13张/68 mask通过、20返修、2排除；父图为58张/337 mask暂通过、20返修、14排除 |
| `M2-T3-RELEASE-TEST-STRESS-EDGE-EXCLUSION-V5` | 第二十九轮压力返修图边缘裁切清退与几何假阳性拦截 | ✅ PASS | 初筛20张返修图并对e0ee/c0e0各运行5个SAM2.1 large多点提示，均0 fallback、几何5 pass/0 suspect；原分辨率否决两组候选，并确认406b/9da2/c0e0/e0ee均有必需甲面触及图像边缘而不完整，4张从返修改为排除，0张/0 mask误提升。压力集为13张/68 mask通过、16返修、6排除；父图为58张/337 mask暂通过、16返修、18排除 |
| `M2-T3-RELEASE-TEST-STRESS-EDGE-EXCLUSION-V6` | 第三十轮交叠甲/指腹污染复跑与第二批边缘裁切清退 | ✅ PASS | d970连续4轮、f075一轮各5个SAM2.1 large提示均完成、0 fallback；几何均5 pass/0 suspect，d970相邻polygon交集由约700像素降为0，但原分辨率仍分别存在指腹污染或只覆盖蓝色前段，2张继续返修。6df0/424a/a4a4/b548/cf0c因必需甲根或甲面被图像边缘裁断转排除，0张/0 mask误提升。压力集为13张/68 mask通过、11返修、11排除；父图为58张/337 mask暂通过、11返修、23排除 |
| `M2-T3-RELEASE-TEST-STRESS-EDGE-EXCLUSION-V7` | 第三十一轮局部甲面/皮肤污染复核与第三批边缘裁切清退 | ✅ PASS | 6d9a/d951各5个SAM2.1 large提示完成、0 fallback、几何5 pass/0 suspect且polygon无相交；原分辨率分别发现透明/白色甲尖或粉色甲根遗漏，以及拇指皮肤污染和小拇指漏甲，均继续返修。02f顶部甲面和6d83右侧甲根触边裁断转排除，0张/0 mask误提升。压力集为13张/68 mask通过、9返修、13排除；父图为58张/337 mask暂通过、9返修、25排除 |
| `M2-T3-RELEASE-TEST-STRESS-LARGE-REPAIR-V8` | 第三十二轮重复/局部mask、漏小指与交叠边界返修 | ✅ PASS | f8a/2c79各5提示一次收敛；2236经v18—v23把无名指/小指polygon相交从71.39像素降为0，并通过放大复核补齐水钻相邻透明拇指甲根、拒绝皮肤吸收中间态。最终3张/15提示均0 fallback、几何15 pass/0 suspect且polygon无相交，原分辨率接受3张/15完整mask。压力集为16张/83 mask通过、6返修、13排除；父图为61张/352 mask暂通过、6返修、25排除 |
| `M2-T3-RELEASE-TEST-STRESS-MANUAL-REPAIR-V9` | 第三十三轮单甲fallback返修与透明相邻长甲人工多边形闭环 | ✅ PASS | b1184仅重建黑甲，4/4完成、0 fallback、几何4 pass/0 suspect且零交叠；eac9的SAM v25虽9/9几何通过但因皮肤/邻指合并被视觉门拒绝，原分辨率人工绘制9甲后通过9 pass/0 suspect、合法性、零交叠和三处放大视觉复核。接受2张/13完整mask。压力集为18张/96 mask通过、4返修、13排除；父图为63张/365 mask暂通过、4返修、25排除 |
| `M2-T3-RELEASE-TEST-STRESS-MANUAL-REPAIR-V10` | 第三十四轮混合人工polygon返修与压力队列清零 | ✅ PASS | 新增混合返修工具，保留10个已审polygon、替换10个局部/无效/皮肤污染polygon，并生成整图及20组逐甲原图/overlay 2×证据；f075/d970/d951/6d9a共4张/20 mask全部合法、几何20 pass/0 suspect/0 missing、零交叠且通过视觉复核。该轮记录的67张/385 mask是冻结前统计，后续拓扑冻结门移除030的1个关节假阳性，最终冻结量为67张/384 mask |
| `M2-T3-RELEASE-TEST-STRESS-LARGE-SAM-COMPARE` | eac9透明相邻长甲SAM2.1 large容量对照 | ✅ PASS（拒绝候选） | box与多正负点各完成9提示、0错误，几何均为8 pass/1 suspect；原分辨率仍发现皮肤/邻指合并和局部甲面，未提升审核决定，eac9继续返修，证明大模型容量不能替代视觉真值门 |
| `M2-T3-REAL-MATERIAL-20260714-INTAKE` | 7月14日新增实拍候选完整性、去重、来源分组与授权隔离 | ✅ PASS | 1277/1277可解码，196个原始笔记来源组，批内0精确重复/70对近重复；跨1053张参照0精确重复/86对近重复。候选清单逐图复核SHA-256/尺寸并固定authorization=pending、trainingUse=prohibited；14页全量联系表仅用于分布抽查，不冒充逐图审核 |
| `M2-T3-REAL-MATERIAL-AUTHORIZATION-CONTRACT` | 7月14日实拍候选A/B/C授权决策登记与未审核隔离 | ✅ PASS（等待用户选择） | 新增`authorize-real-material-candidate-intake.py`，绑定原候选intake SHA-256、逐图SHA-256、来源组及聚合哈希；A/B/C分别映射商业训练+发布测试+回归、仅发布测试+回归、仅存档。A只登记审核后训练资格，所有未审核条目仍固定`trainingUse=prohibited`，且训练与独立发布测试必须互斥分配；图片漂移时输出invalid并拒绝 |
| `M2-T3-REAL-MATERIAL-EXCLUSIVE-ASSIGNMENT` | 授权后完整来源组原子分配与训练/发布测试防泄漏 | ✅ PASS（等待授权与逐图审核） | 新增`audit-real-material-exclusive-assignment.py`，复验授权清单、原候选intake与逐图图片哈希；A/B要求pass/exclude最终审核全覆盖，A可分配train/val/独立发布测试，B仅可分配独立发布测试，C无需视觉审核直接归档。同一`sourceGroup`跨角色、rework、漏审、越权角色、图片或清单漂移均拒绝；val仍须通过独立真值门 |
| `M2-T3-REAL-MATERIAL-REVIEW-WORKSPACE` | 授权实拍候选原分辨率审核工作区与来源组原子分片 | ✅ PASS（等待A/B授权） | 新增`build-real-material-review-workspace.py`，只接受已确认A/B授权，复验授权/原intake/图片哈希后生成逐图全覆盖`review-all.csv`和按完整`sourceGroup`分片的CSV；记录分片、聚合行与文件SHA-256，允许大来源组超过目标分片大小但禁止拆组。审核状态、完整露出甲数、完整mask数、问题码、角色和备注保持空白，空字段不构成通过；不复制图片 |
| `M2-T3-REAL-MATERIAL-20260714-AUTHORIZED` | 当前实存批次A授权、目录漂移拒绝与来源组审核工作区 | ✅ PASS | 旧1277张清单因6张缺失被安全拒绝；按当前1271张/196来源组重建盘点、intake和A授权，允许商业训练、独立发布测试和长期回归。外部工作区生成28个来源组原子分片；未完成逐图审核前每项仍为`trainingUse=prohibited` |
| `M2-T3-REAL-MATERIAL-NEAR-DUPLICATE-REVIEW` | 跨语料与批内近重复原图视觉审核 | ✅ PASS | 20页联系表覆盖156对并绑定页面SHA-256；视觉确认86对跨历史语料重复、14对批内重复、52对含非照片模板、4对同场景不同甲色/设计需保留。终结器强制全部页面确认和决策全覆盖，排除105个唯一候选，剩余1166张继续逐图完整甲面审核；判重不冒充质量通过 |
| `M2-T3-REAL-MATERIAL-QUALITY-REVIEW-QUEUE` | 近重复排除后的逐图完整甲面质量审核队列 | ✅ PASS | 新增`build-real-material-quality-review-queue.py`，绑定1271张原审核工作区与近重复终结报告哈希；扣除105张后将1166张/193来源组组织为26个原子分片，最大50张。已排除条目不得回流、来源组不得跨分片，空审核字段不构成通过且训练用途继续禁止 |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-001` | 质量分片001源图适用性与完整露出甲面审核 | ✅ PASS | 12页覆盖48张并绑定页哈希；联系表预筛后对29张保留项逐张回看原分辨率，确认需标注甲面均完整在框，另19张教程图/拼图排除。终结器验证48/48决策覆盖；29张仅进入待标注候选，仍固定`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-002` | 质量分片002模糊、残缺与非单图源图硬门 | ✅ PASS | 12页覆盖47张，27张单图逐文件回看原分辨率；2张模糊、1张甲面仅局部露出、2张非上手甲片和18张截图/拼图排除，24张仅进入待标注候选。模糊、裁断、残缺及仅局部甲面图片和派生物禁止训练；保留项继续`trainingUse=prohibited` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-003` | 质量分片003清晰度、完整甲面与单图源图硬门 | ✅ PASS | 12页覆盖48张并逐文件回看原分辨率；7张模糊/低清、7张裁断/遮挡/仅局部甲面、13张拼图和2张护肤品主体图排除，19张仅进入待标注候选。分片001—003累计143张、72张待标注、71张排除；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-004` | 质量分片004拼图、模糊与残缺甲面源图硬门 | ✅ PASS | 11页覆盖44张，21张非拼图候选逐文件回看原分辨率；23张拼图/页面排版、9张裁断/遮挡/仅局部甲面和3张模糊低清排除，9张仅进入待标注候选。分片001—004累计187张、81张待标注、106张排除；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-005` | 质量分片005报告绑定、清晰度与完整甲面源图硬门 | ✅ PASS | 11页覆盖44张/7来源组；按报告绑定分片复验25张非拼图原文件，19张拼图/页面排版、4张模糊低清和2张遮挡/仅局部甲面排除，19张仅进入待标注候选。分片001—005累计231张、100张待标注、131张排除；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-006` | 质量分片006清晰度、拼图排版与完整甲面源图硬门 | ✅ PASS | 13页覆盖50张/9来源组；20张非拼图候选逐文件回看原分辨率，30张拼图/页面排版和5张模糊低清排除，15张仅进入待标注候选。分片001—006累计281张、115张待标注、166张排除，另885张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-007` | 质量分片007像素化视频帧与目标域源图硬门 | ✅ PASS | 12页覆盖47张/7来源组；46张非页面排版候选逐文件回看原分辨率，4张像素化/失焦视频帧和1张无美甲主体的人像拼接页排除，42张仅进入待标注候选。分片001—007累计328张、157张待标注、171张排除，另838张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-008` | 质量分片008拼图、低清视频帧与边缘裁断硬门 | ✅ PASS | 11页覆盖42张/9来源组；27张非拼图候选逐文件回看原分辨率，15张拼图/页面排版、7张像素化/失焦视频帧和2张边缘裁断甲面图排除，18张仅进入待标注候选。分片001—008累计370张、175张待标注、195张排除，另796张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-009` | 质量分片009拼图排版与低清视频帧源图硬门 | ✅ PASS | 13页覆盖49张/7来源组；23张拼图/页面排版直接排除，其余26张逐文件回看原分辨率，7张失焦、像素化或甲缘细节不足图片排除，19张仅进入待标注候选。分片001—009累计419张、194张待标注、225张排除，另747张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-010` | 质量分片010拼图、边缘截甲与低清源图硬门 | ✅ PASS | 12页覆盖46张/6来源组；10张拼图/页面排版、3张边缘截断甲面图和2张明显像素化/偏软图片排除，31张仅进入待标注候选。分片001—010累计465张、225张待标注、240张排除，另701张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-011` | 质量分片011模板、拼贴与低清源图硬门 | ✅ PASS | 10页覆盖38张/5来源组；14张甲型示意模板、10张拼图/页面排版和4张明显像素化/失焦图片排除，10张仅进入待标注候选。分片001—011累计503张、235张待标注、268张排除，另663张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-012` | 质量分片012低清与压缩素材源图硬门 | ✅ PASS | 12页覆盖45张/6来源组并逐文件回看原分辨率；4张明显像素化、压缩涂抹或失焦图片排除，41张仅进入待标注候选，共277个完整可见甲面。分片001—012累计548张、276张待标注、272张排除，另618张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-013` | 质量分片013拼图、低清与边缘截甲源图硬门 | ✅ PASS | 11页覆盖42张/5来源组并逐文件回看原分辨率；21张拼图/页面排版、2张明显像素化/失焦图和1张边缘截断甲面图排除，18张仅进入待标注候选，共113个完整可见甲面。分片001—013累计590张、294张待标注、296张排除，另576张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-014` | 质量分片014拼图、低清与边缘截甲源图硬门 | ✅ PASS | 11页覆盖44张/7来源组并逐文件回看原分辨率；12张拼图/页面排版、3张明显像素化/失焦图和1张边缘截断甲面图排除，28张仅进入待标注候选，共192个完整可见甲面。分片001—014累计634张、322张待标注、312张排除，另532张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-015` | 质量分片015拼图、低清、残缺甲面与域外源图硬门 | ✅ PASS | 12页覆盖48张/6来源组并逐文件回看原分辨率；3张拼图/页面排版、4张明显像素化/失焦/压缩图、5张边缘裁断或仅局部露出甲面图和1张无美甲主体图排除，35张仅进入待标注候选，共278个完整可见甲面。分片001—015累计682张、357张待标注、325张排除，另484张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-016` | 质量分片016拼图、低清视频帧与残缺甲面源图硬门 | ✅ PASS | 11页覆盖43张/8来源组并逐文件回看原分辨率；2张拼图/嵌入截图、6张明显像素化/失焦/压缩视频帧和6张边缘截断或仅局部露出甲面图排除，29张仅进入待标注候选，共187个完整可见甲面。分片001—016累计725张、386张待标注、339张排除，另441张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-017` | 质量分片017拼贴页面与手绘模板源图硬门 | ✅ PASS | 11页覆盖42张/6来源组并逐文件回看原分辨率；29张多图拼贴/社交平台页面排版和10张手绘甲型设计模板排除，3张清晰单场景图仅进入待标注候选，共25个完整可见甲面。分片001—017累计767张、389张待标注、378张排除，另399张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-018` | 质量分片018拼贴页面与低质量源图硬门 | ✅ PASS | 12页覆盖46张/5来源组并逐文件回看原分辨率；31张拼图/社交平台页面排版和4张模糊或过曝图排除，11张清晰单场景图仅进入待标注候选，共62个完整可见甲面。分片001—018累计813张、400张待标注、413张排除，另353张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-019` | 质量分片019页面拼图、低清与局部甲面源图硬门 | ✅ PASS | 12页覆盖48张/8来源组并逐文件回看原分辨率；11张社交平台页面/拼图、4张失焦/像素化/压缩图和2张局部露出甲面图排除，31张清晰单场景图仅进入待标注候选，共179个完整可见甲面。分片001—019累计861张、431张待标注、430张排除，另305张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-020` | 质量分片020手绘模板、页面拼版与低清源图硬门 | ✅ PASS | 13页覆盖50张/8来源组并逐文件回看原分辨率；21张手绘模板、九宫格或社交平台海报和3张明显失焦/像素化/压缩图排除，26张清晰单场景图仅进入待标注候选，共145个完整可见甲面。分片001—020累计911张、457张待标注、454张排除，另255张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-021` | 质量分片021拼版、低清与残缺甲面源图硬门 | ✅ PASS | 12页覆盖48张/11来源组并逐文件回看原分辨率；23张拼版/社交平台海报/模板或教程页、3张失焦或破损甲局部、8张遮挡/截断/仅侧面甲面图排除，14张清晰完整单场景图仅进入待标注候选，共80个完整可见甲面。分片001—021累计959张、471张待标注、488张排除，另207张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-022` | 质量分片022甲片/产品页、拼图、低清与残缺甲面源图硬门 | ✅ PASS | 13页覆盖50张/7来源组并逐文件回看原分辨率；22张甲片展示、产品宣传页、多图拼贴或社交平台海报、3张明显像素化/失焦视频帧和9张边缘裁断/遮挡/仅局部甲面图排除，16张清晰完整单场景图仅进入待标注候选，共99个完整可见甲面。分片001—022累计1009张、487张待标注、522张排除，另157张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-023` | 质量分片023拼图/教程模板、独立甲片、低清与截甲源图硬门 | ✅ PASS | 12页覆盖48张/9来源组并逐文件回看原分辨率；19张拼图/教程模板/独立甲片展示、6张明显像素化/失焦/压缩视频帧和2张边缘截甲图排除，21张清晰完整单场景图仅进入待标注候选，共119个完整可见甲面。分片001—023累计1057张、508张待标注、549张排除，另109张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-024` | 质量分片024教程标注页、拼贴及低清视频帧源图硬门 | ✅ PASS | 12页覆盖45张/8来源组并逐文件回看原分辨率；5张手写教程标注页、1张十二宫格拼贴和4张明显像素化/失焦/拖影视频帧排除，35张清晰完整单场景图仅进入待标注候选，共217个完整可见甲面。分片001—024累计1102张、543张待标注、559张排除，另64张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-025` | 质量分片025非照片页面、低清及残缺甲面源图硬门 | ✅ PASS | 11页覆盖43张/12来源组并逐文件回看原分辨率；9张拼图/甲型模板/设计稿/独立甲片展示和12张低清、裁边、遮挡或仅局部甲面图排除，22张清晰完整单场景图仅进入待标注候选，共149个完整可见甲面。分片001—025累计1145张、565张待标注、580张排除，另21张待审；保留项继续`trainingUse=prohibited`、`annotationTruthStatus=not-started` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-026` | 最终质量分片多场景拼图源图硬门 | ✅ PASS | 6页覆盖21张/2来源组并逐文件查看原分辨率；21张全部为四宫格、九宫格或其他多场景拼接图，0张保留、21张排除。终结器21/21覆盖，决策清单SHA-256为`72314f1ef0b82b62f6fc8ea57da1b50405298794674e7c348b58840ed063a7ef`，终结报告SHA-256为`66db49f47e12f8af08cd7eb485eb518936d9089969af352eb3734541b05681a7` |
| `M2-T3-REAL-MATERIAL-SOURCE-SCREENING-COMPLETE` | 26分片源图筛选批次完整性与唯一覆盖终结门 | ✅ PASS | 新增批次终结器并复验26/26分片、1166/1166图片、193/193来源组、队列/分片/审核页/终结报告哈希及逐图身份；565张进入待标注候选、601张排除、0张待审。批次报告SHA-256为`901f52e531b5a93f4be9b010e2e96f585ca850bd733e5d9a4f5f9865a03335c0`；所有待标注项仍禁止训练且mask真值未开始 |
| `M2-T3-REAL-MATERIAL-FIRST-ANNOTATION-PLAN` | 首批来源组互斥角色分配与标注批次规划 | ✅ PASS | 新增确定性来源组原子规划器；565张候选分配为train 502、val 30、独立发布test 33，首批选择train中的160张/39来源组、预计966个完整甲面。互斥审计复验1271/1271授权条目和原图哈希，0来源泄漏；计划/CSV/审计SHA-256分别为`0dbf3a6cf99c455f3b8a8453223ef9df98eca3b16b919fa783dddd40a05dd912`、`dd11c24ba3bea9e479dd1fc4ee1a7dbbc681b7b7d7aa6ccaf7cc5c752d9e9dc4`、`11f76a240d832f8ca29d875d058146ab72aa0323d585392bdd07db4da769aa62`；mask真值仍未开始，全部继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-ANNOTATION-CANDIDATES` | 首批160张YOLO→SAM2候选工作区与几何审计 | ✅ PASS | 外部工作区绑定160张/39来源组、预计966甲面；v6生成881个YOLO候选，SAM2修复空提示边界后160/160完成、881 polygon、0错误、0 fallback。几何审计796 pass、85 suspect、0 missing；报告SHA-256为`91ce4e48461b233f1ebd239f2d1a8704c078a6f0f8272f13cda87539db158160`与`d58872e397e0a78b28aeb8b20ee01fce5e8e087438acfec0480368856ec61399`。该PASS只表示候选生成工程闭环，160张真值审核仍为0，全部禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-WORKSPACE` | 首批160张原分辨率mask审核工作区 | ✅ PASS | 绑定工作区/SAM/几何报告、逐图身份和SHA-256，按39个来源组原子形成10分片/83页，160张/966个预期甲面全覆盖；工作区报告SHA-256为`6c791e7992e61788f8a4815cb7e4d3c0e9edd11bf48d5562d02ebc6a8f7974c4`，导航页不替代原图审核 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-001` | 风险最高mask审核分片001 | ✅ PASS | 14/14张逐图原分辨率审核，1张/10 mask暂通过、13张返修、0排除；4张零候选的SAM2.1 large首轮视觉门0/4通过，未误提升。分片终结仅证明审核覆盖，全部继续禁止训练，暂通过项仍待拓扑与最终真值审计 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-002` | mask审核分片002 | ✅ PASS | 绑定CSV与7页哈希，13/13张逐图原分辨率审核为0直接通过、13返修；帽子文字误检、漏甲、透明延长甲局部覆盖及皮肤外溢均被拦截。累计初审27/160，剩余133张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-003` | mask审核分片003 | ✅ PASS | 绑定CSV SHA-256 `ad49dca0…ed45`与8页哈希，16/16张逐图原分辨率审核为0直接通过、13返修、3排除；三张边缘裁甲源图按硬门排除，漏甲、皮肤/手指/饰品/背景误标及重复候选均被拦截。累计初审43/160，剩余117张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-004` | mask审核分片004 | ✅ PASS | 绑定CSV SHA-256 `47c8c012…1903`与10页哈希，19/19张逐图原分辨率审核为0直接通过、19返修、0排除；漏甲、局部甲面、候选重复/交叠及手指、皮肤、饰品、衣物和背景污染均被拦截。终结报告SHA-256为`c27d0c1d…8b77`，累计初审62/160，剩余98张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-005` | mask审核分片005 | ✅ PASS | 绑定CSV SHA-256 `b6e8a4b3…6156`与5页哈希，9/9张逐图原分辨率审核为1直接通过、6返修、2排除；两张要求甲面被遮挡且仅局部露出的源图按硬门排除。终结报告SHA-256为`359564c8…ef44`，累计初审71/160，剩余89张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-006` | mask审核分片006 | ✅ PASS | 绑定CSV SHA-256 `66870edb…d36`与8页哈希，15/15张逐图原分辨率审核为4直接通过、11返修、0排除；漏甲、候选重复/交叠及头发、面部、手指和皮肤污染均被拦截，候选数相等的污染项也未误通过。终结报告SHA-256为`fd0bbbb7…0f19`，累计初审86/160，剩余74张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-007` | mask审核分片007 | ✅ PASS | 绑定CSV SHA-256 `0ac2192b…1d5`与10页哈希，20/20张逐图原分辨率审核为1直接通过、19返修、0排除；漏甲、重复/交叠、整段手指及眼睛/头发误检被拦截，4张等计数但甲缘缺口/皮肤污染项继续返修。终结报告SHA-256为`50da6fc3…06c4`，累计初审106/160，剩余54张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-008` | mask审核分片008 | ✅ PASS | 绑定CSV SHA-256 `2697b9df…3ea0`与9页哈希，18/18张逐图原分辨率审核为0直接通过、16返修、2排除；两张拇指甲仅露局部甲尖的源图按遮挡残缺硬门排除，漏甲、重复、首饰/绸布/头发误检及等计数甲缘缺口均被拦截。终结报告SHA-256为`34d88d24…188f`，累计初审124/160，剩余36张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-009` | mask审核分片009 | ✅ PASS | 绑定CSV SHA-256 `81b0a6dd…dd10`与10页哈希，19/19张原图和全分辨率overlay逐图审核为6直接通过、13返修、0排除；漏甲、候选重复/交叠及首饰、布料、眼睛、嘴唇、手指和皮肤误检均被拦截。决定清单SHA-256为`ee291680…1ede`，终结报告SHA-256为`b3d81bd0…2446`；累计初审143/160，剩余17张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REVIEW-SHARD-010` | mask审核分片010 | ✅ PASS | 绑定CSV SHA-256 `473e87b1…7ff2`与9页哈希，17/17张原图和全分辨率overlay逐图审核为2直接通过、15返修、0排除；UI按钮、汽车按键、戒指/手链、衣物和整块指腹误检，以及漏甲与误检抵消成等计数的样本均被拦截。决定清单SHA-256为`84730201…ddee`，终结报告SHA-256为`1937a3a9…4378`；首批160/160初审完成，累计15暂通过、138返修、7排除 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-FINALIZER` | 返修视觉证据终结器 | ✅ PASS | 新增哈希绑定终结器，复验初审rework身份、返修提示、SAM报告、几何、annotation、overlay和人工决定；PASS仍固定为候选并禁止训练，漂移拒绝专项通过 |
| `M2-T3-REAL-MATERIAL-FIRST-MANUAL-REPAIR-FINALIZER` | 人工多边形返修证据终结器 | ✅ PASS | 人工构建器写入候选禁训元数据；返修终结器新增互斥`--manual-report`并绑定报告/提示/几何/annotation/overlay/人工决定哈希，要求全部polygon合法且零交叠；专项确认仍不直接授予训练真值 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-001` | 首个训练真值候选 | ✅ PASS | `nail_01052…_9`删除2个帽子文字误检并以收紧多点提示补齐左右拇指，10/10几何、原分辨率视觉、polygon合法性和同图零交叠通过；批准为1张/10 mask训练真值候选，整批物化与来源隔离审计前仍禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-002` | 第二个训练真值候选 | ✅ PASS | `nail_00491…_2`保留4个逐甲提示并删除覆盖整段手指的第5号误检，SAM2.1 large输出4个polygon；几何4/4、原分辨率视觉、polygon合法性和同图零交叠通过。累计2张/14 mask，整批物化与来源隔离审计前仍禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-003` | 第三个训练真值候选 | ✅ PASS | 最终真值终结器新增哈希绑定的初审直接通过模式；`nail_01250…_9`的10/10完整mask经原分辨率视觉、分片身份、annotation哈希、polygon合法性和同图零交叠复验通过。累计3张/24 mask，整批物化与来源隔离审计前仍禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-004` | 第四个训练真值候选 | ✅ PASS | `nail_01241…_3`保留9个已审polygon并人工替换左侧拇指无效回折轮廓；10/10几何、原分辨率整图/局部视觉、polygon合法性和同图零交叠通过。累计4张/34 mask，整批物化与来源隔离审计前仍禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-005` | 第五个训练真值候选 | ✅ PASS | `nail_00188…_0`的5枚裸粉延长甲逐甲完整覆盖，原分辨率视觉、annotation哈希、polygon合法性和同图零交叠通过；真值报告SHA-256为`9b816ea5…1e31` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-006` | 第六个训练真值候选 | ✅ PASS | `nail_00192…_4`的3枚完整可见甲面逐甲完整覆盖，未把指腹或仅露边缘的甲尖误计；原分辨率视觉、合法性和同图零交叠通过，报告SHA-256为`2d155ad8…e441` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-007` | 第七个训练真值候选 | ✅ PASS | `nail_00201…_10`的5枚透明/立体装饰甲完整覆盖至透明甲尖，原分辨率视觉、合法性和同图零交叠通过；报告SHA-256为`53c8c6cc…374f` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-008` | 第八个训练真值候选 | ✅ PASS | `nail_00201…_13`的5枚裸粉延长甲逐甲覆盖甲根至透明甲尖，原分辨率视觉、合法性和同图零交叠通过；报告SHA-256为`4b98f90a…a7d6`。累计8张/52 mask，最低100张train正样本仍缺92张，整批物化与来源隔离前继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-009` | 第九个训练真值候选 | ✅ PASS | `nail_01222…_10`的5枚短方甲逐甲完整覆盖，原分辨率视觉、分片/annotation哈希、polygon合法性和同图零交叠通过；报告SHA-256为`beb3480c…578d`。累计9张/57 mask，最低100张train正样本仍缺91张，整批物化与来源隔离前继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-010` | 第十个训练真值候选 | ✅ PASS | `nail_00529…_2`初始5甲候选在最终真值预审中因第3个贝壳装饰甲polygon自交且漏甲根被拒绝；保留4个已审polygon并人工重绘第3甲完整外轮廓，整图与5个逐甲2×视觉、几何5/5、合法性和同图零交叠通过。真值报告SHA-256为`f8d2b8fc…95d1`，累计10张/62 mask，最低100张train正样本仍缺90张 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-011` | 第十一个训练真值候选 | ✅ PASS | `nail_00839…_2`的5枚完整甲面一甲一mask，侧视拇指甲根至可见甲尖连续覆盖；原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过，报告SHA-256为`13b2d442…e9eb` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-012` | 第十二个训练真值候选 | ✅ PASS | `nail_00838…_0`的5枚蓝黄渐变甲完整覆盖，原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过，报告SHA-256为`fb207f9f…0685` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-013` | 第十三个训练真值候选 | ✅ PASS | `nail_00842…_4`的5枚完整甲面一甲一mask，含侧视拇指且无甲缘缺口；原分辨率视觉、合法性和零交叠通过，报告SHA-256为`5b55c06e…8d9b` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-014` | 第十四个训练真值候选 | ✅ PASS | `nail_00843…_5`的5枚完整甲面逐甲覆盖，原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过，报告SHA-256为`6fc28890…d0db` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-015` | 第十五个训练真值候选 | ✅ PASS | `nail_00951…_0`的5枚完整甲面逐甲覆盖，未把装饰、皮肤或背景计入；原分辨率视觉、合法性和零交叠通过，报告SHA-256为`5740553f…fe20` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-016` | 第十六个训练真值候选 | ✅ PASS | `nail_00663…_2`的5枚完整甲面逐甲覆盖，原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过；报告SHA-256为`239835ec…ca3`。累计16张/92 mask，最低100张train正样本仍缺84张，整批物化与来源隔离前继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-017` | 第十七个训练真值候选 | ✅ PASS | `nail_00077…_2`的5枚短甲含透明星形拇指逐甲完整覆盖，原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过；报告SHA-256为`d9e64479…c098` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-018` | 第十八个训练真值候选 | ✅ PASS | `nail_00792…_0`的5枚金棕透明方甲含侧视拇指逐甲完整覆盖，原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过；报告SHA-256为`b24e33ce…8ce5`。累计18张/102 mask，最低100张train正样本仍缺82张，整批物化与来源隔离前继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-LOW-RISK-REPAIR-BATCH-001` | 首个低风险误检删除返修批次 | ✅ PASS | 分片010两张样本保留10个逐甲提示、删除戒指及方向盘控件/手链流苏3个非甲提示；SAM2.1 large完成2/2张、10/10提示、0 fallback，几何10 pass/0 suspect。原分辨率确认透明长甲尖、立体装饰可见区域和短甲甲缘完整，无皮肤/首饰/背景污染；提示、SAM与几何报告SHA-256分别为`b1bfcc5c…2268`、`ff1f98d3…40d7`和`6022a5c7…7392` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-019` | 第十九个训练真值候选 | ✅ PASS | `nail_00004…_7`的5枚透明长甲及附着立体装饰可见区域完整覆盖，戒指误检已删除；原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过，报告SHA-256为`b4ba3dbf…f03f` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-020` | 第二十个训练真值候选 | ✅ PASS | `nail_00078…_3`的5枚短甲完整覆盖，方向盘控件及手链流苏误检已删除；原分辨率视觉、哈希身份、polygon合法性和同图零交叠通过，报告SHA-256为`17173465…60e`。累计20张/112 mask，最低100张train正样本仍缺80张，整批物化与来源隔离前继续禁止训练 |
| `M2-T3-REAL-MATERIAL-FIRST-LOW-RISK-REPAIR-BATCH-002` | 第二批低风险返修 | ✅ PASS | 分片010三张样本通过SAM2.1 large重建20个逐甲候选，0 fallback、几何20 pass/0 suspect；删除整段手指重复候选、方向盘控件并补齐深色甲和星形拇指甲，原分辨率视觉、哈希身份、合法性与零交叠终审通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-021` | 第二十一个训练真值候选 | ✅ PASS | `nail_00005…_8`的10枚完整甲面一甲一mask，整段手指重复候选已删除；最终真值SHA-256为`faded755…34e7` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-022` | 第二十二个训练真值候选 | ✅ PASS | `nail_00075…_0`补齐棕色甲后5枚甲面完整，方向盘控件已删除；最终真值SHA-256为`55bf4d7f…ab22` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-023` | 第二十三个训练真值候选 | ✅ PASS | `nail_00637…_11`以紧框多点提示替换整段拇指候选，5枚甲面完整；最终真值SHA-256为`9dd6daeb…67ec` |
| `M2-T3-REAL-MATERIAL-FIRST-SIDE-THUMB-REPAIR-BATCH-003` | 三张侧视拇指返修 | ✅ PASS | 三张同系列图片分别保留四枚正面甲并以紧框、双正点、皮肤负点重建侧视拇指；SAM2.1 large完成3/3张、15/15提示、0 fallback，几何15 pass/0 suspect，原分辨率视觉与最终拓扑门全部通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-024` | 第二十四个训练真值候选 | ✅ PASS | `nail_00051…_0`五枚甲面完整、零非法polygon和零交叠；最终真值SHA-256为`e34500c6…4865` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-025` | 第二十五个训练真值候选 | ✅ PASS | `nail_00052…_2`五枚甲面完整、零非法polygon和零交叠；最终真值SHA-256为`1ba84e66…ba0f` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-026` | 第二十六个训练真值候选 | ✅ PASS | `nail_00054…_3`五枚甲面完整、零非法polygon和零交叠；最终真值SHA-256为`40182a0e…f55` |
| `M2-T3-SAM-GEOMETRY-EXACT-POLYGON-OVERLAP` | SAM提示几何精确polygon交集门 | ✅ PASS | 审计器保留外接框IoU诊断，但不再仅凭斜向相邻甲的外接框重叠定性；新增Shapely精确交集面积、非法拓扑拦截及两项回归。批次004确认`nail_00628…_2`相邻甲实际交叠10960.0713像素并继续返修，未放宽质量门 |
| `M2-T3-REAL-MATERIAL-FIRST-CLEANUP-REPAIR-BATCH-004` | 分片010清理返修批次004 | ✅ PASS | 三张/14提示SAM2.1 large均完成、0 fallback；原分辨率审核与精确几何门终结为2张通过、1张因相邻甲polygon实际交叠返修。通过项删除掌侧手指、整段手指、毛衣孔洞和布料误检，并补齐右侧横向侧甲 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-027` | 第二十七个训练真值候选 | ✅ PASS | `nail_00629…_3`四枚完整可见甲面逐甲覆盖，0非法polygon、0交叠；最终真值SHA-256为`4acda3a9…0ae` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-028` | 第二十八个训练真值候选 | ✅ PASS | `nail_00095…_2`五枚长甲完整覆盖至透明甲尖，补齐横向侧甲并清除布料误检，0非法polygon、0交叠；最终真值SHA-256为`cc81a8ef…9e3`。累计28张/156 mask，最低100张train正样本仍缺72张 |
| `M2-T3-REAL-MATERIAL-FIRST-MANUAL-OVERLAP-REPAIR-BATCH-005` | 00628相邻甲人工零交叠返修 | ✅ PASS | 保留4个已审完整polygon，以人工多边形替换合并相邻甲的第5甲候选；生成器先因0.0024像素交集拒绝，边界内收后5个polygon合法、同图0交叠，几何5 pass/0 suspect。整图和第4/5甲2×原分辨率视觉确认两甲各自完整覆盖可见甲面、无袖口污染 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-029` | 第二十九个训练真值候选 | ✅ PASS | `nail_00628…_2`五枚甲面通过人工返修终结、原分辨率视觉、合法性和同图零交叠终审；最终真值SHA-256为`ee09fecc…d414`。累计29张/161 mask，最低100张train正样本完成29%、仍缺71张 |
| `M2-T3-REAL-MATERIAL-FIRST-TEN-NAIL-REPAIR-BATCH-006` | 双手十甲复杂返修批次006 | ✅ PASS | `nail_00076…_1`保留6枚完整甲面候选，以紧框、多正点和邻近皮肤负点补齐4枚漏甲，删除整段手指与手链误检；SAM2.1 large完成1/1张、10/10提示、0 fallback，几何10 pass/0 suspect，原分辨率视觉确认10枚完整露出甲面逐甲完整且无污染 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-030` | 第三十个训练真值候选 | ✅ PASS | `nail_00076…_1`十枚甲面通过原分辨率视觉、哈希绑定、polygon合法性和同图零交叠终审；最终真值SHA-256为`9d0a5602…c8b1f`。累计30张/171 mask，最低100张train正样本完成30%、仍缺70张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-LOW-RISK-REPAIR-BATCH-007` | 分片009低风险返修批次007 | ✅ PASS | 三张/15提示、0 fallback，几何14 pass/1 suspect；珍珠链误检删除图通过，两张侧视拇指图未因总体高通过率放行，按原分辨率皮肤风险和提示中心不一致继续重试 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-SIDE-THUMB-RETRY-BATCH-008` | 分片009侧视拇指重试批次008 | ✅ PASS | 两张各保留四枚完整正面甲，收紧斜向拇指提示并强化皮肤负点；SAM2.1 large完成2/2张、10/10提示、0 fallback，几何10 pass/0 suspect，原分辨率确认侧视甲根至甲尖完整且无皮肤污染 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-031` | 第三十一个训练真值候选 | ✅ PASS | `nail_00542…_3`删除珍珠链误检后五甲完整，0非法polygon、0交叠；最终真值SHA-256为`9d707a18…be72` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-032` | 第三十二个训练真值候选 | ✅ PASS | `nail_00541…_2`补齐透明侧视拇指，五甲完整且无皮肤污染；最终真值SHA-256为`18252db0…2fbc` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-033` | 第三十三个训练真值候选 | ✅ PASS | `nail_00841…_3`补齐黄色侧视拇指，五甲完整、0非法polygon、0交叠；最终真值SHA-256为`a55ad552…d272`。累计33张/186 mask，最低100张train正样本完成33%、仍缺67张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-MISSING-NAIL-REPAIR-BATCH-009` | 分片009漏甲/重复分割返修批次009 | ✅ PASS | 四张/20提示、0 fallback、几何20 pass/0 suspect；原分辨率仅两张通过，两枚拇指因甲根皮肤污染继续返修。通过项补齐竖指透明延长甲，并把同一透明长甲的两个重叠局部候选重建为单一完整mask |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-THUMB-ROOT-RETRY-BATCH-010` | 分片009甲根皮肤重试批次010 | ✅ PASS | 两张/10提示、0 fallback、几何10 pass/0 suspect；收紧提示并加密甲根下缘皮肤负点后，横向长拇指甲完整通过，带立体装饰拇指仍有皮肤污染并继续返修 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-034` | 第三十四个训练真值候选 | ✅ PASS | `nail_01041…_2`补齐竖指透明延长甲，五甲完整、0非法polygon、0交叠；最终真值SHA-256为`eb607d29…7d03` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-035` | 第三十五个训练真值候选 | ✅ PASS | `nail_01177…_0`将同一透明长甲的两个重叠局部候选重建为单一完整mask；最终真值SHA-256为`b7409f8c…6e0b` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-036` | 第三十六个训练真值候选 | ✅ PASS | `nail_01179…_2`补齐横向长拇指甲且无甲根皮肤污染；最终真值SHA-256为`13ab302d…65ea3`。累计36张/201 mask，最低100张train正样本完成36%、仍缺64张 |
| `M2-T3-REAL-MATERIAL-FIRST-MULTI-SHARD-FALSE-POSITIVE-DROP-BATCH-011` | 跨分片明显误检删除批次011 | ✅ PASS | 三张/15提示使用SAM2.1 large完成、0 fallback，几何15 pass/0 suspect；原分辨率仅放行背景标识误检删除图与头发/背景误检删除图，透明甲图因右侧甲缘内缩和局部甲面缺失继续返修，未用几何通过替代视觉门 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-037` | 第三十七个训练真值候选 | ✅ PASS | `nail_01116…_3`删除背景标识误检后五枚长甲从甲根到甲尖完整覆盖；最终真值SHA-256为`f7781902…6663` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-038` | 第三十八个训练真值候选 | ✅ PASS | `nail_00180…_2`删除头发/背景误检后五枚粉色甲面完整、0非法polygon、0交叠；最终真值SHA-256为`291f9b77…dcd`。累计38张/211 mask，最低100张train正样本完成38%、仍缺62张 |
| `M2-T3-REAL-MATERIAL-FIRST-MULTI-SHARD-FALSE-POSITIVE-DROP-BATCH-012` | 跨分片误检删除批次012 | ✅ PASS | 三张/19提示、0 fallback，几何15 pass/4 suspect；原分辨率仅放行四枚裸色甲删除整段手指误检图。双手图暴露8甲候选、2个跨甲重复宽框和2枚漏甲，白色长甲图因立体装饰与透明边缘缺口继续返修 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-002-TEN-NAIL-THUMB-REPAIR-BATCH-013` | 分片002双手拇指补标重试批次013 | ✅ PASS | 删除帽子文字与跨甲重复宽框，以双正点、紧框和定向负点补两枚侧向拇指；SAM2.1 large完成1张/10提示、0 fallback，几何10 pass/0 suspect，但原分辨率确认两枚侧向拇指只露弯曲局部且mask吸收大块指腹，源图不进入训练真值 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-039` | 第三十九个训练真值候选 | ✅ PASS | `nail_00491…_2`删除整段手指误检后四枚低对比裸色甲完整；最终真值SHA-256为`1bea3750…aec0`。累计39张/215 mask |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-SINGLE-NAIL-DROP-BATCH-014` | 分片009单甲误检删除批次014 | ✅ PASS | 仅保留主体星形透明长甲，删除弯曲手指和非要求侧面区域候选；SAM2.1 large完成1张/1提示、0 fallback，几何1 pass/0 suspect，原分辨率确认甲根至透明甲尖完整且无污染 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-040` | 第四十个训练真值候选 | ✅ PASS | `nail_00539…_0`主体单甲通过哈希绑定、原分辨率视觉、polygon合法性和同图零交叠终审；最终真值SHA-256为`ca8118d9…25c3b`。累计40张/216 mask，最低100张train正样本完成40%、仍缺60张 |
| `M2-T3-REAL-MATERIAL-FIRST-MULTI-SHARD-MISSING-THUMB-SAM-BATCH-015-016` | 跨分片漏拇指SAM收紧重试 | ✅ PASS | 批次015三张/15提示完成、几何13 pass/2 suspect；批次016收紧两张提示后10 pass/0 suspect，但原分辨率确认新增mask仍带入甲根皮肤，三张均未因几何通过而晋级真值，第三张同时因相邻甲真实交叠保持返修 |
| `M2-T3-REAL-MATERIAL-FIRST-MULTI-SHARD-MISSING-THUMB-MANUAL-BATCH-017` | 两枚低对比拇指人工多边形返修 | ✅ PASS | 对两轮SAM仍吸收皮肤的两张图保留各4个已审完整polygon，仅按原图重绘缺失拇指甲；人工构建器输出2张/10 polygon、2个人工polygon、0非法、0交叠，几何10 pass/0 suspect，整图与逐甲2×原分辨率审核通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-041` | 第四十一个训练真值候选 | ✅ PASS | `nail_00201…_11`五枚完整甲面逐甲唯一覆盖，人工拇指轮廓贴合甲根、两侧甲缘及金色甲尖；最终真值SHA-256为`cfd9b665…969e` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-042` | 第四十二个训练真值候选 | ✅ PASS | `nail_00060…_0`五枚低对比裸粉银边甲完整、0非法polygon、0交叠；最终真值SHA-256为`e9a5258e…7de2`。累计42张/226 mask，最低100张train正样本完成42%、仍缺58张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-008-RIGHTMOST-NAIL-MANUAL-BATCH-018` | 分片008右侧甲根缺口人工返修 | ✅ PASS | 两张五甲齐全样本各保留4个已审完整polygon，仅替换右侧淡紫/白色渐变甲的甲根侧凹口轮廓；构建器输出2张/10 polygon、2个人工polygon、0非法、0交叠，几何10 pass/0 suspect，整图和逐甲2×原分辨率视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-043` | 第四十三个训练真值候选 | ✅ PASS | `nail_00530…_3`五枚甲面完整，人工淡紫甲补齐甲根侧缺口并覆盖至方形甲尖；最终真值SHA-256为`e7950324…aa23` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-044` | 第四十四个训练真值候选 | ✅ PASS | `nail_00534…_7`五枚甲面完整，人工白色渐变甲覆盖低对比甲根、两侧甲缘和方形甲尖；最终真值SHA-256为`b97d7289…1265`。累计44张/236 mask，最低100张train正样本完成44%、仍缺56张 |
| `M2-T3-REAL-MATERIAL-FIRST-ZERO-CANDIDATE-REPAIR-BATCH-019-023` | 分片001零候选SAM及人工多边形视觉拦截 | ✅ PASS | 00535与00538各按5枚完整露出甲面重建提示；SAM2.1 large完成2张/10提示、0 fallback，几何8 pass/2 suspect。原分辨率确认00535多处吸收皮肤且相邻甲交叠，00538透明低对比第3/4甲无法可靠区分甲面与指尖皮肤；批次020—023即使达到5个合法polygon、零交叠和几何5/5，也因视觉边界不可信而全部保持禁训，0张误晋级 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-UNIQUE-INDEX` | 训练真值唯一图片索引与重复报告门 | ✅ PASS | 新增唯一性审计，以`item.fileName`为图片唯一键；同图证据完全一致的重复报告只计一次，annotation或身份冲突则拒绝。当前63个批准报告中`00491…_2`由003与039重复登记且annotation SHA-256相同，选039为规范记录；另2个历史拒绝报告不计。权威索引为62张唯一图片/332 mask、1个冗余报告、0冲突，SHA-256为`50727dde…356d` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-045` | 第四十五个训练真值报告暨第四十四张唯一真值图片 | ✅ PASS | `nail_01119…_6`已在分片001完成双手10甲原分辨率审核；绑定分片、图片与annotation哈希后，10个完整mask全部polygon合法且同图零交叠。最终真值SHA-256为`687c8d61…3c5c`；按唯一图片索引累计44张/242 mask，最低100张train正样本完成44%、仍缺56张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-008-MISSING-SIDE-THUMB-BATCH-024-027` | 分片008侧视透明拇指SAM失败拦截与人工返修 | ✅ PASS | `nail_00527…_0`保留4枚现有甲面并用多点SAM补左上拇指，SAM 1张/5提示、0 fallback、几何5/5，但视觉发现新增mask吸收三角形指腹。转人工多边形后覆盖透明主体、绿色装饰和灰绿色甲尖，并人工平滑第1甲右侧皮肤凸起；最终5个polygon合法、零交叠、几何5/5，整图与逐甲2×通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-046` | 第四十六个训练真值报告暨第四十五张唯一真值图片 | ✅ PASS | `nail_00527…_0`五枚甲面完整，侧视透明绿色拇指从甲根到甲尖连续覆盖且无皮肤/背景污染；返修终结SHA-256为`dfdb7e46…1868b`，最终真值SHA-256为`5646b11c…901ec`。唯一索引累计45张/247 mask，最低100张train正样本完成45%、仍缺55张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-EYE-DROP-MISSING-PINKY-THUMB-BATCH-028-030` | 分片009眼睛误检删除、漏甲补齐与三甲人工收边 | ✅ PASS | `nail_00704…_3`首轮SAM删除眼睛误检并补左侧横向甲和右上拇指，1张/5提示、0 fallback、几何5/5，但视觉发现横向甲吸收整段手指。转人工多边形重画两枚漏/错甲并收紧中央亮片甲甲根皮肤凸起；最终5个polygon合法、零交叠、几何5/5，整图与逐甲2×通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-047` | 第四十七个训练真值报告暨第四十六张唯一真值图片 | ✅ PASS | `nail_00704…_3`删除人物眼睛误检，五枚粉色长甲从甲根至甲尖完整且无皮肤/面部/背景污染；返修终结SHA-256为`4b2b871c…3f7f`，最终真值SHA-256为`10ae8e37…fa14` |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-008-MISSING-THUMB-MANUAL-BATCH-031` | 分片008黄色甲漏拇指与相邻甲交叠人工返修 | ✅ PASS | `nail_00533…_6`此前SAM补左侧横向拇指时吸收皮肤并与上方黄甲交叠；保留3枚已审polygon，仅按原图重画两枚问题甲面。最终5个polygon合法、零交叠、几何5/5，整图和逐甲2×确认甲根、延长段、甲尖及装饰完整 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-048` | 第四十八个训练真值报告暨第四十七张唯一真值图片 | ✅ PASS | `nail_00533…_6`五枚黄色/裸色甲逐甲唯一完整覆盖；返修终结SHA-256为`acbdd080…79b4`，最终真值SHA-256为`ff901cb7…d59`。唯一索引累计47张/257 mask，最低100张train正样本完成47%、仍缺53张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-008-MISSING-THUMB-FABRIC-BATCH-032` | 分片008漏拇指与右侧横向甲毛衣污染人工返修 | ✅ PASS | `nail_00531…_4`保留中间3枚已审polygon，人工补左侧短拇指并重画右侧横向长甲，删除原候选吸收的大块毛衣；最终5个polygon合法、零交叠、几何5/5，整图与逐甲2×通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-049` | 第四十九个训练真值报告暨第四十八张唯一真值图片 | ✅ PASS | `nail_00531…_4`五枚粉色/裸色甲从甲根至甲尖完整且无皮肤/衣物污染；返修终结SHA-256为`f44ff0c7…fc01`，最终真值SHA-256为`9b8a129e…c769` |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-009-DECORATED-THUMB-BATCH-033-034` | 分片009立体装饰拇指、蝴蝶结甲和银粉方甲人工返修 | ✅ PASS | `nail_00951…_3`两轮SAM补拇指均吸收指腹而拒绝；保留3枚可信候选，人工重画侧视拇指和蝴蝶结甲，并在2×复核后修正银粉方甲右下甲缘缺口。最终5个polygon合法、零交叠、几何5/5，视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-050` | 第五十个训练真值报告暨第四十九张唯一真值图片 | ✅ PASS | `nail_00951…_3`五枚裸粉/银粉甲完整，无指腹、衣物或背景污染；返修终结SHA-256为`c1f0808d…b5d3`，最终真值SHA-256为`8c291c2c…63ea`。唯一索引累计49张/267 mask，最低100张train正样本完成49%、仍缺51张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-ROOT-EDGE-BATCH-035-036` | 分片007同源三图甲根缺口、锯齿与皮肤外刺人工返修 | ✅ PASS | `nail_00274…_0`、`nail_00276…_2`、`nail_00278…_4`首轮只修初审点名甲面后，逐甲2×继续发现其余保留候选的细小缺口/外刺，未提前终结；第二轮对12枚问题甲面按原图重画，仅保留3枚已放大复核polygon。最终3张/15 polygon合法、零交叠，几何15/15，整图与逐甲2×通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-051` | 第五十一个训练真值报告暨第五十张唯一真值图片 | ✅ PASS | `nail_00274…_0`五枚裸粉/奶牛纹甲面逐甲完整，无甲根缺口、皮肤外刺、背景或重复污染；返修终结SHA-256为`a95957fa…e9b1`，最终真值SHA-256为`662d5bed…eea0` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-052` | 第五十二个训练真值报告暨第五十一张唯一真值图片 | ✅ PASS | `nail_00276…_2`五枚甲面覆盖甲根、两侧甲缘与可见甲尖，侧甲及拇指轮廓平滑且无皮肤污染；返修终结SHA-256为`5acd20ce…d614`，最终真值SHA-256为`06ce0bf0…1a73` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-053` | 第五十三个训练真值报告暨第五十二张唯一真值图片 | ✅ PASS | `nail_00278…_4`五枚甲面逐甲唯一完整覆盖，右侧甲及拇指外刺已清除；返修终结SHA-256为`7e534d07…7041`，最终真值SHA-256为`b9443182…47a1`。唯一索引累计52张/282 mask、1冗余、0冲突，最低100张train正样本完成52%、仍缺48张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-MISSING-TWO-NAILS-BATCH-037-038` | 分片007同源三候选图漏甲、整段手指污染与甲尖补齐人工返修 | ✅ PASS | `nail_00277…_3`初始仅3候选且两枚吸收整段手指，五甲全部按原图重画；构建器对相邻甲88.2237像素交叠保持拒绝，分离后逐甲2×再补齐左侧侧甲和右上奶牛纹甲可见甲尖。最终5个polygon合法、零交叠、几何5/5，整图与逐甲局部通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-054` | 第五十四个训练真值报告暨第五十三张唯一真值图片 | ✅ PASS | `nail_00277…_3`五枚裸粉/奶牛纹甲完整覆盖，无整段手指、皮肤、背景、重复或交叠污染；返修终结SHA-256为`1c5ba1ab…d551`，最终真值SHA-256为`81ce29df…31b5`。唯一索引累计53张/287 mask、1冗余、0冲突，最低100张train正样本完成53%、仍缺47张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-CROPPED-NAIL-EXCLUSION-00476` | 分片007同源图00476裁边排除 | ✅ PASS | 原分辨率复核确认左侧拇指甲被图像边缘裁断，纠正旧分片“5甲完整可见”的判断；整张源图及派生候选不生成训练真值，不以补mask绕过源图硬门 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-MISSING-NAILS-BATCH-039-040` | 分片007同源00478/00482漏甲与边缘完整性人工返修 | ✅ PASS | 批次039补齐3枚漏甲后，逐甲2×发现旧候选仍有根部锯齿、侧缘尖刺和透明甲尖漏标；批次040仅保留3枚已审人工polygon并重画其余7枚。最终2张/10 polygon合法、零交叠、几何10/10，整图与10组逐甲局部通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-055` | 第五十五个训练真值报告暨第五十四张唯一真值图片 | ✅ PASS | `nail_00478…_2`五枚灰粉/亮片长甲完整覆盖至可见透明甲尖，无皮肤、衣物或背景污染；返修终结SHA-256为`6469ebc7…d417`，最终真值SHA-256为`5a0702ee…b58b` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-056` | 第五十六个训练真值报告暨第五十五张唯一真值图片 | ✅ PASS | `nail_00482…_6`五枚灰粉/亮片长甲逐甲唯一完整覆盖，无根部凹口、重复或交叠污染；返修终结SHA-256为`a91a8857…12ba`，最终真值SHA-256为`32f73303…3974`。唯一索引累计55张/297 mask、1冗余、0冲突，最低100张train正样本完成55%、仍缺45张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-PARTIAL-NAIL-EXCLUSION-00479` | 分片007同源图00479局部甲尖排除 | ✅ PASS | 原分辨率确认竖指仅露侧向局部甲尖，完整甲面不可见；整张源图及派生候选不进入训练，不因其余四甲清晰而绕过完整性门 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01217-BATCH-041` | 分片007同源01217漏甲与首饰污染人工返修 | ✅ PASS | 初始仅3候选且1个吸收戒指和邻近区域，五枚渐变长甲全部按原图人工重画；5 polygon合法、零交叠、几何5/5，整图与逐甲2×确认甲根、甲缘和蓝色甲尖完整 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-057` | 第五十七个训练真值报告暨第五十六张唯一真值图片 | ✅ PASS | `nail_01217…_4`五枚渐变长甲完整，无首饰、皮肤、背景、重复或交叠污染；返修终结SHA-256为`bb09aa3e…b2ed`，最终真值SHA-256为`4b2f67a4…68b5` |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01218-BATCH-042` | 分片007同源01218重复交叠人工返修 | ✅ PASS | 旧候选存在同甲重复、交叠和皮肤污染，五枚薄荷绿金粉长甲全部重画；5 polygon合法、零交叠、几何5/5，整图与逐甲2×视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-058` | 第五十八个训练真值报告暨第五十七张唯一真值图片 | ✅ PASS | `nail_01218…_5`五枚薄荷绿金粉长甲逐甲完整覆盖；返修终结SHA-256为`51334233…f49f`，最终真值SHA-256为`4f11e483…bd8f` |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01220-BATCH-043-044` | 分片007同源01220基础甲片与外凸装饰双轮人工返修 | ✅ PASS | 首轮五甲重画后，逐甲2×发现3枚金粉甲漏掉甲缘外凸立体装饰；第二轮保留2枚已审polygon并替换3枚问题甲。最终5 polygon合法、零交叠、几何5/5，全部可见金粉颗粒纳入mask |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-059` | 第五十九个训练真值报告暨第五十八张唯一真值图片 | ✅ PASS | `nail_01220…_7`五枚裸粉金粉长甲覆盖基础甲面及甲缘外凸装饰，无皮肤、首饰、背景、重复或交叠污染；返修终结SHA-256为`ea38267a…d560`，最终真值SHA-256为`16bab6f6…3c5c`。唯一索引累计58张/312 mask、1冗余、0冲突，最低100张train正样本完成58%、仍缺42张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01216-01219-01221-BATCH-045-046` | 分片007同源三图去重、指腹污染清除与甲根边缘重画 | ✅ PASS | 批次045先删除`01216/01221`重复候选并重画`01219`吸收大块指腹的拇指；几何15/15后，逐甲2×仍发现前两图旧候选存在甲根凹口，故批次046将其10甲全部人工重画。最终3张/15 polygon合法、同图零交叠、几何15/15，整图及逐甲局部视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-060` | 第六十个训练真值报告暨第五十九张唯一真值图片 | ✅ PASS | `nail_01216…_3`五枚渐变长甲由平滑人工polygon完整覆盖；返修终结SHA-256为`06058354…73f8`，最终真值SHA-256为`1a89e093…c1c1` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-061` | 第六十一个训练真值报告暨第六十张唯一真值图片 | ✅ PASS | `nail_01219…_6`保留4枚完整候选并重画拇指，五甲无指腹、戒指或衣物污染；返修终结SHA-256为`21eac83b…1a34`，最终真值SHA-256为`0e613a88…1562` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-062` | 第六十二个训练真值报告暨第六十一张唯一真值图片 | ✅ PASS | `nail_01221…_8`五枚银色渐变长甲由平滑人工polygon完整覆盖；返修终结SHA-256为`b6d6285b…0b4d`，最终真值SHA-256为`2e1f9b5e…804d`。唯一索引累计61张/327 mask、1冗余、0冲突，最低100张train正样本完成61%、仍缺39张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01215-BATCH-047-049` | 分片007同源01215漏拇指、戒指污染与甲根尖刺三轮返修 | ✅ PASS | 批次047补横向拇指并删除大块指腹候选；逐甲2×发现食指吸收戒指、无名指和小指有甲根尖刺，批次048重画三甲；食指甲尖仍含下方戒指反光，批次049再次收紧。最终1张/5 polygon合法、零交叠、几何5/5，整图和逐甲局部通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-063` | 第六十三个训练真值报告暨第六十二张唯一真值图片 | ✅ PASS | `nail_01215…_2`五枚裸色长甲逐甲完整覆盖，无戒指、指腹、衣物、重复或交叠污染；返修终结SHA-256为`c1efc355…fe92`，最终真值SHA-256为`f5750757…2ed1`。唯一索引累计62张/332 mask、1冗余、0冲突，最低100张train正样本完成62%、仍缺38张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-01213-01222-BATCH-050-051` | 分片007同源01213/01222_9整指污染清除与饰品边缘返修 | ✅ PASS | 两张源图均有5枚清晰完整甲面；批次050保留3枚逐甲完整候选并人工重画其余7枚，逐甲2×发现`01222…_9`第4甲面漏掉左侧甲面附着立体饰品后，批次051仅替换该甲。最终2张/10 polygon合法、同图零交叠，采用终版批次的几何审计均为5/5，整图与逐甲局部视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-064` | 第六十四个训练真值报告暨第六十三张唯一真值图片 | ✅ PASS | `nail_01213…_0`五枚蓝灰渐变长甲逐甲完整覆盖，无整指、皮肤、衣物、重复或交叠污染；返修终结SHA-256为`ac80f0ab…886a`，最终真值SHA-256为`c87d8670…a698` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-065` | 第六十五个训练真值报告暨第六十四张唯一真值图片 | ✅ PASS | `nail_01222…_9`五枚透明尖形装饰长甲完整覆盖甲根、甲缘、甲尖及与甲面相连的饰品外轮廓；返修终结SHA-256为`507aadcc…c11b`，最终真值SHA-256为`18e36cc8…b3b`。唯一索引累计64张/342 mask、1冗余、0冲突，最低100张train正样本完成64%、仍缺36张 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-00965-SOURCE-EXCLUSION` | 分片007同源00965遮挡甲面源图排除 | ✅ PASS | 原分辨率确认至少一枚应标甲面被相邻手指遮挡、仅露局部甲尖/装饰区，无法恢复完整甲面；哈希绑定排除记录SHA-256为`91629e0f…4663`，整张保持`trainingUse=prohibited`，不以人工多边形猜测遮挡区域 |
| `M2-T3-REAL-MATERIAL-FIRST-SHARD-007-00967-BATCH-052-053` | 分片007同源00967眼睛/头发误检清除与双甲人工返修 | ✅ PASS | 批次052保留4个旧候选并重画右侧银粉甲；逐甲2×发现第1项实际覆盖指间头发/阴影、第5项仍吸收指腹，批次053仅保留中间3甲，重画左侧粉黑蝴蝶结甲和右侧银粉甲。构建器曾拦截非法polygon和7.4510像素交叠，修正后5 polygon合法、零交叠、几何5/5，整图和逐甲视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-066` | 第六十六个训练真值报告暨第六十五张唯一真值图片 | ✅ PASS | `nail_00967…_2`五枚长甲逐甲完整覆盖甲根、甲缘、甲尖及甲面附着蝴蝶结，无眼睛、头发、手指、皮肤、衣物、重复或交叠污染；返修终结SHA-256为`7a163fe3…e604`，最终真值SHA-256为`1bf8f509…021e`。唯一索引累计65张/347 mask、1冗余、0冲突，最低100张train正样本完成65%、仍缺35张 |
| `M2-T3-REAL-MATERIAL-FIRST-MULTI-SHARD-BATCH-054-055` | 跨分片00495/01268/00227透明边缘与相邻甲交叠返修 | ✅ PASS | 首轮放大复核拒绝甲根尖刺/皮肤污染、透明甲尖遗漏及相邻灰色星纹甲/深蓝甲12.9567像素交叠；批次055以10个人工多边形和5个已审polygon重建，最终3张/15 polygon合法、同图零交叠、几何15 pass/0 suspect/0 missing，整图和逐甲2×视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-067` | 第六十七个训练真值报告暨第六十六张唯一真值图片 | ✅ PASS | `nail_00495…_6`五枚裸色珠光甲完整覆盖甲根、甲缘、透明甲尖及侧视拇指甲面；返修终结SHA-256为`8b0aedbe…a5fa`，最终真值SHA-256为`f00edc75…4946` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-068` | 第六十八个训练真值报告暨第六十七张唯一真值图片 | ✅ PASS | `nail_01268…_6`五枚灰蓝/乳白/棕色甲面完整覆盖并按真实遮挡边界分离相邻两甲；返修终结SHA-256为`61c603f7…36e4`，最终真值SHA-256为`4ebfc939…a29f` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-069` | 第六十九个训练真值报告暨第六十八张唯一真值图片 | ✅ PASS | `nail_00227…_2`五枚银色、透明和裸色延长甲完整覆盖透明甲尖、甲根及链钻装饰；返修终结SHA-256为`7620ad52…8890`，最终真值SHA-256为`d9d8c8c8…92f7`。唯一索引累计68张/362 mask、1冗余、0冲突，最低100张train正样本完成68%、仍缺32张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-056` | 跨分片透明甲缘、反光缺口与误检清理 | ✅ PASS | `00229/00193/00496`共15枚甲全部改为人工多边形，删除手指关节、戒指和织物误检；3张/15 polygon合法、同图零交叠、几何15/15，整图与逐甲2×原分辨率审核通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-070` | 第七十个训练真值报告暨第六十九张唯一真值图片 | ✅ PASS | `nail_00229…_4`五枚透明延长甲完整覆盖甲根、甲缘、透明甲尖和立体装饰；返修终结SHA-256为`6186d161…d244`，最终真值SHA-256为`252eb5b7…f06` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-071` | 第七十一个训练真值报告暨第七十张唯一真值图片 | ✅ PASS | `nail_00193…_5`清除皮肤外溢、反光缺口和拇指甲右侧污染，五枚甲逐甲完整；返修终结SHA-256为`4bb2aa3a…ac15`，最终真值SHA-256为`64014673…492` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-072` | 第七十二个训练真值报告暨第七十一张唯一真值图片 | ✅ PASS | `nail_00496…_7`删除关节/戒指/织物误检并完整重画五枚裸色花饰甲；返修终结SHA-256为`eb42ab7b…60bb`，最终真值SHA-256为`8d96bc00…cb21`。唯一索引累计71张/377 mask、1冗余、0冲突，最低100张train正样本完成71%、仍缺29张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-057` | 跨分片清晰五甲侧视边界与误检清理 | ✅ PASS | `00902/00196/00661`共15枚甲全部人工重画，删除重复候选、圆形背景、衣袖和整段手指误检；按真实甲根/侧视边界清除指腹污染后，3张/15 polygon合法、零交叠、几何15/15，整图与逐甲2×审核通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-073` | 第七十三个训练真值报告暨第七十二张唯一真值图片 | ✅ PASS | `nail_00902…_4`五枚蓝绿蝴蝶甲完整覆盖并删除重复透明甲及圆形背景误检；返修终结SHA-256为`7328d6b5…cf90`，最终真值SHA-256为`8512b630…9be9` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-074` | 第七十四个训练真值报告暨第七十三张唯一真值图片 | ✅ PASS | `nail_00196…_8`五枚粉色长甲和立体花饰完整，甲根皮肤已按真实曲线清除；返修终结SHA-256为`f750efa5…7796`，最终真值SHA-256为`be4d1a0a…6dc8` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-075` | 第七十五个训练真值报告暨第七十四张唯一真值图片 | ✅ PASS | `nail_00661…_0`删除衣袖/整指误检并重画侧视拇指及灰蓝渐变甲；返修终结SHA-256为`1970a7d8…ff52`，最终真值SHA-256为`22c03d74…107c`。唯一索引累计74张/392 mask、1冗余、0冲突，最低100张train正样本完成74%、仍缺26张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-058` | 跨分片透明长甲、蝴蝶结甲与自然甲边界返修 | ✅ PASS | `00531/00301/00489`共15枚甲经整图和逐甲2×多轮复核；删除白色绸布误检，补齐蝴蝶结甲和透明甲尖，并把自然甲收紧到真实甲沟、甲根和游离缘。最终3张/15 polygon合法、零交叠、几何15/15 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-076` | 第七十六个训练真值报告暨第七十五张唯一真值图片 | ✅ PASS | `nail_00531…_5`删除绸布误检并完整重画三枚透明长甲；返修终结SHA-256为`72933f14…a3d3`，最终真值SHA-256为`d212a959…e1aa` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-077` | 第七十七个训练真值报告暨第七十六张唯一真值图片 | ✅ PASS | `nail_00301…_8`补齐完整蝴蝶结甲并分离相邻两甲，五枚甲面无皮肤、背景、重复或交叠污染；返修终结SHA-256为`e06f91b1…c6af`，最终真值SHA-256为`174e3f19…5b7` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-078` | 第七十八个训练真值报告暨第七十七张唯一真值图片 | ✅ PASS | `nail_00489…_0`五枚自然甲按真实甲沟、甲根和透明游离缘重画，侧视拇指无指腹污染；返修终结SHA-256为`6c07716b…2c40`，最终真值SHA-256为`b96b894e…5112`。唯一索引累计77张/407 mask、1冗余、0冲突，最低100张train正样本仍缺23张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-059` | 清晰长甲头发/猫毛背景误检与漏甲返修 | ✅ PASS | `00194/00906`共9枚完整可见甲面全部人工重画；原分辨率视觉门拦截首轮蝶形透明长甲根部遗漏及三枚宽框皮肤/猫毛污染，返修后2张/9 polygon合法、零交叠、几何9/9，整图和逐甲2×复核通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-079` | 第七十九个训练真值报告暨第七十八张唯一真值图片 | ✅ PASS | `nail_00194…_7`移除头发误检并完整重画五枚绿色长甲；返修终结SHA-256为`e57217c3…f199`，最终真值SHA-256为`c12cd939…1eac` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-080` | 第八十个训练真值报告暨第七十九张唯一真值图片 | ✅ PASS | `nail_00906…_8`补齐两枚蝶形透明甲和两枚深色甲，透明甲从甲根到自由缘完整且无猫毛/皮肤污染；返修终结SHA-256为`35f01f70…1ddb`，最终真值SHA-256为`2371f289…2bd7`。唯一索引累计79张/416 mask、1冗余、0冲突，SHA-256为`6e4dadf9…378d`；最低100张train正样本完成79%、仍缺21张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-060` | `00183/00201`清晰五甲原分辨率人工多边形返修 | ✅ PASS | 两图10枚完整可见甲面为7个已审polygon+3个人工polygon；侧视拇指白色立体装饰纳入完整甲面轮廓，10/10 polygon合法、零交叠、几何10 pass/0 suspect/0 missing，整图与逐甲2×视觉通过 |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-081` | 第八十一个训练真值报告暨第八十张唯一真值图片 | ✅ PASS | `nail_00183…_5`五枚完整甲面一甲一mask，无漏甲、重复、交叠或背景污染；返修/真值SHA-256为`a7821305…15aa`/`b34c4d96…20ea` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-082` | 第八十二个训练真值报告暨第八十一张唯一真值图片 | ✅ PASS | `nail_00201…_9`四枚正视延长甲与一枚侧视装饰拇指甲均完整；返修/真值SHA-256为`d9734c65…cdc5`/`826831f7…3da8`。唯一索引累计81张/426 mask、1冗余、0冲突，SHA-256为`48d5ea4b…ed48`；最低100张train正样本完成81%、仍缺19张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-061` | `00719/01115`清晰五甲混合多边形返修 | ✅ PASS | 两图10枚完整可见长甲以8个已审SAM polygon和2个人工polygon重建；原分辨率整图与逐甲2×复核收紧`00719`第5甲甲根和`01115`第3甲暗色背景外扩，最终10/10 polygon合法、零交叠、几何10 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-083` | 第八十三个训练真值报告暨第八十二张唯一真值图片 | ✅ PASS | `nail_00719…_0`五枚绿色长甲从甲根、两侧甲缘到甲尖完整且无衣物/背景污染；返修/真值SHA-256为`e9bc325d…2960`/`990dbba8…06f9` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-084` | 第八十四个训练真值报告暨第八十三张唯一真值图片 | ✅ PASS | `nail_01115…_2`五枚透明低对比延长甲完整，返修长甲无暗色背景外扩；返修/真值SHA-256为`97c16351…f313`/`07e0e9e9…7e9f`。唯一索引累计83张/436 mask、1冗余、0冲突，SHA-256为`a2942ab0…2d2`；最低100张train正样本完成83%、仍缺17张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-062` | `00722/00723/01118`透明甲与玩偶背景混合人工返修 | ✅ PASS | 两轮SAM多点候选仍吸收衣带、皮肤、玩偶绒毛或眼睛后切换原分辨率人工多边形；终版13个人工polygon与2个已审SAM polygon覆盖3图15枚完整甲面，15/15 polygon合法、零交叠、几何15 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-085` | 第八十五个训练真值报告暨第八十四张唯一真值图片 | ✅ PASS | `nail_00722…_3`五枚完整可见裸粉/装饰长甲均覆盖甲根、甲缘与完整甲尖；返修/真值SHA-256为`ff2bdb04…c63e`/`81baeaff…0cb` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-086` | 第八十六个训练真值报告暨第八十五张唯一真值图片 | ✅ PASS | `nail_00723…_4`五枚完整可见长甲无衣带、皮肤或重复甲面污染；返修/真值SHA-256为`be037c5d…c618`/`7ebe092f…19f8` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-087` | 第八十七个训练真值报告暨第八十六张唯一真值图片 | ✅ PASS | `nail_01118…_5`五枚宝石/银色延长甲完整，玩偶眼睛、绒毛与相邻甲面污染清除；返修/真值SHA-256为`134a1cd7…f389`/`c5bf14a7…369f`。唯一索引累计86张/451 mask、1冗余、0冲突，SHA-256为`300ef9ea…28a2`；最低100张train正样本完成86%、仍缺14张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-063` | `00225/00916/00713`透明甲、格纹雪花甲与银粉延长甲返修 | ✅ PASS | SAM计数15/15但原分辨率视觉仍拦截整指、皮肤、装饰分裂和背景污染；终版11个人工polygon+4个已审SAM polygon覆盖3图15枚完整甲面，15/15 polygon合法、零交叠、几何15 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-088` | 第八十八个训练真值报告暨第八十七张唯一真值图片 | ✅ PASS | `nail_00225…_0`五枚透明裸粉长甲覆盖甲根、两侧甲缘、透明甲尖和立体装饰；返修/真值SHA-256为`cba0b81c…9156`/`dcba46dc…5729` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-089` | 第八十九个训练真值报告暨第八十八张唯一真值图片 | ✅ PASS | `nail_00916…_2`竖直食指、横向拇指、格纹甲、雪花甲和立体花饰完整，无整指或皮肤污染；返修/真值SHA-256为`53909584…9811`/`b8e342c8…4a40` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-090` | 第九十个训练真值报告暨第八十九张唯一真值图片 | ✅ PASS | `nail_00713…_6`五枚银粉裸色延长甲均覆盖完整甲根、甲缘、装饰区和甲尖；返修/真值SHA-256为`0989b27a…58e4`/`b1028bc1…dd2`。唯一索引累计89张/466 mask、1冗余、0冲突，SHA-256为`7f06410c…16b6`；最低100张train正样本完成89%、仍缺11张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-064` | `00476/00712/00291`灰粉亮片、透明银粉与水钻长甲混合返修 | ✅ PASS | 首轮15个SAM候选经原分辨率整图与逐甲2×视觉门拦截金属碎片、衣物、皮肤、邻指和装饰交叠；`00291`收紧重试后仍有污染/75.9302像素交叠，终版以9个已审SAM polygon+6个人工polygon覆盖3图15枚完整甲面，15/15 polygon合法、零交叠、几何15 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-091` | 第九十一个训练真值报告暨第九十张唯一真值图片 | ✅ PASS | `nail_00476…_0`五枚灰粉贝壳亮片甲完整，拇指金属碎片和中指甲根细小支路已清除；返修/真值SHA-256为`6e60e5c6…70ba`/`e5e8d7ac…5b6b` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-092` | 第九十二个训练真值报告暨第九十一张唯一真值图片 | ✅ PASS | `nail_00712…_5`五枚粉白银粉延长甲覆盖透明拇指甲尖、甲根和完整自由缘，无衣物或背景支路；返修/真值SHA-256为`bd70072f…691b`/`d99e3c7a…2926` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-093` | 第九十三个训练真值报告暨第九十二张唯一真值图片 | ✅ PASS | `nail_00291…_2`五枚银灰水钻长甲的甲根、甲身、甲尖和立体装饰均完整且无邻指交叠；返修/真值SHA-256为`98a34ec9…155c`/`136ece68…2174`。唯一索引累计92张/481 mask、1冗余、0冲突，SHA-256为`a9d5936a…2246`；最低100张train正样本完成92%、仍缺8张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-065` | `00293/00711/00292`裸粉金粉、水钻粉甲与透明亮片长甲混合返修 | ✅ PASS | `00915`两轮SAM仍合并手指/手掌后留在返修队列，改选`00292`；终版以6个逐甲审核通过的SAM polygon和9个人工polygon覆盖3图15枚完整甲面。第二轮视觉门继续修正`00293`拇指皮肤、`00711`第4甲漏尖和`00292`拇指衣物轮廓，15/15 polygon合法、零交叠、几何15 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-094` | 第九十四个训练真值报告暨第九十三张唯一真值图片 | ✅ PASS | `nail_00293…_4`五枚裸粉、金粉与透明水钻延长甲完整，横向拇指甲根皮肤和相邻第4/5甲交叠清除；返修/真值SHA-256为`b82e94b7…5f97`/`bc11ac78…9440` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-095` | 第九十五个训练真值报告暨第九十四张唯一真值图片 | ✅ PASS | `nail_00711…_4`五枚透明、粉色水钻及银灰亮片长甲覆盖完整甲根、甲身与甲尖，银灰第4甲漏尖已补齐；返修/真值SHA-256为`acdac8ea…4dac`/`e2d84076…e64c` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-096` | 第九十六个训练真值报告暨第九十五张唯一真值图片 | ✅ PASS | `nail_00292…_3`五枚透明裸粉亮片和水钻长甲完整，衣物、戒指、皮肤及相邻装饰污染清除；返修/真值SHA-256为`96b02ea7…0537d`/`c4854173…34d7`。唯一索引累计95张/496 mask、1冗余、0冲突，SHA-256为`12e3d613…3510`；最低100张train正样本完成95%、仍缺5张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-066` | `00294/00914/01262`黑白水钻、粉白立体装饰与灰银黑纹理甲返修 | ✅ PASS | SAM完成3图/15提示但仅7 pass/8 suspect，原分辨率视觉拦截整指、皮肤、背景及错误指腹；终版15个人工polygon覆盖3图15枚完整甲面，逐甲2×确认侧视装饰、链钻、雪花和完整甲尖，15/15 polygon合法、零交叠、几何15 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-097` | 第九十七个训练真值报告暨第九十六张唯一真值图片 | ✅ PASS | `nail_00294…_5`五枚黑白水钻延长甲完整，横向拇指与食指可见遮挡边界分离；返修/真值SHA-256为`dd4d52e5…5965`/`569b24c9…e570` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-098` | 第九十八个训练真值报告暨第九十七张唯一真值图片 | ✅ PASS | `nail_00914…_0`侧视立体装饰、透明亮片、蝴蝶结、格纹链钻和雪花甲完整，误落指腹候选已替换；返修/真值SHA-256为`bc6e3295…a2c6`/`6c77feb9…be33` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-099` | 第九十九个训练真值报告暨第九十八张唯一真值图片 | ✅ PASS | `nail_01262…_0`五枚灰银黑纹理甲完整，背景碎片、皮肤外刺和甲根锯齿清除；返修/真值SHA-256为`0168a2d8…1a1`/`49ebc05a…6444`。唯一索引累计98张/511 mask、1冗余、0冲突，SHA-256为`35f437d5…937e`；最低100张train正样本完成98%、仍缺2张 |
| `M2-T3-REAL-MATERIAL-FIRST-MASK-REPAIR-BATCH-067` | `00538/00301`白色珍珠花饰甲与低对比裸色水钻甲返修 | ✅ PASS | `01113`因仅4枚人类甲面完整可见而排除；SAM2.1 large完成2图/10提示、1 fallback，但仅3 pass/7 suspect且视觉门发现整指、皮肤、衣物和背景污染。终版10个人工polygon经逐甲2×补齐花饰、透明甲尖和水钻边缘；一次38.5285像素交叠被构建器拦截并纠正，10/10 polygon合法、零交叠、几何10 pass/0 suspect/0 missing |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-100` | 第一百个训练真值报告暨第九十九张唯一真值图片 | ✅ PASS | `nail_00538…_3`五枚白色珍珠、透明水钻与立体花饰甲完整，花饰凹边黑色背景月牙已清除；返修/真值SHA-256为`31b20b81…b414`/`4016ecb6…58b7` |
| `M2-T3-REAL-MATERIAL-FIRST-TRAINING-TRUTH-101` | 第一百零一个训练真值报告暨第一百张唯一真值图片 | ✅ PASS | `nail_00301…_11`五枚低对比裸色珍珠与透明甲完整，甲尖水钻在零交叠约束下补齐；返修/真值SHA-256为`d585525d…61f2`/`ae846132…2006`。唯一索引累计100张/521 mask、1冗余、0冲突，SHA-256为`13f606b5…f125`；最低100张train正样本门已达到，val、hard negative及物化隔离门仍未完成 |
| `M2-T4-INPUT-SIZE` | 用 FP32 基线评估输入尺寸 | ✅ PASS | 640 基线 box/mask mAP50=0.522/0.454；512=0.524/0.468，通过 0.02 退化门禁；384=0.475/0.438，box 退化 0.046，被门禁拒绝；下一轮优先评估 512 |
| `M2-T5-QUANTIZATION` | 评估 INT8 量化且不牺牲细边缘 | ✅ PASS（拒绝候选） | QDQ INT8 从 11.63MB 降至 3.50MB，但 test box/mask mAP50 均为 0；自动质量门禁拒绝，FP32 保持默认 |
| `M2-T6-EXPERIMENT` | 训练并验收真实数据模型试验版 | ✅ PASS（仅辅助标注） | real-prelabel-v3 的 9 张非正式验证集 mask mAP50=0.849、mAP50-95=0.511；512 FP32 ONNX 为 11.03MB，SHA-256 与 manifest 一致，真实 ORT 输出 `[1,37,5376]` / `[1,32,128,128]`，TypeScript fixture 解码出 5 个带 mask 候选。该模型只通过辅助标注用途门，不得注册为正式候选 |
| `M2-T6-SEED-CANDIDATE` | 评估仅使用当前授权正式集训练的 real-seed-v1 | ✅ PASS（拒绝候选） | 46 张独立 test 的 box/mask mAP50=0.380/0.367；相对 512 基线下降 0.143/0.101，均超过 0.02 退化上限，自动质量门拒绝继续导出和发布 |
| `M2-T6-V4-CANDIDATE` | 评估 393 图混合续训候选 | ✅ PASS（拒绝候选） | 独立原 test box/mask mAP50=0.429/0.397，未通过质量门，未导出或发布 |
| `M2-T6-V5-CANDIDATE` | 评估 512 来源隔离真实候选 | ✅ PASS（拒绝候选） | 13 张 deerplanet 独立 test 的 box/mask mAP50=0.848/0.836；box 略低于 0.85，资产门通过但 release gate 拒绝 |
| `M2-T6-V6-CANDIDATE` | 评估 640 训练/512 部署来源隔离真实候选 | ✅ PASS（候选门） | 13 张独立真实 test、102 mask：box/mask mAP50=0.853/0.848；11.03MB ONNX 完整性、ORT 双输出、7 候选 fixture 和 Chromium WebGPU 29 次热推理 P95=133.7ms 均通过 |
| `M2-T6-V6-RELEASE-67-EVAL` | 在冻结67张发布测试快照上复评v6部署质量 | ✅ PASS（拒绝候选） | 评估专用物化独立复算67图/384 mask/18父组及逐文件哈希，和409张正式训练图的来源组、图片SHA-256重叠均为0；512全量box/mask mAP50=0.8370/0.8313，核心45张=0.8485/0.8523，压力22张=0.8179/0.7919，压力组相对历史13张基线下降0.0348/0.0557，质量门拒绝v6。640全量诊断=0.8570/0.8549，但不属于部署512口径，不能覆盖失败结论 |
| `M2-T6-V6-RELEASE-67-FAILURE-PROFILE` | 冻结67张部署阈值逐图实例失败画像 | ✅ PASS（诊断闭环） | 以浏览器默认confidence=0.35、mask IoU=0.50匹配67图/384真值与346个预测：289匹配、95漏检、57误检、76个弱形状匹配，整体召回0.7526；核心召回0.7761，压力召回0.6983。0.20—0.45阈值扫描显示0.25可把压力召回提高到0.7845，但误检由57增至90，未绕过浏览器候选数、误检与Beta门直接改默认值。15张最高风险原分辨率叠加图确认透明相邻长甲、多甲同屏、低对比漏整甲/局部甲面及手指/腕表误检。报告固定禁止将冻结图片、标签、裁剪或父来源组用于训练 |
| `M2-T6-V6-VAL-THRESHOLD-CALIBRATION` | 来源隔离验证集阈值校准与测试集防泄漏门 | ✅ PASS（拒绝写入manifest） | 校准器仅接受split=val及val-only来源组，绑定数据集/来源报告/指标/预测/权重SHA-256，硬拒绝test和跨split来源；v6部署512在13张/45 mask val上box/mask mAP50=0.9376/0.9420，诊断最优confidence=0.20时匹配40、漏5、误检2、F1=0.9195，但发现14个真值polygon需拓扑修复且13<30图，因此`calibrationEligible=false`、`manifestScoreThreshold=null`，生产阈值不变 |
| `M2-T6-V6-VAL-TRUTH-AUDIT` | v6旧验证真值隔离返修候选与原分辨率全覆盖审核 | ✅ PASS（拒绝旧val真值） | 候选生成器绑定dataset/source report/calibration哈希，只处理val且不覆盖源标签；14个无效polygon生成隔离候选、13/13整图和14组逐甲2×证据。审核结果3张通过、7张返修、3张排除，并发现2张未声明交叠以及漏甲、背景/雕塑误标、重复mask、皮肤污染和边缘裁断；机器报告输出`rejected_as_calibration_truth`。旧val的0.9376/0.9420与0.20仅保留为不合格真值上的历史诊断，不用于模型选择、阈值或manifest |
| `M2-T6-VAL-TRUTH-AUDIT-CONTRACT` | 验证真值视觉审核资格接入阈值校准器 | ✅ PASS | 校准器新增`--truth-audit`：正式阈值只接受`approved_as_calibration_truth`，并绑定dataset路径/SHA-256、逐标签哈希和全量pass计数；缺失审核或显式拒绝分别降级为`diagnostic_only_validation_truth_unreviewed/rejected`。v6旧val带拒绝报告复跑仍仅保留0.20诊断点，`calibrationEligible=false`、`manifestScoreThreshold=null` |
| `M2-T6-NEXT-CANDIDATE-PREFLIGHT` | 下一真实候选的数据与训练可行性预检 | ✅ PASS（等待训练授权） | RTX 4060 Laptop 8GB与v6/v9权重可用，正式409图/2142 mask readiness通过；但正式val 46图/234 mask含5处polygon交叠，且300张AI图的同一`sourceGroup`跨train/val/test，不能作为来源隔离模型选择或阈值真值。现有授权真实数据已进入v7–v9且连续退化；未获`真实素材/2026_7_14`商业训练授权前不启动缺乏数据依据的v10，也不触碰冻结发布测试或未授权素材 |
| `M2-T6-CANDIDATE-TRAINING-VALIDATION-GATE` | 正式候选训练的来源隔离与视觉真值前置门 | ✅ PASS（当前正式集被拒绝） | 新增通用来源隔离审计和候选训练验证审计，要求val-only来源组、≥30图、`approved_as_calibration_truth`全pass、dataset/来源/审核/逐标签哈希一致、polygon合法且零交叠；`train-yolo-seg.py --candidate-mode`必须绑定通过报告，默认实验摘要固定`training_intent=experiment`。当前409图集报告明确拒绝AI来源组210/45/45跨split、缺视觉审核及5处交叠，v10 dry-run被入口拦截 |
| `M2-T6-CANDIDATE-PIPELINE-EVIDENCE` | 正式候选验证证据接入训练发布编排器 | ✅ PASS | 编排器新增`--candidate-mode/--candidate-validation-report`，候选模式缺报告在解析阶段失败，报告路径原样下传`train-yolo-seg.py`；流水线报告记录`trainingIntent=candidate`和证据路径。被拒绝证据在train步骤停止，后续评估、导出和治理均不执行；默认运行仍明确为`experiment` |
| `M2-T6-V7-CANDIDATE` | 将新增 5 张审核图并入来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 97 图/672 mask，train/val/test=69/15/13；冻结 test box/mask mAP50=0.840/0.833，box 低于 0.85 且较 v6 退化，未导出或发布 |
| `M2-T6-V8-CANDIDATE` | 将跨分辨率共识审核新增2张并入来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 99图/681 mask，train/val/test=70/16/13；冻结 test box/mask mAP50=0.8487/0.8472，box低于0.85且未超过v6，未导出、注册或发布 |
| `M2-T6-V9-CANDIDATE` | 将7张已审核截图派生图并入v8来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 106图/722 mask，train/val/test=76/17/13；冻结test图片与标签联合SHA-256前后相同，512 test box/mask mAP50=0.8411/0.8393，box低于0.85且两项较v6退化，未导出、注册或发布 |

## 里程碑 3：Beta、设备与质量验收

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `M3-T1-GATES` | 性能、纹理质量、发布测试集代表性与发布决策门禁 | ✅ PASS | 性能、客户端开销、直接可用率、污染率、形状保真、样本量和 release-test-split 硬门禁均有自动测试；发布决策会阻止不合格候选 |
| `M3-T2-DESKTOP-SMOKE` | 桌面浏览器工程性能冒烟 | ✅ PASS | Chromium Worker + WebGPU 连续 20 次已预热实测：端到端 P50=63ms、P95=72ms、max=79ms；Worker P95=57ms；客户端开销 P95=17ms；20/20 均返回 4 个候选。仅证明合成基线工程性能，不代表正式模型质量 |
| `M3-T3-DEVICE` | Windows、Android 与 iPhone 真机矩阵 | 🟠 PARTIAL | Windows Chromium WebGPU 已完成29次热性能和20次内存稳定性基准：P95=133.7ms，JS heap 峰值19.86MiB、首末增长1.69MiB，浏览器私有内存首末增长121.81MiB；Android/iPhone/iPad 真机仍等待执行 |
| `M3-T4-QUALITY` | 真实测试集直接可用率、污染率和人工修正成本 | 🟡 IN PROGRESS | 冻结67张/384 mask已在部署512口径完成v6评估；全量box/mask mAP50=0.8370/0.8313，核心=0.8485/0.8523，压力=0.8179/0.7919，压力组退化触发拒绝。代表性规模仍缺33张，直接可用率、污染率和人工修正成本仍需100张Beta逐图审核 |
| `M3-T5-BETA` | Beta 发布决策 | 🔴 HOLD | v6 在扩展冻结快照的部署512质量门被拒绝；同时仍缺100张代表性真实测试集、移动真机矩阵、用户失败案例和Beta人工质量验收，禁止 promotion |

## 正式发布与回滚

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `REL-T1-TOOLCHAIN` | 模型登记、A/B 比较、发布决策、promotion、trace、历史与回滚 | ✅ PASS | 全量测试覆盖注册完整性、回滚候选、失败阻断、主动学习告警和 trace 证据传递 |
| `REL-T1-CONFIG-GUARD` | 生产与 smoke manifest 配置隔离 | ✅ PASS | `.env.local.example`不再启用smoke覆盖，复制后使用正式manifest默认路径；自动测试拒绝任何启用状态的示例覆盖，防止smoke模型成为共享默认值 |
| `REL-T1-COMPLETION-AUDIT` | 实施规范最终完成度机器审计 | ✅ PASS（HOLD生效） | 总门逐项读取规范清单、进度标记、冻结67张质量报告、代表性test、桌面/移动设备、失败案例、Beta质量和生产资产；当前2/10门通过并输出模型质量退化、失败案例、33张新增测试图、四类移动真机及Beta审核5类阻断，未错误promotion |
| `REL-T1-ACCEPTANCE-EVIDENCE` | 真机、Beta与失败案例外部证据构建器 | ✅ PASS | 真机聚合器拒绝未通过或少于20次的性能/内存报告；Beta CSV强制100张、用户审核、SHA-256和85%直接可用率；失败案例CSV校验图片、来源组、类别、严重度和哈希；成功/拒绝专项6/6通过 |
| `REL-T2-CANDIDATE` | 正式模型候选发布 | 🔴 HOLD | v6保留资产、协议和桌面性能证据，但在冻结67张的部署512质量门被拒绝；生产manifest保持不变，需用训练授权且与冻结快照来源隔离的新压力样本改进候选，再重跑同一门禁 |

## 当前总体验收

`npm.cmd run audit:mvp-readiness:refresh` 的历史权威报告确认数据、来源授权、训练工具链、浏览器接线、反馈闭环、质量/性能门禁、发布治理与验证命令均可运行。当前生产状态仍为 HOLD：v6在历史13张小测试集上曾通过，但在来源隔离的冻结67张扩展快照上以部署512评估后被质量门拒绝；代表性规模、移动真机、用户失败案例与Beta人工门也未完成，生产 manifest 继续指向未部署的正式 ONNX，不能用640诊断或smoke模型绕过。

### 合成数据基线审核记录

- 素材目录 `E:\AI Project\Codex\JiaRu_image` 共 322 张：300 张团队生成图、22 张真实素材；322/322 可解码，0 个完全重复，1 对低阈值近似图片待复核。
- 300 张 AI 图与现有训练集逐文件 SHA-256 核对：300/300 完全匹配，避免了重复导入。
- 修复当前 Ultralytics 的两个真实兼容问题：`batch=auto` 规范化为官方支持的 `batch=-1`；训练/评测使用绝对数据根目录运行时 YAML。
- 训练在第 88 epoch early stop；独立 test 指标为 box mAP50 `0.5216`、mask mAP50 `0.4539`。
- 导出 ONNX 大小 `11626577` 字节（11.09MB），SHA-256 `0af74c0429035f627abd8fadf5e37eeb21cbcf4ebf00e4ed2fdfe78684f96868`；资产门禁通过但高于 8MB 理想目标。
- 真实模型输出为 `[1,37,8400]` 与 `[1,32,160,160]`；TypeScript 后处理得到 4 个带 mask 候选。
- Chromium Worker + WebGPU 冷启动 `3898ms`，缓存后热推理 `82.2ms`，Worker `67.4ms`，客户端开销 `14.8ms`；模型、manifest 和 ORT 资源均由 localhost 加载，控制台 0 错误、0 警告。
- 发布门禁保持失败：box/mask 指标低于正式阈值，且证据不是真实测试集。该模型只保留为合成基线，不 promotion、不覆盖生产 manifest。

## 需要用户协助但暂不阻塞的事项

| 标记 ID | 所需协助 | 状态 | 使用阶段 |
| --- | --- | --- | --- |
| `USER-DATA-01` | 50–100 张可授权的真实美甲参考图 | ✅ PASS | 用户已提供首批22张、新增113张及2026_7_13发布测试候选101张；最新批101/101可解码，9张跨旧批次精确重复排除，92张来源隔离进入独立发布测试/长期回归。后续缺口是标注质量和代表性验收，不再是素材数量 |
| `USER-AUTH-01` | 明确图片仅内部测试或可用于正式训练 | ✅ PASS | 用户于 2026-07-11 选择 A，确认 22 张真实素材可用于商业模型训练和长期回归测试；300 张团队 AI 图亦已确认商业训练授权 |
| `USER-DEVICE-01` | 确认 Windows、Android、iPhone 的优先级和可测试机型 | ✅ PASS | 已确认普通 Windows、Android、Android Pad、iPhone、iPad；可测 ROG 枪神 8 Plus、vivo Pad2、vivo X100s Pro、小米 13 Pro、vivo S30 |
| `USER-REVIEW-01` | 对固定样本标记直接可用、需修正或不可用 | ✅ PASS | 用户确认 22 张图片均清晰可用，但现有自动标注全部有问题；审核表已统一登记为 `needs_manual_fix`，22/22 进入人工多边形修正队列 |
| `USER-ANNOTATION-01` | 修正真实图片的甲面多边形 | 🟡 IN PROGRESS | 外部首批train已形成100张唯一图片/521个完整mask；来源隔离val现有10张唯一图片/44个完整mask通过角色绑定终审，剩余20张返修。整套val未全通过，约100张hard negative和整批物化/来源隔离尚未完成；当前无需用户逐点重画 |
| `USER-AUTH-02` | 确认 `真实素材/2026_7_12` 新增 113 张素材是否可用于商业模型训练和长期回归测试 | ✅ PASS | 用户于2026-07-12选择A，明确允许用于商业模型训练和长期回归；80张已导入、5张因源图质量排除、28张返修项仍隔离 |
| `USER-AUTH-03` | 确认 `claude/2026_7_13` 的1001张生成素材是否可用于商业模型训练和长期回归测试 | ⏸️ USER INPUT | 机器审计与11页视觉总览已完成；当前仅登记为合成候选池，未导入正式集。需明确授权后再进入逐图筛选和标注流程 |
| `USER-AUTH-04` | 确认 `真实素材/2026_7_13` 的101张素材用途 | ✅ PASS | 用户确认允许用于独立发布测试和长期回归；intake将训练用途固定为prohibited，9张跨批重复排除，92张保留 |
| `USER-AUTH-05` | 确认 `真实素材/2026_7_14` 当前实存1271张素材用途 | ✅ PASS | 用户于2026-07-16选择A，允许商业模型训练、独立发布测试和长期回归；授权只提供后续资格，近重复排除后剩余1166张仍须逐图完整甲面审核并按完整来源组互斥分配，审核前训练用途继续禁止 |
| `USER-HARD-NEGATIVE-01` | 补充或确认约100张清晰、来源隔离的hard negative | ⏭ DEFERRED | 2026_7_14源图筛选排除项主要为拼图、低清、裁断、残缺或域外页面，不能冒充合格负样本；先推进160张真实正样本标注，待其他工程项完成后再集中请求或从独立合格语料选择 |
| `USER-SCOPE-01` | 确认 MVP 产品范围保持为“单张上传图片纹理抠图”，实时视频分割不进入本期 | ✅ PASS | 已确认支持单图、单指和多图提取；实时视频分割不进入本期 |
| `USER-FAILURE-01` | 提供实际用户常见失败图片，如遮挡、镜面高光、复杂背景和异形甲 | ⏭ USER INPUT | hard negative 与失败类型优化 |
| `USER-TESTSET-01` | 最终形成至少 100–200 张来源隔离的独立真实发布测试图 | 🟡 IN PROGRESS | 已冻结并评估67张/384 mask，18个父来源组、trainingUse=prohibited、逐文件与聚合哈希通过，且与正式训练集来源组/图片哈希零重叠；v6部署512质量评估已完成并被拒绝。代表性下限为100张，当前仍缺33张，历史13张仅保留为对照基线而不重复计数 |
| `USER-THRESHOLD-01` | 根据首轮真实测试冻结甲面缺失率与分组退化门槛 | ⏭ USER INPUT | Beta 后、正式发布前 |

## 后续里程碑

- 里程碑 2：正确后处理与真实数据试验。
- 里程碑 3：Beta、真机性能和质量验收。
- 正式发布：版本登记、promotion、回滚与主动学习闭环。
