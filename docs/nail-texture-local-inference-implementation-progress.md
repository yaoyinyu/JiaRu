# 美甲纹理端侧实施进度与审核标记

更新日期：2026-07-12
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
| `M2-T2-DATA-GATE` | 数据结构、来源授权、split 与训练环境门禁 | ✅ PASS | 正式有效集 398 图/2083 个 mask、398 条来源记录，split=292/45/61；第二批通过项按 deerplanet/more/other 集合隔离，来源授权、标签、split 比例和训练 readiness 通过 |
| `M2-T3-SYNTHETIC-BASELINE` | 训练、评测并导出隔离的合成数据基线 | ✅ PASS | 300 张 AI 图逐 SHA-256 核对无缺失；88 epochs early stop；test box mAP50=0.522、mask mAP50=0.454；11.09MB ONNX 完整性与浏览器 WebGPU 通过；发布门禁按预期拒绝 |
| `M2-T3-REAL-DATA` | 导入授权真实图片并建立来源隔离测试集 | 🟠 PARTIAL | 新增 113 张已获商业训练与长期回归授权；76 张审核通过图/498 mask 正式导入，37 张继续返修。真实实验集更新为 97 图并保持 deerplanet 13 图/102 mask 为冻结独立 test；样本量尚未达到 100–200 张代表性发布测试要求 |
| `M2-T3-VISION-ANNOTATION` | 识图提示 + SAM2/YOLO 辅助重建真实甲面多边形 | 🟡 IN PROGRESS | v6 对 42 张返修图生成 317 个 640/conf20 候选并完成五页视觉审核，仅 5 张/27 mask 通过；剩余 37 张又以 1024/conf10 生成 458 个候选，但重复、皮肤污染与拼图误检增加，0 张新增提升。第二批累计 76 图/498 mask 通过，37 张继续返修 |
| `M2-T4-INPUT-SIZE` | 用 FP32 基线评估输入尺寸 | ✅ PASS | 640 基线 box/mask mAP50=0.522/0.454；512=0.524/0.468，通过 0.02 退化门禁；384=0.475/0.438，box 退化 0.046，被门禁拒绝；下一轮优先评估 512 |
| `M2-T5-QUANTIZATION` | 评估 INT8 量化且不牺牲细边缘 | ✅ PASS（拒绝候选） | QDQ INT8 从 11.63MB 降至 3.50MB，但 test box/mask mAP50 均为 0；自动质量门禁拒绝，FP32 保持默认 |
| `M2-T6-EXPERIMENT` | 训练并验收真实数据模型试验版 | ✅ PASS（仅辅助标注） | real-prelabel-v3 的 9 张非正式验证集 mask mAP50=0.849、mAP50-95=0.511；512 FP32 ONNX 为 11.03MB，SHA-256 与 manifest 一致，真实 ORT 输出 `[1,37,5376]` / `[1,32,128,128]`，TypeScript fixture 解码出 5 个带 mask 候选。该模型只通过辅助标注用途门，不得注册为正式候选 |
| `M2-T6-SEED-CANDIDATE` | 评估仅使用当前授权正式集训练的 real-seed-v1 | ✅ PASS（拒绝候选） | 46 张独立 test 的 box/mask mAP50=0.380/0.367；相对 512 基线下降 0.143/0.101，均超过 0.02 退化上限，自动质量门拒绝继续导出和发布 |
| `M2-T6-V4-CANDIDATE` | 评估 393 图混合续训候选 | ✅ PASS（拒绝候选） | 独立原 test box/mask mAP50=0.429/0.397，未通过质量门，未导出或发布 |
| `M2-T6-V5-CANDIDATE` | 评估 512 来源隔离真实候选 | ✅ PASS（拒绝候选） | 13 张 deerplanet 独立 test 的 box/mask mAP50=0.848/0.836；box 略低于 0.85，资产门通过但 release gate 拒绝 |
| `M2-T6-V6-CANDIDATE` | 评估 640 训练/512 部署来源隔离真实候选 | ✅ PASS（候选门） | 13 张独立真实 test、102 mask：box/mask mAP50=0.853/0.848；11.03MB ONNX 完整性、ORT 双输出、7 候选 fixture 和 Chromium WebGPU 29 次热推理 P95=133.7ms 均通过 |
| `M2-T6-V7-CANDIDATE` | 将新增 5 张审核图并入来源隔离集后续训复评 | ✅ PASS（拒绝候选） | 97 图/672 mask，train/val/test=69/15/13；冻结 test box/mask mAP50=0.840/0.833，box 低于 0.85 且较 v6 退化，未导出或发布 |

## 里程碑 3：Beta、设备与质量验收

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `M3-T1-GATES` | 性能、纹理质量、发布测试集代表性与发布决策门禁 | ✅ PASS | 性能、客户端开销、直接可用率、污染率、形状保真、样本量和 release-test-split 硬门禁均有自动测试；发布决策会阻止不合格候选 |
| `M3-T2-DESKTOP-SMOKE` | 桌面浏览器工程性能冒烟 | ✅ PASS | Chromium Worker + WebGPU 连续 20 次已预热实测：端到端 P50=63ms、P95=72ms、max=79ms；Worker P95=57ms；客户端开销 P95=17ms；20/20 均返回 4 个候选。仅证明合成基线工程性能，不代表正式模型质量 |
| `M3-T3-DEVICE` | Windows、Android 与 iPhone 真机矩阵 | 🟠 PARTIAL | Windows Chromium WebGPU 已完成29次热性能和20次内存稳定性基准：P95=133.7ms，JS heap 峰值19.86MiB、首末增长1.69MiB，浏览器私有内存首末增长121.81MiB；Android/iPhone/iPad 真机仍等待执行 |
| `M3-T4-QUALITY` | 真实测试集直接可用率、污染率和人工修正成本 | ⏭ USER INPUT | 等待 `USER-DATA-01` 与 `USER-REVIEW-01`；发布门禁拒绝用单张 debug 图代替代表性测试集 |
| `M3-T5-BETA` | Beta 发布决策 | 🔴 HOLD | v6 已通过正式候选工程门，但仍缺代表性真实测试集、真机矩阵和人工质量验收，禁止提前 promotion |

## 正式发布与回滚

| 标记 ID | 任务 | 状态 | 审核证据 |
| --- | --- | --- | --- |
| `REL-T1-TOOLCHAIN` | 模型登记、A/B 比较、发布决策、promotion、trace、历史与回滚 | ✅ PASS | 全量测试覆盖注册完整性、回滚候选、失败阻断、主动学习告警和 trace 证据传递 |
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
| `USER-DATA-01` | 50–100 张可授权的真实美甲参考图 | ✅ PASS | 用户已提供首批 22 张和新增独立批次 113 张；其中 1 张首批图片永久排除，新增批次 113/113 可解码且无批内或跨批完全重复。后续缺口转为标注与来源隔离，不再是素材数量 |
| `USER-AUTH-01` | 明确图片仅内部测试或可用于正式训练 | ✅ PASS | 用户于 2026-07-11 选择 A，确认 22 张真实素材可用于商业模型训练和长期回归测试；300 张团队 AI 图亦已确认商业训练授权 |
| `USER-DEVICE-01` | 确认 Windows、Android、iPhone 的优先级和可测试机型 | ✅ PASS | 已确认普通 Windows、Android、Android Pad、iPhone、iPad；可测 ROG 枪神 8 Plus、vivo Pad2、vivo X100s Pro、小米 13 Pro、vivo S30 |
| `USER-REVIEW-01` | 对固定样本标记直接可用、需修正或不可用 | ✅ PASS | 用户确认 22 张图片均清晰可用，但现有自动标注全部有问题；审核表已统一登记为 `needs_manual_fix`，22/22 进入人工多边形修正队列 |
| `USER-ANNOTATION-01` | 修正真实图片的甲面多边形 | 🟡 IN PROGRESS | 首批 21 张/174 个甲面已完成；新增批次已有 75 张正样本/498 个甲面 mask 和 1 张 hard negative 通过审核，剩余 37 张继续返修。当前无需用户逐点重画 |
| `USER-AUTH-02` | 确认 `真实素材/2026_7_12` 新增 113 张素材是否可用于商业模型训练和长期回归测试 | ✅ PASS | 用户于 2026-07-12 选择 A，明确允许用于商业模型训练和长期回归；76 张审核通过项已导入，37 张返修项仍隔离 |
| `USER-SCOPE-01` | 确认 MVP 产品范围保持为“单张上传图片纹理抠图”，实时视频分割不进入本期 | ✅ PASS | 已确认支持单图、单指和多图提取；实时视频分割不进入本期 |
| `USER-FAILURE-01` | 提供实际用户常见失败图片，如遮挡、镜面高光、复杂背景和异形甲 | ⏭ USER INPUT | hard negative 与失败类型优化 |
| `USER-TESTSET-01` | 最终形成至少 100–200 张来源隔离的独立真实发布测试图 | ⏭ USER INPUT | 正式发布验收 |
| `USER-THRESHOLD-01` | 根据首轮真实测试冻结甲面缺失率与分组退化门槛 | ⏭ USER INPUT | Beta 后、正式发布前 |

## 后续里程碑

- 里程碑 2：正确后处理与真实数据试验。
- 里程碑 3：Beta、真机性能和质量验收。
- 正式发布：版本登记、promotion、回滚与主动学习闭环。
