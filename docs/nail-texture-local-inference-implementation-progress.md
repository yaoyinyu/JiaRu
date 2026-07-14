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
| `M2-T3-RELEASE-TEST-ANNOTATION` | 新增真实发布测试素材逐甲标注与整图复核 | 🟡 IN PROGRESS | 核心首轮8张/59 mask、压力首轮2张/10 mask通过；二十一轮修复累计再提升35张/191 mask。92张父图累计45张/260 mask暂通过、35张返修、12张源图裁断或遮挡排除；候选不得直接当作test真值 |
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
| `M2-T4-INPUT-SIZE` | 用 FP32 基线评估输入尺寸 | ✅ PASS | 640 基线 box/mask mAP50=0.522/0.454；512=0.524/0.468，通过 0.02 退化门禁；384=0.475/0.438，box 退化 0.046，被门禁拒绝；下一轮优先评估 512 |
| `M2-T5-QUANTIZATION` | 评估 INT8 量化且不牺牲细边缘 | ✅ PASS（拒绝候选） | QDQ INT8 从 11.63MB 降至 3.50MB，但 test box/mask mAP50 均为 0；自动质量门禁拒绝，FP32 保持默认 |
| `M2-T6-EXPERIMENT` | 训练并验收真实数据模型试验版 | ✅ PASS（仅辅助标注） | real-prelabel-v3 的 9 张非正式验证集 mask mAP50=0.849、mAP50-95=0.511；512 FP32 ONNX 为 11.03MB，SHA-256 与 manifest 一致，真实 ORT 输出 `[1,37,5376]` / `[1,32,128,128]`，TypeScript fixture 解码出 5 个带 mask 候选。该模型只通过辅助标注用途门，不得注册为正式候选 |
| `M2-T6-SEED-CANDIDATE` | 评估仅使用当前授权正式集训练的 real-seed-v1 | ✅ PASS（拒绝候选） | 46 张独立 test 的 box/mask mAP50=0.380/0.367；相对 512 基线下降 0.143/0.101，均超过 0.02 退化上限，自动质量门拒绝继续导出和发布 |
| `M2-T6-V4-CANDIDATE` | 评估 393 图混合续训候选 | ✅ PASS（拒绝候选） | 独立原 test box/mask mAP50=0.429/0.397，未通过质量门，未导出或发布 |
| `M2-T6-V5-CANDIDATE` | 评估 512 来源隔离真实候选 | ✅ PASS（拒绝候选） | 13 张 deerplanet 独立 test 的 box/mask mAP50=0.848/0.836；box 略低于 0.85，资产门通过但 release gate 拒绝 |
| `M2-T6-V6-CANDIDATE` | 评估 640 训练/512 部署来源隔离真实候选 | ✅ PASS（候选门） | 13 张独立真实 test、102 mask：box/mask mAP50=0.853/0.848；11.03MB ONNX 完整性、ORT 双输出、7 候选 fixture 和 Chromium WebGPU 29 次热推理 P95=133.7ms 均通过 |
| `M2-T6-V7-CANDIDATE` | 将新增 5 张审核图并入来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 97 图/672 mask，train/val/test=69/15/13；冻结 test box/mask mAP50=0.840/0.833，box 低于 0.85 且较 v6 退化，未导出或发布 |
| `M2-T6-V8-CANDIDATE` | 将跨分辨率共识审核新增2张并入来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 99图/681 mask，train/val/test=70/16/13；冻结 test box/mask mAP50=0.8487/0.8472，box低于0.85且未超过v6，未导出、注册或发布 |
| `M2-T6-V9-CANDIDATE` | 将7张已审核截图派生图并入v8来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 106图/722 mask，train/val/test=76/17/13；冻结test图片与标签联合SHA-256前后相同，512 test box/mask mAP50=0.8411/0.8393，box低于0.85且两项较v6退化，未导出、注册或发布 |

## 里程碑 3：Beta、设备与质量验收

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `M3-T1-GATES` | 性能、纹理质量、发布测试集代表性与发布决策门禁 | ✅ PASS | 性能、客户端开销、直接可用率、污染率、形状保真、样本量和 release-test-split 硬门禁均有自动测试；发布决策会阻止不合格候选 |
| `M3-T2-DESKTOP-SMOKE` | 桌面浏览器工程性能冒烟 | ✅ PASS | Chromium Worker + WebGPU 连续 20 次已预热实测：端到端 P50=63ms、P95=72ms、max=79ms；Worker P95=57ms；客户端开销 P95=17ms；20/20 均返回 4 个候选。仅证明合成基线工程性能，不代表正式模型质量 |
| `M3-T3-DEVICE` | Windows、Android 与 iPhone 真机矩阵 | 🟠 PARTIAL | Windows Chromium WebGPU 已完成29次热性能和20次内存稳定性基准：P95=133.7ms，JS heap 峰值19.86MiB、首末增长1.69MiB，浏览器私有内存首末增长121.81MiB；Android/iPhone/iPad 真机仍等待执行 |
| `M3-T4-QUALITY` | 真实测试集直接可用率、污染率和人工修正成本 | 🟡 IN PROGRESS | 新增92张来源隔离发布测试父图均完成首轮及二十一轮受审计返修，当前45张/260 mask暂通过、35张返修、12张源图裁断或遮挡排除。完整露出甲面只在单一完整mask覆盖时通过；仍等待`USER-FAILURE-01`和完整Beta逐图质量审核 |
| `M3-T5-BETA` | Beta 发布决策 | 🔴 HOLD | v6 已通过正式候选工程门，但仍缺代表性真实测试集、真机矩阵和人工质量验收，禁止提前 promotion |

## 正式发布与回滚

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `REL-T1-TOOLCHAIN` | 模型登记、A/B 比较、发布决策、promotion、trace、历史与回滚 | ✅ PASS | 全量测试覆盖注册完整性、回滚候选、失败阻断、主动学习告警和 trace 证据传递 |
| `REL-T1-CONFIG-GUARD` | 生产与 smoke manifest 配置隔离 | ✅ PASS | `.env.local.example`不再启用smoke覆盖，复制后使用正式manifest默认路径；自动测试拒绝任何启用状态的示例覆盖，防止smoke模型成为共享默认值 |
| `REL-T1-COMPLETION-AUDIT` | 实施规范最终完成度机器审计 | ✅ PASS（HOLD生效） | 总门逐项读取规范清单、进度标记、数据授权、v6精度、代表性test、桌面/移动设备、失败案例、Beta质量和生产资产；当前3/10门通过并正确输出4类外部证据阻断，未错误promotion |
| `REL-T1-ACCEPTANCE-EVIDENCE` | 真机、Beta与失败案例外部证据构建器 | ✅ PASS | 真机聚合器拒绝未通过或少于20次的性能/内存报告；Beta CSV强制100张、用户审核、SHA-256和85%直接可用率；失败案例CSV校验图片、来源组、类别、严重度和哈希；成功/拒绝专项6/6通过 |
| `REL-T2-CANDIDATE` | 正式模型候选发布 | 🔴 HOLD | v6 已通过候选精度、资产、协议和桌面性能门；独立真实 test 仅 13 张，仍缺 100–200 张代表性测试集、移动真机矩阵和 Beta 人工质量门，暂不切换生产 manifest |

## 当前总体验收

`npm.cmd run audit:mvp-readiness:refresh` 的历史权威报告确认数据、来源授权、训练工具链、浏览器接线、反馈闭环、质量/性能门禁、发布治理与验证命令均可运行。当前生产状态仍为 HOLD：v6 候选尚未因 13 张 test、移动真机和 Beta 人工门不足而 promotion，生产 manifest 继续指向未部署的正式 ONNX；不能用 smoke 模型绕过。

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
| `USER-SCOPE-01` | 确认 MVP 产品范围保持为“单张上传图片纹理抠图”，实时视频分割不进入本期 | ✅ PASS | 已确认支持单图、单指和多图提取；实时视频分割不进入本期 |
| `USER-FAILURE-01` | 提供实际用户常见失败图片，如遮挡、镜面高光、复杂背景和异形甲 | ⏭ USER INPUT | hard negative 与失败类型优化 |
| `USER-TESTSET-01` | 最终形成至少 100–200 张来源隔离的独立真实发布测试图 | 🟡 IN PROGRESS | 新增92张来源隔离父图均完成首轮及二十一轮受审计返修；当前45张/260 mask暂通过，35张返修、12张源图裁断或遮挡排除，尚未冻结为发布test真值；未审候选不计入合格规模 |
| `USER-THRESHOLD-01` | 根据首轮真实测试冻结甲面缺失率与分组退化门槛 | ⏭ USER INPUT | Beta 后、正式发布前 |

## 后续里程碑

- 里程碑 2：正确后处理与真实数据试验。
- 里程碑 3：Beta、真机性能和质量验收。
- 正式发布：版本登记、promotion、回滚与主动学习闭环。
