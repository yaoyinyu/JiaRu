# 美甲纹理端侧实施进度与审核标记

更新日期：2026-07-13
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
| `M2-T3-VISION-ANNOTATION` | 识图提示 + SAM2/YOLO 辅助重建真实甲面多边形 | 🟡 IN PROGRESS | 9张截图派生照片7张/41 mask已通过并安全导入，2张返修；正式集409图/2142 mask，剩余原图返修和代表性test扩充继续推进 |
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
| `USER-ANNOTATION-01` | 修正真实图片的甲面多边形 | 🟡 IN PROGRESS | 首批21张/174个甲面已完成；新增批次已有79张正样本/516个甲面mask和1张hard negative通过，5张源图排除，剩余28张继续返修。当前无需用户逐点重画 |
| `USER-AUTH-02` | 确认 `真实素材/2026_7_12` 新增 113 张素材是否可用于商业模型训练和长期回归测试 | ✅ PASS | 用户于2026-07-12选择A，明确允许用于商业模型训练和长期回归；80张已导入、5张因源图质量排除、28张返修项仍隔离 |
| `USER-AUTH-03` | 确认 `claude/2026_7_13` 的1001张生成素材是否可用于商业模型训练和长期回归测试 | ⏸️ USER INPUT | 机器审计与11页视觉总览已完成；当前仅登记为合成候选池，未导入正式集。需明确授权后再进入逐图筛选和标注流程 |
| `USER-AUTH-04` | 确认 `真实素材/2026_7_13` 的101张素材用途 | ✅ PASS | 用户确认允许用于独立发布测试和长期回归；intake将训练用途固定为prohibited，9张跨批重复排除，92张保留 |
| `USER-AUTH-05` | 确认 `真实素材/2026_7_14` 的1277张素材用途 | ⏸️ USER INPUT | 技术候选入库审计已通过，但当前authorizedUses为空、训练用途禁止；需用户明确选择仅发布测试/长期回归、允许商业训练，或仅存档不用模型后，才能继续逐组去重和逐图审核 |
| `USER-SCOPE-01` | 确认 MVP 产品范围保持为“单张上传图片纹理抠图”，实时视频分割不进入本期 | ✅ PASS | 已确认支持单图、单指和多图提取；实时视频分割不进入本期 |
| `USER-FAILURE-01` | 提供实际用户常见失败图片，如遮挡、镜面高光、复杂背景和异形甲 | ⏭ USER INPUT | hard negative 与失败类型优化 |
| `USER-TESTSET-01` | 最终形成至少 100–200 张来源隔离的独立真实发布测试图 | 🟡 IN PROGRESS | 已冻结并评估67张/384 mask，18个父来源组、trainingUse=prohibited、逐文件与聚合哈希通过，且与正式训练集来源组/图片哈希零重叠；v6部署512质量评估已完成并被拒绝。代表性下限为100张，当前仍缺33张，历史13张仅保留为对照基线而不重复计数 |
| `USER-THRESHOLD-01` | 根据首轮真实测试冻结甲面缺失率与分组退化门槛 | ⏭ USER INPUT | Beta 后、正式发布前 |

## 后续里程碑

- 里程碑 2：正确后处理与真实数据试验。
- 里程碑 3：Beta、真机性能和质量验收。
- 正式发布：版本登记、promotion、回滚与主动学习闭环。
