# 甲如（JiaRu）技术白皮书

> 文档版本：v1.1.210
>
> 基线日期：2026-07-12
>
> 最近全面审查：2026-07-12
>
> 文档状态：持续维护
>
> 适用范围：产品页面、前端组件、浏览器端识别、AR 试戴、服务端 API、数据集、训练、模型发布与验证

## 1. 文档定位与维护规则

本文档是甲如项目各功能模块对接的唯一总入口，用于回答以下问题：

- 当前有哪些能力，分别处于已完成、待验证、未完成还是占位状态；
- 页面、组件、函数、HTTP API、模型文件和训练脚本之间如何对接；
- 开发、测试和使用时需要哪些输入、输出、环境变量与前置条件；
- 后续任务完成后，应修改哪些接口说明、状态和变更记录。

### 1.1 状态定义

| 状态 | 含义 | 对接要求 |
| --- | --- | --- |
| 已完成 | 代码已存在，主流程可运行，已有相应验证 | 可以接入，但仍应遵守接口约束 |
| 待验证 | 代码已实现，但缺少目标设备、真实数据或完整验收 | 只能试用，不应作为正式质量承诺 |
| 进行中 | 已有部分实现，接口可能变化 | 对接前确认版本和缺口 |
| 占位 | 页面、清单、模拟模型或接口骨架存在，但不具备生产能力 | 不得按正式能力上线 |
| 未完成 | 尚无可用实现 | 需要先完成设计和开发 |
| 阻塞 | 已有实现或流程，但存在明确发布阻断项 | 修复阻断项并重新验证后才能发布 |

### 1.2 信息来源与冲突处理

白皮书不是独立于代码的事实来源。审查或对接时按以下优先级确认当前事实：

1. 当前工作区实际源码、`package.json`、manifest 和文件是否存在；
2. 当前生成的机器可读审计报告；
3. 自动化测试和最近一次有记录的真机/浏览器验证；
4. 本白皮书；
5. 其他规划、历史记录和归档文档。

如果白皮书与更高优先级来源冲突，应以可复现的当前事实为准，并在同一任务内修订白皮书和开发日志。历史规划中的“已完成”不能覆盖当前审计中的 `blocked` 或文件缺失事实。

### 1.3 强制任务生命周期

每个任务都必须执行以下门禁；“任务”包括代码修改、文档修改、诊断、测试、配置、模型、数据和脚本工作。

#### 开始任务前

1. 读取 `AGENTS.md`；
2. 读取本文档，至少覆盖“功能状态总表”、任务对应模块、已知限制和最新变更记录；
3. 对照当前源码或机器可读报告确认相关状态没有过期；
4. 在开始实施前确定本次需要修改或新增的白皮书章节；
5. 若白皮书与源码冲突，先把冲突列入本次任务范围，不得继续引用错误信息。

任务第一次进度更新必须明确说明已读取白皮书，并指出本次采用的模块章节和当前状态，作为可观察的开始凭证。

#### 结束任务前

1. 更新对应模块的状态、接口、使用方式、配置、限制或验证结论；
2. 在“版本与变更记录”追加本次任务记录；
3. 将同一摘要追加到当天唯一的 `dev-log/YYYY-MM-DD.md`；
4. 执行文档差异检查和编码审计；行为变更还需执行相应代码测试；
5. 最终答复必须说明白皮书和开发日志已同步；任一项未完成时不得宣称任务完成。

最终答复应点名本次修改的白皮书章节/变更记录和当天日志文件，作为结束凭证。

即使任务没有改变任何接口，也必须在白皮书变更记录和当天日志中写明“已复核，无接口/状态变化”及原因。这样可以留下任务确实读取并核对白皮书的证据。

### 1.4 内容维护要求

每完成一项会影响功能、接口、使用方式、配置、数据结构、模型、脚本或部署方式的任务，必须在结束任务前同步更新本文档：

1. 更新对应模块的状态、接口或使用说明；
2. 若新增或修改 HTTP/TypeScript/Worker/模型接口，更新相应契约；
3. 更新“已知限制与待办”；
4. 在“版本与变更记录”追加一条记录；
5. 在当天唯一的 `dev-log/YYYY-MM-DD.md` 中记录任务摘要；
6. 执行与风险相匹配的验证，并记录验证结论，不得把“代码存在”直接写成“生产可用”。

仅修改注释、拼写或不影响行为的格式调整时，可只追加简短变更记录，但仍须同步当天开发日志。

## 2. 系统概览

甲如是基于 Next.js App Router 的美甲设计与试戴应用。核心处理原则是“图片与摄像头数据尽量留在浏览器本地”，仅 AI 文生图功能向服务端发送文字描述。

### 2.1 技术栈

| 层级 | 技术 | 当前版本/方式 |
| --- | --- | --- |
| Web 框架 | Next.js App Router | 16.2.9 |
| UI | React | 19.2.4 |
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS + CSS Modules | Tailwind 4 |
| 手部关键点 | MediaPipe Hands | 浏览器端运行；当前脚本和运行资源从 jsDelivr CDN 加载 |
| 纹理模型推理 | ONNX Runtime Web | 1.27.0，WebGPU/WASM |
| 图形处理 | Canvas、OffscreenCanvas、ImageBitmap | 浏览器端 |
| 3D 依赖 | Three.js | 0.184.0，仅安装依赖，当前 `src` 未使用 |
| AI 生图 | OpenAI Images HTTP API | 当前代码使用 `dall-e-3`，依赖服务端密钥 |

### 2.2 逻辑数据流

```text
图片试色：用户照片 -> 浏览器 Canvas 手工涂色 -> 本地 PNG 下载

纹理 AR：参考图 -> 浏览器纹理识别/人工裁剪 -> ImageBitmap
                                      + 摄像头 -> MediaPipe 关键点 -> Canvas AR 合成

AI 生图：文字描述 -> POST /api/generate-ai -> 外部图像 API -> 远程图片 URL/本地下载
```

三条流程目前彼此独立：AI 生成结果和图库款式不会自动写入编辑器或 AR；只有 `/ar-tryon` 内上传的参考图可以进入纹理识别/裁剪链路。

## 3. 功能状态总表

| 模块 | 用户入口/接口 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| 首页与统一导航 | `/` | 已完成 | 提供功能入口与统一视觉框架 |
| 灵感图库 | `/gallery` | 占位 | 当前使用本地占位素材，尚无真实内容管理后端 |
| 图片试色编辑器 | `/editor` | 已完成 | 本地上传、MIME/大小/分辨率/解码校验、逐指选色、Canvas 涂抹与本地保存链路均已实现并通过浏览器审核 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 待验证 | 前后端已实现；依赖有效密钥、联网和当前模型可用性，尚无正式服务可用性承诺 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 单手摄像头、关键点、指甲绘制、手心/手背识别已实现；依赖 CDN，仍需多设备真机验收 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | 支持手动裁剪和多候选纹理分配；贴合质量需继续实测 |
| 独立 AR 演示桥接 | `/ar-demo` | 占位 | 仅将本机 `http://localhost:8080/?embedded=jiaru-main` 临时嵌入 iframe，要求用户另行启动 Python demo；不是生产 AR 服务，部署环境不能依赖该地址 |
| 视频自适应展示 | `calculateCoverVideoLayout()` | 已完成 | 保持比例，采用居中 cover 裁切，不拉伸 |
| 美甲纹理自动识别 | `recognizeNailTextures()` | 进行中 | 浏览器推理、Worker、后处理和 fallback 已实现；v6资产、协议及桌面性能证据有效，但冻结67张在部署512下的扩展质量门未通过，尚无可晋升生产的模型 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()` | 已完成 | 模型不可用时仍可返回候选，但质量不等同正式模型 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 阻塞 | v6候选ONNX的资产、协议和桌面性能门通过，但旧冻结67张/384 mask在部署512下box/mask mAP50=0.8370/0.8313，box未达0.85且压力组退化，候选已被拒绝。新增33张/170 mask已完成原分辨率终审并与旧67张合并为100张/554 mask冻结快照，代表性规模门已满足；新100张尚未产生正式候选模型质量结果，移动真机与Beta门也未解除，生产manifest保持不变 |
| 数据集治理 | `model/datasets/nail-texture-v1` | 进行中 | 正式训练集仍为409图、2142个mask，split=300/46/63。2026_7_14候选经来源组互斥规划后，train真值为100张/521 mask、val真值为30张/144 mask；两者均已完成原分辨率、合法性、零交叠和唯一索引终审。独立发布test补充33张经第二轮SAM与人工polygon迭代后形成33张/170 mask、0拒绝/冗余/冲突，索引SHA-256为`93588fb6…e04c`；与旧67张/384 mask合并后的冻结快照为100张/554 mask、core 78、stress 22、29个父来源组，manifest SHA-256为`b3baa41c…23c6`。评估专用物化为test 100、train/val 0，来源组、图片SHA-256和文件名与正式409图训练集零重叠，深度重放通过。对既有排除池及派生区域穷举复筛仍无新增安全hard negative，正式训练输入保持train正样本100/100、val 30/30、hard negative 1/100，仍缺99张，候选数据集不物化、正式候选训练继续HOLD。1001张Claude生成图仍为未授权、未标注的合成候选池 |
| 训练真值历史增量 | 外部`training-truth-index-v1.json` | 历史记录 | v1.1.167曾形成79张唯一图片/416个完整mask的中间快照；该数量已被下一行“训练真值当前权威快照”的100张/521 mask替代，不得再作为当前训练准备度依据 |
| 训练真值当前权威快照 | 外部工作区根目录`training-truth-index-v1.json` | 进行中 | 101个批准报告归并为100张唯一图片/521个完整mask，2个历史拒绝报告、1个冗余报告、0冲突，索引SHA-256为`13f606b547c32d2b8f34651f55e1bca1e826bf3ac13bdcdca345a1cef267f125`。最低100张train正样本门已达到；来源隔离val 30张/144 mask已通过物化和校准真值终审。约100张hard negative仅找到1张安全候选且尚未正式物化，正式候选训练继续HOLD。权威索引位于审核工作区根目录；`final/training-truth-index-v1.json`为字节一致镜像 |
| 验证真值当前快照 | 外部`val-annotation-workspace-v1/validation-truth-index-v1.json` | 已完成 | v1.1.189：30个批准报告归并为30张唯一图片/144个完整mask、0拒绝、0冗余、0冲突，索引SHA-256为`2ccde9420141e5e67a9696959cc18e78aaee808ba29b592670990967bdc4b92d`。批次014—018严格排除裁断、遮挡或甲数错误源图，透明甲尖和全部附着装饰均经整图与逐甲2×复核；所有polygon合法且同图严格零交叠。规范val-only数据集物化为30图/30 annotation/30 label/144 mask、train/test均0、孤儿0，物化报告SHA-256为`200b087b…b1776`。来源隔离审计对当前train 100张和冻结test 67张重新读取、复算身份，文件名、图片SHA-256和来源组均零重叠，报告SHA-256为`7372d14d…f6479e`。最终审计SHA-256为`5152dc52…66a3a`，决定`approved_as_calibration_truth`、`calibrationTruthEligible=true`，同时保持`trainingUse=prohibited` |
| 规范候选训练数据与输入门 | `finalize-reviewed-hard-negative-manifest.py`、`materialize-canonical-candidate-training-dataset.py`、`audit-candidate-training-input.py`、`train-yolo-seg.py --candidate-mode` | 已完成（工程门） | 固定正式下限为train正样本100、正式hard negative 100、val 30，CLI不得下调。hard negative终结器schema v2先重放逐图原分辨率审核、A授权、图片哈希、Pillow完整解码/尺寸与审核隔离证据；不足100张只产生不可训练HOLD，达到门槛后批准报告仍由角色隔离、物化器和输入审计从当前证据深验。物化前重算四角色文件名、图片SHA-256和来源组隔离；候选包固定train=正样本+空标签hard negative、val=规范校准真值、test为空，并绑定逐文件/聚合哈希。输入审计独立重算allow-list、annotation→YOLO标签、polygon合法性/零交叠、负样本字节空标签、源/物化负样本再次解码和孤儿文件；训练入口在加载Ultralytics或占用GPU前深度重放PASS。真实输入仍为100/1/30，schema v2报告正确HOLD，候选数据集目录未创建，仍缺99张合格hard negative |
| 2026-07-23 AI困难负样本与首个正式候选 | 外部`2026_7_23_hard-negative-ai-v1`、候选权重SHA-256 `bcb145b5…1a50` | 评估中 | 626张AI图完成解码/哈希清点，0损坏、0完全重复；原分辨率严格审核通过99张，与历史1张合并后schema v2批准100张。候选输入为train正样本100/521 mask、困难负样本100/空标签、val30/144 mask、test0，并与权威冻结test100张按文件名、图片SHA-256和来源组零重叠；物化文件树SHA-256仍为`4a97f5b6…12b8`。以v6续训50轮所得候选在冻结100图/554 mask、部署512口径达到box/mask mAP50=0.965/0.960，但AI负样本存在系统性右下角水印/模糊角标，水印消融与困难负样本误检审计未完成，因此仅为候选，禁止直接替换生产模型。 |
| 规范val30阈值校准门 | `evaluate.py`、`calibrate-model-score-threshold.py` | 已完成（工程门；v6拒绝） | 规范30图/144 mask终审、角色隔离与当前文件字节被独立重放；评估使用独立runtime副本并复验源树前后逐文件哈希，制品索引绑定稳定文件清单、逐文件SHA和30图显式预测记录。v6部署512 box/mask mAP50=0.6241/0.5630；0.05—0.50无阈值同时满足召回≥0.75、每图误检≤1和单图候选≤10，正式决定`no_threshold_meets_validation_constraints`、`manifestScoreThreshold=null`，不修改生产manifest |
| 候选三路训练发布编排 | `run-training-release-pipeline.ts --candidate-mode`、`verify-training-release.ts --candidate-mode` | 已完成（工程门；训练仍HOLD） | 强制训练、规范val与冻结release-test使用三套不同dataset，固定训练→val评估/校准→test评估→导出顺序；冻结test物化报告、校准报告、release metrics、权重、预测制品和manifest阈值证据均深度绑定。val/test互换、伪造PASS、文件/权重漂移、手工阈值及未绑定skip/resume会拒绝。当前hard negative仍为1/100且v6无合格阈值，未启动训练或候选导出 |
| 移动真机基准与证据门 | `/device-benchmark`、`build-nail-texture-mobile-memory-raw.ts`、`build-nail-texture-device-acceptance.ts` | 已完成（工程门） | 真机页固定3次预热+20次正式推理，导出同一session/device/model/backend/input身份；fallback、混合身份和少样本不能晋级。Android Profiler/iOS Instruments内存CSV经会话与源SHA绑定后进入内存验证；设备验收v2和最终完成度审计均深度重算性能样本、原始内存、统计、路径及哈希，拒绝伪造外层PASS、跨session和写后漂移。四类物理设备尚未实际运行，因此`M3-T3-DEVICE`继续PARTIAL |
| 训练/评估/导出 | `model/training/*` | 进行中 | v4、v5、v7、v8、v9均被拒绝；v6历史13张test为0.853/0.848，但冻结67张部署512复评降至0.8370/0.8313并正式拒绝。11.03MB FP32 ONNX与桌面WebGPU工程证据保留，不等于发布质量通过 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门、逐图失败画像、规范val30阈值深审、三路候选编排、最终完成度审计和外部验收证据构建器。冻结质量报告schema v2新增独立只读重放，完成度审计会重建整份报告并保护全部传递输入；代表性100图快照存在时禁止退回历史13图或旧67图指标。规范用户/工程清单须非空、checkbox格式完整且同章节文本唯一，进度标记须格式完整且ID唯一；空文档、畸形/重复清单、畸形漏行或重复PASS不能虚增完成度。当前没有与新100图绑定的新候选模型质量报告，因此现场审计为341个进度标记/331个PASS、13个正式门中3个通过并输出HOLD。该3/13衡量完整发布闭环，不等于候选训练只完成23% |
| 隐私说明 | `/privacy` | 待验证 | 静态说明页已实现；尚未完成法律/产品审核，部分“保存试戴效果图”文案领先于现有 AR 能力 |
| 用户账户、云同步、商城/门店 | 无 | 未完成 | 当前没有对应后端接口或数据模型 |

## 4. 页面与用户使用接口

### 4.1 启动与访问

```powershell
cd "E:\AI Project\Codex\JiaRu"
npm.cmd install
npm.cmd run dev
```

默认访问 `https://localhost:3000`。开发脚本使用 `next dev --experimental-https`；若本机自签名证书生成失败，Next.js 可能回退至 HTTP。摄像头应通过 `localhost` 或正式 HTTPS 域名访问，不应使用普通局域网 HTTP 地址。

生产启动应先执行 `npm.cmd run build`，再执行 `npm.cmd run start`。开发模式的实验性自签名 HTTPS 不等同正式部署证书。

生产验证命令：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

### 4.2 `/editor` 图片试色

状态：已完成。

使用方式：

1. 上传或拍摄清晰的手部图片；文件选择器与运行时均限制为 JPG/PNG/WebP、最大 10 MB、宽高各 320–4096 像素；
2. 选择拇指至小指之一；
3. 选择颜色，可将当前颜色应用到全部手指；
4. 在 Canvas 上点击或拖动完成局部涂色；
5. 使用组件提供的撤销、重置和保存能力。

数据边界：上传校验在浏览器本地完成；通过后才调用 `URL.createObjectURL()`，页面卸载或更换文件时释放对象 URL。无效 MIME、超限大小、解码失败、过小或过大分辨率会在上传区显示可读错误，不创建编辑会话。

核心组件接口：

```ts
<UploadButton onUpload={(file: File) => void | Promise<void>} />

<NailCanvas
  imageUrl={string}
  selectedColor={string | undefined}
  nailColors={string[] | undefined}
  activeFinger={number | undefined}
  brushSize={number}
/>

<ColorPalette
  selectedColor={string}
  onSelectColor={(color: string) => void}
/>
```

### 4.3 `/gallery` 灵感图库

状态：占位。

当前使用 `src/lib/utils.ts` 中的 `GALLERY_IMAGES` 和 `public/nail-gallery/placeholder-*.svg`。点击条目会跳转到 `/editor?gallery=<id>`，但 `/editor` 当前没有读取 `gallery` 参数，因此只会打开编辑器，不会自动载入对应款式。这是未完成的模块对接，不应把“点击进入试色”理解为已应用图库设计。

当前没有数据库、上传管理、分页、搜索、收藏或真实素材授权接口。后续接入真实图库时应至少补充：资源 ID、来源授权、缩略图、原图、可试戴纹理、标签、创建时间、审核状态和删除策略。

### 4.4 `/ai-generate` AI 生图

状态：待验证。

使用方式：输入 1～500 字符描述，或选择预设风格按钮循环填入详细提示词，点击生成；成功后前端显示外部服务返回的远程图片 URL，并尝试跨域下载，失败时在新窗口打开图片。前端只向本项目 API 发送文字，不发送用户照片。

风格提示词库：`src/lib/ai-style-prompts.ts` 导出 `AI_STYLE_PROMPTS`，包含 10 个风格（甜美风、欧美风、日系、极简、复古、节日、水墨、几何、花草、金属），每个风格 50 段独立的中文场景提示词。用户点击风格按钮时，按轮转索引依次填入该风格的下一段提示词，第 50 段后回到第 1 段。提示词描述了底色、装饰、甲型、手持道具、光线、背景和皮肤质感等完整场景。`src/lib/utils.ts` 中原有的 `AI_STYLES` 字符串数组仍保留以维持向后兼容，但 `/ai-generate` 页面已改为从 `AI_STYLE_PROMPTS` 读取。

前置条件：

```env
OPENAI_API_KEY=有效的服务端密钥
```

限制：当前代码固定请求 `dall-e-3`、`1024x1024`、`standard`，超时 30 秒。该模型名称和接口可用性属于外部依赖，正式部署前必须重新确认并完成联网实测。AI 输出不会自动进入图库、编辑器或 AR，当前需要用户先下载再手动上传。

### 4.5 `/ar-tryon` AR 试戴

状态：待验证。

使用方式：

1. 选择“纯色”或“纹理”；
2. 纯色模式可逐指选色或应用全部；
3. 纹理模式可上传单个纹理手动裁剪，也可上传参考图自动识别多个候选；
4. 点击画面内唯一的“开启摄像头”按钮；该次点击会直接调用摄像头权限请求，不需要再点第二个启动按钮；
5. 将手放入画面并展示手背，系统根据手部关键点绘制指甲；
6. 手心、手背或不确定状态会显示对应提示，手心状态不绘制指甲纹理。

上传约束：PNG/JPEG/WebP，最大 10 MB，宽高各 320–4096 像素，并要求浏览器可成功解码；编辑器与AR共用同一校验器。摄像头画面只在内存中处理，不录制、不上传。

运行约束：当前 `maxNumHands: 1`、`modelComplexity: 0`，检测和跟踪阈值均为 `0.5`。`hands.js`、WASM 和相关 MediaPipe 文件从固定版本的 jsDelivr URL 加载，脚本等待超时为 15 秒；离线、CSP 限制或 CDN 故障会导致 AR 无法启动。

摄像头启动故障排查顺序：

1. 确认项目服务正在运行，并通过 `http://localhost:3000/ar-tryon` 或有效 HTTPS 地址访问；
2. 页面初始状态只能出现一个“开启摄像头”按钮；点击一次后应立即显示“请求摄像头权限...”及诊断步骤 `1/7`；
3. 浏览器弹出权限请求时选择允许；若曾拒绝，在地址栏网站权限中重新允许并刷新；
4. 若显示设备占用，关闭系统相机、视频会议及其他占用摄像头的应用；
5. 摄像头画面启动后若停在“加载手部识别”，检查 jsDelivr 网络访问或 CSP；此时摄像头权限本身已经成功。

2026-07-14 修复：`/ar-tryon` 页面原先先显示外层启动按钮，第一次点击只挂载 `ArView`，随后 `ArView` 又显示第二个同名按钮，必须点击两次才会调用 `getUserMedia()`。现已移除页面外层 `isStarted` 门控，始终挂载 `ArView`，由组件内部唯一按钮直接处理用户手势和权限请求。浏览器 DOM 验证确认初始按钮数量为 1，一次点击后进入 `1/7 请求摄像头权限...`。自动化应用内浏览器无法提供真实摄像头设备，本轮不把该状态转换验证当作真机画面验收，模块继续保持“待验证”。

主要组件：

```ts
<ArView
  nailColors={string[]}
  nailTextures={(ImageBitmap | null)[] | undefined}
  mode={"color" | "texture" | undefined}
/>

<TextureCropper
  imageUrl={string}
  onConfirm={(bitmap: ImageBitmap) => void}
  onCancel={() => void}
/>

<NailArtPicker
  imageUrl={string}
  onConfirm={(assignments: NailAssignment[]) => void}
  onCancel={() => void}
/>

interface NailAssignment {
  texture: ImageBitmap;
  diagnostics?: TextureExtractionDiagnostics;
  finger: number;
}
```

约定上页面始终传入 5 个颜色/纹理槽位并使用手指索引 `0..4`，但组件公开的 TypeScript Props 当前只是普通数组和 `number`，没有在类型层强制长度或索引范围；外部调用方必须自行校验。

AR 内部关键契约：

```ts
type HandOrientation = "dorsum" | "palm" | "ambiguous" | "none";

interface NailGeometry {
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
}
```

朝向语义：`palm` 明确禁止绘制；`dorsum` 允许绘制；`ambiguous` 在 UI 中显示“侧手”，当前采用 fail-open 策略仍允许绘制。状态切换需要连续稳定帧以减少抖动，因此提示不会在单帧内立即变化。这个策略有误贴风险，仍属于真机待验证项。

视频布局使用 `calculateCoverVideoLayout(videoWidth, videoHeight, viewportWidth, viewportHeight)`，输出缩放后的显示尺寸和居中偏移。宽屏转竖屏时从左右两侧对称裁切，竖屏转宽屏时从上下两侧对称裁切，不做非等比拉伸。

## 5. HTTP API 契约

### 5.1 `POST /api/generate-ai`

状态：待验证。

请求：

```http
POST /api/generate-ai
Content-Type: application/json

{"prompt":"银色亮片渐变，月光质感"}
```

成功响应：

```json
{"imageUrl":"https://..."}
```

错误响应统一格式：

```json
{"error":"错误说明"}
```

| HTTP 状态 | 含义 |
| --- | --- |
| 400 | 非法 JSON、空描述或超过 500 字符 |
| 401 | 外部 API 密钥无效 |
| 429 | 外部 API 限流 |
| 500 | 未分类服务端异常 |
| 502 | 外部 API 错误或响应缺少图片 URL |
| 503 | 未配置 `OPENAI_API_KEY` |
| 504 | 30 秒超时 |

当前未实现鉴权、用户配额、内容审核记录、请求幂等、结果持久化和计费统计；正式开放前必须补齐相应治理能力。

## 6. 浏览器端美甲纹理识别接口

### 6.1 对外入口

公共 barrel 位于 `src/lib/nail-texture-recognition/index.ts`。业务主入口是 `recognizeNailTexturesInWorker()`；底层同步流程入口是 `recognizeNailTextures()`：

```ts
async function recognizeNailTexturesInWorker(
  source: ImagePixels,
  options?: RecognizeNailTexturesOptions
): Promise<NailTextureRecognitionResult>

async function recognizeNailTextures(
  source: ImagePixels,
  options?: RecognizeNailTexturesOptions
): Promise<NailTextureRecognitionResult>
```

`ImagePixels` 的实际结构为 `{ width: number; height: number; data: ArrayLike<number> }`，浏览器 `ImageData.data` 的 `Uint8ClampedArray` 是兼容输入之一。

同一 barrel 还导出 manifest/runtime、预处理、后处理、质量排序、mask 提取、反光修复、debug 对比、首跑记录验证和 Worker 生命周期接口。这些属于内部研发接口，除上述识别入口和稳定类型外暂不承诺跨版本兼容；新增外部调用方前必须在本节登记具体函数、输入输出和兼容策略。

主要选项：

```ts
interface RecognizeNailTexturesOptions {
  preferModel?: boolean;
  manifestUrl?: string;
  maxCandidates?: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  debugOutputs?: boolean;
  debugRawModelOutputs?: boolean;
  signal?: AbortSignal;
}
```

主要返回：

```ts
interface NailTextureRecognitionResult {
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  workerElapsedMs?: number;
  modelVersion?: string;
  warnings: string[];
}

interface NailTextureCandidate {
  id: string;
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  score: number;
  confidence: "high" | "medium" | "low";
  source: "model" | "mediapipe" | "saliency" | "manual";
  mask?: NailMask;
  warnings?: string[];
  suggestedFinger: number | null;
}
```

### 6.2 运行策略

1. 直接调用 `recognizeNailTextures()` 时只有显式传入 `preferModel: true` 才加载模型，否则直接使用 fallback；`recognizeNailTexturesInWorker()` 默认将 `preferModel` 设为 `true`；
2. 优先尝试 WebGPU，不支持时回退 WASM；
3. 模型加载、推理、Worker 或后处理失败时返回 fallback 结果和 warning；
4. 候选经过置信度评估、角度稳定、手指建议和纹理提取；
5. UI 必须展示低置信度或提取质量告警，并允许用户人工调整或取消。

当前 `NailArtPicker` 将检测输入最长边限制在 800 像素，最多请求 10 个候选，Worker 超时为 15 秒。候选确认后以 `NailAssignment[]` 返回，每个 `ImageBitmap` 的所有权转移给 `/ar-tryon` 页面，页面在替换或卸载时负责释放。

环境变量：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg/manifest.json
```

开发烟雾验证可临时指向：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg-smoke/manifest.json
```

`.env.local.example` 默认不再启用 manifest 覆盖；直接复制时由代码使用 `/models/nail-texture-seg/manifest.json`。只有受控 smoke 验证才应临时取消示例注释并指向 smoke manifest。回归测试会拒绝示例文件中任何启用状态的 `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL`，避免测试模型成为共享默认值。在正式 ONNX 缺失期间，默认正式路径仍会进入 fallback，不代表正式模型已经可用。

烟雾/合成模型只验证工程链路，不得用于宣称真实美甲识别质量。结果顶层 `backend: "model"` 只表示走了模型路径；实际执行提供程序 `webgpu`/`wasm` 位于 `modelInfo.backend`。

### 6.3 Worker 消息契约

```ts
interface RecognizeNailTextureRequest {
  id: string;
  imageBitmap: ImageBitmap;
  maxCandidates: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  preferModel: boolean;
  manifestUrl?: string;
}

interface RecognizeNailTextureResponse {
  id: string;
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  warnings: string[];
  modelVersion?: string;
  modelInfo?: NailTextureModelInfo;
}
```

调用方应在超时、取消、页面卸载或更换图片时释放 `ImageBitmap` 和 Worker 资源。当前 Worker 超时后会重置 Worker，并通过主线程 fallback 尝试返回降级结果；用户取消会重置 Worker 并以 `AbortError` 拒绝当前请求，不执行 fallback。调用方必须分别处理异常和 `warnings`，不能只检查是否返回候选。

### 6.4 纹理提取接口

```ts
extractTexture(imageUrl, { x, y, w, h }): Promise<ImageBitmap>
clampTextureSize(bitmap, maxSize?): Promise<ImageBitmap>
disposeTexture(bitmap): void
disposeAllTextures(bitmaps): void
```

普通裁剪输出最大边默认不超过 256 像素。自动识别路径支持带 mask 的透明纹理提取、羽化边缘、反光检查/修复和诊断信息。

## 7. 模型产物契约

正式 manifest 路径：`public/models/nail-texture-seg/manifest.json`。

```json
{
  "version": "nail-texture-seg-v1",
  "inputSize": 640,
  "inputLayout": "NCHW",
  "colorOrder": "RGB",
  "normalization": "zero_to_one",
  "resizeMode": "letterbox",
  "task": "segment",
  "backendPreferences": ["webgpu", "wasm"],
  "modelFile": "nail-texture-seg-v1.onnx",
  "outputContract": "ultralytics-seg-raw-v1",
  "scoreThreshold": 0.35,
  "labels": ["nail_texture"]
}
```

`scoreThreshold`是模型版本级候选阈值：运行时、原始输出过滤和质量排序使用同一有效值；字段缺省时保持`0.35`兼容，显式值必须为0和1之间的有限数。`export-onnx.py`可通过`--score-threshold`写入校准值，浏览器manifest校验和`verify-model-artifact.ts`执行相同约束。该字段只是保存已完成验证的模型校准结果，不能用单次阈值扫描绕过误检、候选数量、直接可用率或Beta发布门。

正式阈值必须由`calibrate-model-score-threshold.py`使用来源隔离的`val`预测生成。校准器绑定数据集、来源报告、模型权重、评估指标和预测制品SHA-256，拒绝`test`/冻结发布测试、val来源跨split和未知预测文件；`--truth-audit`还必须提供`approved_as_calibration_truth`报告，且dataset路径/哈希、逐标签SHA-256、预期/已审/通过数量全部一致、返修和排除均为0。未提供审核或审核明确拒绝时分别输出未审核/已拒绝诊断，永远不生成manifest阈值。至少30张验证图、真值polygon零修复、所有验证图通过原分辨率完整甲面审核，同时满足召回、每图误检和单图候选数门，才输出非空`manifestScoreThreshold`。任何返修/排除项、未声明交叠、漏甲、重复、误标、污染或边缘裁断都会使整套split失去校准资格。

规范校准不能直接让Ultralytics读取受审核数据根目录：标签扫描会自动创建`labels/*.cache`并污染不可变物化清单。`evaluate.py`现在先把所选split的图片与标签逐文件复制到输出侧`evaluation-runtime-dataset`，运行YAML只指向该副本，并在物化后和推理结束后重算源数据整树相对路径及逐文件SHA-256；源树任一新增、删除或字节变化都会拒绝证据。评估制品按POSIX相对路径字符串稳定排序，绑定逐文件SHA-256及覆盖每张验证图的`prediction_records`，无预测图必须显式记录为零而不是从清单消失。v6在规范val30部署512上的box/mask mAP50为0.6241/0.5630；confidence=0.05时召回0.7569但每图误检9.8333、单图最多28候选，其余扫描点召回均低于0.75，因此没有合格manifest阈值。

正式发布要求：

- manifest 通过结构校验；
- ONNX 文件存在，文件名与 manifest 一致；
- 输入/输出名称和张量形状与后处理契约一致；
- 通过 fixture、真实图片、浏览器集成和性能门；
- 具备版本、SHA-256、体积、指标、发布和回滚记录。

当前结论：v6 ONNX 已在隔离导出目录通过资产、输出协议与桌面 WebGPU 性能门，但冻结67张扩展发布测试在部署512下未通过质量门，因此不再是可发布候选；生产 manifest 仍指向缺失的 `nail-texture-seg-v1.onnx`，`real-model-final-audit-report.json` 的生产决策继续为 `blocked`。现有 synthetic 与 smoke 模型仍只能作为工程测试资源。

## 8. 数据集与训练接口

### 8.1 数据集契约

数据集根目录：`model/datasets/nail-texture-v1`。

核心版本：`nail-texture-dataset/v1`。标注以多边形 mask 为主，可转换为 YOLO segmentation 格式。必须维护素材来源、授权、哈希、审核状态、数据切分和负样本信息。

旧的`audit-dataset-source-isolation.py`与`audit-candidate-training-validation.py`保留为历史实验数据诊断工具，但其外层PASS不再能够单独授权正式候选训练。正式链路先运行`materialize-canonical-candidate-training-dataset.py`：必须绑定当前训练真值唯一索引、`approved_hard_negative_manifest`、规范val-only `dataset.yaml`及`approved_as_calibration_truth`终审、冻结发布测试清单；在写目录前固定核验train正样本不少于100张、正式hard negative不少于100张、val不少于30张，并重算四角色文件名、图片SHA-256和来源组零重叠。输出采用事务式目录替换，固定`images/labels train|val|test`，其中hard negative标签必须为零字节、test必须为空，`records`、`datasetFiles`、角色身份和全部聚合哈希写入物化报告。

`approved_hard_negative_manifest`只能由`finalize-reviewed-hard-negative-manifest.py`生成。schema v2终结器重放每批候选清单、原分辨率审核决定、A授权、当前图片哈希和既有来源隔离证据，并固定不少于100张；数量不足时只输出`HOLD`、`trainingUse=prohibited`及不可消费的`candidateItems`。图片在批准前必须由Pillow完成结构验证和完整像素解码，最短边不少于320像素，当前宽高必须与审核记录一致；损坏文件、文本伪装图片或审核/授权漂移均拒绝。若内容是受支持的真实图片格式但扩展名错误，源文件和审核身份不改，正式物化文件名按解码格式规范化。角色隔离器、候选物化器和GPU前输入审计都会调用该终结器的`verify_approved_report()`重放当前证据；输入审计还会再次解码物化后的负样本。

物化成功后必须运行`audit-candidate-training-input.py`，它不信任物化报告外层PASS，而是独立重算上游allow-list、训练annotation到YOLO label转换、val终审逐项等价、polygon合法性与任意非零交叠、负样本空标签、孤儿文件和四角色隔离；正式100/100/30下限不能由CLI调低。`train-yolo-seg.py --candidate-mode --candidate-input-report <report>`在创建训练输出、加载Ultralytics和占用GPU前调用`verify_approved_report()`深度重放当前字节；训练结束后再重放一次，数据中途漂移时不生成合格候选摘要。普通运行仍记录`training_intent=experiment`，旧`--candidate-validation-report`明确拒绝作为候选授权。

候选模型的部署口径val评估必须使用上述只读runtime副本和不可复用的新输出目录；`val-metrics`同时绑定原dataset YAML、权重、源树前后inventory、runtime物化记录和评估制品索引。`calibrate-model-score-threshold.py`对规范模式再次调用validation终审器，重放truth index、物化报告、角色隔离、图片、annotation、label、polygon合法性和零交叠；旧`experiment_only_source_isolated_real_dataset`只允许输出诊断，不能产生manifest阈值。

训练发布编排器使用三路权威证据：`run-training-release-pipeline.ts --candidate-mode`除训练dataset和`candidate-input-report`外，还必须提供规范val的dataset、物化报告、校准真值终审和校准输出，以及冻结release-test的dataset与物化报告；三套dataset路径必须不同，候选模式禁止通用`--split`、`--skip-evaluate`和`--skip-export`。`candidate-input-preflight`与冻结test的`--verify-report`在环境检查/GPU前执行，随后顺序固定为训练、val评估、阈值校准、冻结test评估和证据化导出。恢复训练仍须绑定同一dataset路径/SHA-256、输入报告路径/SHA-256及权重SHA-256；任何不一致都在评估、导出和治理之前停止。dry-run只展示全部命令且不启动Python/GPU，不能生成授权证据。

冻结release-test物化报告为schema v2，绑定冻结manifest路径/SHA/`itemsSha256`、训练身份、三份dataset YAML、评估manifest、core/stress记录及整棵输出树逐文件与聚合SHA；固定test非空、train/val为空、`trainingUse=prohibited`。`materialize-frozen-release-test-evaluation.py --verify-report`会重新读取源manifest、训练sources、图片、annotation、YOLO label、polygon拓扑、来源隔离和当前文件清单，拒绝伪造PASS、写后漂移或dataset错配。`calibrate-model-score-threshold.py --verify-report --expected-weights`同样重放规范val全链路；`export-onnx.py --candidate-mode --calibration-report`禁止手工`--score-threshold`，manifest的`scoreThresholdEvidence`必须记录报告、dataset、metrics、制品索引和权重SHA。最终`verify-training-release.ts --candidate-mode`再次要求release metrics为`split=test`，重算test全树、预测制品和阈值证据，防止把val结果误当发布质量。

当前 readiness 快照：

| 指标 | 当前值 |
| --- | ---: |
| 图片 | 409 |
| mask | 2142 |
| 有效 mask | 2142 |
| train / val / test | 300 / 46 / 63 |
| 错误文件 | 0 |
| warning 文件 | 2 |

2026-07-13 实拍数据继续同步：对剩余 37 张返修图执行 v6 640/conf=0.20 与 1024/conf=0.10 跨分辨率 polygon 共识筛选，得到 34 图/209 个稳定候选；五页联系表和原分辨率复核证明共识仍会保留拼图重复区域、皮肤污染和漏甲，因此自动输出继续标记为候选而非训练真值。仅 2 张/9 mask 通过整图视觉门，第二批累计 77 张正样本、1 张 hard negative、507 个 mask 正式导入，35 张继续返修。正式集更新为 400 图/2092 mask、split=293/45/62，400 条来源授权、标签、split 比例及训练 readiness 均通过。

同日继续对35张返修图执行3×3重叠分块推理：19张产生88个候选并拒绝32个tile边缘碎片，但装饰圆点误检、漏甲和拼图区域混淆使五页视觉门0张通过。随后对4张最接近完成的非拼图图执行33个视觉紧框+SAM2提示，3张生成多边形、1张因失焦返回空mask；原分辨率复核确认其中3张存在画面边缘截断甲面、1张存在不可恢复的失焦背景甲面，统一从训练候选中排除。当前批次为78张通过、4张排除、31张继续返修；正式训练集未变化。

2026-07-13 再对6张非拼图返修图执行24个视觉紧框+SAM2提示并逐张查看原分辨率叠加图：仅单指近景图的1个mask完整覆盖甲面且无明显皮肤/背景污染，正式提升；其余5张仍存在粘连皮肤、袖口或相邻区域，继续返修。另有1张右侧甲面被源画面裁断，按完整甲面源图门禁排除。第二批更新为79张通过（78正样本、1 hard negative）、5张排除、29张返修，正式集更新为401图/2093 mask、split=293/45/63，来源授权与训练数据readiness继续通过。

同日继续从29张返修图中筛选6张清晰 Deerplanet 素材，先对3张配置27个逐甲紧框执行SAM2，再对其中2张以19个收紧框和box-center提示复跑。原分辨率叠加图只接收1张/8 mask；另2张仍有皮肤外溢、轮廓缺口或双色甲面分割不完整，继续返修，其余3张也未因画面清晰而绕过标注门禁。第二批更新为80张通过（79正样本、1 hard negative）、5张排除、28张返修；正式集更新为402图/2101 mask、split=294/45/63，402条来源审计和release readiness通过。该增量不改变v6冻结13张真实test评估，也不解除100–200张代表性真实测试集、移动真机和Beta人工质量门的HOLD。

同日对余下3张清晰Deerplanet返修图执行25个逐甲紧框，并针对低对比甲面追加9个收紧框、两轮各9个box-center定点复跑。2张虽生成多边形但仍有皮肤外溢或局部轮廓缺口，1张低对比图在第6/9提示上返回空mask，原分辨率审核0张提升，队列仍为80通过、5排除、28返修。辅助标注脚本已补充FastSAM/SAM2提示序号、提示模式和polygon转换阶段错误定位；复跑报告可直接指出`prompt 6 (box)`与`prompt 9 (box-center)`，避免把单甲失败误报为不可定位的整图失败。数据集未变化，来源与训练readiness仍通过；总体MVP readiness继续因生产ONNX缺失而按预期失败。

同日对28张返修源图生成四页新联系表，确认其中18张为“真实照片+界面文字/重复圆图或双图排版”的截图素材。新增受审计区域提取器，以父文件名、归一化框和区域ID生成确定性派生PNG，并记录父子SHA-256、像素框、尺寸和按父图稳定的`sourceGroup`。首批9张小红书截图各提取1个主照片区域，9/9成功且联系表确认已移除页面UI与重复圆图；v6在派生图上以1024/conf=0.10生成92个候选，但重复框和少量误检使其继续保持`candidate_only_not_training_truth`。原截图仍为返修，正式集仍是402图/2101 mask，下一步对9张派生图执行逐甲SAM2和原分辨率审核。

随后以1024/conf=0.30复跑v6，候选由92个收敛至64个，但仍存在漏甲、重复框和装饰误检，继续仅作紧框定位。对9张派生图逐甲执行SAM2并查看原分辨率叠加图：7张/41个mask通过，2张因花朵装饰分离或装饰/玩偶边缘误分继续返修；3个触及裁剪边界的不完整甲面明确排除。`sam-assisted-nail-annotation.py`现允许每张图覆盖`sourceGroup`，机器审计会核对派生图SHA-256、尺寸、父图稳定分组、标注数量、多边形边界与面积；本轮审计9/9有决策、0错误。通过项尚未安全导入正式集，因此正式集仍为402图/2101 mask，原截图审核状态和发布HOLD不变。

7张通过派生图随后经独立intake批次安全导入。清单逐图保留区域提取报告给出的父图稳定`sourceGroup`，授权继承自`real-reference-2026-07-12-batch-02`的`user-authorized-commercial-training-and-long-term-regression`，来源记录同时写入父文件名、父SHA-256、区域ID和归一化裁剪框。正式集更新为409图/2142 mask、split=300/46/63；7张派生图中6张进入train、1张进入val，父组无跨split。来源审计、release授权、标签审计、split完整性、训练数据物化和readiness均通过。2张派生图及对应原截图继续返修；冻结13张真实test、v6指标和生产HOLD不变。

同日登记 `E:\AI Project\Codex\JiaRu_image\claude\2026_7_13` 的1001张新增生成素材：1001/1001可解码且均为1024×1024 PNG，批内无精确/近重复，与导入前400张正式集无精确SHA-256或同dHash重复。11页视觉联系表显示其主体清楚但具有明显合成模板分布，只登记为合成训练候选池；在本批商业训练/长期回归授权和逐图标注审核完成前，不导入正式集，也不得用于真实test或发布门禁。

同日接收 `E:\AI Project\Codex\JiaRu_image\真实素材\2026_7_13` 的101张真实美甲图，并按 `real_release_20260713_001.jpg` 至 `real_release_20260713_101.jpg` 两阶段安全改名；`rename-manifest.json` 保留原文件名、来源标题/作者/序号、来源组和SHA-256，可回溯且101/101改名前后哈希一致。解码、尺寸、批内及跨语料审计通过：批内无精确或dHash≤2近重复，与409张正式原图、2026_7_11及2026_7_12旧素材共543张参照比较后发现9张跨批精确重复，均已排除；其余92张按57张单照片核心图和35张截图/拼图压力图进入独立发布测试与长期回归intake，19个来源组，用户授权明确禁止训练用途。

v6以1024/conf=0.30为101张图生成852个定位候选，核心57张再以345个逐甲框运行SAM2，57/57完成、0失败；几何审计为310个pass、35个suspect，但该结果仅能证明候选相对提示框的几何关系，不能替代整图漏甲、源图裁断和皮肤污染审核。原分辨率视觉复核后仅8张/59 mask、4个来源组暂通过，48张返修，1张因左侧甲面被画面裁断排除，35张压力图仍待第二阶段拆图/复核。新增样本尚未成为冻结test真值，100–200张代表性发布测试门和生产HOLD不变。

随后完成35张截图/拼图压力父图的主照片区域提取：35/35成功，报告逐项核对父图SHA-256、归一化/像素裁剪框、派生SHA-256及父图稳定`sourceGroup`；新增`build-release-test-region-intake.py`从原发布测试intake继承独立发布测试/长期回归授权，并强制`trainingUse=prohibited`、父项必须为stress、父子哈希一致且每父图仅一个主区域。v6在35张派生区域上生成201个候选，SAM2处理201/201、0失败；几何审计183 pass/18 suspect，但原分辨率整图门仅接受2张/10 mask，33张因漏甲、重复/重叠mask、皮肤污染或裁剪边缘问题返修。至此92张非重复父图均完成首轮处理，累计10张/69 mask暂通过、81张返修、1张源图裁断排除；仍不计入冻结test真值。

首个返修批次使用`build-reviewed-sam-repair-prompts.py`按人工逐图决定保留正确提示、删除重复/背景误检并预留补充漏甲框；输出固定记录源提示与修复清单SHA-256、逐图`sourceGroup`和候选用途。选取5张核心返修图共25个提示重跑SAM2，25/25成功且几何审计25 pass/0 suspect；原分辨率复核提升4张/20 mask，另1张因遮挡布料附近轮廓仍不完整继续返修。`build-release-test-annotation-review.py`支持按顺序叠加修复报告并核对最终polygon数与来源组；`build-release-test-review-summary.py`将压力派生决定映射回父图、强制训练禁用并证明92张父图全覆盖。累计结果更新为14张/89 mask暂通过、77张返修、1张源图裁断排除、7个暂通过来源组；仍为候选审核结果，不是冻结test真值。

第二轮返修从核心返修集中选择6张/29个逐甲提示，按人工keep/drop/add清单重跑SAM2；29/29完成且几何审计29 pass/0 suspect。原分辨率逐图复核只接受002与027两张共9个完整甲面mask；001、051、052、091仍因大面积皮肤污染、相邻手指区域混入或触及画面边界继续返修。分层审核与父图聚合后，核心集为14张/88 mask通过、42张返修、1张排除，92张父图总计16张/98 mask暂通过、75张返修、1张源图裁断排除，仍只有7个通过来源组；训练用途继续固定为prohibited，几何通过不替代视觉真值审核。

第三轮返修补充逐新增框提示模式：`build-reviewed-sam-repair-prompts.py`现在保留来源提示模式，并允许逐框选择`box`、`center`、`box-center`或`center-negative-corners`，同时拒绝数量不匹配和非法模式。对031、050、079、082、090五张高潜力返修图保留正确mask、删除污染/重复/背景提示，并用5个`box-center`紧框替换问题甲面；24/24提示完成、0 fallback，几何审计24 pass/0 suspect，原分辨率复核5张/24 mask全部通过。核心集更新为19张/112 mask通过、37张返修、1张排除；92张父图总计21张/122 mask暂通过、70张返修、1张源图裁断排除、9个通过来源组。结果继续隔离为发布测试候选且禁止训练。

第四轮返修选取004、022、043、044、064、080六张高置信候选，按人工决定删除污染/重复提示、补齐漏甲并生成30个逐甲提示；SAM2完成30/30、0 fallback，几何审计30 pass/0 suspect。原分辨率复核没有把几何绿灯直接当作真值：004仍有皮肤外溢、022只覆盖装饰层、080仍吸收衣物，三张继续返修；043、044、064共3张/15 mask通过。核心集更新为22张/127 mask通过、34张返修、1张排除、9个来源组；父图聚合更新为24张/137 mask暂通过、67张返修、1张源图裁断排除、10个通过来源组，训练用途继续`prohibited`。

第五轮返修将`center-negative-corners`集中用于004、022、033、045、048、071、080七张复杂图，37/37提示完成、0 fallback，几何审计37 pass/0 suspect。原分辨率只接受033、045、048共3张/18 mask；004、022、071、080仍因皮肤/衣物污染、透明延长甲漏分或整段手指误分继续返修。另对剩余队列重新执行源图完整性门，034与070因甲面触及画面边缘且露出不全转为排除。核心集更新为25张/145 mask通过、29张返修、3张排除、9个来源组；父图聚合更新为27张/155 mask暂通过、62张返修、3张排除、10个通过来源组，训练用途继续`prohibited`。

第六轮返修选取051、052、054、077、083、091六张重复/漏甲候选，生成31个提示；31/31完成、0 fallback，几何审计31 pass/0 suspect。原分辨率严格执行“完整露出甲面必须由单一完整mask覆盖”的优先规则，只接受051、054、077共3张/16 mask；052重复覆盖、083吸收衣袖、091只覆盖左拇指装饰区域，均继续返修。049因拇指甲触及图片下边界且露出不全转为排除。核心集更新为28张/161 mask通过、25张返修、4张排除、10个来源组；父图聚合更新为30张/171 mask暂通过、58张返修、4张排除、11个来源组，训练用途继续`prohibited`。

第七轮返修选取023、024、067、073、075、084六张完整性高风险图重建或清理40个提示；SAM2完成40/40、0 fallback，几何审计38 pass/2 suspect。原分辨率视觉门没有接受任何新mask：024与075仍吸收背景/皮肤，067只覆盖有色区域而漏掉透明延长甲，073替换mask仍跨入手指，四张继续返修；023的背景手指甲被画面上/右边缘裁断，084的重叠手势遮挡必需甲面，转为排除。同期复核085的绸布遮挡与088的杯体/重叠手遮挡，也按源图完整性规则排除。核心集保持28张/161 mask通过，更新为21张返修、8张排除、10个来源组；父图聚合保持30张/171 mask暂通过，更新为54张返修、8张排除、11个来源组，训练用途继续`prohibited`。该轮明确允许“0个新mask通过”的真实审核结果，不用放宽完整甲面门换取表面通过率。

第八轮先补齐多点提示契约：`build-reviewed-sam-repair-prompts.py`现在可逐框保留或新增`positivePoints`与`negativePoints`，校验数组数量、点结构和归一化边界，并在修复来源中记录新增正负点数量；`sam-assisted-nail-annotation.py`独立复核输入并按实际正负点数构造标签，自定义负点会替代默认四角负点。专项5/5通过。随后用067的5个透明延长甲验证：每甲两个正点覆盖有色基底与透明甲尖，右侧污染区用定向负点压制；SAM2完成5/5、0 fallback，几何5 pass/0 suspect，原分辨率确认5个单一mask均覆盖完整可见甲面且无皮肤/袖口污染。核心集更新为29张/166 mask通过、20张返修、8张排除、10个来源组；父图聚合更新为31张/176 mask暂通过、53张返修、8张排除、11个来源组，训练用途继续`prohibited`。

第九轮将完整轴向多正点与甲根/背景定向负点应用于024和075共10个长甲与低对比裸色甲面。SAM2完成2张/10提示、0 fallback，几何审计9 pass/1 suspect；024的立体钻饰使第2个提示中心不在polygon内，但原分辨率确认该单一mask仍完整覆盖甲面和附着装饰且无皮肤/背景污染。075在三次收紧甲根框和补充皮肤、纸巾负点后，5个单一mask完整覆盖裸色甲面。原图视觉门接受2张/10 mask，核心集更新为31张/176 mask通过、18张返修、8张排除、11个来源组；父图聚合更新为33张/186 mask暂通过、51张返修、8张排除、12个来源组，训练用途继续`prohibited`。

第十轮独立处理073的双手9甲相邻长甲难例，废弃v8中漏掉带钻白色延长段及跨入下手手指的局部mask，对9个甲面全部使用甲尖、甲中、甲根轴向正点及相邻皮肤定向负点重建。SAM2完成1张/9提示、0 fallback，几何审计9 pass/0 suspect；原分辨率确认上下两手全部完整露出甲面均为一甲一mask，白色延长段与下手相邻三甲完整分离且无皮肤污染，接受1张/9 mask。核心集更新为32张/185 mask通过、17张返修、8张排除、11个来源组；父图聚合更新为34张/195 mask暂通过、50张返修、8张排除、12个来源组，训练用途继续`prohibited`。

第十一轮处理同一来源组的025与026，各用5个完整轴向多点提示替换首轮漏甲、电视背景、戒指和床品误检。SAM2完成2张/10提示、0 fallback，几何审计10 pass/0 suspect；原分辨率视觉门只接受025的5个完整mask，其裸色拇指甲面及立体钻饰由单一mask完整覆盖且没有越过甲根。026虽然几何通过，但拇指候选仍吸收矩形皮肤区域，继续返修。核心集更新为33张/190 mask通过、16张返修、8张排除、11个来源组；父图聚合更新为35张/200 mask暂通过、49张返修、8张排除、12个来源组，训练用途继续`prohibited`。

第十二轮处理065与071共10个低对比裸色/透明甲面，全部用完整轴向多正点和甲根、衣物定向负点重建。SAM2完成2张/10提示、0 fallback，几何审计9 pass/1 suspect；suspect来自065拇指提示中心不在污染多边形内。原分辨率视觉门只接受071的5个完整mask，侧向透明拇指完整纳入且中央两甲的甲根污染已消除；065拇指仍吸收牛仔布与皮肤，继续返修。核心集更新为34张/195 mask通过、15张返修、8张排除、11个来源组；父图聚合更新为36张/205 mask暂通过、48张返修、8张排除、12个来源组，训练用途继续`prohibited`。

第十三轮处理080与091共10个提示，全部重建为每甲单一完整轴向多正点并配置甲根、皮肤或背景定向负点。SAM2完成2张/10提示、0 fallback，最终几何审计10 pass/0 suspect；080首轮拇指正点落入皮肤后立即收紧框和轴向点，原分辨率确认5个完整露出甲面均由单一mask覆盖且不再吸收大块皮肤，接受1张/5 mask。091最右侧小拇指甲面被图片右边界裁断，按源图完整性门直接排除，不用局部mask补救。核心集更新为35张/200 mask通过、13张返修、9张排除、11个来源组；父图聚合更新为37张/210 mask暂通过、46张返修、9张排除、12个来源组，训练用途继续`prohibited`。

第十四轮独立处理078的双手10甲难例：旧结果将上下两枚蝴蝶结甲拆成局部/重复mask并漏掉下手拇指，因此废弃全部旧提示，对10个甲面分别使用完整轴向多正点与相邻皮肤定向负点重建。SAM2完成1张/10提示、0 fallback，几何审计10 pass/0 suspect；原分辨率确认上下两手全部完整露出甲面均为一甲一mask，两枚立体蝴蝶结随完整甲面纳入，下手拇指补齐且无重复覆盖，接受1张/10 mask。同期复核069发现左侧长甲尖端被图片左边界裁断，按源图门转为排除。核心集更新为36张/210 mask通过、11张返修、10张排除、11个来源组；父图聚合更新为38张/220 mask暂通过、44张返修、10张排除、12个来源组，训练用途继续`prohibited`。

第十五轮处理001与047共2张/14提示，均以完整轴向多正点和紧邻皮肤/摆件负点重建，SAM2完成14/14、0 fallback，最终几何审计14 pass/0 suspect。原分辨率审核接受001的1张/5 mask：5个完整露出深色甲面均为一甲一mask，收紧后的小拇指不再吸收周围皮肤；047最左低对比紫色甲仍吸收白色摆件，整图继续返修，不以其余8甲通过替代整图门。同期复核081左下甲面被图片左边界裁断，083背景手可见甲面被前景手与袖口遮挡，二者均按源图门排除。核心集更新为37张/215 mask通过、8张返修、12张排除、11个来源组；父图聚合更新为39张/225 mask暂通过、41张返修、12张排除、12个来源组，训练用途继续`prohibited`。

第十六轮定点处理004：保留原分辨率已确认完整的4个深色甲面提示，只对仍吸收下方皮肤的拇指改用收紧框、沿甲面多正点和紧邻皮肤负点。SAM2完成1张/5提示、0 fallback，几何审计5 pass/0 suspect；原分辨率确认5个完整露出甲面均为一甲一mask，拇指不再带入皮肤，接受1张/5 mask。核心集更新为38张/220 mask通过、7张返修、12张排除、11个来源组；父图聚合更新为40张/230 mask暂通过、40张返修、12张排除、12个来源组，训练用途继续`prohibited`。

第十七轮定点处理022：保留原分辨率已确认完整的4个甲面提示，只对甲根和侧边有缺口的右上长甲使用完整轴向多正点及甲根/侧向皮肤负点重建；首跑虽几何5/5通过但仍吸收甲根上方皮肤，视觉门拒绝后下移正点、收紧框并补甲根负点复跑。最终SAM2完成1张/5提示、0 fallback，几何审计5 pass/0 suspect；原分辨率确认右上长甲从甲根到甲尖完整覆盖、链饰随甲面纳入且无皮肤外溢，接受1张/5 mask。核心集更新为39张/225 mask通过、6张返修、12张排除、12个来源组；父图聚合更新为41张/235 mask暂通过、39张返修、12张排除、13个来源组，训练用途继续`prohibited`。

第十八轮定点处理026：保留原分辨率已确认完整的4个手指甲面，只重建先前吸收矩形皮肤区域的拇指。返修清单使用从1开始的提示序号保留前4项，并为拇指配置从甲尖到甲根的4个轴向正点及两侧、甲根外缘6个皮肤负点。SAM2完成1张/5提示、0 fallback，几何审计5 pass/0 suspect；原分辨率确认拇指由单一mask从甲根连续覆盖至甲尖、甲上钻饰被纳入且上一轮矩形皮肤污染消失，接受1张/5 mask。核心集更新为40张/230 mask通过、5张返修、12张排除、12个来源组；父图聚合更新为42张/240 mask暂通过、38张返修、12张排除、13个来源组，训练用途继续`prohibited`。

第十九轮定点处理065：保留原分辨率已确认完整的4个手指甲面，只重建先前吸收牛仔布与皮肤的透明延长拇指甲。沿有色甲面和透明甲尖放置4个轴向正点，并在框两侧、甲根外缘及牛仔布污染区放置6个负点。SAM2完成1张/5提示、0 fallback，几何审计5 pass/0 suspect；原分辨率确认拇指由单一mask从甲根连续覆盖有色甲面和透明延长甲尖，装饰随甲面纳入且不再吸收牛仔布或皮肤，接受1张/5 mask。核心集更新为41张/235 mask通过、4张返修、12张排除、13个来源组；父图聚合更新为43张/245 mask暂通过、37张返修、12张排除、14个来源组，训练用途继续`prohibited`。

第二十轮定点处理052：保留原分辨率已确认完整的3个甲面，删除黑色蝴蝶结甲的两个重叠候选，以4个轴向正点和周边负点重建为单一完整mask；同时为首轮漏标的左下拇指沿裸色甲面至黑色法式甲尖放置4个正点并用6个皮肤/毛衣负点补齐。SAM2完成1张/5提示、0 fallback，几何审计5 pass/0 suspect；原分辨率确认黑色蝴蝶结甲仅有一个完整mask，拇指从甲根到甲尖连续覆盖且无皮肤或毛衣污染，接受1张/5 mask。核心集更新为42张/240 mask通过、3张返修、12张排除、13个来源组；父图聚合更新为44张/250 mask暂通过、36张返修、12张排除、14个来源组，训练用途继续`prohibited`。

第二十一轮定点处理072：源图两只手共10个甲面全部完整露出，保留7个原分辨率已确认完整的mask，仅重建中部两枚交叠长甲与前景蝴蝶拇指。首跑SAM2完成10/10、0 fallback且几何10 pass/0 suspect，但原分辨率视觉门发现蝴蝶拇指下缘仍带入皮肤，因此拒绝首跑并收紧框、上移正点、沿污染边缘补充负点后复跑。最终两枚交叠甲面各由单一完整且互不侵入的mask覆盖，蝴蝶拇指皮肤污染消失，接受1张/10 mask。核心集更新为43张/250 mask通过、2张返修、12张排除、13个来源组；父图聚合更新为45张/260 mask暂通过、35张返修、12张排除、14个来源组，训练用途继续`prohibited`。几何绿灯未被用来替代视觉真值审核。

第二十二轮定点处理047：源图实际可见的9个甲面均完整露出，保留v16中已通过原分辨率复核的8个mask，只重建最左侧低对比紫色甲。通过收紧框、沿甲面配置4个轴向正点，并在相邻白色摆件、皮肤和框外缘配置7个定向负点，SAM2完成1张/9提示、0 fallback，几何审计9 pass/0 suspect。原分辨率并排复核确认该紫色甲由单一mask完整覆盖甲根至甲尖，边界止于甲缘且不再吸收白色摆件；接受1张/9 mask。核心集更新为44张/259 mask通过、1张返修、12张排除、13个来源组；父图聚合更新为46张/269 mask暂通过、34张返修、12张排除、14个来源组，训练用途继续`prohibited`。核心返修队列仅余076。

第二十三轮定点处理076：源图两只手共10个甲面全部完整露出，保留9个原分辨率已确认完整的mask，删除1个手掌和2个腕表误检，仅重建上方手左侧拇指。SAM2完成1张/10提示、0 fallback，几何审计9 pass/1 suspect；suspect来自下方狭长斜向拇指的旧提示中心落在多边形外，原分辨率确认其完整覆盖且无污染。新增拇指从甲根到弯曲异形甲尖由单一mask完整覆盖，未吸收皮肤或木质背景，接受1张/10 mask。核心集更新为45张/269 mask通过、0张返修、12张排除、13个来源组，核心返修队列清零；父图聚合更新为47张/279 mask暂通过、33张返修、12张排除、14个来源组，训练用途继续`prohibited`。

第二十四轮转入压力派生图，优先处理3张非拼图、源图完整且候选接近合格的单手照片。3e9b保留4甲并补拇指，51a2保留4甲、删除黑背景误检并补黑色拇指，e826保留3甲并补上方侧向甲与下方裸粉甲。首跑虽几何15/15通过，但原分辨率拒绝拇指皮肤、侧向甲皮肤及裸粉甲白布污染；经过三次收紧框和定向负点复跑，最终SAM2完成3张/15提示、0 fallback、几何15 pass/0 suspect，15个完整露出甲面均为一甲一完整mask且污染消失，接受3张/15 mask。压力集更新为5张/25 mask通过、30张返修、0排除、5个来源组；父图聚合更新为50张/294 mask暂通过、30张返修、12张排除、16个来源组，训练用途继续`prohibited`。

第二十五轮继续压力派生图返修并补齐几何审计复现入口。新增`audit-sam-prompt-geometry.py`读取提示和多边形，统一输出面积比、提示框包含率、提示中心关系、同图边界框IoU及JSON/CSV；它对第二十四轮15个mask逐行复现0差异，但明确只证明提示一致性。0662保留3个完整mask并两次收紧重建袖口相邻的2甲，d17a经第二次原分辨率审核确认5甲完整且相邻多边形实际交集为0；SAM2最终完成2张/10提示、0 fallback，几何10 pass/0 suspect，接受2张/10 mask。父截图复核同时确认0c2b与6be4的主照片本身在画面边缘裁断必需甲面，转为排除；对bc6b、c541、eac9、f8c5则确认是首轮派生区域选错局部图而非父图不可用，保留到下一轮重新提取，未误排除。压力集更新为7张/35 mask通过、26张返修、2张排除、7个来源组；父图聚合更新为52张/304 mask暂通过、26张返修、14张排除、16个通过来源组，训练用途继续`prohibited`。

第二十六轮落实4个错误派生区域的重提取。`stress-primary-regions-v2.json`按父截图原分辨率重新框定011、096、098、101的主照片，去除011、096、101相邻拼图边缘的半甲干扰；4/4父图SHA-256、派生SHA-256、像素框和稳定`sourceGroup`复核通过。新增`merge-reviewed-region-reports.py`按父图用新区域替换旧区域，强制父哈希与来源组一致，将31个旧区域和4个替换区域物化为仍为35图的一父一派生聚合包；成功路径和来源漂移拒绝测试通过。SAM2对4张/27提示全部生成、1次box-only fallback、0错误；最终几何为22 pass/5 suspect，但视觉门只接受f8c5、bc6b、c541共3张/18个完整mask，eac9的相邻透明长甲在box-center和point-only复跑后仍合并皮肤或邻指，继续返修。压力集更新为10张/53 mask通过、23张返修、2张排除、10个通过来源组；父图聚合为55张/322 mask暂通过、23张返修、14张排除、17个通过来源组，训练用途继续`prohibited`。

外部素材根目录随后完成统一命名治理。除已被发布测试清单和标注稳定引用、继续保留`real_release_20260713_001..101.jpg`的101张发布测试图外，其余5个批次1435张图片统一采用`素材类型_来源_YYYYMMDD_四位序号.原扩展名`：300张早期生成图、1001张Claude新增生成图、21张首批真实训练素材和113张第二批真实训练素材均完成两阶段安全改名。5份本地映射清单逐图保存原名、新名、SHA-256和来源组，改名后1435/1435复算哈希一致且无临时文件；素材及改名映射目录均由`.gitignore`排除，不进入Git。正式数据集内部副本、标注及历史报告继续保留导入时稳定名称，通过SHA-256映射追溯，不改写历史证据；该治理不改变授权、split、标注审核或生产HOLD状态。

2026-07-16 对eac9透明相邻长甲追加SAM2.1 large对照：box和多正负点两种方案均完成9个提示、0错误，各自几何审计均为8 pass/1 suspect；原分辨率叠加图仍显示部分mask合并皮肤、邻指或只覆盖局部甲面，因此大模型候选被拒绝，eac9继续返修，55张/322 mask通过总量不变。该对照再次证明提升模型容量不能替代逐甲提示设计和原分辨率视觉审核。

同日登记 `E:\AI Project\Codex\JiaRu_image\真实素材\2026_7_14` 的1277张新增实拍候选：1277/1277可解码、0个批内精确重复组、70对批内dHash≤2近重复；与正式集物化图及2026_7_11—13旧批共1053张参照比较，0个跨语料精确重复、86对近重复。文件名可归并为196个原始笔记来源组。新增候选intake逐图复算SHA-256和尺寸，以笔记ID的不可逆摘要生成稳定`sourceGroup`，不读取或复制外部元数据中的页面令牌；授权状态固定为`pending-user-confirmation`，`authorizedUses=[]`、`trainingUse=prohibited`。14页全量联系表覆盖1277张并抽查首、中、尾页，确认主体以实拍手部美甲为主，但同时包含拼图、社交平台截图、教程图、近似连续帧和不完整甲面，故当前只通过技术候选入库审计，不代表逐图视觉真值通过，不进入训练集、发布测试集或正式标注。

授权执行时复验发现目录已从初盘1277张变为1271张，原清单中的6张图片已不存在；旧授权尝试因此按漂移规则拒绝，没有以缺图清单继续。重新盘点和重建`corpus-audit-v2.json`、`candidate-intake-v2.json`后，当前1271/1271张可解码、196个来源组、批内0精确重复/70对近重复，跨1053张参照0精确重复/86对近重复。用户选择A，`authorized-intake-A-v2.json`正式登记允许商业模型训练、独立发布测试和长期回归，但逐图审核前每项仍为`trainingUse=prohibited`。外部审核工作区按完整来源组生成28个分片，不复制素材。

`build-real-material-near-duplicate-review.py`把70对批内与86对跨语料近重复渲染为20页双图联系表，并记录原报告、CSV和每页SHA-256；dHash与缩放像素MAE只负责召回候选，不自动排除。20页逐对视觉审核确认86对与既有语料为同一画面、14对为批内重复、52对涉及非照片甲型模板，另4对只是同一手部/场景下甲色或设计不同，保留为同来源相关样本。`finalize-real-material-near-duplicate-review.py`要求全部页面哈希确认和156对决策全覆盖，最终排除105个不重复计数的候选，剩余1166张进入完整甲面逐图审核；本轮判重不等于其余图片质量通过，也不允许跨来源组拆分。

`build-real-material-quality-review-queue.py`绑定原1271张审核工作区和近重复终结报告的文件哈希，扣除105个已裁决候选后，将1166张/193个剩余来源组重新组织为26个质量审核分片，最大分片50张；同一来源组即使超过目标大小也不得拆分。生成的CSV沿用空白审核字段且不复制图片，只有后续逐图填写最终`pass`/`exclude`、完整露出甲数、完整mask数、问题码和用途角色后，才可能进入互斥分配审计。

质量审核分片003的12页审核表覆盖48张/13个来源组，逐文件原分辨率复核后仅19张清晰、完整甲面单图进入待标注候选；7张模糊或低清、7张裁断/遮挡/仅局部甲面、13张拼图和2张护肤品主体图排除。终结器验证48/48决策及逐页哈希，输出继续把`trainingUse=prohibited`和`annotationTruthStatus=not-started`写死。分片001—003累计审核143张，其中72张待标注、71张排除；源图清晰完整只代表可进入标注，不代表已具备训练资格。

质量审核分片004的11页审核表覆盖44张/6个来源组；联系表先排除23张拼图或社交平台页面排版，再对21张非拼图候选逐文件回看原分辨率。9张裁断、重叠遮挡或仅局部甲面以及3张模糊低清排除，仅9张清晰完整单图进入待标注候选。终结器验证44/44决策和逐页哈希，保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`。分片001—004累计审核187张，其中81张待标注、106张排除，剩余979张仍待源图审核。

质量审核分片005的11页审核表覆盖44张/7个来源组。审核时复验报告绑定的`quality-review-queue/shards/quality-review-005.csv`路径、SHA-256和44条条目，未混用工作区内同编号旧CSV；25张非拼图候选逐文件回看原分辨率，19张拼图或社交平台多图排版、4张模糊低清和2张遮挡/仅局部甲面排除，19张清晰完整单场景图仅进入待标注候选。终结器44/44通过，分片001—005累计审核231张，其中100张待标注、131张排除，剩余935张仍待源图审核；所有保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`。

质量审核分片006的13页审核表覆盖50张/9个来源组，并绑定`quality-review-queue/shards/quality-review-006.csv`及其SHA-256。联系表先识别30张拼图或社交平台页面排版，再对20张非拼图候选逐文件打开原分辨率；5张因失焦、低清或块状压缩导致甲缘不稳定而排除，15张清晰且至少存在完整可见甲面的单场景图仅进入待标注候选。终结器验证50/50决定、13页哈希和输入报告哈希全部一致；分片001—006累计审核281张，其中115张待标注、166张排除，剩余885张仍待源图审核。源图通过仍不代表mask真值通过，保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`。

质量审核分片007的12页审核表覆盖47张/7个来源组，并绑定`quality-review-queue/shards/quality-review-007.csv`及其SHA-256。除1张纯人像上下拼接页无手部美甲主体外，其余46张候选逐文件打开原分辨率；4张视频帧因明显像素化、失焦或压缩导致甲缘不稳定而排除，42张清晰且至少存在完整可见甲面的单场景图仅进入待标注候选。终结器验证47/47决定、12页哈希和输入报告哈希全部一致；分片001—007累计审核328张，其中157张待标注、171张排除，剩余838张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片008的11页审核表覆盖42张/9个来源组，并绑定`quality-review-queue/shards/quality-review-008.csv`及其SHA-256。联系表先识别15张拼图或社交平台页面排版，再对27张非拼图候选逐文件打开原分辨率；7张视频帧因明显像素化、失焦或压缩导致甲缘不稳定而排除，2张因画面边缘裁掉已经露出的甲面而排除，18张清晰且至少存在完整可见甲面的单场景图仅进入待标注候选。终结器验证42/42决定、11页哈希和输入报告哈希全部一致；分片001—008累计审核370张，其中175张待标注、195张排除，剩余796张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片009的13页审核表覆盖49张/7个来源组，并绑定`quality-review-queue/shards/quality-review-009.csv`及其SHA-256。联系表先识别23张拼图或社交平台页面排版，再对26张非拼图候选逐文件打开原分辨率；7张因明显失焦、像素化或甲缘细节不足而排除，19张清晰且至少存在完整可见甲面的单场景图仅进入待标注候选。终结器验证49/49决定、13页哈希和输入报告哈希全部一致；分片001—009累计审核419张，其中194张待标注、225张排除，剩余747张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片010的12页审核表覆盖46张/6个来源组，并绑定`quality-review-queue/shards/quality-review-010.csv`及其SHA-256。联系表先识别10张拼图或社交平台页面排版，其余36张逐文件打开原分辨率；3张因画面边缘截断已经露出的甲面而排除，2张因明显像素化、偏软或甲缘细节不足而排除，31张清晰且至少存在完整可见甲面的单场景图仅进入待标注候选。终结器验证46/46决定、12页哈希和输入报告哈希全部一致；分片001—010累计审核465张，其中225张待标注、240张排除，剩余701张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片011的10页审核表覆盖38张/5个来源组，并绑定`quality-review-queue/shards/quality-review-011.csv`及其SHA-256 `1ac31b59cf0f1b9264a8d1f60978185480b3eabff93bd52d7da3cfb89d91e9a4`。审核页识别14张甲型示意模板和10张拼图或社交平台页面排版，其余14张逐文件打开原分辨率；4张因明显像素化、压缩涂抹或失焦到甲缘不稳定而排除，10张清晰且存在完整可见甲面的单场景图仅进入待标注候选。终结器验证38/38决定、10页哈希和输入报告哈希全部一致；分片001—011累计审核503张，其中235张待标注、268张排除，剩余663张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片012的12页审核表覆盖45张/6个来源组，并绑定`quality-review-queue/shards/quality-review-012.csv`及其SHA-256 `df535369bbd12fc969b210120feafea384bd1158fc5a3ec0af05e0ef1350cfec`。45张候选均逐文件打开原分辨率；4张因明显像素化、压缩涂抹或失焦到甲缘及装饰边界不稳定而排除，41张清晰且存在完整可见甲面的单场景图仅进入待标注候选，共计277个完整可见甲面。终结器验证45/45决定、12页哈希和输入报告哈希全部一致；分片001—012累计审核548张，其中276张待标注、272张排除，剩余618张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片013的11页审核表覆盖42张/5个来源组，并绑定`quality-review-queue/shards/quality-review-013.csv`及其SHA-256 `1a6d98a660b7b048b0bf419c1ef035597e18cbcd1f66e77ea7db27665949aaab`。联系表预筛后42张均逐文件打开原分辨率；21张拼图或社交平台页面排版、2张因明显像素化/失焦到甲缘不稳定和1张因画面边缘截断已露出甲面而排除，18张清晰单场景图仅进入待标注候选，共计113个完整可见甲面。终结器验证42/42决定、11页哈希和输入报告哈希全部一致；分片001—013累计审核590张，其中294张待标注、296张排除，剩余576张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片014的11页审核表覆盖44张/7个来源组，并绑定`quality-review-queue/shards/quality-review-014.csv`及其SHA-256 `8d93e405c7c84586b905916d8d833528818a9baa183d5459e4f6fc68566614da`。联系表预筛后44张均逐文件打开原分辨率；12张拼图或社交平台页面排版、3张因明显像素化/失焦到甲缘不稳定和1张因画面边缘截断已露出甲面而排除，28张清晰单场景图仅进入待标注候选，共计192个完整可见甲面。终结器验证44/44决定、11页哈希和输入报告哈希全部一致；分片001—014累计审核634张，其中322张待标注、312张排除，剩余532张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片015的12页审核表覆盖48张/6个来源组，并绑定`quality-review-queue/shards/quality-review-015.csv`及其SHA-256 `26629fd3a5bd6d4a303f8e762cf19862a99bcd5190ffead0080bc7145b53eed6`。联系表预筛后48张均逐文件打开原分辨率；3张拼图或带嵌入示意图的页面排版、4张因明显像素化/失焦/压缩到甲缘不稳定、5张因画面边缘裁断或被其他手指遮挡到仅局部露出甲面、1张因无美甲主体而排除，35张清晰单场景图仅进入待标注候选，共计278个完整可见甲面。终结器验证48/48决定、12页哈希和输入报告哈希全部一致；分片001—015累计审核682张，其中357张待标注、325张排除，剩余484张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片016的11页审核表覆盖43张/8个来源组，并绑定`quality-review-queue/shards/quality-review-016.csv`及其SHA-256 `9f7a987da495f1f1e29a02026544c1c71b3b3372b7e48e129d5387a66131ea20`。联系表预筛后43张均逐文件打开原分辨率；2张九宫格或嵌入社交平台截图的非单一场景、6张因明显像素化/失焦/压缩到甲缘不稳定的视频帧、6张因画面边缘截断或手势遮挡到仅局部露出甲面而排除，29张清晰单场景图仅进入待标注候选，共计187个完整可见甲面。终结器验证43/43决定、11页哈希和输入报告哈希全部一致；分片001—016累计审核725张，其中386张待标注、339张排除，剩余441张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片017的11页审核表覆盖42张/6个来源组，并绑定`quality-review-queue/shards/quality-review-017.csv`及其SHA-256 `34757af387286472b7df4de8efa407ea74194080e48fa2ddc0d84a672b47aad2`。联系表预筛后42张均逐文件打开原分辨率并复算源文件哈希；29张多图拼贴或社交平台页面排版、10张手绘甲型设计模板排除，3张清晰单场景图仅进入待标注候选，共计25个完整可见甲面。终结器验证42/42决定、11页哈希、输入报告和全部源图哈希一致；分片001—017累计审核767张，其中389张待标注、378张排除，剩余399张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片018的12页审核表覆盖46张/5个来源组，并绑定`quality-review-queue/shards/quality-review-018.csv`及其SHA-256 `16e29e4143c72289fb0062d22144cf06b06248ff5a7e0e22a3df9d99cecec8d9`。联系表预筛后46张均逐文件打开原分辨率并复算源文件哈希；31张多图拼贴或社交平台页面排版、4张明显模糊或过曝到甲缘不稳定的图片排除，11张清晰单场景图仅进入待标注候选，共计62个完整可见甲面。终结器验证46/46决定、12页哈希、输入报告和全部源图哈希一致；分片001—018累计审核813张，其中400张待标注、413张排除，剩余353张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片019的12页审核表覆盖48张/8个来源组，并绑定`quality-review-queue/shards/quality-review-019.csv`及其SHA-256 `aa9cedb1ef2ac9f1f27a6848cf5b6cf9f82de71039a426b7df5b1898bd538fb0`。联系表预筛后48张均逐文件打开原分辨率并复算源文件哈希；11张社交平台页面或九宫格拼图、4张明显失焦/像素化/视频压缩到甲缘不稳定的图片和2张仅露出局部甲面的图片排除，31张清晰单场景图仅进入待标注候选，共计179个完整可见甲面。终结器验证48/48决定、12页哈希、输入报告和全部源图哈希一致；分片001—019累计审核861张，其中431张待标注、430张排除，剩余305张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片020的13页审核表覆盖50张/8个来源组，并绑定`quality-review-queue/shards/quality-review-020.csv`及其SHA-256 `ca8ff4602d566df982eae2680f49ca27a90479dd25512c88967335b1581a18b2`。联系表预筛后50张均逐文件打开原分辨率；21张手绘甲片设计稿、九宫格或社交平台海报按非原始单场景排除，3张因明显失焦、像素化或视频压缩到甲缘不稳定而排除，26张清晰单场景图仅进入待标注候选，共计145个完整可见甲面。决定清单SHA-256为`06258635a82b90ffe47ad3a3a0d8a4fa048b68ab1530236cdde35535bf37e172`；终结器验证50/50决定、13页哈希和输入报告一致，终结报告SHA-256为`b2c73b4e727965aef9cb95acbed1c7fd2d41b63e30ebdd9907840c68acfa0512`。分片001—020累计审核911张，其中457张待标注、454张排除，剩余255张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片021的12页审核表覆盖48张/11个来源组，并绑定`quality-review-queue/shards/quality-review-021.csv`及其SHA-256 `22b00f5db9203743e32d6f59459ae68e0a2974d9616af1eb85b768542eaff8b8`。联系表预筛后48张均逐文件打开原分辨率；23张多图拼贴、社交平台海报、线稿模板或教程页按非原始单场景排除，3张因明显失焦、像素化或只展示破损甲局部而排除，8张因手势遮挡、画面边缘截断或甲面仅以侧面露出而排除，14张清晰完整单场景图仅进入待标注候选，共计80个完整可见甲面。决定清单SHA-256为`a1141ed78540a1f535ed096419338561ab2f546ccdd818e3e84df2b0e55c637a`；终结器验证48/48决定、12页哈希和输入报告一致，终结报告SHA-256为`b1ab655b0552b1437b298c475a2ef97bc5804046197385ee16ca2208795e1c82`。分片001—021累计审核959张，其中471张待标注、488张排除，剩余207张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片022的13页审核表覆盖50张/7个来源组，并绑定`quality-review-queue/shards/quality-review-022.csv`及其SHA-256 `bf04510ae10b4990ce05b1eec4873b47ef148f5be1a8c44e6630add24f425494`。联系表预筛后50张均逐文件打开原分辨率；22张甲片展示、产品宣传页、多图拼贴或社交平台海报按非原始单场景排除，3张因明显像素化、失焦或视频压缩到甲缘不稳定而排除，9张因边缘裁断、相互遮挡或甲面仅局部露出而排除，16张清晰完整单场景图仅进入待标注候选，共计99个完整可见甲面。决定清单SHA-256为`5ae5536db5ddcf55bdcac6c821f7a46aabd014fbe58cdb58f1d1aa6f9bf3db78`；终结器验证50/50决定、13页哈希和输入报告一致，终结报告SHA-256为`67120641e68c45e87fe71432ae642826410bbe692609c589166538901b26616b`。分片001—022累计审核1009张，其中487张待标注、522张排除，剩余157张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片023的12页审核表覆盖48张/9个来源组，并绑定`quality-review-queue/shards/quality-review-023.csv`及其SHA-256 `a00552bac1f47b5cd2a45c6bef0a00f37de910dec804b032107eb2aa78f3b2fe`。联系表预筛后48张均逐文件打开原分辨率；19张拼图、教程模板或独立甲片展示按非原始单场景排除，6张因明显像素化、失焦或视频压缩到甲缘不稳定而排除，2张因甲面被图像边缘截断而排除，21张清晰完整单场景图仅进入待标注候选，共计119个完整可见甲面。决定清单SHA-256为`01ca37d3126952609da08021d7ea76232dc17f6f0ddd0feb02772984306dd3d5`；终结器验证48/48决定、12页哈希和输入报告一致，终结报告SHA-256为`37194bd8c180c9e86228ca0fd347c1bf7f559c589c0e23b5cf874352217a7656`。分片001—023累计审核1057张，其中508张待标注、549张排除，剩余109张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片024的12页审核表覆盖45张/8个来源组，并绑定`quality-review-queue/shards/quality-review-024.csv`及其SHA-256 `91519adf8758f5e276ab80be3e5898cc198bb90aeed0f5570acc989982199028`。联系表预筛后45张均逐文件打开原分辨率；5张手写教程标注页和1张十二宫格拼贴按非原始单场景排除，4张因明显像素化、失焦或视频拖影到甲缘不稳定而排除，35张清晰完整单场景图仅进入待标注候选，共计217个完整可见甲面。决定清单SHA-256为`123975ab8b27ae1693590add3a65c0a2facc012362b2885faf303a0439b29605`；终结器验证45/45决定、12页哈希和输入报告一致，终结报告SHA-256为`00c521d3a7d5d49dc92c575c9d20791e9f8ed84112d7075742698dc95de3d695`。分片001—024累计审核1102张，其中543张待标注、559张排除，剩余64张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片025的11页审核表覆盖43张/12个来源组，并绑定`quality-review-queue/shards/quality-review-025.csv`及其SHA-256 `677211154ccd4f27cf993b7570a783d2a829ed2c0455680b106494729925d146`。联系表预筛后43张均逐文件打开原分辨率并复算源文件哈希；9张拼图、甲型模板、设计稿或独立甲片展示按非原始单场景排除，12张因明显像素化/失焦、甲面裁边、手势遮挡或仅局部露出而排除，22张清晰完整单场景图仅进入待标注候选，共计149个完整可见甲面。决定清单SHA-256为`8b00ccf791bfd55381fb05e9d270e8313a97d718795b47b80162b068f1a3216c`；终结器验证43/43决定、11页哈希、输入报告及源文件哈希一致，终结报告SHA-256为`ab250a3925e5d9e7135e2dee9c393e4c0299c911e51b1725079420e6af18beba`。分片001—025累计审核1145张，其中565张待标注、580张排除，剩余21张仍待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，未生成或审核mask。

质量审核分片026的6页审核表覆盖21张/2个来源组，并绑定`quality-review-queue/shards/quality-review-026.csv`及其SHA-256 `7cde5102ffffd7abb7ec3d26a538744369e3c5678d044b1817a487168cd09c84`。21张均逐文件查看原分辨率，全部确认是四宫格、九宫格或其他多场景拼接图，0张保留、21张排除，不从拼图拆格生成派生训练素材。决定清单SHA-256为`72314f1ef0b82b62f6fc8ea57da1b50405298794674e7c348b58840ed063a7ef`，终结报告SHA-256为`66db49f47e12f8af08cd7eb485eb518936d9089969af352eb3734541b05681a7`。新增`finalize-real-material-source-screening-batch.py`复验质量队列、26个分片及其审核页/终结报告哈希，并逐项核对1166个文件名、图片SHA-256、来源组和训练禁用状态；真实批次输出`source_screening_batch_pass`，覆盖26/26分片、1166/1166图片和193/193来源组，565张待标注、601张排除、0张待审，批次报告SHA-256为`901f52e531b5a93f4be9b010e2e96f585ca850bd733e5d9a4f5f9865a03335c0`。源图筛选阶段至此收口，但565张仍无合格mask且不得直接训练。

`plan-real-material-first-annotation-batch.py`绑定A授权清单、近重复终结报告和源图筛选批次报告，以固定种子执行来源组原子子集和选择。565张待标注候选分配为train 502张、val 30张、独立发布test 33张；从train中优先选择160张/39个完整来源组作为首批标注，源图审核记录预计包含966个完整甲面。生成的角色CSV继续由`audit-real-material-exclusive-assignment.py`逐文件复验授权清单与1271张原图哈希，结果1271/1271覆盖、0来源泄漏；计划、CSV和审计SHA-256分别为`0dbf3a6cf99c455f3b8a8453223ef9df98eca3b16b919fa783dddd40a05dd912`、`dd11c24ba3bea9e479dd1fc4ee1a7dbbc681b7b7d7aa6ccaf7cc5c752d9e9dc4`、`11f76a240d832f8ca29d875d058146ab72aa0323d585392bdd07db4da769aa62`。这只是标注顺序和最终角色规划，不授予训练资格；val仍需独立真值审核，test始终禁止训练。当前筛选排除池没有可安全复用的hard negative，约100张负样本需求单独延后，禁止用拼图、模糊或残缺甲素材补数。

`build-real-material-quality-review-sheets.py`将单个质量分片渲染为带行号、文件名、来源组和尺寸的审核页，并记录输入分片、逐图和逐页SHA-256；审核页只是导航证据，保留项仍须回到原图分辨率查看。`finalize-real-material-source-screening-shard.py`要求决策对分片逐项全覆盖并复验页面确认哈希，同时把源图适用性与mask真值严格分开。分片001共48张：19张教程图、拼图或非单张实拍被排除，29张在原分辨率下确认所有需要计数的甲面完整露出，仅进入后续标注候选；终结报告固定其`trainingUse=prohibited`和`annotationTruthStatus=not-started`，不得把源图筛选通过冒充完整mask审核通过。

分片002共47张，联系表预筛后对27张单图逐文件回看原分辨率；其中2张明显模糊、1张除单枚拇指外其余甲面仅局部露出，按严格训练标准排除，另有2张非上手甲片展示和18张截图/拼图排除，最终24张仅保留为待标注候选。源图硬门规定：模糊到无法确认轮廓、图像边缘裁甲、应标甲面残缺或仅局部露出的图片及其派生物不得训练；清晰源图也必须等完整mask逐甲通过原分辨率审核后才可进入用途分配。

`authorize-real-material-candidate-intake.py`把后续用户A/B/C选择落成可审计授权清单：A允许商业模型训练、独立发布测试和长期回归，B仅允许独立发布测试和长期回归，C仅存档。工具绑定原候选intake SHA-256、逐图图片SHA-256、来源组及条目聚合哈希，并在图片漂移时拒绝。A只授予“完成原分辨率完整甲面审核和来源隔离后可训练”的批次资格；所有未审核条目仍保持`trainingUse=prohibited`，后续必须按完整`sourceGroup`互斥分配到训练或独立发布测试，禁止同图或同源组兼任两种角色。当前尚未替用户选择或生成正式授权清单。

`audit-real-material-exclusive-assignment.py`承接授权后的最终逐图审核清单。A/B必须覆盖授权清单中的每一张图片，且每项只能是最终`pass`或`exclude`；`rework`、漏审和重复行均阻断。A的pass项可分配为train、val或`independent-release-test`，B只能进入独立发布测试，C可在不做视觉审核时整体归档。所有pass项按完整`sourceGroup`保持单一角色，跨train/val/独立发布测试即视为泄漏；工具复验授权清单、原候选intake、聚合条目和当前图片SHA-256。该审计只证明授权、审核覆盖和用途互斥，val仍须另行通过原分辨率真值审核与候选训练验证门，独立发布测试仍须冻结门和代表性规模门。

`build-real-material-review-workspace.py`为A/B授权后的原分辨率逐图审核生成可复现工作区。工具复验授权清单、原候选intake和当前图片SHA-256，生成全覆盖`review-all.csv`以及按完整`sourceGroup`组织的分片CSV；一个来源组绝不跨分片，大来源组可超过目标分片大小。每个分片和聚合CSV均记录SHA-256，审核列包含最终状态、完整露出甲数、完整mask数、问题码、用途角色和备注，初始均为空；报告明确空字段不是审核通过。工作区只引用原图，不复制素材，也不自动授权、标注、分配或晋升真值。

第二十七轮继续复核压力返修父截图，确认007、037、094、095的父图均有完整主照片，但首轮派生区域误选了小图、裁断象限或被相邻插图覆盖的区域。`stress-primary-regions-v3.json`重新提取4张主照片，4/4父图SHA-256、派生SHA-256、像素框和稳定`sourceGroup`通过；在v2聚合包上按父图替换后仍为35父图/35派生区域，没有新旧区域重复计数。SAM2对4张/19提示全部完成、0 fallback、几何19 pass/0 suspect；原分辨率视觉门只接受7a92的5个完整mask，86ac、956d、b1184虽已换成正确主照片，但仍有手指/手掌皮肤外溢而继续返修。压力集更新为11张/58 mask通过、22张返修、2张排除、11个通过来源组；92张父图聚合更新为56张/327 mask暂通过、22张返修、14张排除、17个通过来源组，训练用途继续`prohibited`。

第二十八轮使用SAM2.1 large对86ac、956d、b1184执行3张/14提示收紧返修，首轮全部生成、0 fallback，几何为13 pass/1 suspect。原分辨率并排复核只接受86ac与956d共2张/10个完整mask；b1184第1—3甲仍吸收甲根皮肤，v5/v6进一步证明提示2/3初始均返回0 mask并退化为box-only，因此继续返修而未被几何结果误提升。`sam-assisted-nail-annotation.py`新增逐文件、提示序号、提示模式和初始mask数的fallback明细，并为多mask响应记录按正点覆盖、负点排除、提示框包含率和面积选择的诊断。压力集更新为13张/68 mask通过、20张返修、2张排除、13个通过来源组；92张父图聚合为58张/337 mask暂通过、20张返修、14张排除、17个通过来源组，正式训练集及训练禁用策略不变。

第二十九轮先对剩余20张压力返修图执行原图初筛，并用SAM2.1 large分别对e0ee与c0e0运行5个逐甲多点提示；两轮均0 fallback、几何5 pass/0 suspect，但原分辨率叠加复核仍发现边缘甲面不完整或缎带/皮肤污染，候选全部拒绝。连同初筛确认的406b与9da2，本轮共将4张必需甲面触及图像边缘的图片从返修改为排除，未新增通过图或mask。压力集更新为13张/68 mask通过、16张返修、6张排除；92张父图聚合为58张/337 mask暂通过、16张返修、18张排除、17个通过来源组。该结果再次证明几何全通过不能覆盖源图完整性门，正式训练集、训练禁用策略与生产HOLD不变。

第三十轮继续处理压力返修图。d970连续进行v9—v12四轮5甲重建：每轮均1张/5提示完成、0 fallback，几何5 pass/0 suspect；通过收紧相邻透明甲提示后，第2/第3甲多边形相交面积由约700像素降为0，但横向蓝甲在“吸收指腹”和“仅覆盖蓝色前段、遗漏粉色甲根”之间仍未达到完整甲面门。f075的5甲重建同样0 fallback、几何5 pass/0 suspect，原分辨率仍发现横向甲吸收大块指腹，因此两张均继续返修。同期确认6df0、424a、a4a4、b548、cf0c存在必需甲根或甲面被图像边缘裁断，转为排除。压力集更新为13张/68 mask通过、11张返修、11张排除；92张父图聚合为58张/337 mask暂通过、11张返修、23张排除、17个通过来源组，未新增通过图或mask。

第三十一轮分别对6d9a与d951执行1张/5提示的SAM2.1 large完整重建，两轮均0 fallback、几何5 pass/0 suspect且同图polygon相交为空。原分辨率审核仍拒绝两张：6d9a第2甲遗漏透明/白色甲尖、第5甲只覆盖白色前段而遗漏粉色甲根；d951拇指mask吸收大块皮肤，右下小拇指甲因提示错位未被覆盖。两张继续返修。同期确认02f顶部必需甲面及6d83最右甲根被图像边缘裁断，转为排除。压力集更新为13张/68 mask通过、9张返修、13张排除；92张父图聚合为58张/337 mask暂通过、9张返修、25张排除、17个通过来源组，未新增通过图或mask。

第三十二轮优先重建f8a、2c79与2236三张完整露出、但首轮被重复局部mask和漏小指破坏的压力图。f8a与2c79各以5个逐甲紧框、完整轴向多正点及皮肤/衣物负点一次收敛，均5/5提示完成、0 fallback、几何5 pass/0 suspect且polygon两两相交为0；原分辨率确认透明甲尖、金属/蝴蝶设计区和横向小指均完整，接受2张/10 mask。2236经过v18—v23六轮：先将8个重复局部mask重建为5甲，再把无名指/小指相交面积从71.39像素降至0，并在放大复核中拒绝拇指甲根遗漏与皮肤吸收中间态，最终补齐水钻相邻透明甲根且无皮肤污染，接受1张/5 mask。压力集更新为16张/83 mask通过、6张返修、13张排除、16个通过来源组；92张父图聚合为61张/352 mask暂通过、6张返修、25张排除，训练用途继续`prohibited`。

第三十三轮先对b1184的4枚可见甲面缩小问题范围：v6放大图确认第1、2、4甲完整，只有黑色第3甲因box-only fallback吸收甲根指腹。v24对三枚稳定甲使用box，只为黑甲配置稀疏轴向正点和甲根负点，4/4完成、0 fallback、几何4 pass/0 suspect、polygon零交叠；原分辨率确认黑甲止于甲根，接受1张/4 mask。eac9的9枚透明相邻长甲在v25虽9/9几何通过且0 fallback，但仍合并皮肤/邻指，因此拒绝SAM候选并切换为原分辨率人工多边形；9个多边形全部合法、几何9 pass/0 suspect、两两交叠为0，整图及上手/下手三处放大复核确认甲根、透明甲尖、金属尖与装饰完整且无皮肤污染，接受1张/9 mask。压力集更新为18张/96 mask通过、4张返修、13张排除、18个通过来源组；92张父图聚合为63张/365 mask暂通过、4张返修、25张排除。人工绘制只是一种候选来源，仍必须通过几何、交叠和放大视觉门；训练用途继续`prohibited`。

第三十四轮处理压力集最后4张返修图f075、d970、d951和6d9a。新增`build-reviewed-manual-polygon-repair.py`，通过清单按1起始序号保留已审完整polygon并只替换失败甲面，强制校验原图尺寸/来源组、坐标边界、Shapely合法性和同图两两零交叠，同时生成整图overlay、逐甲原图/overlay 2×放大图、真实外接框提示及机器报告；产物仍明确为候选，不自动晋升训练或test真值。四张共保留10个已审polygon、人工重画10个局部/无效/皮肤污染polygon；放大复核中继续纠正d951拇指遗漏透明/白色甲身、6d9a星形甲甲尖及相邻斜甲/横向甲皮肤污染，最终4张/20 mask全部合法、几何20 pass/0 suspect/0 missing、polygon零交叠，整图与20组逐甲2×原图/叠加图确认甲根、透明甲尖、白色延长段及装饰完整且无皮肤污染。压力集更新为22张/116 mask通过、0返修、13排除、22个通过来源组；92张父图聚合为67张/385 mask暂通过、0返修、25排除。返修队列清零只代表候选审核阶段闭环，冻结代表性test真值、移动真机与Beta门仍未完成；训练用途继续`prohibited`。

冻结前全量拓扑门发现核心030中原第9个区域实为手部关节假阳性，同时5张核心图和8张压力图存在自交polygon或相邻甲面交叠。030改为8个真实完整甲面；新增`repair-reviewed-annotation-topology.py`，只允许修复清单明确声明的无效项和前后景遮挡对，超出面积/损失阈值或仍有未声明交叠即失败。13张/82 mask修复结果全部合法、两两零交叠，并通过13张整图原分辨率审核及047、078、c541显著变更甲面的逐甲2×复核。上游统计据此更正为核心45张/268 mask、压力22张/116 mask，父图合计67张/384 mask、0返修、25排除。

`freeze-reviewed-release-test-candidates.py`随后把首版通过项复制到隔离快照`frozen-reviewed-candidate-v1`，逐项记录图片、标注、图片/标注联合SHA-256和清单聚合SHA-256。独立复算确认67张图片、67份标注、384 mask、18个父来源组全部一致且0错误，`trainingUse=prohibited`。该首版快照是受审核候选真值与历史规模证据，不是模型质量评估结果；其当时代表性门为67/100。2026-07-22已将补充33张/170 mask与其合并为100张/554 mask、core78/stress22、29父来源组的新规范冻结快照，旧67图质量结论只保留为历史诊断，不能换绑新100图。

冻结快照随后通过`materialize-frozen-release-test-evaluation.py`物化为仅含test split的评估包。脚本独立复算快照聚合及逐文件图片/标注/联合哈希、多边形合法性、同图零交叠，并核对409张正式训练图：18个冻结父来源组与13个训练来源组重叠为0，图片SHA-256重叠也为0；输出继续固定`trainingUse=prohibited`，不得反向用于训练。v6在部署512下全量67张box/mask mAP50=0.8370/0.8313，核心45张=0.8485/0.8523，压力22张=0.8179/0.7919；压力组相对历史13张基线分别下降0.0348/0.0557，超过0.02退化上限。640全量诊断为0.8570/0.8549，但不属于部署输入契约，不能覆盖512失败。正式质量报告据此输出`reject_v6_release_at_deployment_resolution`，生产配置保持不变。

为把总体退化转换成可执行改进方向，新增`profile-frozen-release-test-failures.py`。工具校验冻结清单、训练禁用、来源隔离、真值标签哈希和67份预测覆盖，再按浏览器默认confidence=0.35与mask IoU=0.50逐实例匹配。384个真值对应346个阈值内预测：289个匹配、95个漏检、57个误检、76个匹配仅达到0.50—0.75弱形状区间，整体召回0.7526；核心45张召回0.7761，压力22张召回0.6983。0.20—0.45阈值扫描显示0.25可把压力召回提高到0.7845，但阈值内误检由57增至90；因此只登记为下一候选的召回优先诊断点，不在浏览器候选数、误检和Beta门完成前修改默认值。15张最高风险原分辨率叠加图视觉确认透明相邻长甲、多甲同屏、低对比整甲漏检/局部识别，以及手指或腕表误检。该画像不是训练清单：冻结图片、标签、裁剪和父来源组均不得回流训练。

`build-frozen-release-test-quality-report.py`现升级为通用schema v2，不再把候选名称或67图数量写死。它从冻结manifest和评估物化证据动态复算图片、mask、core/stress和父来源组，校验assessment标签、预测制品覆盖与baseline图片数，并要求baseline及全量512、全量640、core512、stress512全部使用同一候选权重且记录权重SHA-256。正式判定只看部署512，全量、core和stress三组必须同时满足绝对精度与相对退化门；640只作诊断，少于100张的快照无论指标如何都拒绝。输出路径不得与任何输入直接相同，也不得通过Windows路径别名或硬链接覆盖证据。`--verify-report`会从已写报告读取并重放全部输入，在临时目录重新构建整份报告后逐字段比较；手写外层决定、源指标写后漂移和传递输入覆盖都会被拒绝。完成度审计直接调用该验证器；只要代表性100图快照存在，就不得以历史13图指标或旧67图报告满足候选质量门。旧67真实证据重放仍为`reject_candidate_release_at_deployment_resolution`；新100图manifest与schema v2物化证据已通过契约深验，但尚无新候选模型指标，因此不能形成新100图质量PASS。

首批train正样本的mask审核分片009绑定工作区报告SHA-256 `6c791e7992e61788f8a4815cb7e4d3c0e9edd11bf48d5562d02ebc6a8f7974c4`、分片CSV SHA-256 `81b0a6ddd60fa3fc63877ade812debc4ca3b095e772ea1ca0e8dece4dae9dd10`及10页审核图哈希。19张原图和全分辨率叠加图逐张审核为6直接通过、13返修、0排除；漏甲、候选重复/交叠及首饰、布料、眼睛、嘴唇、手指和皮肤误检均被拒绝。决定清单和分片终结报告SHA-256分别为`ee291680efb795776f402811b71b05914ecc9f2ba2fc820e0c3c6b874c1e1ede`与`b3d81bd099cb617e7f78afa674f9374b15e47b5960b502319df3ba6665f72446`。6张直通样本共30个mask进一步通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审，训练真值累计16张/92 mask；所有产物在整批数据物化与来源隔离审计前继续禁止训练。

最后一个mask审核分片010绑定分片CSV SHA-256 `473e87b104511eed1eecebbfec134e1544a802598f4c54eeef7d3eba98767ff2`及9页审核图哈希。17张原图和全分辨率叠加图逐张审核为2直接通过、15返修、0排除；UI按钮、汽车按键、戒指/手链、衣物、整块指腹误检，以及漏掉深色甲但同时误检按键而造成候选数相等的样本均被拒绝。决定清单和分片终结报告SHA-256分别为`8473020100e3c54d11f30da28cac67d65bbd3faedab99d14983fd6aa97e6ddee`与`1937a3a9b7e2507cc8569d826bef38b58f3cc3556777ef4c2b9695d843bc4378`。2张直通样本共10个mask进一步通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审，真值报告SHA-256为`d9e644798905d3b4ba69a0554c2ef41ec8739b4ecb3a164add860e0aa30cc098`和`b24e33ce756e607ae846383f9cac0b753947b105e240292fa1481fe239cc8ce5`。首批160/160初审闭环并不等于可训练：训练真值仅18张/102 mask，仍缺82张合格train正样本、30张val和约100张hard negative。

首个低风险误检删除返修批次从分片010选择`nail_00004…_7`与`nail_00078…_3`：保留10个已对应完整甲面的1起始提示，删除戒指、方向盘控件和手链流苏3个非甲提示。返修提示、SAM2.1 large报告与几何报告SHA-256分别为`b1bfcc5c5f6c179257a5f9c9a15a557447fa28e8b525c68f188e57d1de132268`、`ff1f98d3bb171ef533ba05c74771fec13e2af7ace331007d045dfba907a140d7`和`6022a5c71e80bee4e8090a36f2c7510b587a88e1a8806d799eea4b4b09627392`；2/2张、10/10提示完成，0 fallback、几何10 pass/0 suspect。原分辨率复核确认透明长甲尖、附着立体装饰可见区域和5枚短甲甲缘均由单一完整mask覆盖，无皮肤或背景污染；随后两张均通过polygon合法性和同图零交叠终审，真值报告SHA-256为`b4ba3dbf888176444598d67012af885a10043ee1af41081b89f9f0077344f03f`与`171734650eee1665cf728ce22a648480a41818fa5e8e898ef39a17d1fb3cb60e`。训练真值累计20张/112 mask，最低100张train正样本完成20%、仍缺80张；val真值0/30和约100张hard negative不变。

第二批低风险返修从分片010选择`nail_00005…_8`、`nail_00075…_0`和`nail_00637…_11`，删除整段手指、方向盘控件等误检并以紧框多点提示补齐棕色甲与星形拇指甲。返修清单、提示、SAM报告和几何JSON SHA-256依次为`72fa4d5e092887a29dfa5f0581636e53fd05d8188926e79265b1f9108a39bc10`、`754f031fca1566b8bc1fe30eff37b4097f06c978aa38a7af3c5b5e57cdcafb00`、`4b342a70575450d80dbf54a1db99ed746306e986822c7be9290ddac8322722c3`和`7326d6c0e639ba8f61df842aa152966a2a2c21911a6b59314ac62e49fba08c44`；3/3张、20/20提示、0 fallback、几何20 pass/0 suspect。原分辨率视觉及最终拓扑门通过，形成第21至23个训练真值，共20个mask，累计23张/132 mask。

第三批针对`nail_00051…_0`、`nail_00052…_2`和`nail_00054…_3`的侧视拇指：每张保留四枚正面甲，以紧框、轴向双正点和皮肤负点重建完整拇指甲。返修清单、提示、SAM报告和几何JSON SHA-256依次为`8d0d6e0e8d0e9fdd142a844f810a409759c6a4903d7d229d8cc90baab90bf515`、`fba0d91e2ee7d94e28438719d662daf559a2d11cce333ab821f5ea52be49a437`、`08885931a3fcc185721e28c37e42ea0f4d4ff6a8dd9bc8a5375e2140adc0235b`和`73bf0ac51f3b3f4e84e5347db98949b8834edd7fba0c545c898447f41be2dbd6`；3/3张、15/15提示、0 fallback、几何15 pass/0 suspect。三张均通过原分辨率视觉、合法polygon与零交叠终审，形成第24至26个训练真值，共15个mask，累计26张/147 mask。

第四批清理3张/14提示全部由SAM2.1 large完成且0 fallback。为避免把斜向相邻甲仅因外接框相交误拒，同时继续严防重复/交叠，`audit-sam-prompt-geometry.py`保留`maximumPeerBoundsIou`诊断并新增Shapely精确`maximumPeerPolygonIntersectionArea`：非法拓扑或真实交集仍判suspect；“外接框高重叠但polygon分离”和“polygon真实交叠”两项回归均通过。复跑后12 pass/2 suspect；`nail_00628…_2`第4与第5甲真实交集10960.0713像素，明确继续返修，不生成真值。`nail_00629…_3`与`nail_00095…_2`分别以4和5个完整mask通过原分辨率视觉、合法性与零交叠终审，真值报告SHA-256为`4acda3a9f99fe1c051753dbfbc1af6334156ad578a2d857ccc65aaf33ac600ae`和`cc81a8ef45ef3cf4f6527fc81765c7ec7661ffd96f59b81607cf226ea506b9e3`。累计28张/156 mask，最低100张train正样本完成28%、仍缺72张；val真值0/30和约100张hard negative仍未建立。

第五批针对`nail_00628…_2`执行人工零交叠返修：保留4个已完成原分辨率视觉审核的polygon，以人工多边形替换原先合并相邻甲的第5甲。构建器对第一版边界0.0024像素残余交集继续拒绝；边界向可见甲面内收后，5个polygon全部合法、同图零交叠，几何5 pass/0 suspect。整图及第4、5甲2×局部复核确认两枚相邻甲分别覆盖各自完整可见甲面，交界无重复，衣物误检和袖口污染已清除。最终真值报告SHA-256为`ee09fecc837390f32ce34a7ae2e39b32d4726d2102327e41fc8a315ed435d414`，训练真值累计29张/161 mask，最低100张train正样本完成29%、仍缺71张。

第六批针对`nail_00076…_1`的双手十甲复杂图重建候选：删除整段手指和手链误检，保留6个已完整覆盖的甲面提示，并以紧框、多正点及邻近皮肤负点补齐左侧小指甲、左侧横向拇指甲、右侧蓝色横向甲和右侧棕色拇指甲。SAM2.1 large完成1/1张、10/10提示、0 fallback，几何10 pass/0 suspect；原分辨率整图复核确认10枚完整露出甲面均由单一完整mask覆盖，无整段手指、手链、皮肤或背景污染。最终真值报告SHA-256为`9d0a5602da1a60a296b7dab0e45888fb830b9e577f183825868cfcd97abc8b1f`，10个polygon全部合法且同图零交叠；训练真值累计30张/171 mask，最低100张train正样本完成30%、仍缺70张。

第七批从分片009选择三张低风险样本：`nail_00542…_3`保留五甲并删除珍珠链误检，`nail_00541…_2`与`nail_00841…_3`各补一枚完整露出但漏标的侧视拇指甲。首轮SAM2.1 large完成3/3张、15/15提示、0 fallback，几何14 pass/1 suspect；原分辨率仅确认删除珍珠链的五甲图通过，两张侧视拇指图因边缘皮肤风险或提示中心落在polygon外继续返修，没有用总体14/15通过率放宽单图门。

第八批收紧两张侧视拇指的提示框，沿斜向甲面布置双正点，并在相邻皮肤设置定向负点；SAM2.1 large完成2/2张、10/10提示、0 fallback，几何10 pass/0 suspect。原分辨率复核确认两枚侧视拇指甲均从甲根到可见甲尖完整覆盖且不吸收皮肤，其余八甲保持完整；三张最终均通过合法polygon与同图零交叠终审，真值SHA-256依次为`9d707a18a411eff36a69fd455137a2b9fcdc150948197f7e1d1f2147403cbe72`、`18252db09c514c5359c06f4a73a9abb4c502d1542bf24960d47ab2099bd52fbc`和`a55ad552eb8cf5c3ee067465cbca75758be3e3e082546a0f97ba608201bdd272`。训练真值累计33张/186 mask，最低100张train正样本完成33%、仍缺67张。

第九批选择分片009四张漏甲或重复分割样本，保留每张四枚已审完整甲，以紧框、多正点和皮肤负点补齐或重建第五甲；SAM2.1 large完成4/4张、20/20提示、0 fallback，几何20 pass/0 suspect。原分辨率只接受`nail_01041…_2`的竖指透明延长甲和`nail_01177…_0`由两个重叠局部候选合并重建的透明长甲；另两枚拇指甲仍吸收甲根下方皮肤，继续返修，没有把几何全通过当成视觉通过。

第十批进一步压缩两枚拇指甲提示高度并在甲根下缘加密皮肤负点，SAM2.1 large完成2/2张、10/10提示、0 fallback，几何10 pass/0 suspect。原分辨率确认`nail_01179…_2`横向长拇指甲从甲根到透明甲尖完整且无皮肤污染，`nail_00951…_3`带立体装饰拇指甲仍有皮肤吸收，继续返修。新增三个真值SHA-256为`eb607d29541a30847837e717d7a60fd58d435938977ab69d5c98564ca80d7d03`、`b7409f8ca1677224cbaea44683913b17b503a0f5f1b196841137e673036d6e0b`和`13ab302d73b0b8a0eac9c7758f74d56b60d3f4ad90ad459f2e5c9f245e565ea3`；训练真值累计36张/201 mask，最低100张train正样本完成36%、仍缺64张。

第十一批跨分片处理三张仅含明显额外误检的低风险样本：每张保留五个逐甲提示并删除背景标识、头发/背景或白色绸布误检。SAM2.1 large完成3/3张、15/15提示、0 fallback，几何15 pass/0 suspect。原分辨率只接受`nail_01116…_3`和`nail_00180…_2`，确认各五枚完整甲面且无背景、头发或皮肤污染；`nail_00531…_5`虽然几何通过，但透明甲右侧边界内缩、局部甲面缺失，继续返修且`trainingUse=prohibited`。两个新增真值SHA-256为`f77819020b612ac7507aebb1a695867cec1ce8eed0658d965a856239b4ff6663`和`291f9b77e5e63092da997184e456779ac1763ddb3b523526a35a058f44236dcd`；10个polygon合法且同图零交叠。训练真值累计38张/211 mask，最低100张train正样本完成38%、仍缺62张。

第十二批跨分片处理双手黑甲、四枚低对比裸色甲和五枚白色立体装饰长甲，共3张/19提示、0 fallback；几何15 pass/4 suspect。原分辨率只接受四枚裸色甲图，确认删除整段手指误检后四甲从甲根到方形甲尖完整。双手图实际只有8个独立甲面候选，另有两个跨甲重复宽框并漏两枚侧向拇指；白色长甲图的立体装饰和透明边缘仍有缺口，均继续返修。

第十三批为双手图保留8个独立甲面，以左右紧框、双正点和皮肤/帽子定向负点补两枚拇指；SAM2.1 large完成1张/10提示、0 fallback，几何10 pass/0 suspect。原分辨率仍确认两枚侧向拇指mask吸收大块指腹，且原图只露弯曲局部甲面，停止继续修补并拒绝生成训练真值。第十四批仅保留`nail_00539…_0`主体星形透明长甲，删除弯曲手指和非要求侧面候选；1/1提示、0 fallback、几何1 pass/0 suspect，原分辨率确认甲根至透明甲尖完整。第39至40个真值SHA-256为`1bea37501d1cafd54f5bdce3fa7e684295b82465b7b18a203a26190cd523aec0`和`ca8118d9955849628c573ec41d9b2739459b9d2a4b509c63581e61ea5c425c3b`；新增5个polygon合法、同图零交叠。第十五至十六批对三张漏拇指图使用SAM2.1 large生成并收紧提示，几何最多10/10通过，但原分辨率仍发现新增mask吸收甲根皮肤，全部拒绝直接晋级；第十七批对其中两张保留各4个已审polygon，仅人工重绘漏标拇指，2张/10 polygon合法、同图零交叠、几何10 pass/0 suspect，并通过逐甲2×视觉门。第41至42个真值SHA-256为`cfd9b6659f8e9e149afa23f1eb964693c83dc3b1bbfb9160fe1d81848727969e`和`e9a5258e88127508007e354b16ed417e141994ed87e8ae331eb75ece2f757de2`。第十八批选择两张五甲候选齐全、仅右侧甲根轮廓存在凹口的样本，保留各4个已审polygon并人工替换淡紫/白色渐变甲；2张/10 polygon合法、同图零交叠、几何10 pass/0 suspect，整图和逐甲2×视觉确认低对比甲根、两侧甲缘及方形甲尖完整。第43至44个真值SHA-256为`e79503242f149102c07e2198b4bba6d53e3944d3d25819a2dbd93ffbe970aa23`和`b97d7289762e92853e631ead084ef712ae1ccb7216716915d5bce45d6a231265`。该阶段按报告序号累计44张/236 mask；本轮唯一性索引已在下文纠正重复报告口径。

第十九批从分片001选择两张零候选图，以每图5枚完整露出甲面建立紧框、多正点和皮肤/背景负点。SAM2.1 large完成2张/10提示、0 fallback，几何8 pass/2 suspect；原分辨率确认`nail_00535…_0`多处吸收皮肤且相邻甲真实交叠，`nail_00538…_3`全部SAM候选吸收指尖/背景。批次020—023转人工多边形并反复收紧00538；最终候选虽为5个合法polygon、零交叠、几何5/5，但第3、4枚透明低对比甲仍无法可靠区分甲面与指尖皮肤，因此两图均保持`trainingUse=prohibited`，0张生成真值。随后对分片001已原分辨率直通的`nail_01119…_6`执行最终终审，双手10甲的图片、分片和annotation哈希绑定通过，10个polygon合法且同图零交叠；真值报告SHA-256为`687c8d6192fb70b9bf911d801dc328584d1031f2628c44fe601f5d3580993c5c`。

新增`audit-first-annotation-training-truths.py`，以`item.fileName`建立训练真值唯一图片索引，并在同图身份、annotation SHA-256或mask数冲突时拒绝。当前54个批准报告中，`nail_00491…_2`的003与039报告绑定同一图片和相同annotation SHA-256，规范选择039且只计一次；另2个历史拒绝报告不进入索引。权威索引为53张唯一图片/287 mask、1个冗余报告、0冲突，SHA-256为`a2912ec58501c27015bb19b7907d91ddb88a926fd1fff38171678aaf7f3b5684`。最低100张train正样本按唯一图片完成53%、仍缺47张；val真值0/30和约100张hard negative不变。

第二十四批选择分片008仅漏左上侧视拇指的`nail_00527…_0`，保留4枚初审候选，以紧框、三正点及皮肤/背景负点补齐透明绿色拇指。SAM2.1 large完成1张/5提示、0 fallback、几何5 pass/0 suspect，但原分辨率确认新增mask吸收三角形指腹，拒绝直接晋级。批次025—027转为受审人工多边形：补齐透明主体、绿色装饰可见区域和灰绿色甲尖，并将第1甲原候选右侧皮肤凸起改为平滑贴边轮廓；最终5个polygon合法、同图零交叠、几何5/5，整图及逐甲2×视觉确认五甲从甲根至甲尖完整且无皮肤、白墙、衣物或背景污染。返修终结SHA-256为`dfdb7e46b6612e6482d6fb78358a1d8f1d655a3c28f4c408edaee67d0081868b`，第46个批准真值报告SHA-256为`5646b11c3247a380a3725141631cc3ee30a6ad7b0a0d5ada560bcc2e80d901ec`。更新唯一索引后为45张唯一图片/247 mask、1个冗余报告、0冲突，索引SHA-256为`ad00766a927f99766e21d16e9a662d0cbded6e9e8d68e1987a99431cfe7f023c`；最低100张train正样本完成45%、仍缺55张。

第二十八批选择分片009的`nail_00704…_3`，删除人物眼睛误检并补左侧横向粉色延长甲与右上拇指；SAM2.1 large完成1张/5提示、0 fallback、几何5/5，但原分辨率发现新增横向mask吸收整段手指，拒绝晋级。批次029—030改用人工多边形重画两枚漏/错甲并收紧中央亮片甲甲根右侧皮肤凸起，最终5个polygon合法、零交叠、几何5/5，整图与逐甲2×通过。批次031处理分片008`nail_00533…_6`：此前SAM补左侧横向拇指时吸收皮肤并与上方黄色甲交叠，故保留3枚已审polygon并人工重画两枚问题甲面；最终同样达到5个合法polygon、零交叠、几何5/5及原分辨率视觉通过。两份返修终结SHA-256为`4b2b871ce201fc9d902d96e06c63d76f56b97f4befc306808be857c0483d3f7f`、`acbdd080126e6761ce6ba37fd52f593d7c201988e3338e1e6f635f9e7a9979b4`，第47至48个批准真值报告SHA-256为`10ae8e3776bfd08b0b14bb2f6295d5f723b5e62f7cd4d2d9d5ee40dcc599fa14`、`ff901cb7b1b559aa84117921e3a1ace4fec7552ce7b51db67a57fa980e6bad59`。唯一索引更新为48个批准报告、47张唯一图片/257 mask、1个冗余、0冲突，SHA-256为`94e3e0cb1d160fe6573392dce4383ac3a3700be48df8b79fa2b1b357dd944a2b`；最低100张train正样本完成47%、仍缺53张，val 0/30和约100张hard negative不变。

第三十二批处理分片008`nail_00531…_4`：保留中间3枚已审polygon，人工补齐左侧短拇指并重画右侧横向长甲，删除原候选吸收的大块毛衣；最终5个polygon合法、零交叠、几何5/5，整图和逐甲2×通过。批次033—034处理分片009`nail_00951…_3`：两轮SAM补立体装饰侧视拇指均吸收指腹而拒绝，转为保留3枚可信候选、人工重画拇指与蝴蝶结甲，并在2×复核后修正银粉方甲右下连续甲缘缺口；最终同样达到5个合法polygon、零交叠、几何5/5及视觉通过。两份返修终结SHA-256为`f44ff0c7bc83766595b80ee372bf0fc6366f175579ac194b91161dd392d1fc01`、`c1f0808d94b116ba5662872d75e4d4c30b5fc5742e2fcf1535ec1ec06c6ab5d3`，第49至50个批准真值报告SHA-256为`9b8a129eab35b53b1fd5c76257e0885e45861808748a615b455b0efe364bc769`、`8c291c2c6b56daccb9d5d4840b9663a83a6c7a12c434e5952d632b8391f063ea`。唯一索引更新为50个批准报告、49张唯一图片/267 mask、1个冗余、0冲突，SHA-256为`c2b338b3f74a0ef3e4416e1906dfed05c994b5d5602022d91a661738332d577a`；最低100张train正样本完成49%、仍缺51张，val 0/30和约100张hard negative不变。

第三十五至三十六批处理分片007同一来源组的`nail_00274…_0`、`nail_00276…_2`与`nail_00278…_4`。首轮只替换初审点名的拇指/侧甲后，逐甲2×复核继续发现其余保留候选存在细小甲根缺口、锯齿和皮肤外刺，因此没有直接终结；第二轮对12枚问题甲面按原图重画，仅保留3枚已通过放大复核的polygon。最终3张/15 polygon全部合法、同图零交叠，几何15 pass/0 suspect，整图与15组逐甲2×确认甲根、两侧甲缘、装饰区和可见甲尖连续完整，无皮肤、背景、重复或交叠污染。三份返修终结SHA-256为`a95957fa…e9b1`、`5acd20ce…d614`、`7e534d07…7041`，第51至53个批准真值报告SHA-256为`662d5bed…eea0`、`06ce0bf0…1a73`、`b9443182…47a1`。唯一索引更新为53个批准报告、52张唯一图片/282 mask、1个冗余、0冲突，SHA-256为`c5f37ae5…549a`；最低100张train正样本完成52%、仍缺48张，val 0/30和约100张hard negative不变。

第三十七至三十八批继续处理同来源`nail_00277…_3`。初始只有3个候选且其中两个吸收整段手指，五枚完整可见甲面全部按原图人工重画；构建器先对相邻两甲88.2237像素交叠保持拒绝，按真实遮挡边界分离后5个polygon合法、零交叠。首轮逐甲2×又发现左侧侧甲与右上奶牛纹甲的可见甲尖不足，第二轮只替换这两枚，最终几何5 pass/0 suspect，整图与5组逐甲2×确认甲根、甲缘、装饰和甲尖完整。返修终结SHA-256为`1c5ba1ab…d551`，第54个批准真值报告SHA-256为`81ce29df…31b5`。唯一索引更新为54个批准报告、53张唯一图片/287 mask、1个冗余、0冲突，SHA-256为`a2912ec5…5684`；最低100张train正样本完成53%、仍缺47张，val 0/30和约100张hard negative不变。

第三十九至四十批处理同来源`nail_00476…_0`、`nail_00478…_2`和`nail_00482…_6`。原分辨率源图复核纠正了旧分片记录：`00476`的左侧拇指甲被图像边缘裁断，整张排除且不生成训练真值；`00478`与`00482`各有5枚完整可见甲面。批次039先补齐3枚漏甲，逐甲2×复核发现旧候选仍有甲根锯齿、侧缘尖刺和透明甲尖漏标；批次040仅保留3枚已审人工polygon，其余7枚按原图重画。最终2张/10 polygon全部合法、同图零交叠、几何10 pass/0 suspect，整图与10组逐甲2×视觉确认甲根、两侧甲缘、装饰及可见甲尖完整，无皮肤、衣物、背景、重复或交叠污染。两份返修终结SHA-256为`6469ebc7…d417`、`a91a8857…12ba`，第55至56个批准真值报告SHA-256为`5a0702ee…b58b`、`32f73303…3974`。唯一索引更新为56个批准报告、55张唯一图片/297 mask、1个冗余、0冲突，SHA-256为`2d4fde0a…1fb0`；最低100张train正样本完成55%、仍缺45张，val 0/30和约100张hard negative不变。

第四十一至四十四批处理分片007同来源`nail_01217…_4`、`nail_01218…_5`与`nail_01220…_7`。三张源图均为5枚完整可见长甲；旧候选存在漏甲、同甲重复、交叠、整段污染或吸收首饰，故三图15甲按原图人工重画。`01217`与`01218`首轮即通过；`01220`首轮放大复核发现3枚金粉甲只覆盖基础甲片、漏掉甲缘外凸立体装饰，第二轮仅保留2枚已审polygon并重画其余3枚。最终3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect，整图与15组逐甲2×视觉确认甲根、两侧甲缘、渐变/金粉装饰和甲尖完整，无皮肤、首饰、衣物、背景、重复或交叠污染。返修终结SHA-256为`bb09aa3e…b2ed`、`51334233…f49f`、`ea38267a…d560`，第57至59个批准真值报告SHA-256为`4b2f67a4…68b5`、`4f11e483…bd8f`、`16bab6f6…3c5c`。同来源`nail_00479…_3`因竖指仅露侧向局部甲尖排除。唯一索引更新为59个批准报告、58张唯一图片/312 mask、1个冗余、0冲突，SHA-256为`2d9687cd…8764`；最低100张train正样本完成58%、仍缺42张，val 0/30和约100张hard negative不变。

第四十五至四十六批继续处理同来源`nail_01216…_3`、`nail_01219…_6`与`nail_01221…_8`。三张原图均清晰且各有5枚完整可见甲面；批次045先删除前后两图重复候选，并把`01219`吸收大块指腹的拇指改为人工多边形。机器几何虽为15 pass/0 suspect，逐甲2×仍发现`01216/01221`多个保留候选有甲根凹口或边缘尖刺，因此未终结；批次046将两图10甲全部按原图人工重画。最终3张/15 polygon合法、同图零交叠、几何15/15，整图和15组逐甲局部确认甲根、两侧甲缘、渐变/亮片装饰与甲尖完整，无指腹、皮肤、戒指、衣物、背景、重复或交叠污染。返修终结SHA-256为`06058354…73f8`、`21eac83b…1a34`、`b6d6285b…0b4d`，第60至62个批准真值报告SHA-256为`1a89e093…c1c1`、`0e613a88…1562`、`2e1f9b5e…804d`。唯一索引更新为62个批准报告、61张唯一图片/327 mask、1个冗余、0冲突，SHA-256为`f6479f21…f1db`；最低100张train正样本完成61%、仍缺39张，val 0/30和约100张hard negative不变。

第四十七至四十九批处理同来源`nail_01215…_2`。源图5枚裸色长甲均清晰完整，但旧候选漏横向拇指，并用两个额外候选吸收大块指腹。批次047保留4枚候选、人工补拇指后几何5/5；逐甲2×继续发现食指吸收下方戒指、无名指和小指存在甲根尖刺，批次048重画这3枚。第二次放大复核又确认食指甲尖仍纳入戒指反光区域，批次049仅替换该甲并保留其余4枚。最终1张/5 polygon合法、同图零交叠、几何5/5，整图与逐甲局部确认甲根、两侧甲缘和可见甲尖完整，无戒指、指腹、衣物、背景、重复或交叠污染。返修终结SHA-256为`c1efc355…fe92`，第63个批准真值报告SHA-256为`f5750757…2ed1`。唯一索引更新为63个批准报告、62张唯一图片/332 mask、1个冗余、0冲突，SHA-256为`50727dde…356d`；最低100张train正样本完成62%、仍缺38张，val 0/30和约100张hard negative不变。

第五十至五十一批处理同来源`nail_01213…_0`与`nail_01222…_9`。两张原图均清晰且各有5枚完整可见长甲，旧候选则存在漏甲、重复及整段手指/皮肤污染。批次050保留3枚已确认逐甲完整的polygon并人工重画其余7枚，输出2张/10个合法polygon、同图零交叠；整图及逐甲2×复核发现`01222…_9`第4甲面仍漏掉左侧与甲面相连的立体饰品，批次051仅替换该甲并保留其余4枚。终版两图分别通过5/5几何审计，视觉确认甲根、两侧甲缘、透明或渐变甲尖及甲面附着饰品外轮廓完整，无整指、戒指、衣物、背景、重复或交叠污染。返修终结SHA-256为`ac80f0ab…886a`、`507aadcc…c11b`，第64至65个批准真值报告SHA-256为`c87d8670…a698`、`18e36cc8…b3b`。唯一索引更新为65个批准报告、64张唯一图片/342 mask、1个冗余、0冲突，SHA-256为`c95b2a13…772f`；最低100张train正样本完成64%、仍缺36张，val 0/30和约100张hard negative不变。

同来源`nail_00965…_0`与`nail_00967…_2`随后完成原分辨率分流。`00965`至少一枚应标甲面被相邻手指遮挡，仅露局部甲尖/装饰区，按完整甲面硬门整张排除；哈希绑定排除记录SHA-256为`91629e0f…4663`。`00967`五甲完整可见，但旧7候选含眼睛、大片头发及甲缘污染。批次052保留4个候选并重画右侧银粉甲，逐甲2×又识别出第1项实际覆盖指间头发/阴影、第5项吸收指腹；批次053仅保留中间3甲并重画左侧粉黑蝴蝶结甲与右侧银粉甲。构建器先后拦截非法polygon与7.4510像素交叠，修正后5个polygon合法、同图零交叠、几何5/5，整图及逐甲视觉确认甲根、两侧甲缘、甲尖与甲面附着蝴蝶结完整。返修终结SHA-256为`7a163fe3…e604`，第66个批准真值报告SHA-256为`1bf8f509…021e`。唯一索引更新为66个批准报告、65张唯一图片/347 mask、1个冗余、0冲突，SHA-256为`8b0f4276…d790`；最低100张train正样本完成65%、仍缺35张，val 0/30和约100张hard negative不变。

跨分片低风险完整甲批次055处理`nail_00495…_6`、`nail_01268…_6`与`nail_00227…_2`。三张源图均清晰且各有5枚完整可见甲面；首轮批次054保留旧候选并补两枚拇指，但放大复核发现`00495`四甲甲根存在尖刺/皮肤污染、`00227`小指与拇指遗漏透明甲尖，`01268`相邻灰色星纹甲与深蓝甲仍有12.9567像素交叠，因此未终结。批次055改为10个人工多边形并只保留5个已逐甲通过的polygon，构建器再次拦截交叠后按真实接触边界分离；最终3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect/0 missing，整图和15组逐甲2×复核确认甲根、两侧甲缘、透明/渐变甲尖及甲面链钻装饰完整，无皮肤、衣物、背景、漏甲、重复或交叠污染。返修终结SHA-256为`8b0aedbe…a5fa`、`61c603f7…36e4`、`7620ad52…8890`，第67至69个批准真值报告SHA-256为`f00edc75…4946`、`4ebfc939…a29f`、`d9d8c8c8…92f7`。唯一索引更新为69个批准报告、68张唯一图片/362 mask、1个冗余、0冲突，SHA-256为`d0550359…2385`；最低100张train正样本完成68%、仍缺32张，val 0/30和约100张hard negative不变。

跨分片边缘返修批次056处理`nail_00229…_4`、`nail_00193…_5`与`nail_00496…_7`。原分辨率放大复核确认自动候选虽计数等于5，仍分别存在透明甲边缘不完整、皮肤外溢、反光造成的甲缘缺口、甲根断裂，以及把手指关节、戒指和织物当作甲面的误检；因此15枚甲全部改为人工多边形。最终3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect/0 missing，整图和15组逐甲2×复核确认甲根、两侧甲缘、透明甲尖及甲面立体装饰完整，无皮肤、衣物、背景、漏甲、重复或交叠污染。返修终结SHA-256为`6186d161…d244`、`4bb2aa3a…ac15`、`eb42ab7b…60bb`，第70至72个批准真值报告SHA-256为`252eb5b7…f06`、`64014673…492`、`8d96bc00…cb21`。唯一索引更新为72个批准报告、71张唯一图片/377 mask、1个冗余、0冲突，SHA-256为`2d28a5cf…64b3`；最低100张train正样本完成71%、仍缺29张，val 0/30和约100张hard negative不变。

跨分片清晰五甲批次057处理`nail_00902…_4`、`nail_00196…_8`与`nail_00661…_0`。三张源图清晰且各有5枚完整可见甲面，但旧候选含重复透明甲、底部圆形背景、衣袖和整段手指误检，立体花饰甲根与三枚侧视/斜向甲还存在指腹污染；因此15枚甲全部改为人工多边形。首轮整图与逐甲2×继续拒绝短甲、拇指和两枚斜向甲的大块皮肤外溢，按真实甲根与侧视边界收紧后，最终3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect/0 missing，完整覆盖甲根、两侧甲缘、透明/渐变甲尖和甲面立体装饰。返修终结SHA-256为`7328d6b5…cf90`、`f750efa5…7796`、`1970a7d8…ff52`，第73至75个批准真值报告SHA-256为`8512b630…9be9`、`be4d1a0a…6dc8`、`22c03d74…107c`。唯一索引更新为75个批准报告、74张唯一图片/392 mask、1个冗余、0冲突，SHA-256为`28a81e40…e309`；最低100张train正样本完成74%、仍缺26张，val 0/30和约100张hard negative不变。

跨分片批次058处理`nail_00531…_5`、`nail_00301…_8`与`nail_00489…_0`。整图和逐甲2×首轮拦截了绸布误检、蝴蝶结甲仅覆盖局部、相邻两甲14.3736像素交叠、自然甲甲根吸收指腹以及透明游离缘遗漏；三图最终以3个已审polygon和12个人工polygon重建。终版3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect/0 missing，完整覆盖透明长甲、立体蝴蝶结和五枚自然甲的真实甲沟/甲根/游离缘。返修终结SHA-256为`72933f14…a3d3`、`e06f91b1…c6af`、`6c07716b…2c40`，第76至78个批准真值报告SHA-256为`d212a959…e1aa`、`174e3f19…5b7`、`b96b894e…5112`。唯一索引更新为78个批准报告、77张唯一图片/407 mask、1个冗余、0冲突，SHA-256为`b9299635…3a5e`；最低100张train正样本仍缺23张。

批次059处理`nail_00194…_7`与`nail_00906…_8`。两图9枚完整可见甲面全部人工重画；首轮机器合法性虽可生成候选，原分辨率视觉仍发现绿色长甲外的头发误检，以及蝶形透明甲漏甲根、深色甲/透明甲宽框吸收皮肤和猫毛，因此未提前终结。按真实甲缘重画后，终版2张/9 polygon合法、同图零交叠、几何9 pass/0 suspect/0 missing，整图和全部逐甲2×复核通过。返修终结SHA-256为`e57217c3…f199`、`35f01f70…1ddb`，第79至80个批准真值报告SHA-256为`c12cd939…1eac`、`2371f289…2bd7`。唯一索引更新为80个批准报告、79张唯一图片/416 mask、1个冗余、0冲突，SHA-256为`6e4dadf9…378d`；最低100张train正样本完成79%、仍缺21张，val 0/30和约100张hard negative不变。

批次060处理`nail_00183…_5`与`nail_00201…_9`。两张清晰实拍图各有5枚完整可见甲面，以7个已通过放大视觉审核的polygon和3个人工polygon重建。原分辨率局部复核进一步补齐侧视拇指甲面右缘的白色立体装饰，最终2张/10 polygon合法、同图零交叠、几何10 pass/0 suspect/0 missing，整图和全部逐甲2×复核通过。返修终结SHA-256为`a7821305…15aa`、`d9734c65…cdc5`，第81至82个批准真值报告SHA-256为`b34c4d96…20ea`、`826831f7…3da8`。唯一索引更新为82个批准报告、81张唯一图片/426 mask、1个冗余、0冲突，SHA-256为`48d5ea4b…ed48`；最低100张train正样本完成81%、仍缺19张。

批次061处理`nail_00719…_0`与`nail_01115…_2`。两张清晰实拍图各有5枚完整可见长甲，以8个已通过逐甲放大审核的SAM polygon和2个人工polygon重建；原分辨率视觉门进一步收紧`00719`第5甲甲根，并重画`01115`第3枚透明低对比长甲以清除暗色背景外扩。终版2张/10 polygon合法、同图零交叠、几何10 pass/0 suspect/0 missing，整图和全部逐甲2×复核确认甲根、两侧甲缘、装饰区与完整甲尖无遗漏。返修终结SHA-256为`e9bc325d…2960`、`97c16351…f313`，第83至84个批准真值报告SHA-256为`990dbba8…06f9`、`07e0e9e9…7e9f`。唯一索引更新为84个批准报告、83张唯一图片/436 mask、1个冗余、0冲突，SHA-256为`a2942ab0…2d2`；最低100张train正样本完成83%、仍缺17张。

批次062处理`nail_00722…_3`、`nail_00723…_4`与`nail_01118…_5`。三张清晰实拍图各有5枚完整可见长甲；首轮SAM和多正点/贴边负点重试仍分别吸收衣带、皮肤、玩偶绒毛或眼睛，因此按门禁停止继续盲目提示并切换原分辨率人工多边形。终版以13个人工polygon和2个已通过逐甲放大审核的SAM polygon重建3张/15甲，整图及全部逐甲2×复核确认甲根、两侧甲缘、装饰区、透明/裸粉甲面和完整甲尖无遗漏，15/15 polygon合法、同图零交叠、几何15 pass/0 suspect/0 missing。返修终结SHA-256为`ff2bdb04…c63e`、`be037c5d…c618`、`134a1cd7…f389`，第85至87个批准真值报告SHA-256为`81baeaff…0cb`、`7ebe092f…19f8`、`c5bf14a7…369f`。唯一索引更新为87个批准报告、86张唯一图片/451 mask、1个冗余、0冲突，SHA-256为`300ef9ea…28a2`；最低100张train正样本完成86%、仍缺14张。

批次063处理`nail_00225…_0`、`nail_00916…_2`与`nail_00713…_6`。三张清晰实拍图各有5枚完整可见甲面；逐甲紧框SAM虽生成15个候选，原分辨率整图和逐甲2×复核仍拒绝整段指腹、皮肤、装饰分裂与背景污染。终版以11个人工polygon和4个已审SAM polygon重建3张/15甲，透明裸粉甲、立体花饰、格纹/雪花甲及银粉裸色延长甲的甲根、两侧甲缘、装饰区和完整甲尖均由唯一polygon覆盖。15/15 polygon合法、同图零交叠、几何15 pass/0 suspect/0 missing。返修终结SHA-256为`cba0b81c…9156`、`53909584…9811`、`0989b27a…58e4`，第88至90个批准真值报告SHA-256为`dcba46dc…5729`、`b8e342c8…4a40`、`b1028bc1…dd2`。唯一索引更新为90个批准报告、89张唯一图片/466 mask、1个冗余、0冲突，SHA-256为`7f06410c…16b6`；最低100张train正样本完成89%、仍缺11张，val 0/30和约100张hard negative不变。

批次064处理`nail_00476…_0`、`nail_00712…_5`与`nail_00291…_2`。源图逐张确认各有5枚清晰、完整可见甲面；`00710`因仅4甲而排除。首轮15个SAM候选经整图和全部逐甲2×复核发现拇指金属碎片、透明甲衣物/背景支路、邻指皮肤污染与水钻装饰交叠；`00291`收紧提示重试后第2/3甲仍污染，第4/5甲仍交叠75.9302像素，因此按门禁切换相应人工多边形。终版以9个逐甲放大通过的SAM polygon和6个人工polygon重建3张/15甲，灰粉贝壳亮片、透明银粉延长甲及银灰水钻长甲的甲根、甲身、立体装饰和完整甲尖均由唯一polygon覆盖。15/15 polygon合法、同图零交叠、几何15 pass/0 suspect/0 missing。返修终结SHA-256为`6e60e5c6…70ba`、`bd70072f…691b`、`98a34ec9…155c`，第91至93个批准真值报告SHA-256为`e5e8d7ac…5b6b`、`d99e3c7a…2926`、`136ece68…2174`。唯一索引更新为93个批准报告、92张唯一图片/481 mask、1个冗余、0冲突，SHA-256为`a9d5936a…2246`；最低100张train正样本完成92%、仍缺8张，val 0/30和约100张hard negative不变。

批次065处理`nail_00293…_4`、`nail_00711…_4`与替换候选`nail_00292…_3`。原候选`00915`在首轮与收紧重试后仍大面积合并手指/手掌，保持返修且未生成真值；替换图逐张确认5枚甲面清晰完整。终版以6个逐甲2×审核通过的SAM polygon和9个人工polygon重建3张/15甲；首轮整图与逐甲复核后，第二轮继续修正`00293`横向拇指甲根皮肤、`00711`第4枚银灰亮片长甲漏尖和`00292`横向拇指衣物轮廓。裸粉、金粉、水钻、银灰亮片及透明长甲的甲根、甲身、立体装饰和完整甲尖均由唯一polygon覆盖，15/15 polygon合法、同图零交叠、几何15 pass/0 suspect/0 missing。返修终结SHA-256为`b82e94b7…5f97`、`acdac8ea…4dac`、`96b02ea7…0537d`，第94至96个批准真值报告SHA-256为`bc11ac78…9440`、`e2d84076…e64c`、`c4854173…34d7`。唯一索引更新为96个批准报告、95张唯一图片/496 mask、1个冗余、0冲突，SHA-256为`12e3d613…3510`；最低100张train正样本完成95%、仍缺5张，val 0/30和约100张hard negative不变。

批次066处理`nail_00294…_5`、`nail_00914…_0`与`nail_01262…_0`。逐甲SAM完成3张/15提示、0 fallback，但初轮几何仅7 pass/8 suspect，原分辨率整图和逐甲2×复核还发现整指、皮肤、背景、错误弯曲指腹以及相邻甲面污染，因此未用候选计数替代视觉门，15枚甲面全部转为人工polygon。多轮复核继续修正`00294`横向拇指与食指的可见遮挡边界、`00914`侧视立体装饰与误落指腹的第5候选、格纹链钻甲和雪花甲的遮挡边界，并平滑`01262`甲根锯齿与皮肤外刺。终版3张/15 polygon全部合法、同图零交叠、几何15 pass/0 suspect/0 missing，整图和全部逐甲2×确认甲根、甲身、附着装饰与甲尖完整。返修终结SHA-256为`dd4d52e5…5965`、`bc6e3295…a2c6`、`0168a2d8…1a1`，第97至99个批准真值报告SHA-256为`569b24c9…e570`、`6c77feb9…be33`、`49ebc05a…6444`。唯一索引更新为99个批准报告、98张唯一图片/511 mask、1个冗余、0冲突，SHA-256为`35f437d5…937e`；最低100张train正样本完成98%、仍缺2张，val 0/30和约100张hard negative不变。

批次067处理`nail_00538…_3`与`nail_00301…_11`；原候选`01113`经原图复核只有4枚人类甲面完整可见，未进入本批。SAM2.1 large完成2张/10提示、1次box fallback，但初轮几何仅3 pass/7 suspect，原分辨率整图和逐甲2×复核发现候选吸收整指、皮肤、衣物与背景，未直接晋级。终版10枚甲面全部以原分辨率人工polygon重建；首版视觉门继续补齐透明甲尖、立体花饰与水钻边缘，其中一次扩边触发38.5285像素真实交叠并被构建器拒绝，按真实可见遮挡边界分离后，10/10 polygon合法、同图零交叠、几何10 pass/0 suspect/0 missing，整图及全部10组逐甲2×叠加图通过。返修终结SHA-256为`31b20b817b38465fb6135fcfa03e9c57542b13caaf349c282feafb667d75b414`、`d585525d8aeadf610dfb06eddfe67e77d9c6411af4bdabbcf7a1fb966be061f2`，第100至101个批准真值报告SHA-256为`4016ecb6a3ccf521c53d5a02233175b6908c3b1bb2092049dbaa3d55d9cf58b7`、`ae846132b1fcc5a1df169ebac830733e914e74bda0e6444dae4d7a1f10502006`。唯一索引更新为101个批准报告、100张唯一图片/521 mask、1个冗余、0冲突，SHA-256为`13f606b547c32d2b8f34651f55e1bca1e826bf3ac13bdcdca345a1cef267f125`；最低100张train正样本门已达到。根目录权威索引与`final`当前镜像一致；val 0/30、约100张hard negative、整批物化和来源隔离门仍未完成。

v1.1.178转入来源隔离val：`build-real-material-annotation-workspace.py`新增显式`--selection-mode val`，按计划`assignedRole=val`选取完整角色并保持默认`first-train`兼容。真实工作区物化30张/7来源组/3分片/159枚预期完整甲面，30/30为硬链接，manifest SHA-256为`59c5f421…1d47`。YOLO v6在部署512口径生成155候选，14张少候选、4张计数相等、12张多候选、6对重复重叠；SAM2.1 large完成30图/155提示、0 fallback、0错误，几何112 pass/43 suspect。16页原分辨率审核仅`nail_00456…_2`的2枚完整甲面直通，其余29张因漏甲、重复、眼睛/头发/瓶体/衣物/背景或皮肤污染返修，0张源图排除。工作区SHA-256为`3a13a2c1…2c32`，四个终结报告SHA-256为`65e8cdd9…261d`、`b831bb9e…c4d`、`696d0d3a…498b`、`09876d17…ace9`。

这次首轮审核完成不等于val真值完成：1张直通项仍须通过polygon合法性、同图零交叠和val角色真值终审；29张返修全部清零前，整套split按规则仍记为正式val真值0/30，不能用于模型选择、阈值校准或候选训练。

v1.1.179把最终真值终结和唯一索引扩展为角色感知模式。val终审必须显式传入`--truth-role val --role-manifest`，逐图核对工作区`selectionMode/assignedRole=val`、图片哈希、来源组、预期甲数和训练禁用状态；成功报告使用独立validation决定与状态，训练真值索引不会接纳。唯一索引按`validation-truth-*-final.json`去重并继续拒绝同图身份、annotation哈希、来源组或mask数冲突；默认train行为保持兼容。

返修批次001—004共晋级5张，连同直通`00456`形成6张/24 mask。`00454/00457/00384`通过删除袖口/整指假阳性或紧框重建；`00829`的两枚透明/紫色甲在SAM重试后仍断开透明区或带入后方局部甲，转为2个人工polygon；`00672`保留3枚已审polygon并重画2枚持续吸收指腹的长甲。`00455`的拇指SAM重试仍吸收大块皮肤，保持返修未计入。6个终审报告SHA-256为`a6fb8820…0942`、`6b2f2235…a10b`、`9943371a…eeb4`、`bb35a251…34fc`、`597489b4…c6d5`、`cd9c0395…c89a`；唯一索引SHA-256为`adac6dc3…33c7`。

这代表数据结构门当前通过，不代表模型质量已经达标。

### 8.2 训练主流程

```text
素材入库与授权审计
  -> 标注/人工复核
  -> 标签审计与数据切分
  -> materialize 训练数据
  -> train-yolo-seg.py
  -> evaluate.py / assess-model-metrics.py
  -> export-onnx.py
  -> quantize-onnx-int8.py（可选）
  -> 浏览器 fixture 与性能验证
  -> 发布注册、切换与回滚验证
```

关键脚本分类：

| 类别 | 主要入口 |
| --- | --- |
| 环境检查 | `check-training-environment.py` |
| 数据盘点 | `audit-image-corpus.py`、`audit-labels.ts`、`audit-phase1-readiness.ts`；平铺语料统一归入`.`根桶，避免把文件名误计为一级目录 |
| 实拍候选intake、授权、审核工作区与分配 | `build-real-material-candidate-intake.py`、`authorize-real-material-candidate-intake.py`、`build-real-material-review-workspace.py`、`audit-real-material-exclusive-assignment.py`；逐图复核哈希/尺寸、稳定分组并按来源组原子分片，A/B/C授权绑定原证据；未审核条目禁止训练，最终审核必须全覆盖且训练、val、独立发布测试按来源组互斥 |
| 数据准备 | `convert-annotations.ts`、`split-dataset.ts`、`materialize-training-dataset.ts` |
| 辅助标注 | `sam-assisted-nail-annotation.py` |
| 审核区域提取 | `extract-reviewed-image-regions.py` |
| 审核区域替换合并 | `merge-reviewed-region-reports.py`；按父图替换错误派生区域，强制父哈希和稳定来源组一致，并物化无重复父项的新版聚合区域包 |
| 发布测试派生区域intake | `build-release-test-region-intake.py`；继承发布测试/长期回归授权，禁止训练，校验stress父项、父子哈希、派生文件和一父一主区域 |
| 发布测试提示修复 | `build-reviewed-sam-repair-prompts.py`；按人工keep/drop/add决定重建提示，支持逐新增框选择SAM提示模式，记录源提示/修复清单哈希并保持候选隔离 |
| SAM提示几何审计 | `audit-sam-prompt-geometry.py`；按提示与多边形输出面积比、包含率、中心关系和同图边界框IoU的JSON/CSV，仅作为提示一致性证据，不能替代原分辨率视觉审核 |
| 发布测试审核聚合 | `build-release-test-annotation-review.py`、`build-release-test-review-summary.py`；叠加修复报告、核对polygon数/来源组并将派生决定映射回父图 |
| 发布测试拓扑返修 | `repair-reviewed-annotation-topology.py`；仅处理清单声明的无效polygon/遮挡交叠，限制丢弃面积与甲面损失，并输出整图和逐甲2×审核证据 |
| 发布测试候选冻结 | `freeze-reviewed-release-test-candidates.py`；要求全部polygon合法、同图零交叠、训练禁用，并固定图片/标注/联合/聚合SHA-256与100张代表性规模门 |
| 冻结测试评估物化 | `materialize-frozen-release-test-evaluation.py`；独立复算冻结快照、验证与正式训练集来源组及图片哈希零重叠，只物化test并禁止训练；schema v2绑定源manifest、三份YAML、评估manifest和递归文件清单，`--verify-report`只读重放全部当前字节 |
| 冻结测试质量报告 | `build-frozen-release-test-quality-report.py`；schema v2动态绑定旧67或新100快照，深验评估物化、assessment标签、部署512全量/核心/压力指标、预测覆盖及同一候选权重SHA-256；三组512必须同时通过，640仅诊断。`--verify-report`重读全部传递输入、临时重建并逐字段比较，完成度审计据此拒绝伪造、漂移、换绑及历史小测试回退 |
| 冻结测试失败画像 | `profile-frozen-release-test-failures.py`；按部署置信度逐实例匹配真值/预测，聚合lane与父来源组并生成最高风险原分辨率叠加图，严格禁止测试数据回流训练 |
| 验证集阈值校准 | `calibrate-model-score-threshold.py`；只接受来源隔离val证据，绑定数据/权重/预测哈希，少于30图、真值polygon需修复或质量约束不满足时禁止生成manifest阈值；`--verify-report --expected-weights`用于导出前只读深验 |
| 派生区域标注审计 | `verify-reviewed-region-annotations.ts` |
| 派生区域入库构建 | `build-reviewed-region-intake-batch.ts` |
| 训练 | `train-yolo-seg.py` |
| 评估 | `evaluate.py`、`assess-model-metrics.py` |
| 来源隔离实验集增量构建 | `extend-source-isolated-dataset.py`；从已审计快照加入授权样本，禁止新增项进入 test，并对冻结 test 图片与标签做逐文件联合 SHA-256 校验 |
| 导出/量化 | `export-onnx.py`、`quantize-onnx-int8.py`；候选导出必须使用`--candidate-mode --calibration-report`派生阈值并写入`scoreThresholdEvidence`，禁止手工阈值绕过 |
| 浏览器烟雾模型 | `build-browser-smoke-model.py` |
| 发布门 | `scripts/verify-*.ts`、`scripts/run-*-pipeline.ts` |
| 发布治理 | `register-model-release.ts`、`switch-model-release.ts`、`promote-approved-release.ts` |
| 最终完成度审计 | `audit-nail-texture-local-inference-completion.ts`；核对实施规范清单、全部关键证据和生产资产，缺证据时输出HOLD及责任方；用户/工程清单必须非空、候选checkbox格式合法且文本唯一，所有候选进度行必须可解析且标记ID唯一，拒绝空文档、畸形/重复清单、静默漏行和重复PASS计数 |
| 外部验收证据 | `build-nail-texture-device-acceptance.ts`、`build-nail-texture-beta-review.ts`、`build-nail-texture-user-failure-cases.ts`；由已验证原始报告或CSV生成总门稳定JSON |

真实训练在本地 Python/Ultralytics/PyTorch 环境执行，不需要在训练循环中调用 GPT。GPT 或其他视觉模型只能作为素材生成、辅助标注或审核工具，生成结果必须经过授权与人工质量控制。

`sam-assisted-nail-annotation.py` 的失败报告会包含具体提示序号和提示模式；mask轮廓转换失败也会记录对应序号。报告中的推理成功只代表候选已生成，仍必须查看原分辨率overlay，整图所有应标甲面完整且无皮肤/背景污染后才能复制到正式审核目录。

### 8.3 real-prelabel-v3 隔离工程验证

`nail-texture-seg-real-prelabel-v3` 仅用于提高人工审核候选召回率，不是正式发布候选。其 512 FP32 ONNX 已完成以下轻量工程检查：

- 文件大小 11,566,101 字节（11.03MB），低于 15MB MVP 上限、高于 8MB 理想值；
- manifest SHA-256 `280a2ff809231ee07130ea350469b26ccd34ab086904c5434c7fa095e1dbb4b8` 与实际文件一致；
- ONNX Runtime 实际输出为 `[1,37,5376]` 和 `[1,32,128,128]`；
- TypeScript 后处理 fixture 解码得到 5 个带 mask 候选；
- 该批次现已获得正式授权，但此历史产物训练时使用的是未完成人工闭环的候选标注，且没有通过正式独立质量门；因此仍只允许辅助标注，不得覆盖生产 manifest、注册或 promotion。

仅使用当前授权正式集训练的 `nail-texture-seg-real-seed-v1` 已在 46 张独立 test 上复评：box mAP50 为 0.380，mask mAP50 为 0.367；相对 512 合成基线分别下降 0.143 和 0.101，均超过 0.02 退化上限。质量门按预期拒绝该候选，因此不继续导出、注册或发布。

### 8.4 真实候选 v4–v9 结论

- v4 使用 393 图混合集继续训练，独立原 test 的 box/mask mAP50=0.429/0.397，未通过质量门，未导出或发布。
- v5 使用 92 张真实图构建来源隔离实验集（66/13/13），以 deerplanet 集合作为从未参与训练的 test；512 评估 box/mask mAP50=0.848/0.836，box 略低于 0.85 冻结门槛，资产门通过但发布门正确拒绝。
- v6 在相同无泄漏实验集上以 640 训练、512 部署评估；13 张独立真实 test、102 个 mask 的 box/mask mAP50=0.853/0.848，超过 0.85/0.75 门槛。FP32 ONNX 为 11,566,102 字节（11.03MB），SHA-256 为 `d122da819a4b1c70a954a55d84b26ed53fc33fb9bd8374a9e69c0e106909e57d`，ORT 输出 `[1,37,5376]` / `[1,32,128,128]`，TypeScript fixture 解码 7 个带 mask 候选。
- Chromium + WebGPU 采集 29 次热推理：端到端 P50/P95/最大值为 108.9/133.7/159.5ms，Worker P95 为 100ms，低于桌面 800ms 门槛；冷启动单次约 4.10s，仅作为加载基线，不混入热推理统计。
- Windows / Playwright Chromium / WebGPU 连续运行 20 次：JS heap 峰值 19.86MiB、首末五次均值增长 1.69MiB；Chromium 全进程 private memory 峰值 929.50MiB、首末窗口增长 121.81MiB，最长连续增长 7 次，未持续单调增长。桌面暂定稳定性门通过；全进程值包含 renderer/GPU/utility/缓存，不能替代移动端模型增量内存。
- v6曾是首个通过历史13张独立真实精度、模型资产、输出协议和桌面热性能门的候选；冻结67张扩展快照经来源隔离物化后，在部署512下全量box/mask mAP50=0.8370/0.8313，核心45张=0.8485/0.8523，压力22张=0.8179/0.7919。全量box未达0.85，压力组相对历史基线退化超过0.02，因此正式拒绝v6发布。640全量0.8570/0.8549仅作诊断，不能改变部署512结论。生产promotion保持HOLD。
- v7 将新增 5 张审核图并入来源隔离实验集，规模更新为 97 图、672 mask，train/val/test=69/15/13；冻结 deerplanet test 保持 13 图/102 mask 不变。以 v6 权重继续训练后，512 test 的 box/mask mAP50=0.840/0.833，box 低于 0.85 且两项均较 v6 退化，因此质量门拒绝；未导出 ONNX、未注册、未发布，v6 继续作为最佳候选。
- v8 将跨分辨率共识后新增的 2 张/9 mask 并入来源隔离实验集，规模更新为 99 图/681 mask，train/val/test=70/16/13；冻结 deerplanet test 仍为 13 图/102 mask。以 v6 权重续训 16 epochs 后 early stop，512 test box/mask mAP50=0.8487/0.8472；box 低于 0.85，且两项均未超过 v6，质量门拒绝。未导出 ONNX、未注册、未发布。
- v9 从已审计 v8 快照安全加入 7 张截图派生图/41 mask，规模更新为 106 图/722 mask，train/val/test=76/17/13。新增项仅进入 train/val；冻结 13 图/102 mask test 的图片和标签联合 SHA-256 前后均为 `7af1a82c8b20608b486ed7e744366a842a722f86519e49ba0b34cf922984059e`。以 v6 权重续训 16 epochs 后 early stop，512 test box/mask mAP50=0.8411/0.8393，分别较 v6 下降 0.0116/0.0084；box 未达 0.85 且两项均未改善，质量门拒绝。未导出 ONNX、未注册、未发布；v6当时保持历史13张小测试集最佳，后续扩展67张评估结论见本节前述。
- 冻结67张阈值画像暴露了共享固定阈值不利于模型版本独立校准的问题。浏览器现已支持由manifest携带模型级`scoreThreshold`，并在原始候选和质量排序两道过滤中统一生效；旧manifest仍用0.35。本次仅完成机制，不把诊断点0.25写入生产manifest，v6拒绝与HOLD结论不变。
- v6原始来源隔离实验集的13张val（来源组`more`，不进入train/test）曾按部署512得到box/mask mAP50=0.9376/0.9420，阈值0.20曾得到40/45匹配、5漏检、2误检。后续隔离拓扑候选和13/13张原分辨率审核确认：14个无效polygon之外，还存在2张未声明交叠，以及漏甲、背景/雕塑误标、重复mask、皮肤污染、边缘裁断和1张域外空标签；最终仅3张通过、7张返修、3张排除，整套split输出`rejected_as_calibration_truth`。因此上述mAP和0.20均降级为基于不合格真值的历史诊断，不得用于模型选择、候选比较或manifest；`manifestScoreThreshold`继续为空，下一轮必须另建不少于30张且全部视觉通过的来源隔离val。
- 将该拒绝审核报告显式传入新版校准器复跑，输出`diagnostic_only_validation_truth_rejected`、`calibrationEligible=false`和`manifestScoreThreshold=null`；说明视觉门不是文档约定，而是校准代码的实际阻断条件。
- 下一候选训练预检确认RTX 4060 Laptop 8GB、v6/v9权重和正式409图物化集可用，但正式val 46图/234 mask存在5处polygon交叠；300张AI图均属于`ai-nail-2026-07-04`且该来源组分布为train/val/test=210/45/45，因此该val只能作为训练过程内部观察，不能作为来源隔离模型选择或阈值真值。现有授权真实增量已用于v7–v9且候选连续退化；在`真实素材/2026_7_14`的1277张素材获得商业训练授权并完成去重/视觉审核前，不启动数据依据不足的v10，不使用冻结发布测试或未授权素材训练。
- 上述预检现已成为代码硬门：正式409图集的来源审计输出`rejected_dataset_source_isolation`，候选验证审计输出`rejected_candidate_training_validation`，明确列出AI来源组跨split、缺少46/46视觉审核和5处polygon交叠。将该拒绝报告传给v10候选模式，即使`--dry-run`也会在模型加载前报`candidate validation report is not approved`；普通实验路径仍兼容但摘要明确标记为experiment。

## 9. 验证与质量门

基础工程门：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

纹理识别与模型发布还应根据改动范围执行：

- `scripts/verify-model-artifact.ts`
- `scripts/verify-model-output-fixture.ts`
- `scripts/verify-browser-integration.ts`
- `scripts/verify-recognition-performance.ts`
- `scripts/verify-texture-quality-gate.ts`
- `scripts/verify-real-model-readiness.ts`
- `scripts/run-real-model-final-audit.ts`
- `scripts/audit-nail-texture-local-inference-completion.ts`
- `scripts/build-nail-texture-device-acceptance.ts`
- `scripts/build-nail-texture-mobile-memory-raw.ts`
- `scripts/build-nail-texture-beta-review.ts`
- `scripts/build-nail-texture-user-failure-cases.ts`

验收原则：

- 单元测试通过不等于真实设备通过；
- synthetic/smoke 模型通过不等于真实模型质量通过；
- 数据 readiness 通过不等于训练指标或用户体验通过；
- 摄像头、WebGPU、移动端裁切和手心/手背识别必须进行目标浏览器真机测试。

`npm.cmd run audit:mvp-readiness:deferred`只用于明确排除真实数据与真实模型资产的工程脚手架阶段；它会把数据集、训练授权和浏览器模型资产三项标为`deferred`，不能替代严格`audit:mvp-readiness`，也不能作为实施规范最终完成、生产 promotion 或发布解锁证据。

移动真机验收必须从`/device-benchmark`导出的20次同会话性能样本开始；浏览器JS堆只作诊断，Android整体进程内存必须来自Profiler或系统采样，iPhone/iPad必须来自Instruments。`build-nail-texture-device-acceptance.ts`当前输出`nail-texture-device-acceptance/v2`，并绑定性能验证、内存验证及原始内存文件路径和SHA-256；最终完成度审计会重新打开这些文件并重算统计与身份，不能只信任设备报告外层`ok=true`。具体执行步骤见`docs/mobile-device-acceptance-runbook.md`。

Git 推送若出现`Failed to connect to github.com port 443`，应先用只读的DNS、HTTPS和`git ls-remote`复核链路，再比较`origin/master...master`，避免在提交其实已经到达远端时重复推送。2026-07-20复核时Git智能HTTPS端点已恢复，`git ls-remote`约1.18秒返回，本地`master`与`origin/master`均为`cc1f263`且ahead/behind为0/0；该现象属于传输层瞬时超时，不改变模型、数据或发布状态。2026-07-21再次收到同类21.595秒连接超时后，只读复核确认DNS解析、GitHub首页HTTPS 200和`git ls-remote origin HEAD`均已恢复，Git握手约1秒返回；环境变量与WinHTTP均无代理，GitHub状态页的Git Operations为正常。因此仍按瞬时链路故障处理，不通过改分支、重写提交、关闭TLS校验或重复推送规避。

### 9.1 最近一次白皮书一致性审查

2026-07-12 v1.1.0 审查结果：

- 当前 6 个页面路由和唯一 HTTP API 均已在本文档登记；
- Next.js/React 版本与 `package.json` 一致；
- 正式 ONNX 文件缺失与最终审计 `blocked` 状态一致；
- smoke 环境变量覆盖风险已登记；
- 文本编码审计通过：294 个文件，0 个失败；
- 本次只修改文档与项目规则，未重新执行运行时代码测试，不能用本次审查替代最近一次功能测试或真机测试。

### 9.2 端侧实施技术规范复核

2026-07-12 对 `docs/nail-texture-local-inference-implementation-spec.md` v1.0 进行现状复核：

- 文档的产品边界、浏览器端侧架构、模型/数据/性能分阶段门禁、隐私和回滚原则仍可作为目标实施规范；
- 第 3.2 节及第 16–17 节部分“当前缺口/待办”已过期：源码现已具备 Worker 环境识别、可静态分析的 ONNX Runtime WebGPU/WASM 导入和 letterbox 预处理，对应进度文档的 `M1-T1-RUNTIME` 已通过；
- 正式 `nail-texture-seg-v1.onnx` 仍缺失，生产 manifest 的最终状态继续为 blocked；真实数据已开始导入和视觉审核，但尚未形成独立真实测试集与正式发布证据；
- 因此该文档当前应定位为“目标规范 + 历史实施基线”，不能单独作为当前完成度来源；实时状态应以本白皮书和 `docs/nail-texture-local-inference-implementation-progress.md` 为准。

本次为只读评审，没有修改运行时接口、模块状态或被评审规范原文。

## 10. 隐私、安全与资源管理

- `/editor` 上传照片在浏览器本地处理；
- `/ar-tryon` 摄像头帧在浏览器内存中处理，不录制、不上传，但 MediaPipe 程序资源会从 jsDelivr CDN 下载；
- 自动纹理识别默认在浏览器 Worker/主线程中运行；
- `/api/generate-ai` 只接收文字，但会把增强后的文字发送给外部图像服务，返回的图片也由浏览器访问外部 URL；
- `OPENAI_API_KEY` 只能存在于服务端环境变量；
- `ImageBitmap`、对象 URL、MediaStream track、Worker 和动画帧循环必须在取消或卸载时释放；
- 用户素材、训练图片、大模型权重和生成数据默认不应加入 Git；应通过 `.gitignore`、对象存储或独立数据盘管理；
- 正式 API 上线前需增加鉴权、限流、内容安全、审计、费用保护和错误信息脱敏。
- `/privacy` 是当前产品文案，不构成已完成的法律合规审计；其中“保存的试戴效果图”在现有 AR 页面没有对应保存按钮，应在实现功能或修订文案后再验收。

## 11. 已知限制与下一阶段

### 11.1 阻塞项

1. v6资产、协议和桌面性能证据有效，但旧冻结67张/384 mask在部署512下的扩展质量门失败，正式拒绝发布；部署阈值画像进一步确认压力组召回仅0.6983，透明相邻长甲、多甲同屏、低对比漏整甲/局部识别及手指/腕表误检是首要方向。规范val30又以部署512得到box/mask mAP50=0.6241/0.5630，0.05—0.50扫描无合格阈值，`manifestScoreThreshold=null`，进一步证明不能靠降低置信度挽救v6。候选训练数据门当前为train 100/100张、521个完整mask，val 30/30张、144个完整mask并已通过规范物化、校准真值终审、与train/冻结test三类身份零重叠及真实阈值深审；hard negative严格复筛后仅1/100张安全候选，尚未晋升`approved_hard_negative_manifest`且缺99张。按三类最低图片数量为131/230，约57%。规范候选数据集物化器、独立完整输入审计、训练入口双重重放、训练/val/test三路强隔离编排、冻结test只读深验、校准报告只读深验和最终发布证据复核均已实现，且将100/100/30与固定角色编码为不可下调门；真实输入运行输出`hold_canonical_candidate_dataset_materialization`，观察数量100/1/30，HOLD报告SHA-256为`a0cec8aafaf1aef7c69124824cc9c108a8af02df69730bbad725bc88bb151493`，候选数据集目录未创建。因此当前唯一候选训练数据阻塞仍是补充、授权、原分辨率审核并正式汇总剩余99张hard negative；补齐后须重跑物化和输入审计取得PASS，再由三路流水线启动训练，不能直接越门。代表性发布test已补齐并冻结为100张/554 mask，但仍缺绑定新候选模型的该快照质量结果、用户典型失败案例、四类移动真机和至少100张Beta人工质量审核；这些阻塞正式发布，但不替代上述候选训练输入门。移动真机采集页、Profiler/Instruments CSV转换、设备验收v2及完成度深度重放已就绪，但没有真实物理设备证据前四个设备报告仍必须缺失或HOLD；
截至v1.1.157，阻塞项中的训练真值数量以56个批准报告、55张唯一图片/297 mask为准；最低100张train正样本仍缺45张。`00476`裁边排除，`00478`与`00482`新增10个终审mask；该更新替代本条前半段的v1.1.156嵌入快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

截至v1.1.162，训练真值数量以66个批准报告、65张唯一图片/347 mask为准；最低100张train正样本仍缺35张。同来源`00967`新增5个终审mask，眼睛/头发误检及指腹污染均已清除；`00965`因甲面遮挡正式排除。该更新替代上方v1.1.161嵌入快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

截至v1.1.165，训练真值数量以75个批准报告、74张唯一图片/392 mask为准；最低100张train正样本仍缺26张。跨分片`00902/00196/00661`新增15个终审mask，重复候选、圆形背景、衣袖、整段手指和指腹污染均已清除。该更新替代上方v1.1.164快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

截至v1.1.167，训练真值数量以80个批准报告、79张唯一图片/416 mask为准；最低100张train正样本仍缺21张。批次058—059新增5张/24个终审mask，绸布、头发、皮肤、猫毛背景、局部甲面、漏甲根和透明游离缘遗漏均已清除；第三张相邻甲交叠候选未为凑数放行，仍留在返修队列。该更新替代上方v1.1.165快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

截至v1.1.168，训练真值数量以82个批准报告、81张唯一图片/426 mask为准；最低100张train正样本仍缺19张。批次060新增2张/10个终审mask，两图的完整甲根、甲缘、延长甲尖及侧视白色立体装饰均已由唯一完整polygon覆盖。该更新替代上方v1.1.167快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.168收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计为274个标记/261个PASS、2/10门，按预期保持HOLD。HOLD由发布质量与外部验收门触发，不否定本批训练真值的通过结论。

截至v1.1.169，训练真值数量以84个批准报告、83张唯一图片/436 mask为准；最低100张train正样本仍缺17张。批次061新增2张/10个终审mask，透明低对比长甲的完整甲根、两侧甲缘、装饰区和甲尖均由唯一完整polygon覆盖；原分辨率视觉门清除了第3甲暗色背景外扩。该更新替代上方v1.1.168快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.169收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计为277个标记/264个PASS、2/10门，按预期保持HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口未改变，训练禁用状态保持；本轮GitHub热力图与比较页乱码仅作本地/远端只读诊断，不改变模型接口或仓库分支。

截至v1.1.170，训练真值数量以87个批准报告、86张唯一图片/451 mask为准；最低100张train正样本仍缺14张。批次062新增3张/15个终审mask，两轮SAM失败后以人工多边形清除衣带、皮肤、玩偶绒毛和眼睛污染，并在相邻延长甲接触区保持可见甲面完整且同图零交叠。该更新替代上方v1.1.169快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.170收口验证为联合专项12/12、文本编码407/407、README严格结构通过；完成度审计更新为281个标记/268个PASS、2/10门并按预期保持HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，训练禁用状态保持。`E:\.pnpm-store`只读核对为pnpm v11依赖缓存，创建和最后写入均在2026-06-29，本轮未修改或删除。

截至v1.1.171，训练真值数量以90个批准报告、89张唯一图片/466 mask为准；最低100张train正样本仍缺11张。批次063新增3张/15个终审mask，原分辨率视觉门把SAM计数齐全但吸收整指/皮肤、只覆盖装饰或漂移到背景的候选转为人工多边形，并保留4个已逐甲放大通过的SAM polygon。该更新替代上方v1.1.170快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.171收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为285个标记/272个PASS、2/10门并按预期保持HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，训练禁用状态保持。权威训练真值索引固定为审核工作区根目录文件，历史`final`同名副本不参与当前计数。

截至v1.1.173，训练真值数量以93个批准报告、92张唯一图片/481 mask为准；最低100张train正样本仍缺8张。批次064新增3张/15个终审mask，原分辨率视觉门清除金属碎片、衣物、皮肤、邻指和装饰交叠，并保留9个逐甲放大通过的SAM polygon、重画6个问题polygon。该更新替代v1.1.171数量快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.173收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为289个标记/276个PASS、2/10门并按预期保持HOLD。审计中的`M2-T3-VISION-ANNOTATION`和`USER-ANNOTATION-01`证据已纠正为92张唯一图片/481 mask，避免沿用旧79张快照。正式409图/2142 mask数据集、生产manifest和运行时接口不变，训练禁用状态保持；v1.1.172仅为pnpm缓存诊断记录，不改变训练数量基线。

截至v1.1.174，训练真值数量以96个批准报告、95张唯一图片/496 mask为准；最低100张train正样本仍缺5张。批次065新增3张/15个终审mask，原分辨率视觉门拒绝两轮SAM仍合并手掌的`00915`并以`00292`替换，终版保留6个逐甲放大通过的SAM polygon、重画9个问题polygon；第二轮继续清除拇指皮肤/衣物边界并补齐银灰长甲完整甲尖。该更新替代v1.1.173数量快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.174收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为293个标记/280个PASS、2/10门并按预期保持HOLD。审计中的`M2-T3-VISION-ANNOTATION`和`USER-ANNOTATION-01`已同步为95张唯一图片/496 mask。正式409图/2142 mask数据集、生产manifest和运行时接口不变，训练禁用状态保持；素材不入Git，未执行Git提交或推送。

截至v1.1.175，训练真值数量以99个批准报告、98张唯一图片/511 mask为准；最低100张train正样本仍缺2张。批次066新增3张/15个终审mask，原分辨率视觉门否决SAM中几何疑点和语义错位候选并全部转为人工polygon，重点纠正横向遮挡边界、侧视附着装饰、误落弯曲指腹、链钻/雪花甲遮挡及灰银黑甲根锯齿。该更新替代v1.1.174数量快照，val 0/30、约100张hard negative、物化和来源隔离门均未改变。

v1.1.175未改变正式409图/2142 mask数据集、生产manifest或运行时接口；训练用途继续禁止，直至最低train正样本、val、hard negative、整批物化和来源隔离门全部通过。素材仍位于Git外部审核工作区，未执行Git提交或推送。

v1.1.175收口验证为联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为297个标记/284个PASS、2/10门并按预期保持HOLD。审计中的`M2-T3-VISION-ANNOTATION`和`USER-ANNOTATION-01`已同步为98张唯一图片/511 mask、最低train正样本仍缺2张。

v1.1.176补充核对`E:\.pnpm-store`的创建来源：2026-06-29 09:06:53，Codex项目检查调用其捆绑运行时中的`pnpm.cmd`执行lint/build；pnpm随后于09:07:01自动创建`E:\.pnpm-store`，时间与命令记录严格对应。因此该目录可归因为Codex任务触发、pnpm自动生成，并非用户手工创建，也不是项目源码。当前目录仍为pnpm v11内容寻址依赖缓存，共18743个文件、约471.88 MiB；本轮未删除、清理或写入缓存，运行时接口、训练真值98/100状态和发布HOLD均无变化。

截至v1.1.177，训练真值为101个批准报告、100张唯一图片/521 mask、1个冗余、0冲突，最低100张train正样本门已达到。批次067新增`00538/00301`两张/10个终审mask；`01113`因只有4枚人类甲面完整可见而排除，SAM2.1 large候选因整指、皮肤、衣物与背景污染全部拒绝直接晋级，终版10枚甲面以人工polygon重建并通过原分辨率整图、全部逐甲2×、合法性、零交叠和几何10/10审核。权威索引SHA-256为`13f606b5…f125`，根目录索引与`final`当前镜像一致。

达到train最低规模不等于允许开训：val仍为0/30，约100张来源隔离hard negative、整批物化及来源隔离审计尚未完成。正式409图/2142 mask数据集、生产manifest和运行时接口不变，训练用途和发布状态继续HOLD；素材不入Git，未执行Git提交或推送。

v1.1.177收口验证为唯一索引、SAM提示几何、人工多边形构建、返修终结和训练真值终结联合专项12/12通过，文本编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为300个标记/287个PASS、2/10门并按预期保持HOLD。审计中的`M2-T3-VISION-ANNOTATION`和`USER-ANNOTATION-01`已同步为100张唯一图片/521 mask、最低train正样本门达到。

v1.1.178已完成val专用工作区、自动候选生成和30张全量首轮原分辨率审核，但只有1张/2 mask直通、29张仍须返修，因此候选训练仍被正确阻断。正式409图/2142 mask数据集、生产manifest和运行时接口未改变；素材及审核产物继续位于Git外部，未执行Git提交或推送。

v1.1.178收口验证为val工作区、YOLO预标注审计、SAM提示构建、mask审核工作区与分片终结联合专项8/8通过，修改脚本Python编译、ESLint、文本编码407/407、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及`git diff --check`通过；完成度审计更新为302个标记/289个PASS、2/10门并按预期保持HOLD。

v1.1.179已将val角色误用风险前置到终审与唯一索引，当前可复现进度为6/30张、24个完整mask；剩余24张、约100张hard negative、整批物化和来源隔离仍阻塞候选训练。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.180再次只读复核`E:\.pnpm-store`：该目录由2026-06-29的Codex项目检查调用pnpm后触发，实际目录与内容由pnpm自动生成和维护，不是项目源码、训练素材或用户手工创建的业务目录。当前活动pnpm 11.9.0仍将store解析到`E:\.pnpm-store\v11`，共18743个文件、约471.88 MiB；本轮未写入、清理或删除缓存，模型接口、验证真值6/30和发布HOLD状态均无变化。

v1.1.181完成val返修批次005—006并把验证真值推进到8/30张、34个完整mask。`00946`与`00945`的首轮SAM均出现“几何通过但视觉不完整/污染”的情况：前者右侧拇指吸收面部且另一甲漏白色延长甲尖，后者横向甲吸收指腹；经人工polygon与逐甲2×复核后，两图10个polygon均合法、零交叠、几何10/10。剩余22张、约100张hard negative、整批物化和来源隔离仍阻塞候选训练；正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.182复核正式候选训练启动距离：最低train正样本门已完成100/100，val真值为8/30、仍缺22张，约100张来源隔离hard negative尚未建立；按三类最低样本数量合计为108/230，约47%，但该比例不包含逐甲原分辨率返修难度及后续整批物化、来源隔离、polygon合法性和同图零交叠审计，因此只能作为数量进度，不能作为正式模型或发布完成度。进度表`USER-ANNOTATION-01`已由旧的6/30、24 mask同步为8/30、34 mask；完成度审计为307个标记、294个PASS、2/10门并按预期保持HOLD。模型接口、正式数据集与生产状态均无变化，未执行Git提交或推送。

v1.1.183完成val返修批次007并把验证真值推进到10/30张、44个完整mask。`00944/00936`的SAM候选虽几何10/10，但横向甲仍吸收面部/眼镜，拇指仍带入头发/皮肤；首轮人工修复后，逐甲2×又拦截5枚甲根碎边或立体装饰边界不完整的候选。第二轮终版10个polygon均合法、零交叠、几何通过并完成整图与全部逐甲2×审核。剩余20张、约100张hard negative、整批物化和来源隔离仍阻塞候选训练；按最低三类样本数量现为110/230，约47.8%，只作数量进度。收口验证为终结链专项15/15、ESLint、编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为309个标记/296个PASS、2/10门并按预期保持HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.184完成val返修批次008并把验证真值推进到12/30张、54个完整mask。`00933/00942`的SAM候选虽几何10/10，但视觉门拦截`00942`横向透明甲吸收整段手指，以及多甲甲根皮肤、锯齿和附着装饰边界问题；终版保留5个已审polygon、人工重画5个问题polygon，逐甲2×进一步收紧第1甲侧边立体装饰。两图10个polygon均合法、零交叠、几何通过并完成整图与全部逐甲2×审核。剩余18张val、约100张hard negative、整批物化和来源隔离仍阻塞候选训练；按最低三类样本数量现为112/230，约48.7%，只作数量进度。收口验证为终结链专项15/15、ESLint、编码407/407、README严格结构和`git diff --check`通过；完成度审计更新为311个标记/298个PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.185复核正式候选训练启动距离：外部权威索引仍为train 100/100张、521个完整mask，以及val 12/30张、54个完整mask；约100张来源隔离hard negative仍未建立。按最低图片数量合计为112/230（48.7%），数量项仍差约118张，即18张val真值和约100张hard negative；这不是正式模型整体完成度。三类数量补齐后仍须整批物化，并通过来源隔离、polygon合法性和同图零交叠审计，之后才允许启动下一轮正式候选训练。本轮只同步状态复核，无接口、正式数据集、manifest或运行时状态变化，未执行Git提交或推送。

v1.1.186完成val返修批次009并把验证真值推进到14/30张、64个完整mask。源图放大门确认`00931…_0/_1`各只能确认4枚完整甲面，`00937`右侧拇指延长甲尖被图片边界裁断，均未虚构mask或晋级；改选`00934/00940`。SAM2.1 large完成2图/10提示、0 fallback，几何8 pass/2 suspect；视觉门拦截相邻甲真实交叠、整块拇指吸收及甲根锯齿，两轮人工后终版保留5个已审polygon、重画5个问题polygon。10/10 polygon合法、零交叠、几何通过并完成整图与全部逐甲2×审核。val剩余16张、约100张hard negative及整批物化/来源隔离仍阻塞候选训练；最低三类样本数量现为114/230，约49.6%，只作数量进度。专项19/19、ESLint和407/407文件编码审计通过，README严格结构与差异检查通过；完成度审计为313个标记、300个PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.187完成val返修批次010并把验证真值推进到16/30张、74个完整mask。源图门拒绝`00938/00941/00943`实际仅4枚完整甲面、`01184`拇指甲触边和`00455`一枚长甲被横向拇指遮挡，改选五甲完整的`00383/00351…_3`。SAM2.1 large完成2图/10提示、0 fallback、几何10/10；原分辨率视觉门保留8个干净polygon，点纹长甲和侧向拇指甲改为人工polygon，逐甲2×首轮又发现两枚轮廓偏窄并扩大重画。终版10/10 polygon合法、零交叠、几何通过并完成整图与全部逐甲2×审核。第15—16个validation报告SHA-256为`96023c50…e412`、`be9e8fc5…f872`，唯一索引SHA-256为`a583b884…ef8d`。val剩余14张、约100张hard negative及整批物化/来源隔离仍阻塞候选训练；最低三类样本数量现为116/230，约50.4%，只作数量进度。相关专项测试19/19、ESLint、407文件编码审计、README严格格式和`git diff --check`通过；完成度审计315标记/302 PASS、2/10门，按预期保持HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送。

v1.1.188完成val返修批次011—013、替补角色扩展和候选物化。`00351…_4/00826/00828`共15枚甲面经人工或混合polygon重建后通过整图、全部逐甲2×、合法性、零交叠和几何15/15；`00935`因右侧拇指甲根触边、实际仅4枚完整甲面而排除。第17—19个validation报告SHA-256为`0619a628…bfd`、`2432fab0…9fc`、`5908fbfc…c2d`，唯一索引更新为19张/89 mask、0冗余、0冲突，SHA-256为`924d04f0…faf4`。原30张源图复核后确认11张不可用；新角色扩展器以授权、计划、train真值和原图SHA为输入，整组拒绝独立test、已有train真值、首批train工作区和部分来源组，11张/7组替补角色清单SHA-256为`1daddbe5…2495`。扩展专用工作区11/11硬链接、3分片/55枚预期甲面，manifest SHA-256为`28a2dbfa…614c`；v6生成73个紧框候选，整图筛选为55个逐甲提示，SAM2.1 large完成55/55、0 fallback/0错误，几何46 pass/9 suspect。候选生成不等于真值通过，批次014—016仍须清除整指、皮肤、衣物、背景和重复污染。最低train/val/hard-negative数量为119/230（51.7%），仍差11张val和约100张hard negative；整批物化/来源隔离完成前禁止候选训练。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材与候选不入Git，未执行Git提交或推送。

2. AI 生图依赖外部模型与密钥，尚未完成生产环境可用性、成本和内容安全验证；
3. AR 摄像头和朝向识别仍需要更多手机、浏览器、光线和肤色组合的真机验收；纹理识别桌面内存基线已建立，但 Android手机、Android平板、iPhone和iPad峰值内存仍未测量。

下一轮有效候选训练不需要等待565张待标注候选全部完成标注，也不受移动真机或Beta发布证据阻止。train最低正样本门100/100张、val门30/30张和独立发布test代表性规模100/100张均已完成；规范候选数据集物化器、完整训练输入审计、训练/发布入口预检及新val终审到正式校准器的桥接均已完成。当前素材侧唯一训练启动缺口是补齐、授权并原分辨率审核99张合格hard negative，形成不少于100张的`approved_hard_negative_manifest`；随后使用既有工程门重跑100/100/30物化和输入深审取得真实PASS，才允许启动下一轮候选训练。正式发布仍需使用新冻结100张评估新候选模型，并继续满足300—500张Beta真实正样本、至少200张负样本、移动真机、用户失败案例和100张Beta人工质量门。候选训练启动不得被表述为发布通过，完整发布审计通过率也不得反向解释为训练准备度。

截至v1.1.210已完成连续第三轮正式阻断复核：`hard-negative-formalization-hold-v2.json`仍为`HOLD`，其SHA-256为`c35214e92abdfcb57b6e3005afa67230b1aab2aaea21107c71e1afd8c1f365a4`；现有37张域外排除项已逐图穷尽复筛，只有1张满足清晰、无有效真人甲面、授权A和来源隔离要求，剩余36张均因模板、独立甲片、拼图、含有效真人甲面或不适配部署场景被排除，缺口仍为99张。当前不存在可安全继续的本地工程项：候选质量、生产ONNX、Beta、移动真机和回滚均依赖新候选训练或用户/设备证据，不能通过伪造报告、降低100张门槛或回收不合格素材推进。持续目标因此正式进入`blocked_waiting_for_user_input`，不改变产品`HOLD`、`trainingUse=prohibited`、生产manifest或运行时接口；收到新的合格困难负样本候选及商业训练/长期回归授权后，从原分辨率审核、来源隔离汇总和候选数据物化门继续。

### 11.2 未完成或占位能力

1. 真实灵感图库与内容后台；
2. 用户账户、云端项目保存、跨设备同步；
3. 订单、门店、商品、预约、支付等业务后端；
4. 正式 3D 指甲网格、遮挡、光照和物理材质试戴；
5. AI 生图的供应商抽象、任务队列、结果持久化和配额系统；
6. 正式模型监控、线上质量回流和自动回滚闭环。
7. 图库款式到编辑器/AR 的参数消费和纹理传递；
8. AI 生成结果一键进入图库、编辑器或 AR 的集成链路；

## 12. 新模块对接登记模板

后续新增模块时，在对应章节至少记录以下内容：

```md
### 模块名称

- 状态：已完成 / 待验证 / 进行中 / 占位 / 未完成 / 阻塞
- 负责人或来源：
- 用户入口：
- 代码入口：
- 输入：
- 输出：
- 错误与降级：
- 环境变量/配置：
- 隐私与资源释放：
- 使用步骤：
- 验证命令与结果：
- 已知限制：
- 关联文档：
```

## 13. 版本与变更记录

| 日期 | 版本 | 变更摘要 | 影响范围 |
| --- | --- | --- | --- |
| 2026-07-23 | v1.1.210 | 完成连续第三轮正式训练与发布依赖链阻断复核：外部困难负样本正式化报告SHA-256为`c35214e9…65a4`，现有37张域外项已穷尽复筛，仅1张合格、36张按质量/用途规则排除，仍缺99张；train100/100、val30/30和冻结test100/100保持就绪。确认剩余模型质量、生产ONNX、移动真机、Beta和回滚项均依赖新训练或用户/设备证据，当前没有可安全独立推进的工程项，持续目标标记为`blocked_waiting_for_user_input`，产品继续HOLD且训练禁用。新增规范勾选和`REL-T1-FINAL-BLOCKER-AUDIT-004` PASS审计标记；完成度审计342标记/332 PASS、13门中3门通过并保持HOLD。未启动训练、未修改生产manifest、未提交或推送Git | 最终阻断审计、训练输入、困难负样本、目标暂停、发布治理 |
| 2026-07-23 | v1.1.209 | 收紧最终完成度审计的文档结构门：规范用户/工程清单必须存在且非空，候选清单行须采用合法checkbox格式且同章节文本唯一；进度表必须包含可解析标记，所有反引号开头的候选标记行都要满足四列格式，标记ID必须唯一。新增空进度、缺失清单章节、畸形/重复清单、畸形静默漏行和重复PASS ID拒绝回归；专项36/36、全量串行639/639、ESLint、443文件编码审计、生产构建和差异检查通过。真实规范复验为用户6项、工程169项且0畸形/重复，进度表341标记/341唯一ID、0畸形行，331个PASS、10个非PASS，13个正式门中3个通过并继续HOLD。正式训练输入与接口不变，仍为train100/100、val30/30、hard negative1/100，缺99张；未启动训练、未修改生产manifest、未提交或推送Git | 完成度审计、规范结构完整性、唯一清单与PASS标记、完整回归、训练HOLD |
| 2026-07-22 | v1.1.208 | 为冻结质量报告加入`--verify-report`独立只读重放：验证器从报告读取全部输入，在临时目录重建schema v2报告并逐字段比较，拒绝手写外层决定、源指标漂移和输入/硬链接覆盖。最终完成度审计已接入该重放器、保护传递证据，并在代表性100图快照存在时禁止退回历史13图或旧67图指标；现场审计因此从先前错误偏松的4/13纠正为340标记/330 PASS、3/13正式门并继续HOLD。联合专项41/41、全量串行634/634、ESLint、443文件编码审计、Python编译、生产构建和差异检查通过；正式训练输入仍为train100/100、val30/30、hard negative1/100，缺99张。同步澄清旧2026_7_13批次28张返修是可选扩充项，不是当前规范train100的开训阻断。未启动训练、未修改生产manifest、未提交或推送Git | 冻结质量报告深重放、完成度审计收紧、完整回归、训练距离口径 |
| 2026-07-22 | v1.1.207 | 将冻结发布测试质量报告升级为通用schema v2：动态复算旧67/384与新100/554快照的lane及父来源组，深验评估物化、assessment、预测覆盖、baseline与四次评估的同一权重及SHA-256，固定部署512全量/core/stress三组必须同时通过，640仅诊断，并阻止output直接或硬链接覆盖输入。旧67真实证据重放仍正确拒绝；新100快照和物化证据契约通过，但尚无新候选指标，未误报质量PASS。同步修复发布治理测试fixture，为候选模型manifest写入真实`modelSizeBytes`与SHA-256，未降低生产回滚逻辑；专项质量报告8/8、治理与训练发布27/27、全量串行630/630、ESLint、443文件编码审计、Python编译、生产构建和差异检查通过。完成度审计为339标记/329 PASS、4/13正式门并按预期HOLD。新增PowerShell 7显式执行规则及素材忽略复核；正式训练仍因hard negative 1/100、缺99张HOLD，未启动训练、未修改生产manifest、未提交或推送Git | 冻结质量报告schema v2、发布治理回归、PowerShell 7、完整回归、训练HOLD |
| 2026-07-22 | v1.1.206 | 完成补充发布测试真值与100张冻结快照闭环。13张第二轮SAM返修经逐甲视觉审核后8张直接通过、5张转人工polygon；人工轮廓在独立复核中拦截3处延长甲尖/附饰遗漏并迭代至29/29几何、0交叠及整图视觉通过。补充唯一索引终结为33张/170 mask、0拒绝/冗余/冲突，SHA-256为`93588fb6…e04c`。新增专用冻结合并器，深验旧67与新33、train100、val30的文件名/图片哈希/来源组和父来源组隔离，输出100张/554 mask、core78/stress22、29父来源组冻结快照，manifest SHA-256为`b3baa41c…23c6`；评估专用物化与只读重放均PASS。完成度审计绑定新快照复跑为337标记/327 PASS、4/13正式发布门并按预期HOLD。代表性test规模门解除，但正式训练仍因hard negative 1/100、缺99张保持HOLD；README同步当前100张状态且严格结构复核通过。全量串行测试613/623，10个既有发布治理回滚完整性用例失败且单文件复验仍为3/9失败，未将其误报为本轮通过；ESLint、443文件编码审计、生产构建、Python编译及差异检查通过。未启动训练、未修改生产manifest、未提交或推送Git | 发布测试人工返修、100张冻结快照、来源隔离、评估物化、README、正式训练距离 |
| 2026-07-22 | v1.1.205 | 复核正式训练启动距离并推进发布测试返修。训练输入仍为train正样本100/100、val 30/30、hard negative 1/100；数量口径131/230（约57%），但开训门为硬门，唯一直接素材缺口仍是99张合格hard negative，随后还需正式manifest终结、规范候选数据集物化和GPU前输入深审。发布测试首轮17张逐甲严审仅4张直接通过，已使用schema v2哈希绑定原图、annotation、overlay及逐甲裁剪证据完成终结；候选真值索引由16张/81 mask推进至20张/101 mask、0拒绝、0冲突，SHA-256为`a1915455…a91`。其余13张第二轮SAM完成69/69 mask、0 fallback、0错误，几何59 pass/10 suspect，等待逐甲视觉审核并按需转人工polygon。对既有排除池和派生区域的并行复筛新增hard negative为0，缺口仍为99。正式冻结test仍为67/100，未启动训练、未修改生产manifest、未提交或推送Git | 正式训练距离、困难负样本、发布测试真值、视觉证据终结、SAM返修、发布HOLD |
| 2026-07-22 | v1.1.204 | 现场刷新正式训练与发布测试进度。训练启动三类权威输入仍为train正样本100/100、val 30/30、hard negative 1/100，即131/230（约57%）；唯一直接素材缺口仍是99张合格hard negative，补齐后还需执行正式manifest终结、规范候选数据集物化和GPU前输入深审。发布测试侧完成终结器/唯一索引加固并由独立安全复核通过：原15张候选全部重放，拓扑项只修复1个自交polygon，当前索引为16张/81 mask、0冲突，SHA-256为`2c40aa2f…711b`。剩余17张已用SAM2.1 Large完成89/89 mask、0 fallback、0错误，几何审计86 pass/3 suspect，17张整图与89组2×逐甲证据已生成并进入原分辨率终审；未终结前冻结test仍为67/100。本轮未启动训练、未修改生产manifest、未执行Git提交或推送 | 正式训练距离、困难负样本、发布测试真值、SAM返修、原分辨率审核、发布HOLD |
| 2026-07-22 | v1.1.203 | 复核正式训练启动距离并登记发布测试标注增量：训练输入仍为train 100/100、val 30/30、hard negative 1/100，数量口径131/230（约57%），唯一开训素材缺口仍是99张合格hard negative及其正式终结、规范物化和输入深审。33张发布测试补充候选中，7张直通与8张仅删除误检项已形成15张/76 mask候选真值索引；另1张拓扑修复候选完成，剩余17张的89个SAM返修提示已准备但未运行GPU。因真值终结器正在补充发布角色/视觉证据深度重放和输出覆盖防护，15张既有报告仍需加固后复验，冻结test继续按67/100计数。相关安全专项8/8与Python编译通过；未启动训练、未修改生产manifest、未执行Git提交或推送 | 训练启动距离、发布测试返修、证据深度重放、发布HOLD |
| 2026-07-22 | v1.1.202 | 刷新正式训练与发布测试进度：训练正样本100/100、val30/30已满足，hard negative仍为1/100、缺99，规范训练输入继续HOLD；按三类最低图片数为131/230（约57%）。补足代表性发布测试规模所需的33张候选已按4个完整来源组完成角色替换，形成33张/170个预期甲面/11组且与train100、val30、冻结test67三层隔离；标注工作区4个来源组原子分片及33个硬链接深验通过。v6以YOLO生成204候选、SAM2完成204/204 mask，33/33原分辨率首审结论为7张通过、26张返修、0张排除；正式冻结规模仍为67/100。完成度审计v2现场复跑为333标记/321 PASS、2/13发布门通过并保持HOLD；本轮为进度核验，无运行时接口或生产manifest变化，未执行Git提交或推送 | 训练启动门、发布测试标注、完成度审计、发布HOLD |
| 2026-07-22 | v1.1.201 | 复核当前训练启动与训练后发布门口径：规范训练输入为train 100张、val 30张、hard negative 1张，仍缺99张合格hard negative，按三类角色最低图片数量为131/230（约57%）；另缺的33张代表性发布测试属于训练后的模型质量评估与正式发布门，不阻止候选训练输入门满足后启动训练。原规划33张独立发布测试候选已完成原分辨率审核，结论为25张保留、8张排除；已找到4个完整train来源组共8张替补，并新增按完整来源组迁出、身份隔离和哈希重放的角色替换工具，专项8/8通过。产品质量原始证据链专项16/16、回滚深验专项26/26通过；真实冻结67图质量结论仍为HOLD，主completion集成与全量回归尚未完成，因此不改变生产发布状态。未执行Git提交或推送 | 训练启动口径、发布测试角色替换、产品质量证据、回滚深验、发布HOLD |
| 2026-07-22 | v1.1.200 | 再次只读复核用户遇到的GitHub 443连接超时：远端地址仍为`https://github.com/yaoyinyu/JiaRu.git`，当前分支为`master`，未发现Git或环境代理；DNS解析正常、GitHub首页HTTPS返回200，Git自身的`ls-remote --heads origin master`成功返回。当前本地`HEAD`、缓存的`origin/master`与GitHub远端`master`三者均为`2be103b19e258a20f0e93986012b5df9d46376f8`，对应提交`Validate hard-negative image integrity and approval evidence`，说明远端已包含该提交且当前没有待推送提交。结论为执行push时的瞬时网络连接失败，或连接恢复后已由用户重试成功；不是分支名称、提交信息或仓库内容问题。未执行提交、推送、fetch或Git配置修改；模型接口、数据集、训练HOLD与生产manifest均无变化。hard negative schema v2阶段最终验收同时完成：`npm.cmd test`全量550/550、Next.js生产构建、ESLint、Python编译、431个文件编码审计及`git diff --check`均通过；完成度审计为330个标记/318个PASS、2/10发布门通过并按预期HOLD | Git网络诊断、远端提交核验、hard negative最终验收、无模型状态变更 |
| 2026-07-22 | v1.1.199 | 建立hard negative schema v2正式终结与消费端深度重放：新增`finalize-reviewed-hard-negative-manifest.py`，固定100张正式下限并绑定候选清单、原分辨率视觉审核、A授权、当前图片哈希、尺寸及来源隔离证据；不足100张只输出不可训练HOLD，达到门槛后`approved_hard_negative_manifest`仍由角色隔离、候选物化和GPU前输入审计从当前证据重放。Pillow执行结构验证与完整像素解码，最短边320像素，损坏/文本伪装/尺寸漂移拒绝；可解码格式与扩展名不一致时只规范物化文件名，不修改源文件。真实1张候选复跑发现源`.jpg`实际为WEBP，输出schema v2 HOLD及`.webp`物化名，报告SHA-256为`c35214e9…65a4`，仍缺99张且未创建候选训练数据集。已审计300张既有授权AI美甲图的现有候选证据，无一可安全直接作为无甲负样本。联合专项63/63、Python编译和ESLint通过；新增`M2-T3-HARD-NEGATIVE-FINALIZER-002` PASS工程标记，训练与生产HOLD不变；本阶段最终全量验收数字见v1.1.200 | hard negative终结、视觉/授权证据链、图片解码、格式规范化、GPU前深验、训练HOLD |
| 2026-07-22 | v1.1.198 | 只读复核用户再次遇到的GitHub 443连接超时：远端地址仍为`https://github.com/yaoyinyu/JiaRu.git`，当前分支为`master`；DNS解析正常、GitHub首页HTTPS返回200，且`git ls-remote --exit-code origin HEAD refs/heads/master`成功返回。当前本地`HEAD`、`origin/master`与远端`master`均为`2a22715b143b3272168cf225c75ed6114ea1fe83`，仓库无待推送提交；Git和环境变量均未配置代理。结论为命令执行当时的瞬时网络超时，不是分支名、提交信息或仓库内容问题。未执行提交、推送、fetch或Git配置修改；模型接口、数据集、训练HOLD及生产manifest均无变化 | Git网络诊断、远端同步核验、无模型状态变更 |
| 2026-07-21 | v1.1.197 | 完成候选训练、规范val校准和冻结release-test三路强隔离编排。候选模式固定三套不同dataset和六份证据，顺序为训练→val评估/阈值校准→冻结test评估→候选导出；冻结test物化报告升级schema v2并新增只读深验，校准报告新增`--verify-report --expected-weights`，候选导出只能从合格报告派生阈值并写`scoreThresholdEvidence`。最终发布校验重算test全树、预测制品、权重及manifest证据，拒绝val/test互换、伪造PASS、写后漂移和手工阈值。联合专项63/63与Python编译通过；首次全量并发运行的旧测试因历史skip契约和子进程竞争暴露1项失败，删除已被三路专项替代的重复断言，并将`npm.cmd test`固定`--test-concurrency=1`后全量541/541、ESLint、生产构建和428文件编码审计通过。完成度审计329标记/317 PASS、2/10门并按预期HOLD。v6真实校准仍为无合格阈值，hard negative仅1/100，未训练、未导出或修改生产manifest | 候选训练编排、角色隔离、冻结test深验、阈值证据、稳定串行测试、发布HOLD |
| 2026-07-21 | v1.1.196 | 只读诊断用户本次GitHub推送的443连接超时：远端地址为`https://github.com/yaoyinyu/JiaRu.git`且分支为`master`；DNS解析成功、GitHub首页HTTPS返回200、`git ls-remote origin HEAD`约1秒返回`fae266b…7262`，环境变量与WinHTTP均无代理，GitHub状态页显示Git Operations正常。结论为推送当时的瞬时网络超时，和分支名、提交信息、仓库内容及贡献图无关；未执行提交、推送、fetch或Git配置修改，模型接口、训练HOLD和生产manifest均无变化 | Git网络诊断、只读远端握手、无模型状态变更 |
| 2026-07-21 | v1.1.195 | 完成规范val30到部署512评估与正式阈值校准的真实桥接。校准器只允许规范物化报告与`approved_as_calibration_truth`，独立重放truth index、角色隔离、当前图片/annotation/label、polygon合法性与零交叠；旧实验报告固定为diagnostic-only。评估器绑定dataset/weights/制品逐文件SHA和每图显式预测记录，并在真实运行中发现Ultralytics会向规范标签目录写`val.cache`，因此改为复制所选split到独立runtime dataset并复验源树前后inventory；首次污染cache已隔离保存，源数据重新终审30图/144 mask、0孤儿。第二次真实运行又暴露Windows Path排序与POSIX规范顺序不一致，修复为相对POSIX路径稳定排序后从全新目录重跑。v6最终部署512 box/mask mAP50=0.6241/0.5630；0.05召回0.7569但每图误检9.8333且单图最多28候选，其余阈值召回不足0.75，正式决定`no_threshold_meets_validation_constraints`、`manifestScoreThreshold=null`。工程门PASS但v6继续拒绝，生产manifest未修改；候选训练仍因hard negative 1/100、缺99张而HOLD。全量串行523/523、ESLint、Next.js 16.2.9生产构建、428文件编码和README结构复核通过；完成度审计328标记/316 PASS、2/10门并按预期HOLD | 规范val、只读源数据、评估制品哈希、阈值校准、Windows稳定排序、v6质量拒绝、训练HOLD |
| 2026-07-20 | v1.1.194 | 对用户再次遇到的GitHub 443连接超时进行只读复核：DNS解析与HTTPS访问已恢复，Git智能HTTPS端点`git ls-remote`约1.18秒成功返回；本地`master`、`origin/master`和远端`master`均为`cc1f263`，ahead/behind为0/0，说明当前没有待推送提交且此前提交已在远端。GitHub状态页显示Git Operations正常，结论为瞬时网络超时；未重推、未改Git配置，模型接口、训练HOLD与生产manifest均无变化 | Git网络诊断、远端同步核验、无模型状态变更 |
| 2026-07-20 | v1.1.193 | 建立移动真机基准采集与不可伪造设备证据链：新增`/device-benchmark`，固定3次预热+20次正式推理，导出session/device/model/backend/input与逐次时间；fallback、混合身份、无效时间或少样本保持HOLD。新增Profiler/Instruments内存CSV转换器、模板和操作手册，把系统级内存与同一会话及源SHA-256绑定。设备验收升级为v2，独立重算性能P95、内存增长/峰值/连续增长、样本数、路径和三层哈希；最终完成度审计再次深度重放，拒绝伪造外层PASS、跨session、输出覆盖与写后漂移。专项21/21、ESLint和Next.js 16.2.9生产构建通过；完成度审计更新为327个进度标记/315个PASS、2/10发布门并按预期HOLD。本项仅证明工具链，Android手机/平板、iPhone、iPad实际报告继续等待真机，训练数据仍为100/1/30 HOLD，生产manifest未修改 | 移动真机、批量基准、系统内存、证据哈希、完成度深审、物理设备HOLD |
| 2026-07-20 | v1.1.192 | 建立规范候选训练数据物化、独立输入深审和训练/发布入口前置门：固定train正样本100、正式hard negative 100、val 30且CLI不可下调；逐文件重算annotation→YOLO标签、空负标签、polygon合法性/零交叠、孤儿、四角色身份和聚合哈希。`train-yolo-seg.py --candidate-mode`改为只接受`--candidate-input-report`并在训练前后深度重放；发布编排即使`--skip-train`也先预检，恢复运行须绑定同一dataset、输入报告和权重哈希。真实100/1/30运行正确HOLD，外部报告SHA-256 `a0cec8aa…51493`，候选数据集目录零写入；仍缺99张合格hard negative，未启动训练、未改生产manifest。另对用户push的GitHub 443超时做只读复核：DNS/TCP/HTTP/`git ls-remote`均正常且提交实际已到远端，判定为瞬时连接故障，未再次推送或修改Git配置。专项物化12/12、输入/联调10/10、全量506/506、ESLint、421文件编码审计和生产构建通过；完成度审计326标记/314 PASS、2/10发布门并按预期HOLD | 候选训练数据物化、hard negative、输入深审、GPU前置门、发布编排、训练HOLD、Git网络诊断 |
| 2026-07-20 | v1.1.191 | 按用户明确要求将本地与GitHub远端分支名称恢复为`master`：本地当前分支已重命名并跟踪`origin/master`，GitHub仓库默认分支经API更新为`master`，远端旧分支`JiaRu_让每一次抬手都遇见未来`已删除，`origin/HEAD`复核指向`master`且本地/远端提交均为`41d5074`。本次仅执行完成分支重命名所必需的远端操作，没有创建新提交；模型接口、训练数据、训练HOLD和生产manifest均无变化。GitHub贡献图仍按提交作者邮箱关联、默认分支可达性和GitHub统计延迟计算，分支改回`master`不单独保证已有提交立即显示贡献 | Git分支治理、GitHub默认分支、远端HEAD、贡献统计说明 |
| 2026-07-20 | v1.1.190 | 刷新实施完成度审计为323个进度标记/311个PASS、2/10发布门并按预期HOLD；明确2/10是完整发布闭环而非训练准备度。复核候选训练输入为train 100/100张、val 30/30张、hard negative 1/100张，最低数量131/230（约57%），当前仍缺99张合格hard negative、训练包正式物化/来源隔离终审及新val证据桥接报告。纠正§11.1中train 53、val 0的过时快照；记录候选训练代码尚未强制train/hard-negative数量的治理缺口，禁止利用该缺口绕过文档门。代表性test缺33张、四类移动真机、用户失败案例和Beta审核继续阻塞发布而非单独阻塞下一轮训练。未运行训练，未提交或推送Git | 训练启动距离、完成度口径、hard negative、候选训练输入门、文档一致性 |
| 2026-07-19 | v1.1.189 | 完成val替补返修批次014—018并关闭30图验证门：最终30张/144个完整mask、0冗余、0冲突，索引SHA-256 `2ccde942…b92d`；01295/01300/01060在主线程复核中继续补齐丝带尾、立体花瓣、圆珠、完整甲根和透明甲尖，未以几何通过代替视觉审核。新增规范val-only物化、角色隔离和最终晋升三段工具；独立审查发现并修复伪造隔离报告、输出覆盖/写后孤儿、hard-negative弱契约、冻结test路径逃逸和微小非零交叠容差。真实物化30图/144 mask、train/test为0、孤儿0；与train 100张及冻结test 67张按文件名/图片SHA-256/sourceGroup零重叠，最终`approved_as_calibration_truth`。37张潜在hard negative只保留1张candidate-only，仍缺99张，候选训练继续HOLD。专项60/60、全量484/484、ESLint和417文件编码审计通过；未提交或推送Git | val 30/30、完整附着装饰、规范物化、来源隔离、校准真值、hard negative缺口、门禁加固 |
| 2026-07-19 | v1.1.188 | 完成val返修批次011—013并把真值推进到19张/89 mask；`00351…_4/00826/00828`共15甲通过整图、全部逐甲2×、合法性、零交叠和几何审核，`00935`因拇指甲根触边、实际仅4甲而排除。原30张源图共确认11张不可用；新增替补角色扩展器，整组拒绝独立test、已有train真值、首批train工作区、部分来源组和哈希漂移，迁移11张/7组val候选。扩展专用工作区11/11硬链接、3分片/55枚预期甲面；v6生成73候选并筛为55个逐甲提示，SAM2.1 large完成55/55、0 fallback/0错误，几何46 pass/9 suspect，仍由批次014—016做视觉返修。角色扩展与物化专项9/9通过；正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val真值、源图排除、整组角色迁移、工作区物化、SAM候选、训练禁用 |
| 2026-07-19 | v1.1.187 | 完成来源隔离val返修批次010。源图门拦截三张实际仅4枚完整甲面、`01184`拇指甲触边和`00455`一枚长甲被拇指遮挡，改用五甲完整的`00383/00351…_3`；SAM2.1 large完成2图/10提示、0 fallback、几何10/10。视觉门保留8个干净polygon，人工重画点纹长甲与侧向拇指甲，逐甲2×首轮发现两枚轮廓偏窄后再次扩大；终版10/10通过整图、全部逐甲2×、合法性、零交叠和几何审核。validation唯一索引更新为16张/74 mask、0冗余、0冲突，SHA-256 `a583b884…ef8d`；剩余14张、约100张hard negative及物化/来源隔离前继续禁止训练。专项19/19、ESLint、407文件编码、README严格格式及diff检查通过；完成度审计315标记/302 PASS、2/10门并按预期HOLD。正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val返修、源图完整露出、人工多边形、逐甲2×、训练禁用 |
| 2026-07-18 | v1.1.186 | 完成来源隔离val返修批次009。源图门拦截`00931…_0/_1`各仅4枚完整甲面及`00937`右侧拇指甲被边界裁断，改选五甲完整的`00934/00940`；SAM2.1 large完成2图/10提示、0 fallback、几何8 pass/2 suspect。视觉门修复相邻甲真实交叠、整块拇指吸收和第1/2甲甲根锯齿，终版保留5个已审polygon、人工重画5个，10/10通过整图、全部逐甲2×、合法性、零交叠和几何审核。validation唯一索引更新为14张/64 mask、0冗余、0冲突，SHA-256 `8e0a536d…c08cfb`；剩余16张、约100张hard negative及物化/来源隔离前继续禁止训练。专项19/19、ESLint、编码407/407、README严格结构及差异检查通过；完成度审计313标记/300 PASS、2/10门并按预期HOLD。正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val返修、源图裁断、相邻透明甲、人工多边形、训练禁用 |
| 2026-07-18 | v1.1.185 | 复核正式候选训练启动距离：train正样本100/100已满足，val为12/30张、54 mask，仍缺18张；约100张来源隔离hard negative未建立。最低三类图片数量为112/230（48.7%），仍差约118张，但数量补齐后还须完成整批物化、来源隔离、polygon合法性和同图零交叠审计。无接口、正式数据集、manifest或运行时状态变化，未提交或推送 | 训练启动门、验证真值、困难负样本、数据物化、状态复核 |
| 2026-07-18 | v1.1.184 | 完成来源隔离val返修批次008。`00933/00942`均确认5枚完整长甲；SAM2.1 large完成2图/10提示、0 fallback、几何10/10，但视觉门仍拒绝`00942`横向透明甲吸收整段手指及多甲甲根皮肤、锯齿或装饰边界风险。终版保留5个已审polygon、人工重画5个问题polygon，并以逐甲2×收紧第1甲侧边立体装饰；10/10通过整图、全部逐甲2×、合法性、零交叠和几何审核。validation唯一索引更新为12张/54 mask、0冗余、0冲突，SHA-256 `28e609c7…9b0f`；剩余18张、约100张hard negative及物化/来源隔离前继续禁止训练。专项15/15、ESLint、编码407/407、README结构与差异检查通过；完成度审计311标记/298 PASS、2/10门并按预期HOLD。正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val返修、透明长甲、立体装饰、人工多边形、训练禁用 |
| 2026-07-18 | v1.1.183 | 完成来源隔离val返修批次007。`00944/00936`均确认5枚完整长甲，删除全部漏甲及眼睛、眼镜、头发、衣物或皮肤旧候选；SAM2.1 large完成2图/10提示、0 fallback、几何10/10，但视觉门仍拒绝横向甲吸收面部/眼镜和拇指带入头发/皮肤。首轮人工后逐甲2×再发现5枚甲根碎边或装饰边界问题，第二轮终版保留5个已审polygon、重画5个，10/10通过整图、全部逐甲2×、合法性、零交叠和几何审核。validation唯一索引更新为10张/44 mask、0冗余、0冲突，SHA-256 `f7f3c9f3…379c`；剩余20张、约100张hard negative及物化/来源隔离前继续禁止训练。专项15/15、ESLint、编码407/407、README结构与差异检查通过；完成度审计309标记/296 PASS、2/10门并按预期HOLD。正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val返修、透明长甲、横向甲、立体装饰、人工多边形、训练禁用 |
| 2026-07-18 | v1.1.182 | 复核正式候选训练启动距离：train最低正样本100/100已完成；val为8/30、仍缺22张；约100张来源隔离hard negative尚未建立。三类最低数量合计108/230（约47%），但还必须完成整批物化、来源隔离、polygon合法性和同图零交叠审计，不能把数量比例当作正式模型完成度。纠正进度表`USER-ANNOTATION-01`旧的6/30、24 mask证据为8/30、34 mask；重跑完成度审计为307标记/294 PASS、2/10门并按预期HOLD。无接口、正式数据集或生产状态变化，未提交或推送 | 训练启动门、验证真值、hard negative、进度一致性、完成度审计 |
| 2026-07-18 | v1.1.181 | 完成来源隔离val返修批次005—006。`00946`删除眼睛、镜片、衣物与重复候选，紧框SAM重建左上长甲后，右侧拇指仍吸收面部而改人工polygon；逐甲2×又发现第2甲漏白色延长甲尖并重画。`00945`五甲全部紧框SAM，横向甲吸收整个指腹后人工重画，2×复核发现甲根起点仍过早并再次收紧至真实甲沟。终版2张/10 polygon合法、零交叠、几何10/10，整图及全部逐甲2×视觉通过；第7—8个validation报告SHA-256为`a31c372c…9ef7`、`867782a0…843c`。唯一索引更新为8张/34 mask、0冗余、0冲突，SHA-256 `b080d9d1…fa69`；剩余22张、约100张hard negative及物化/来源隔离前继续禁止训练。正式数据集、manifest与运行时接口不变，素材不入Git，未提交或推送 | val返修、透明延长甲、立体装饰、人工多边形、原分辨率审核、训练禁用 |
| 2026-07-18 | v1.1.180 | 再次只读复核`E:\.pnpm-store`来源和用途：2026-06-29的Codex项目检查触发pnpm运行，目录及内容由pnpm自动创建和维护；当前pnpm 11.9.0的活动store为`E:\.pnpm-store\v11`，18743个文件、约471.88 MiB。该目录是可复用的依赖内容缓存，不是项目源码或训练素材；本轮未写入、清理或删除，无接口、训练/验证真值或发布状态变化，未执行Git提交或推送 | 本地开发环境、pnpm依赖缓存、只读复核、无接口变更 |
| 2026-07-18 | v1.1.179 | 将最终真值终结器与唯一索引扩展为角色感知模式：val必须绑定角色manifest并核对`assignedRole=val`、图片哈希、来源组、预期甲数和训练禁用，输出独立validation状态；唯一索引支持validation前缀并拒绝同图冲突，默认train兼容，专项5/5通过。完成返修批次001—004：`00454/00457/00384`以误检删除或紧框SAM形成15 mask；`00829`两甲全人工重画，`00672`保留3甲并重画2甲；`00455`SAM仍吸收皮肤而未晋级。6个批准报告归并为6张唯一图片/24 mask、0冗余、0冲突，索引SHA-256 `adac6dc3…33c7`；全部绑定val角色且trainingUse=prohibited，剩余24张清零及物化前禁止校准和训练。正式数据集、manifest与运行时接口不变，素材不入Git，未执行Git提交或推送 | val角色门、验证真值终审、唯一索引、人工多边形、训练禁用 |
| 2026-07-18 | v1.1.178 | 扩展首批标注工作区构建器，新增显式`--selection-mode val`并保持默认first-train兼容；专项测试证明仅物化完整val角色且来源组不拆分。按计划在Git外部建立30张/7来源组/3分片/159枚预期甲面的val工作区，30/30硬链接，manifest SHA-256 `59c5f421…1d47`。YOLO v6部署512生成155候选，SAM2.1 large完成30图/155提示、0 fallback/0错误，几何112 pass/43 suspect。16页逐图原分辨率审核为1 pass/29 rework/0 exclude，仅`nail_00456…_2`的2枚甲面直通；四个哈希绑定分片终结报告SHA-256为`65e8cdd9…261d`、`b831bb9e…c4d`、`696d0d3a…498b`、`09876d17…ace9`。正式val真值仍0/30，返修清零及最终拓扑/角色审计前禁止校准与训练。联合专项8/8、Python编译、ESLint、编码407/407、README严格结构与差异检查通过；完成度审计302标记/289 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | val工作区、来源隔离、YOLO/SAM候选、原分辨率审核、训练禁用 |
| 2026-07-18 | v1.1.177 | 完成`00538/00301`批次067与第100至101个批准真值报告；`01113`因仅4枚人类甲面完整可见而排除。SAM2.1 large完成2图/10提示、1 fallback，但几何仅3 pass/7 suspect且原分辨率视觉门发现整指、皮肤、衣物和背景污染，终版10枚甲面全部以人工polygon重建。逐甲2×复核补齐透明甲尖、立体花饰和水钻边缘；一次38.5285像素真实交叠被构建器拦截并纠正，10/10 polygon合法、零交叠、几何10/10。返修SHA-256为`31b20b81…b414`、`d585525d…61f2`，真值SHA-256为`4016ecb6…58b7`、`ae846132…2006`。唯一索引更新为101个批准报告、100张唯一图片/521 mask、1冗余、0冲突，SHA-256为`13f606b5…f125`，根目录权威索引与`final`当前镜像一致；最低100张train正样本门达到，但val 0/30、约100张hard negative、整批物化和来源隔离仍阻塞训练。联合专项12/12、编码407/407、README结构与差异检查通过；完成度审计300标记/287 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变；素材不入Git，未执行Git提交或推送 | 白色珍珠花饰甲、低对比裸色透明甲、第100至101报告、train最低规模门、训练禁用 |
| 2026-07-18 | v1.1.176 | 依据2026-06-29任务原始命令记录补正`E:\.pnpm-store`来源：Codex于09:06:53调用捆绑`pnpm.cmd`执行lint/build，pnpm于09:07:01自动创建缓存目录，故可确认是Codex任务触发、pnpm自动生成，而非用户手工创建。当前仍为pnpm v11内容寻址依赖缓存，18743个文件、约471.88 MiB；本轮仅只读核验，未修改或删除缓存，模型接口、训练真值98/100及发布HOLD不变，未执行Git提交或推送 | 本地开发环境、依赖缓存、来源归因、文档复核 |
| 2026-07-18 | v1.1.175 | 完成`00294/00914/01262`批次066与第97至99个批准真值报告。SAM完成3图/15提示但仅7 pass/8 suspect，原分辨率整图与逐甲2×视觉继续拦截整指、皮肤、背景、错误弯曲指腹及相邻甲面污染，终版15枚甲面全部以人工polygon重建。多轮收边修正`00294`横向遮挡、`00914`侧视立体装饰及链钻/雪花甲遮挡、`01262`甲根锯齿与皮肤外刺；15/15 polygon合法、零交叠、几何15/15。返修SHA-256为`dd4d52e5…5965`、`bc6e3295…a2c6`、`0168a2d8…1a1`，真值SHA-256为`569b24c9…e570`、`6c77feb9…be33`、`49ebc05a…6444`。唯一索引更新为99个批准报告、98张唯一图片/511 mask、1冗余、0冲突，SHA-256为`35f437d5…937e`；最低100张train正样本完成98%、仍缺2张，val 0/30和约100张hard negative不变。联合专项12/12、编码407/407、README结构和差异检查通过；完成度审计297标记/284 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变；素材不入Git，未执行Git提交或推送 | 黑白水钻长甲、侧视立体装饰、链钻雪花甲、灰银黑纹理甲、第97至99报告、训练禁用 |
| 2026-07-18 | v1.1.174 | 完成`00293/00711/00292`批次065与第94至96个批准真值报告。`00915`两轮SAM仍合并手指/手掌后保持返修，以5甲清晰完整的`00292`替换；终版以6个逐甲审核通过的SAM polygon和9个人工polygon重建3张/15枚完整甲面。第二轮原分辨率视觉门继续移除`00293`拇指甲根皮肤、补齐`00711`第4枚银灰长甲完整甲尖并清除`00292`横向拇指衣物轮廓，15/15 polygon合法、零交叠、几何15/15。返修SHA-256为`b82e94b7…5f97`、`acdac8ea…4dac`、`96b02ea7…0537d`，真值SHA-256为`bc11ac78…9440`、`e2d84076…e64c`、`c4854173…34d7`。唯一索引更新为96个批准报告、95张唯一图片/496 mask、1冗余、0冲突，SHA-256为`12e3d613…3510`；最低100张train正样本完成95%、仍缺5张，val 0/30和约100张hard negative不变。联合专项12/12、编码407/407、README结构及差异检查通过；完成度审计293标记/280 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变；素材不入Git，未执行Git提交或推送 | 裸粉金粉甲、透明水钻甲、银灰亮片长甲、完整甲尖、第94至96报告、训练禁用 |
| 2026-07-18 | v1.1.173 | 完成`00476/00712/00291`批次064与第91至93个批准真值报告。首轮15个SAM候选和`00291`收紧重试经原分辨率整图/逐甲2×视觉门拦截金属碎片、衣物、皮肤、邻指污染及75.9302像素装饰交叠，终版以9个已审SAM polygon和6个人工polygon重建3张/15枚完整甲面；15/15 polygon合法、零交叠、几何15/15。返修SHA-256为`6e60e5c6…70ba`、`bd70072f…691b`、`98a34ec9…155c`，真值SHA-256为`e5e8d7ac…5b6b`、`d99e3c7a…2926`、`136ece68…2174`。唯一索引更新为93个批准报告、92张唯一图片/481 mask、1冗余、0冲突，SHA-256为`a9d5936a…2246`；最低100张train正样本完成92%、仍缺8张，val 0/30和约100张hard negative不变。联合专项12/12、编码407/407、README结构通过；完成度审计289标记/276 PASS、2/10门并按预期HOLD。纠正机器审计中的旧79张标注证据；素材不入Git，未执行Git提交或推送 | 灰粉亮片甲、透明银粉甲、水钻长甲、邻指与装饰交叠、第91至93报告、训练禁用 |
| 2026-07-18 | v1.1.172 | 只读复核`E:\.pnpm-store`：目录创建于2026-06-29，当前pnpm 11.9.0将活动项目缓存解析到`E:\.pnpm-store\v11`，共18743个文件、约471.88MiB；环境中未设置`store-dir`覆盖，目录属于pnpm自动维护的依赖内容缓存，不是本轮手工创建。本轮未修改、清理或删除该目录，运行时接口、训练真值状态和发布HOLD均无变化；未执行Git提交或推送 | 本地开发环境、依赖缓存、文档复核 |
| 2026-07-18 | v1.1.171 | 完成`00225/00916/00713`批次063与第88至90个批准真值报告。SAM逐甲紧框虽生成15个候选，原分辨率整图和逐甲2×视觉门仍拦截整指、皮肤、装饰分裂与背景污染，终版以11个人工polygon和4个已审SAM polygon重建3张/15枚完整甲面；15/15 polygon合法、零交叠、几何15/15。返修SHA-256为`cba0b81c…9156`、`53909584…9811`、`0989b27a…58e4`，真值SHA-256为`dcba46dc…5729`、`b8e342c8…4a40`、`b1028bc1…dd2`。唯一索引更新为90个批准报告、89张唯一图片/466 mask、1冗余、0冲突，SHA-256为`7f06410c…16b6`；最低100张train正样本完成89%、仍缺11张，val 0/30和约100张hard negative不变。联合专项12/12、编码407/407、README结构及差异检查通过；完成度审计285标记/272 PASS、2/10门并按预期HOLD。明确审核工作区根目录索引为权威，`final`同名文件仅为历史副本；素材不入Git，未执行Git提交或推送 | 透明甲、格纹雪花甲、银粉延长甲、整指与皮肤污染、第88至90报告、索引路径门、训练禁用 |
| 2026-07-18 | v1.1.170 | 完成`00722/00723/01118`批次062与第85至87个批准真值报告。两轮SAM多点提示仍吸收衣带、皮肤、玩偶绒毛或眼睛后，按质量门切换13个人工polygon与2个已审SAM polygon；原分辨率整图和全部逐甲2×复核确认3张/15枚完整甲面，终版15/15 polygon合法、零交叠、几何15/15。返修SHA-256为`ff2bdb04…c63e`、`be037c5d…c618`、`134a1cd7…f389`，真值SHA-256为`81baeaff…0cb`、`7ebe092f…19f8`、`c5bf14a7…369f`。唯一索引更新为87个批准报告、86张唯一图片/451 mask、1冗余、0冲突，SHA-256为`300ef9ea…28a2`；最低100张train正样本完成86%、仍缺14张，val 0/30和约100张hard negative不变。README版本链接与段落间距同步整理；`E:\.pnpm-store`只读确认是2026-06-29生成的pnpm v11依赖缓存，本轮未改动。素材不入Git，未执行Git提交或推送 | 人工多边形、玩偶污染、透明裸粉长甲、完整甲面、第85至87报告、README格式、pnpm缓存、训练禁用 |
| 2026-07-18 | v1.1.169 | 完成`00719/01115`批次061与第83至84个批准真值报告。两图10枚完整可见长甲以8个已审SAM polygon和2个人工polygon重建；原分辨率整图与逐甲2×复核收紧`00719`第5甲甲根和`01115`第3甲暗色背景外扩，终版2张/10 polygon合法、零交叠、几何10/10。返修SHA-256为`e9bc325d…2960`、`97c16351…f313`，真值SHA-256为`990dbba8…06f9`、`07e0e9e9…7e9f`。唯一索引更新为84个批准报告、83张唯一图片/436 mask、1冗余、0冲突，SHA-256为`a2942ab0…2d2`；最低100张train正样本完成83%、仍缺17张，val 0/30和约100张hard negative不变。联合专项12/12、文本编码407/407、README严格结构和`git diff --check`通过；完成度审计277标记/264 PASS、2/10门并按预期HOLD。GitHub只读诊断确认当前远端唯一默认分支中文名正常，比较页乱码为历史/缓存建议，7月17日提交邮箱关联需由账号设置确认；模型接口与仓库分支未改，素材不入Git，未执行Git提交或推送 | 透明低对比长甲、背景外扩、完整甲面、第83至84报告、训练禁用、GitHub只读诊断 |
| 2026-07-18 | v1.1.168 | 完成`00183/00201`批次060与第81至82个批准真值报告。两图10枚完整可见甲面以7个已审polygon和3个人工polygon重建；原分辨率逐甲2×复核补齐侧视拇指的白色立体装饰，终版2张/10 polygon合法、零交叠、几何10/10。返修SHA-256为`a7821305…15aa`、`d9734c65…cdc5`，真值SHA-256为`b34c4d96…20ea`、`826831f7…3da8`。唯一索引更新为82个批准报告、81张唯一图片/426 mask、1冗余、0冲突，SHA-256为`48d5ea4b…ed48`；最低100张train正样本完成81%、仍缺19张，val 0/30和约100张hard negative不变。联合专项12/12通过；正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 侧视拇指、立体装饰、完整甲面、第81至82报告、训练禁用 |
| 2026-07-18 | v1.1.167 | 完成`00194/00906`批次059与第79至80个批准真值报告。两图9枚完整可见甲面全部人工重画；原分辨率视觉门拦截首轮头发误检、蝶形透明甲漏甲根及深色/透明甲宽框吸收皮肤和猫毛，返修后2张/9 polygon合法、零交叠、几何9/9，整图及逐甲2×视觉通过。返修SHA-256为`e57217c3…f199`、`35f01f70…1ddb`，真值SHA-256为`c12cd939…1eac`、`2371f289…2bd7`。唯一索引更新为80个批准报告、79张唯一图片/416 mask、1冗余、0冲突，SHA-256为`6e4dadf9…378d`；最低100张train正样本完成79%、仍缺21张，val 0/30和约100张hard negative不变。联合专项12/12、文本编码407/407与README严格结构通过；完成度审计271标记/258 PASS、2/10门并按预期HOLD。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 头发误检、猫毛背景、透明甲根、完整甲面、第79至80报告、训练禁用 |
| 2026-07-18 | v1.1.166 | 完成跨分片`00531/00301/00489`批次058与第76至78个批准真值报告。整图和逐甲2×多轮复核拦截绸布误检、蝴蝶结甲局部覆盖、相邻两甲14.3736像素交叠、自然甲甲根吸收指腹和透明游离缘遗漏；终版以3个已审polygon和12个人工polygon重建为3张/15 polygon合法、零交叠、几何15/15。返修SHA-256为`72933f14…a3d3`、`e06f91b1…c6af`、`6c07716b…2c40`，真值SHA-256为`d212a959…e1aa`、`174e3f19…5b7`、`b96b894e…5112`。唯一索引更新为78个批准报告、77张唯一图片/407 mask、1冗余、0冲突，SHA-256为`b9299635…3a5e`；最低100张train正样本仍缺23张，val 0/30和约100张hard negative不变。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 绸布误检、蝴蝶结甲、自然甲游离缘、相邻甲交叠、第76至78报告、训练禁用 |
| 2026-07-18 | v1.1.165 | 完成跨分片`00902/00196/00661`清晰五甲返修批次057与第73至75个批准真值报告。三图各5枚完整可见甲面，旧候选含重复透明甲、底部圆形背景、衣袖和整段手指误检，立体花饰甲根及侧视/斜向甲还存在指腹污染；15枚甲全部改为人工多边形。首轮放大审核继续拒绝4处大块皮肤外溢，按真实甲根与侧视边界收紧后，最终3张/15 polygon合法、零交叠、几何15/15，整图与逐甲2×视觉通过。返修SHA-256为`7328d6b5…cf90`、`f750efa5…7796`、`1970a7d8…ff52`，真值SHA-256为`8512b630…9be9`、`be4d1a0a…6dc8`、`22c03d74…107c`。唯一索引更新为75个批准报告、74张唯一图片/392 mask、1冗余、0冲突，SHA-256为`28a81e40…e309`；最低100张train正样本完成74%、仍缺26张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格结构检查通过；完成度审计264个标记/251个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 五甲完整、侧视甲、指腹污染、背景误检、第73至75报告、训练禁用 |
| 2026-07-18 | v1.1.164 | 完成跨分片`00229/00193/00496`边缘返修批次056与第70至72个批准真值报告。原分辨率放大复核拒绝透明甲边缘缺口、皮肤外溢、反光缺口、甲根断裂及手指关节/戒指/织物误检，15枚甲全部改为人工多边形。最终3张/15 polygon合法、零交叠、几何15/15，整图及逐甲2×视觉确认甲根、甲缘、透明甲尖和立体装饰完整。返修SHA-256为`6186d161…d244`、`4bb2aa3a…ac15`、`eb42ab7b…60bb`，真值SHA-256为`252eb5b7…f06`、`64014673…492`、`8d96bc00…cb21`。唯一索引更新为72个批准报告、71张唯一图片/377 mask、1冗余、0冲突，SHA-256为`2d28a5cf…64b3`；最低100张train正样本完成71%、仍缺29张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格结构检查通过；完成度审计260个标记/247个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 人工多边形、透明甲缘、反光缺口、误检清理、第70至72报告、训练禁用 |
| 2026-07-18 | v1.1.163 | 完成跨分片`00495/01268/00227`批次054—055与第67至69个批准真值报告。首轮放大复核拒绝`00495`甲根尖刺/皮肤污染、`00227`透明甲尖遗漏及`01268`相邻甲12.9567像素交叠；批次055以10个人工多边形和5个已审polygon重建，构建器再次拦截交叠后按真实接触边界分离。最终3张/15 polygon合法、零交叠、几何15/15，整图及逐甲2×视觉确认甲根、甲缘、透明/渐变甲尖和链钻装饰完整。返修SHA-256为`8b0aedbe…a5fa`、`61c603f7…36e4`、`7620ad52…8890`，真值SHA-256为`f00edc75…4946`、`4ebfc939…a29f`、`d9d8c8c8…92f7`。唯一索引更新为69个批准报告、68张唯一图片/362 mask、1冗余、0冲突，SHA-256为`d0550359…2385`；最低100张train正样本完成68%、仍缺32张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格结构检查通过；完成度审计256个标记/243个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 透明甲尖、甲根尖刺、链钻装饰、相邻甲交叠、人工多边形、第67至69报告、训练禁用 |
| 2026-07-18 | v1.1.162 | 完成分片007同来源`00965/00967`原分辨率分流、批次052—053及第66个批准真值报告暨第65张唯一真值图片。`00965`至少一枚应标甲面被相邻手指遮挡，哈希绑定排除；`00967`首轮保留4候选并重画右侧银粉甲后，逐甲2×识别出第1项实际覆盖指间头发/阴影、第5项吸收指腹，第二轮仅保留中间3甲并重画两枚问题甲。构建器先后拦截非法polygon及7.4510像素交叠，最终5 polygon合法、零交叠、几何5/5，整图及局部视觉通过。返修SHA-256为`7a163fe3…e604`，真值SHA-256为`1bf8f509…021e`。唯一索引更新为66个批准报告、65张唯一图片/347 mask、1冗余、0冲突，SHA-256为`8b0f4276…d790`；最低100张train正样本完成65%、仍缺35张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格结构检查通过；完成度审计252个标记/239个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 遮挡甲排除、眼睛误检、头发误检、指腹污染、蝴蝶结装饰、第66报告、训练禁用 |
| 2026-07-17 | v1.1.161 | 完成分片007同来源`01213/01222…_9`批次050—051并形成第64至65个批准真值报告暨第63至64张唯一真值图片。两图旧候选存在漏甲、重复和整段手指/皮肤污染；批次050保留3枚逐甲完整候选并人工重画7甲，逐甲2×发现`01222…_9`第4甲面漏掉左侧甲面附着立体饰品后，批次051仅替换该甲。最终2张/10 polygon合法、零交叠，终版各5/5几何通过，整图与局部视觉通过。返修SHA-256为`ac80f0ab…886a`、`507aadcc…c11b`，真值SHA-256为`c87d8670…a698`、`18e36cc8…b3b`。唯一索引更新为65个批准报告、64张唯一图片/342 mask、1冗余、0冲突，SHA-256为`c95b2a13…772f`；最低100张train正样本完成64%、仍缺36张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格格式检查通过；完成度审计249个标记/236个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 整指污染、漏甲、透明长甲、立体饰品外凸、人工多边形、第64至65报告、训练禁用 |
| 2026-07-17 | v1.1.160 | 完成分片007同来源`01215`批次047—049并形成第63个批准真值报告暨第62张唯一真值图片。批次047补齐横向拇指并删除大块指腹候选；逐甲2×发现食指吸收戒指、无名指与小指存在甲根尖刺，批次048重画三甲；第二次放大复核又发现食指甲尖仍纳入下方戒指反光，批次049再次收紧。最终1张/5 polygon合法、零交叠、几何5/5，整图与局部视觉通过。返修SHA-256为`c1efc355…fe92`，真值SHA-256为`f5750757…2ed1`。唯一索引更新为63个批准报告、62张唯一图片/332 mask、1冗余、0冲突，SHA-256为`50727dde…356d`；最低100张train正样本完成62%、仍缺38张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格格式检查通过；完成度审计246个标记/233个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 漏拇指、指腹污染、戒指污染、甲根尖刺、人工多边形、第63报告、训练禁用 |
| 2026-07-17 | v1.1.159 | 完成分片007同来源`01216/01219/01221`批次045—046并形成第60至62个批准真值报告暨第59至61张唯一真值图片。批次045删除前后两图重复候选、重画`01219`吸收大块指腹的拇指；几何15/15后，逐甲2×仍发现`01216/01221`旧候选存在甲根凹口，批次046将其10甲全部人工重画。最终3张/15 polygon合法、零交叠、几何15/15，整图与局部视觉通过。返修SHA-256为`06058354…73f8`、`21eac83b…1a34`、`b6d6285b…0b4d`，真值SHA-256为`1a89e093…c1c1`、`0e613a88…1562`、`2e1f9b5e…804d`。唯一索引更新为62个批准报告、61张唯一图片/327 mask、1冗余、0冲突，SHA-256为`f6479f21…f1db`；最低100张train正样本完成61%、仍缺39张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格格式检查通过；完成度审计244个标记/231个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 重复候选、指腹污染、甲根凹口、人工多边形、第60至62报告、训练禁用 |
| 2026-07-17 | v1.1.158 | 完成分片007同来源`01217/01218/01220`批次041—044并形成第57至59个批准真值报告暨第56至58张唯一真值图片；三图15甲全部人工重画，`01220`在首轮逐甲2×发现三枚金粉甲漏掉甲缘外凸装饰后进行第二轮局部替换。最终15 polygon合法、零交叠、几何15/15，整图与局部视觉通过；同来源`00479`因竖指只露侧向局部甲尖排除。返修SHA-256为`bb09aa3e…b2ed`、`51334233…f49f`、`ea38267a…d560`，真值SHA-256为`4b2f67a4…68b5`、`4f11e483…bd8f`、`16bab6f6…3c5c`。唯一索引更新为59个批准报告、58张唯一图片/312 mask、1冗余、0冲突，SHA-256为`2d9687cd…8764`；最低100张train正样本完成58%、仍缺42张，val 0/30和约100张hard negative不变。联合专项测试12/12、文本编码审计407/407和README严格格式检查通过；完成度审计240个标记/227个PASS、2/10门并按预期HOLD，`git diff --check`通过。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 局部甲尖排除、漏甲、首饰污染、立体装饰外凸、人工多边形、第57至59报告、训练禁用 |
| 2026-07-17 | v1.1.157 | 继续处理分片007同来源`00476/00478/00482`并形成第55至56个批准真值报告暨第54至55张唯一真值图片。原分辨率源图复核确认`00476`拇指甲被左侧图像边缘裁断，整张排除；`00478`和`00482`共10甲在批次039补齐3枚漏甲后，经逐甲2×发现旧候选仍有根部锯齿、侧缘尖刺和透明甲尖漏标，批次040仅保留3枚已审人工polygon并重画其余7枚。最终10 polygon合法、零交叠、几何10/10，整图和逐甲局部通过。返修SHA-256为`6469ebc7…d417`、`a91a8857…12ba`，真值SHA-256为`5a0702ee…b58b`、`32f73303…3974`。唯一索引更新为56个批准报告、55张唯一图片/297 mask、1冗余、0冲突，SHA-256为`2d4fde0a…1fb0`；最低100张train正样本完成55%、仍缺45张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码审计、README严格格式及`git diff --check`通过；完成度审计233标记/220 PASS、2/10门并按预期HOLD。正式数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 裁边排除、漏甲、根部锯齿、透明甲尖、人工多边形、第55至56报告、训练禁用 |
| 2026-07-17 | v1.1.156 | 完成分片007同源`00277`批次037—038，形成第54个批准真值报告暨第53张唯一真值图片。初始3候选漏2甲且吸收整段手指，五甲全部人工重画；构建器先拒绝相邻甲88.2237像素交叠，按真实遮挡边界分离后零交叠。逐甲2×继续补齐左侧侧甲和右上奶牛纹甲可见甲尖，最终5 polygon合法、几何5/5，整图与局部通过。返修SHA-256为`1c5ba1ab…d551`，真值SHA-256为`81ce29df…31b5`。唯一索引更新为54个批准报告、53张唯一图片/287 mask、1个冗余、0冲突，SHA-256为`a2912ec5…5684`；最低100张train正样本完成53%、仍缺47张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计229标记/216 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 漏甲、整段手指污染、相邻甲交叠拒绝、人工多边形、第54报告、训练禁用 |
| 2026-07-17 | v1.1.155 | 完成分片007同源`00274/00276/00278`批次035—036，形成第51至53个批准真值报告。首轮替换初审点名甲面后，逐甲2×继续发现其余保留候选的细小缺口/外刺，故第二轮对12枚问题甲面人工重画、仅保留3枚已放大复核polygon；最终3张/15 polygon合法、零交叠、几何15/15，整图与逐甲局部均通过。返修SHA-256为`a95957fa…e9b1`、`5acd20ce…d614`、`7e534d07…7041`，真值SHA-256为`662d5bed…eea0`、`06ce0bf0…1a73`、`b9443182…47a1`。唯一索引更新为53个批准报告、52张唯一图片/282 mask、1个冗余、0冲突，SHA-256为`c5f37ae5…549a`；最低100张train正样本完成52%、仍缺48张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计227标记/214 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 同源五甲、甲根缺口、皮肤外刺、人工多边形、第51至53报告、训练禁用 |
| 2026-07-17 | v1.1.154 | 完成分片008`00531`批次032及分片009`00951`批次033—034，形成第49至50个批准真值报告。`00531`保留3甲并人工补短拇指、重画横向长甲，删除毛衣污染；`00951`两轮SAM补立体装饰拇指均吸收指腹，转人工重画拇指和蝴蝶结甲，并修正银粉方甲右下缺口。两张最终均为5个合法polygon、零交叠、几何5/5，整图与逐甲2×通过；返修SHA-256为`f44ff0c7…fc01`、`c1f0808d…b5d3`，真值SHA-256为`9b8a129e…c769`、`8c291c2c…63ea`。唯一索引更新为50个批准报告、49张唯一图片/267 mask、1个冗余、0冲突，SHA-256为`c2b338b3…d577a`；最低100张train正样本完成49%、仍缺51张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计223标记/210 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 漏拇指、毛衣污染、立体装饰、人工多边形、第49至50报告、训练禁用 |
| 2026-07-17 | v1.1.153 | 完成分片009`00704`批次028—030及分片008`00533`批次031，形成第47至48个批准真值报告。`00704`首轮SAM删除眼睛误检并补两甲，几何5/5但视觉发现横向mask吸收整段手指；转人工重画两枚漏/错甲并收紧中央亮片甲甲根。`00533`此前SAM补横向拇指时吸收皮肤并与上方黄甲交叠，改为保留3甲、人工重画2甲。两张最终均为5个合法polygon、零交叠、几何5/5，整图与逐甲2×通过；返修SHA-256为`4b2b871c…3f7f`、`acbdd080…79b4`，真值SHA-256为`10ae8e37…fa14`、`ff901cb7…d59`。唯一索引更新为48个批准报告、47张唯一图片/257 mask、1个冗余、0冲突，SHA-256为`94e3e0cb…44a2b`；最低100张train正样本完成47%、仍缺53张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计219标记/206 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 眼睛误检、漏拇指、人工多边形、第47至48报告、训练禁用 |
| 2026-07-17 | v1.1.152 | 完成分片008侧视透明拇指批次024—027及第46个批准真值报告。`00527…_0`首轮保留4甲并用多点SAM补拇指，1张/5提示、0 fallback、几何5/5，但原分辨率发现新增mask吸收三角形指腹而拒绝；转人工多边形覆盖透明主体、绿色装饰和灰绿色甲尖，并平滑第1甲右侧皮肤凸起。最终5个polygon合法、零交叠、几何5/5，整图和逐甲2×通过；返修与真值SHA-256为`dfdb7e46…1868b`、`5646b11c…901ec`。唯一索引更新为46个批准报告、45张唯一图片/247 mask、1个冗余、0冲突，SHA-256为`ad00766a…f023c`；最低100张train正样本完成45%、仍缺55张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计215标记/202 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 侧视拇指、SAM视觉拦截、人工多边形、第46报告、训练禁用 |
| 2026-07-17 | v1.1.151 | 优先推进首批训练真值并纠正唯一计数。批次019对00535/00538两张零候选图建立10个提示，SAM2.1 large完成2/2、0 fallback、几何8 pass/2 suspect；批次020—023将00538转人工多边形并达到5个合法polygon、零交叠、几何5/5，但原分辨率仍无法可靠排除第3/4透明低对比甲的指尖皮肤，两图均0晋级。分片001直通`01119…_6`经绑定哈希、10个合法polygon和零交叠终审生成第45个批准报告，SHA-256为`687c8d61…3c5c`。新增训练真值唯一性审计，发现`00491…_2`的003与039报告绑定相同annotation，选039且只计一次；45个批准报告归并为44张唯一图片/242 mask、1个冗余、0冲突，索引SHA-256为`824c9b3a…33cdc`。最低100张train正样本仍缺56张，val 0/30和约100张hard negative不变。联合专项12/12、407文件编码、README严格格式及`git diff --check`通过；完成度审计213标记/200 PASS、2/10门并按预期HOLD。正式409图/2142 mask、生产manifest与运行时接口不变，素材不入Git，未提交或推送 | 训练真值去重、零候选返修、视觉门禁、第45报告、训练禁用 |
| 2026-07-17 | v1.1.150 | 完成分片008右侧甲根缺口人工多边形批次018，形成第43至44个训练真值。两张原候选均有五甲，仅最右侧淡紫/白色渐变甲的甲根侧出现连续可见甲面凹口；每张保留4个已审完整polygon，仅替换问题甲面。人工构建器输出2张/10 polygon、保留8个、人工2个、0非法、0交叠，几何10 pass/0 suspect，整图及逐甲2×原分辨率确认甲根、两侧甲缘和方形甲尖完整。返修终结SHA-256为`f55cbf9c…d97d`和`a9a59c6f…ae28`，真值SHA-256为`e7950324…aa23`和`b97d7289…1265`。累计44张/236 mask，最低100张train正样本完成44%、仍缺56张；val 0/30和约100张hard negative不变。专项10/10、405文件编码、README严格格式及`git diff --check`通过；完成度审计210标记/197 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 甲根缺口、人工多边形、第43至44训练真值、训练禁用 |
| 2026-07-17 | v1.1.149 | 完成跨分片漏拇指SAM批次015—016及人工多边形批次017，形成第41至42个训练真值。批次015三张/15提示为13 pass/2 suspect，批次016收紧两张后几何10 pass/0 suspect，但原分辨率仍发现新增拇指mask吸收甲根皮肤，三张均未直接晋级。对其中两张保留各4个已审完整polygon，仅人工重绘漏标拇指；构建器输出2张/10 polygon、2个人工polygon、0非法、0交叠，几何10 pass/0 suspect，整图和逐甲2×视觉通过。返修终结SHA-256为`d036c2da…6ca3`和`aec62ddf…27e`，真值SHA-256为`cfd9b665…969e`和`e9a5258e…7de2`。累计42张/226 mask，最低100张train正样本完成42%、仍缺58张；val 0/30和约100张hard negative不变。专项10/10、405文件编码、README严格格式及`git diff --check`通过；完成度审计207标记/194 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 漏拇指、几何与视觉双门、人工多边形、第41至42训练真值、训练禁用 |
| 2026-07-17 | v1.1.148 | 完成跨分片返修批次012、双手侧向拇指重试批次013及单甲误检删除批次014，形成第39至40个训练真值。批次012三张/19提示、0 fallback、几何15 pass/4 suspect，只放行删除整段手指误检的四枚低对比裸色甲图；双手图暴露8甲、2个跨甲重复宽框和2枚漏甲，白色立体装饰长甲图因透明边缘缺口继续返修。批次013补两枚侧向拇指后几何10 pass，但原分辨率仍吸收大块指腹且只露局部，拒绝真值。批次014单甲1/1提示、几何1 pass，主体星形透明长甲完整。两个真值共5个合法polygon、同图零交叠，SHA-256为`1bea3750…aec0`和`ca8118d9…25c3b`。累计40张/216 mask，最低100张train正样本完成40%、仍缺60张；val 0/30和约100张hard negative不变。专项8/8、405文件编码、README严格格式及`git diff --check`通过；完成度审计203标记/190 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 低风险返修、局部甲面拦截、单甲真值、第39至40训练真值、训练禁用 |
| 2026-07-17 | v1.1.147 | 完成跨分片明显误检删除批次011并形成第37至38个训练真值。三张/15提示由SAM2.1 large完成、0 fallback，几何15 pass/0 suspect；原分辨率仅放行删除背景标识误检的`nail_01116…_3`与删除头发/背景误检的`nail_00180…_2`，每张五枚甲面完整。`nail_00531…_5`透明甲边界内缩、局部甲面缺失，继续返修且禁训。两个真值均为5个合法polygon、同图零交叠，SHA-256为`f7781902…6663`和`291f9b77…dcd`。累计38张/211 mask，最低100张train正样本完成38%、仍缺62张；val 0/30和约100张hard negative不变。专项8/8、405文件编码、README严格格式及`git diff --check`通过；完成度审计198标记/185 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 跨分片返修、明显误检、透明甲拦截、第37至38训练真值、训练禁用 |
| 2026-07-17 | v1.1.146 | 完成分片009漏甲/重复分割返修批次009与甲根皮肤重试批次010，形成第34至36个训练真值。批次009四张/20提示、0 fallback、几何20 pass/0 suspect，但原分辨率只放行竖指透明延长甲和由两个重叠局部候选重建的单一透明长甲；两枚吸收甲根皮肤的拇指继续返修。批次010两张/10提示、0 fallback、几何10 pass/0 suspect，原分辨率只接受横向长拇指甲，带立体装饰拇指仍返修。三个真值均为5个合法polygon、同图零交叠，SHA-256为`eb607d29…7d03`、`b7409f8c…6e0b`和`13ab302d…65ea3`。累计36张/201 mask，最低100张train正样本完成36%、仍缺64张；val 0/30和约100张hard negative不变。专项8/8、405文件编码、README严格格式及`git diff --check`通过；完成度审计195标记/182 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片009、漏甲、重复分割、皮肤污染、第34至36训练真值、训练禁用 |
| 2026-07-17 | v1.1.145 | 完成分片009低风险返修批次007及侧视拇指重试批次008，形成第31至33个训练真值。批次007三张/15提示、0 fallback，首轮几何14 pass/1 suspect；仅珍珠链误检删除图直接通过，两张侧视拇指图因皮肤风险或提示中心不一致继续返修。批次008收紧斜向提示并强化皮肤负点，2/2张、10/10提示、0 fallback、几何10 pass/0 suspect；原分辨率确认三张共15枚完整露出甲面一甲一mask且无皮肤、首饰或背景污染，最终polygon合法、同图零交叠。真值SHA-256为`9d707a18…be72`、`18252db0…2fbc`和`a55ad552…d272`。累计33张/186 mask，最低100张train正样本完成33%、仍缺67张；val 0/30和约100张hard negative不变。专项8/8、405文件编码、README严格格式及`git diff --check`通过；完成度审计190标记/177 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片009、珍珠链误检、侧视拇指、第31至33训练真值、训练禁用 |
| 2026-07-17 | v1.1.144 | 完成`nail_00076…_1`双手十甲复杂返修并形成第30个训练真值：保留6个完整候选，以紧框、多正点和邻近皮肤负点补齐4个漏甲，删除整段手指与手链误检。SAM2.1 large完成1/1张、10/10提示、0 fallback，几何10 pass/0 suspect；原分辨率整图确认10枚完整露出甲面均由单一完整mask覆盖且无皮肤、首饰或背景污染，最终10个polygon合法、同图零交叠。真值SHA-256为`9d0a5602da1a60a296b7dab0e45888fb830b9e577f183825868cfcd97abc8b1f`。累计30张/171 mask，最低100张train正样本完成30%、仍缺70张；val 0/30和约100张hard negative不变。专项8/8、405文件编码、README严格格式与`git diff --check`通过；完成度审计185标记/172 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 十甲返修、多点提示、第30训练真值、训练距离、训练禁用 |
| 2026-07-17 | v1.1.143 | 完成`nail_00628…_2`相邻甲人工零交叠返修并形成第29个训练真值：保留4个已审完整polygon，人工替换与相邻甲交叠10960.0713像素的第5甲。构建器对首版0.0024像素残余交集继续拒绝，边界内收后1/1张、5个polygon、合法5个、同图0交叠，几何5 pass/0 suspect；整图及第4/5甲2×原分辨率视觉确认完整可见甲面、交界无重复且无袖口污染。最终真值SHA-256为`ee09fecc837390f32ce34a7ae2e39b32d4726d2102327e41fc8a315ed435d414`。累计29张/161 mask，最低100张train正样本完成29%、仍缺71张；val 0/30和约100张hard negative不变。专项10/10、405文件编码、README严格格式与`git diff --check`通过；完成度审计183标记/170 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 人工多边形、相邻甲零交叠、第29训练真值、训练距离、训练禁用 |
| 2026-07-17 | v1.1.142 | 补齐分片010返修批次002—003证据并完成批次004：批次002三张/20提示和批次003三张/15提示均由SAM2.1 large零fallback完成，几何分别20/20与15/15全pass，原分辨率视觉、哈希身份、polygon合法性和同图零交叠终审形成第21至26个训练真值。批次004三张/14提示零fallback；审计器保留外接框IoU诊断并新增Shapely精确polygon交集面积与非法拓扑门，两项新回归证明斜甲外接框相交但polygon分离可通过、真实polygon交叠会拒绝。`nail_00628…_2`相邻甲真实交集10960.0713像素继续返修；另两张形成第27至28个真值。累计28张/156 mask，最低100张train正样本完成28%、仍缺72张；val仍缺30张、约100张hard negative未建立，整批物化和来源隔离前继续禁训。全量410/410、ESLint、405文件编码、README严格格式和`git diff --check`通过；完成度审计181标记/168 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 返修批次002—004、精确polygon交集、第21至28训练真值、训练距离、训练禁用 |
| 2026-07-17 | v1.1.141 | 核验训练启动距离并完成首个低风险误检删除返修批次：从分片010保留两张共10个逐甲提示，删除戒指、方向盘控件和手链流苏3个非甲提示；SAM2.1 large完成2/2张、10/10提示、0 fallback，几何10 pass/0 suspect。两张原图及全分辨率叠加图确认透明长甲尖、附着立体装饰可见区域和短甲甲缘完整，无皮肤/背景污染；哈希绑定返修终结与最终真值审计均通过，polygon全部合法、同图零交叠。训练真值增至20张/112 mask，最低100张train正样本完成20%、仍缺80张；val仍缺30张，约100张hard negative仍未建立，数据物化与来源隔离前继续禁训。同步新增返修批与第19至20个真值PASS标记；全量测试、ESLint、405文件编码审计、README严格格式和`git diff --check`通过，完成度审计为169标记/156 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 训练距离、低风险返修、第19至20训练真值、训练禁用 |
| 2026-07-17 | v1.1.140 | 完成首批mask审核最后分片010并形成第17至18个训练真值候选：复验绑定CSV SHA-256 `473e87b104511eed1eecebbfec134e1544a802598f4c54eeef7d3eba98767ff2`、9页审核哈希及17张逐图身份；原图和全分辨率叠加图审核为2直接通过、15返修、0排除，UI按钮、汽车按键、戒指/手链、衣物、整块指腹误检及漏甲与误检抵消成等计数的样本均被拦截。决定清单SHA-256为`8473020100e3c54d11f30da28cac67d65bbd3faedab99d14983fd6aa97e6ddee`，分片终结报告SHA-256为`1937a3a9b7e2507cc8569d826bef38b58f3cc3556777ef4c2b9695d843bc4378`。2个直接通过项共10个mask全部通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审；真值报告SHA-256为`d9e64479…c098`和`b24e33ce…8ce5`。首批160/160初审完成，累计15暂通过、138返修、7排除；训练真值18张/102 mask，最低train正样本仍缺82张，val 0/30和约100张hard negative未建立。专项3/3、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计更新为166标记/153 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片010、初审闭环、第17至18训练真值、训练禁用 |
| 2026-07-17 | v1.1.139 | 完成首批mask审核分片009并形成第11至16个训练真值候选：复验工作区报告SHA-256 `6c791e7992e61788f8a4815cb7e4d3c0e9edd11bf48d5562d02ebc6a8f7974c4`、绑定CSV SHA-256 `81b0a6ddd60fa3fc63877ade812debc4ca3b095e772ea1ca0e8dece4dae9dd10`、10页审核哈希及19张逐图身份；原图和全分辨率叠加图审核为6直接通过、13返修、0排除，漏甲、重复/交叠及首饰、布料、眼睛、嘴唇、手指和皮肤误检均被拦截。决定清单SHA-256为`ee291680efb795776f402811b71b05914ecc9f2ba2fc820e0c3c6b874c1e1ede`，分片终结报告SHA-256为`b3d81bd099cb617e7f78afa674f9374b15e47b5960b502319df3ba6665f72446`。6个直接通过项共30个mask全部通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审；真值报告SHA-256依次为`13b2d442…e9eb`、`fb207f9f…0685`、`5b55c06e…8d9b`、`6fc28890…d0db`、`5740553f…fe20`和`239835ec…ca3`。累计初审143/160（89.375%）、训练真值16张/92 mask、剩余17张，最低train正样本仍缺84张。专项3/3、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计更新为163标记/150 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片009、完整mask、第11至16训练真值、训练禁用 |
| 2026-07-16 | v1.1.138 | 在分片008闭环后复核下一轮有效候选训练距离：训练、候选验证、评估、ONNX导出和本机算力链路均已具备，可随时运行旧数据实验，但新增实拍批次尚未达到候选训练数据门。首批train初审124/160（77.5%），剩余36张；最终训练真值为10张/62 mask，按模型试验最低100张真实正样本口径完成10%、仍缺90张。即使剩余36张全部通过，仍至少需要从110张返修队列中完成54张真值终结。来源隔离val真值为0/30，约100张合格hard negative尚未建立；按100 train正样本+30 val+约100 hard negative的简单角色数量口径为10/230（约4.3%），但该比例不代表已完成的工程治理工作。三类数据满足后还须执行数据物化、来源隔离、polygon合法性、同图零交叠和候选训练预检，才启动有意义的新候选训练。分片008专项7/7、ESLint、405文件编码审计、README严格格式和`git diff --check`通过；完成度审计更新为156标记/143 PASS、2/10门并按预期HOLD。本次无接口、正式数据集、manifest或训练状态变化，未执行Git提交或推送 | 训练距离、真值进度、数据角色、无接口变更 |
| 2026-07-16 | v1.1.137 | 完成首批mask审核分片008并形成第10个训练真值候选：复验绑定CSV SHA-256 `2697b9dfff18dfb4a4dcdc62d32a85ec57b44b84eeb431ace75a8e9d9aae3ea0`、9页审核哈希和18张逐图身份，原图与叠加图审核为0直接通过、16返修、2张因拇指甲仅露局部甲尖而排除；漏甲、重复/交叠、首饰/绸布/头发误检及等计数甲缘缺口均被拦截。决定清单SHA-256为`3e36af34831fd881b1acc3f4eaf6e42bb54680871f35e7b4261090bd6492e521`，分片终结报告SHA-256为`34d88d24dffa55b9abf644fe7735493a2c2aa0818a4b01bd0112636ef76d188f`。`nail_00529…_2`视觉候选在真值预审中因第3甲polygon自交且漏甲根被拒绝；保留4个已审polygon并人工重绘贝壳装饰甲后，整图/逐甲2×视觉、几何5/5、合法性和零交叠通过，返修终结及真值报告SHA-256分别为`b28c911c9faf59640f8d4224f49ea43c0641521f0dc304783f1ae4df0d1399f6`和`f8d2b8fcf2f211b8d751b1f88a3bdfff9ca6766366b1ac0d6bf3b2ba29a595d1`。累计初审124/160、训练真值10张/62 mask、剩余36张，最低train正样本仍缺90张；整批物化与来源隔离前继续禁止训练。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片008、遮挡残缺硬门、人工多边形、第十训练真值、训练禁用 |
| 2026-07-16 | v1.1.136 | 完成首批mask审核分片007并形成第9个训练真值候选：复验绑定CSV SHA-256 `0ac2192bc1e4bf971beb298697410d58c29801760883b7e9830821ec603fa1d5`、10页审核哈希及20张逐图身份，原图与叠加图原分辨率审核为1直接通过、19返修、0排除；漏甲、重复/交叠、整段手指及眼睛/头发误检均被拦截，4张候选数相等但存在甲缘缺口或皮肤污染的样本继续返修。决定清单SHA-256为`b31c13589a2166a8d086673e19b0e8a3d26a9cd29e986820d2646a7519e5c215`，分片终结报告SHA-256为`50da6fc3dbe348018b8c434875f5750681ba804c3cafa65ccf85a3a5837006c4`。唯一直接通过样本5个mask通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审，真值报告SHA-256为`beb3480c96eff22985a30a301e15d354e8448af2a59955fba9a99cbac7fc578d`。累计初审106/160、训练真值9张/57 mask、剩余54张，最低train正样本仍缺91张；整批物化与来源隔离前继续禁止训练。专项3/3、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计154标记/141 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片007、完整mask、第九训练真值、训练禁用 |
| 2026-07-16 | v1.1.135 | 完成首批mask审核分片006并形成第5至8个训练真值候选：复验绑定CSV SHA-256 `66870edbfc6801f2ce2940d85cd3b78394207b7b20c490e14835e02dec29dd36`、8页审核哈希及15张逐图身份，原图与叠加图原分辨率审核为4直接通过、11返修、0排除；漏甲、重复/交叠、头发/面部误检及手指/皮肤污染均被拦截，候选数相等的污染样本也继续返修。决定清单SHA-256为`c69539a75c4820177e1d46746c917d8cabe4d3c9da4bf928a2d434b81e0681ec`，分片终结报告SHA-256为`fd0bbbb7c148ae80cbe4505ba6fcedd300dcd42888fe7a1a15f79d2e16950f19`。4个直接通过项共18个mask全部通过原图/annotation/分片哈希、polygon合法性和同图零交叠终审，真值报告SHA-256分别为`9b816ea5…1e31`、`2d155ad8…e441`、`53c8c6cc…374f`和`4b98f90a…a7d6`。累计初审86/160、训练真值8张/52 mask、剩余74张，最低train正样本仍缺92张；整批物化与来源隔离前继续禁止训练。专项3/3、全量408/408、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计152标记/139 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、manifest和运行时接口不变，素材不入Git，未执行Git提交或推送 | 分片006、完整mask、第5至8训练真值、训练禁用 |
| 2026-07-16 | v1.1.134 | 复核下一轮有效候选训练的剩余距离：训练代码、候选验证、评估、导出链路和本机算力均已具备，当前关键路径仍是新增实拍完整mask真值。首批train初审71/160（44.375%），剩余89张；最终训练真值候选4张/34 mask，按最低100张train正样本口径完成4%、仍缺96张；来源隔离val为0/30，约100张hard negative尚未建立。若仅按最低数据角色数量100+30+100核算，当前完成4/230，约1.7%，但该比例不代表已完成的工程治理工作。满足三类数据配额后仍须完成数据物化、来源隔离、polygon合法性、同图零交叠和候选验证终审，才可启动有意义的候选训练；既有409张/2142 mask实验训练可立即运行，但不能代表新增实拍批次改进。本次为状态复核，无接口、正式数据集、manifest或训练状态变化，未执行Git提交或推送 | 训练距离、数据真值门、进度口径、无接口变更 |
| 2026-07-16 | v1.1.133 | 完成人工多边形返修候选到训练真值的完整终结链：人工构建器为annotation写入候选禁训元数据；返修终结器新增与`--sam-report`互斥的`--manual-report`，强制绑定人工报告、提示、几何、annotation、原分辨率overlay和人工决定哈希，并要求报告方法匹配、全部polygon合法、同图零交叠。`nail_01241…_3`保留9个已审polygon，人工替换左侧拇指无效回折轮廓；10/10几何、原分辨率整图/局部视觉、合法性和零交叠通过，返修终结SHA-256为`eb898a6cab4f5fc822be918f895f739f4b9992f216183fe3d060c2883a237844`，最终真值SHA-256为`a2d0532c696cfbff260f044d93ae12a410958b0c0301e06d672dd74a63789468`。训练真值累计4张/34 mask，最低train正样本仍缺96张；整批物化和来源隔离前继续禁止训练。专项4/4、全量408/408、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计147标记/134 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变，未执行Git提交或推送 | 人工多边形、返修终结器、第四训练真值、训练禁用 |
| 2026-07-16 | v1.1.132 | 完成首批mask审核分片005并复核训练距离：绑定分片CSV SHA-256 `b6e8a4b34288456274a73bba1ed7d8724440d373e6c574c36d3f9b287f136156`、5页审核哈希和9张逐图身份，原图与叠加图原分辨率审核为1直接通过、6返修、2张因甲面遮挡残缺排除；终结报告SHA-256为`359564c8684a093797cd0c6e408565b609a2cb0fc8337aa7e3a601365480ef44`。最终真值终结器新增哈希绑定的初审直接通过模式，直接通过样本10/10完整mask经polygon合法性和同图零交叠复验后成为第三个训练真值候选。累计初审71/160、训练真值3张/24 mask、剩余89张；按最低候选训练包还缺至少97张合格train正样本、30张合格val、约100张来源隔离hard negative，以及数据物化和来源隔离终审。另1张人工多边形返修尚待完成终结证据链，未提前计数。全量407/407、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计145标记/132 PASS、2/10门并按预期HOLD。正式409图/2142 mask数据集、生产manifest和运行时接口不变；未执行Git提交或推送 | 分片005、直接通过真值、训练距离、训练禁用 |
| 2026-07-16 | v1.1.131 | 完成首批mask审核分片004并复核候选训练距离：绑定分片CSV SHA-256 `47c8c012c137f099c5891a12c92e9f05abbbe57590f1236be9da28a2d2741903`、10页审核哈希和19张逐图身份，原图与叠加图原分辨率审核为0直接通过、19返修、0排除；终结报告SHA-256为`c27d0c1d956d86aa64ea835aa423c81b623cb03dc921b40b24bb4c6e34848b77`。累计初审62/160，训练真值候选仍为2张/14 mask，剩余98张；最低候选训练门仍缺至少98张合格train正样本、30张合格val、约100张来源隔离hard negative，并需完成数据物化、来源隔离、polygon合法性和同图零交叠终审。新增33张独立test用于训练后冻结评估，不参与训练。全量406/406、ESLint、405文件编码审计、README严格格式及`git diff --check`通过；完成度审计143标记/130 PASS、2/10门并按预期HOLD。本轮未执行Git提交或推送 | 分片004、训练距离、完整mask、训练禁用 |
| 2026-07-16 | v1.1.130 | 完成首批mask审核分片003并形成第二个训练真值候选：复验绑定CSV SHA-256 `ad49dca0f125e73febe6326e774379c30b267c7bf1bfdefd16efb523dcfced45`及8页哈希，16张原图与叠加图逐张原分辨率审核为0直接通过、13返修、3张边缘裁甲排除；漏甲、局部甲面、皮肤/手指/饰品/背景误标和重复候选均被拦截。`nail_00491…_2`保留4个逐甲提示并删除覆盖整段手指的第5号提示，SAM2.1 large输出4个polygon、0 fallback，几何4/4；原分辨率视觉、polygon合法性及同图零交叠通过，成为第二个训练真值候选。累计初审43/160，训练真值候选2张/14 mask，剩余117张；全量406/406、ESLint、405文件编码审计、README严格格式及`git diff --check`通过，完成度审计142标记/129 PASS、2/10门并按预期HOLD。整批物化和来源隔离审计前继续禁止训练，本轮未执行Git提交或推送 | 分片003、裁边硬门、SAM返修、第二训练真值候选 |
| 2026-07-16 | v1.1.129 | 复核下一轮有效候选训练的实际距离：训练、候选验证证据、评估和导出链路已具备，当前关键路径仍为真实完整mask真值。正式口径保持首批train初审27/160、训练真值候选1张/10 mask、val真值0/30，另缺约100张来源隔离hard negative；按最低启动门槛仍需至少99张合格train正样本、30张合格val、约100张hard negative，以及数据物化和来源隔离终审。自动生成的881个polygon仅是候选，不计入训练真值。本次为进度核算，无接口、正式数据集、manifest或训练状态变化，未提交或推送Git | 训练距离、数据真值门、进度口径 |
| 2026-07-16 | v1.1.128 | 完成首批mask审核分片002并建立返修/训练真值候选终结门：复验绑定CSV SHA-256 `83a752b3ce8b75346c7d2beb67174073537e26c58c068938d0df7a7eb3a8b423`与7页哈希，13张逐图原分辨率审核为0直接通过、13返修；帽子系列存在漏甲/文字误检，透明延长甲系列存在漏甲、局部甲面或皮肤外溢。新增返修终结器绑定初审、提示、SAM、几何、annotation、overlay及人工决定哈希，并新增训练真值候选终结器强制复验原图SHA-256/尺寸、polygon合法性和两两零交叠。`nail_01052…_9`两轮SAM2.1 large返修后删除帽子文字、补齐两侧拇指，10/10几何通过；原分辨率视觉、polygon合法性和零交叠均通过，成为首个1张/10 mask训练真值候选，但在整批物化与来源隔离审计前继续禁止训练。累计初审27/160，剩余133张；全量406/406、ESLint、405文件编码审计、README严格格式及`git diff --check`通过，完成度审计140标记/127 PASS、2/10门并按预期HOLD。正式数据集、manifest和运行时接口不变，未提交或推送Git | 分片002、返修证据链、训练真值候选、拓扑与零交叠门 |
| 2026-07-16 | v1.1.127 | 建立首批160张mask原分辨率审核工作区并完成风险最高分片001：工作区绑定既有标注、SAM、几何报告及其SHA-256，按39个来源组原子划分10个审核分片、83页，160张/966个预期甲面全覆盖。分片001逐图查看14张原图及7页叠加图，审核为1张/10 mask暂通过、13张返修、0张排除；4张零候选的SAM2.1 large首轮20提示虽15 pass/5 suspect，但原分辨率视觉审核0/4通过，未以几何结果绕过真值门。暂通过项仍须合法性、零交叠和最终真值审计，当前可训练真值保持0/160、val 0/30，至少还需审核146张并返修失败项；所有产物继续`trainingUse=prohibited`。专项2/2、401文件编码审计及`git diff --check`通过；完成度审计137标记/124 PASS、2/10门并按预期HOLD。本轮无运行时接口、正式数据集或manifest变化，未提交或推送Git | 首批mask审核、原分辨率视觉门、训练距离、数据治理 |
| 2026-07-16 | v1.1.126 | 建立首批160张来源隔离实拍标注工作区并完成自动候选收口：工作区绑定160张/39来源组、预计966个完整甲面，图片以外部硬链接保存且全部保持训练禁用。v6在512/conf=0.15下对156张生成881个YOLO候选，4张为0候选；审核显示按单图截断计数覆盖率0.826087、66张少检、45张计数相等、49张多检、31张候选重叠风险。SAM2.1 tiny使用881个`box-center`提示复跑，修复空提示图片`np.stack`失败后达到160/160完成、881 polygon、0错误、0 fallback；报告SHA-256为`91ce4e48461b233f1ebd239f2d1a8704c078a6f0f8272f13cda87539db158160`。几何审计为796 pass、85 suspect、0 missing，报告SHA-256为`d58872e397e0a78b28aeb8b20ee01fce5e8e087438acfec0480368856ec61399`。所有产物仅为候选，160张train和30张val的原分辨率真值审核均未完成。全量402/402、ESLint、397文件编码审计、README严格UTF-8/0 NUL/12个围栏成对/31个标题/6个表格分隔行/末尾换行及`git diff --check`通过；完成度审计135标记/122 PASS、2/10门并按预期HOLD。正式训练集、生产manifest与接口不变；未提交或推送Git | 首批标注工作区、YOLO/SAM候选、空提示边界、几何排序、训练真值门、完整回归 |
| 2026-07-16 | v1.1.125 | 建立2026_7_14实拍批次首批来源隔离标注计划：新增`plan-real-material-first-annotation-batch.py`，绑定A授权、近重复终结和源图筛选批次报告，以固定种子和来源组原子子集和分配565张候选为train 502、val 30、独立发布test 33，并从train中选择160张/39来源组、预计966个完整甲面作为首批标注。既有互斥审计逐文件复验1271/1271授权条目与原图哈希，0来源泄漏；计划/CSV/审计SHA-256分别为`0dbf3a6cf99c455f3b8a8453223ef9df98eca3b16b919fa783dddd40a05dd912`、`dd11c24ba3bea9e479dd1fc4ee1a7dbbc681b7b7d7aa6ccaf7cc5c752d9e9dc4`、`11f76a240d832f8ca29d875d058146ab72aa0323d585392bdd07db4da769aa62`。规划不授予训练资格，val仍需独立真值审核，独立test始终禁止训练；筛选排除池无合格hard negative，约100张负样本单独标记延后。专项1/1、全量397/397、ESLint、390文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/末尾换行及`git diff --check`通过；完成度审计134标记/121 PASS、2/10门并按预期HOLD。正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 首批标注计划、来源组原子分配、train/val/test隔离、hard negative缺口、训练禁用、完整回归 |
| 2026-07-16 | v1.1.124 | 完成实拍质量审核最终分片026并建立批次终结门：6页覆盖21张/2来源组，21张逐文件原分辨率确认均为四宫格、九宫格或其他多场景拼图，0张保留、21张排除；决定清单SHA-256 `72314f1ef0b82b62f6fc8ea57da1b50405298794674e7c348b58840ed063a7ef`，分片终结报告SHA-256 `66db49f47e12f8af08cd7eb485eb518936d9089969af352eb3734541b05681a7`。补齐重建外部工作区019—025终结报告后，新增批次终结器逐项复验队列、26个分片、审核页/终结报告哈希及1166个文件名/图片SHA-256/来源组/训练禁用状态，真实批次26/26分片、1166/1166图片、193/193来源组唯一覆盖，565张待标注、601张排除、0张待审，批次报告SHA-256 `901f52e531b5a93f4be9b010e2e96f585ca850bd733e5d9a4f5f9865a03335c0`。专项3/3、全量396/396、ESLint、388文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/末尾换行及`git diff --check`通过；完成度审计132标记/120 PASS、2/10门并按预期HOLD。源图筛选阶段完成但mask真值仍未开始，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片026、批次终结、全量唯一覆盖、源图筛选收口、训练隔离、完整回归 |
| 2026-07-16 | v1.1.123 | 复核下一轮模型训练启动时点：当前训练工具链已经具备运行条件，但2026_7_14实拍批次仍有最后21张源图待审，565张保留项仍是`annotationTruthStatus=not-started`，尚无新增受审核完整mask可形成有效训练增量。启动顺序明确为：完成最后1个源图质量分片后，立即按完整来源组互斥制作首批训练包；首批达到100—200张新增真实正样本、约100张hard negative、至少30张合格且来源隔离的val，并从新来源补足33张独立test，所有训练/val逐甲完整mask通过原分辨率审核、polygon合法性和零交叠门后，即启动候选训练。无需等待565张候选全部标注；移动真机和Beta质量门属于正式发布条件，不阻止候选训练。本轮仅复核并明确启动口径，无接口、正式数据集、manifest或模型状态变化，未执行Git提交或推送 | 训练计划、首批训练包、完整mask审核、来源隔离、发布边界 |
| 2026-07-16 | v1.1.122 | 完成实拍质量审核分片025：11页覆盖43张/12来源组，复验报告绑定分片路径、SHA-256 `677211154ccd4f27cf993b7570a783d2a829ed2c0455680b106494729925d146`、43条空白审核条目、全部页面及源图哈希；43张逐文件回看原分辨率，9张拼图/甲型模板/设计稿/独立甲片展示和12张低清、裁边、遮挡或仅局部甲面图排除，22张仅保留为待标注候选，共149个完整可见甲面。决定清单SHA-256 `8b00ccf791bfd55381fb05e9d270e8313a97d718795b47b80162b068f1a3216c`，终结报告SHA-256 `ab250a3925e5d9e7135e2dee9c393e4c0299c911e51b1725079420e6af18beba`；终结器43/43及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-025` PASS。分片001—025累计1145张、565张待标注、580张排除，另21张待源图审核，训练启动前剩余质量分片更新为1。ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及`git diff --check`通过；完成度审计为130个标记/118个PASS、2/10门并按预期保持HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片025、原分辨率审核、非照片页面排除、低清与残缺甲排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.121 | 完成实拍质量审核分片024：12页覆盖45张/8来源组，复验报告绑定分片路径、SHA-256 `91519adf8758f5e276ab80be3e5898cc198bb90aeed0f5570acc989982199028`、45条空白审核条目、全部页面及源图哈希；45张逐文件回看原分辨率，5张手写教程标注页、1张十二宫格拼贴和4张明显像素化/失焦/拖影视频帧排除，35张仅保留为待标注候选，共217个完整可见甲面。决定清单SHA-256 `123975ab8b27ae1693590add3a65c0a2facc012362b2885faf303a0439b29605`，终结报告SHA-256 `00c521d3a7d5d49dc92c575c9d20791e9f8ed84112d7075742698dc95de3d695`；终结器45/45及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-024` PASS。分片001—024累计1102张、543张待标注、559张排除，另64张待源图审核，训练启动前剩余质量分片更新为2。ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及`git diff --check`通过；完成度审计为129个标记/117个PASS、2/10门并按预期保持HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片024、原分辨率审核、教程标注页与拼贴排除、低清视频帧排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.120 | 完成实拍质量审核分片023：12页覆盖48张/9来源组，复验报告绑定分片路径、SHA-256 `a00552bac1f47b5cd2a45c6bef0a00f37de910dec804b032107eb2aa78f3b2fe`、48条空白审核条目、全部页面及源图哈希；48张逐文件回看原分辨率，19张拼图/教程模板/独立甲片展示、6张明显像素化/失焦/压缩视频帧和2张边缘截甲图排除，21张仅保留为待标注候选，共119个完整可见甲面。决定清单SHA-256 `01ca37d3126952609da08021d7ea76232dc17f6f0ddd0feb02772984306dd3d5`，终结报告SHA-256 `37194bd8c180c9e86228ca0fd347c1bf7f559c589c0e23b5cf874352217a7656`；终结器48/48及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-023` PASS。分片001—023累计1057张、508张待标注、549张排除，另109张待源图审核，训练启动前剩余质量分片更新为3。ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及`git diff --check`通过；完成度审计为128个标记/116个PASS、2/10门并按预期保持HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片023、原分辨率审核、拼图与教程模板排除、独立甲片排除、低清与截甲排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.119 | 完成实拍质量审核分片022：13页覆盖50张/7来源组，复验报告绑定分片路径、SHA-256 `bf04510ae10b4990ce05b1eec4873b47ef148f5be1a8c44e6630add24f425494`、50条空白审核条目及全部页面哈希；50张逐文件回看原分辨率，22张甲片展示/产品宣传页/多图拼贴或社交平台海报、3张明显像素化/失焦视频帧和9张边缘裁断/遮挡/仅局部甲面图排除，16张仅保留为待标注候选，共99个完整可见甲面。决定清单SHA-256 `5ae5536db5ddcf55bdcac6c821f7a46aabd014fbe58cdb58f1d1aa6f9bf3db78`，终结报告SHA-256 `67120641e68c45e87fe71432ae642826410bbe692609c589166538901b26616b`；终结器50/50及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-022` PASS。分片001—022累计1009张、487张待标注、522张排除，另157张待源图审核，训练启动前剩余质量分片更新为4。ESLint、386文件编码审计、README严格UTF-8与Markdown结构检查及`git diff --check`通过；完成度审计为127个标记/115个PASS、2/10门并按预期保持HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片022、原分辨率审核、甲片与产品页排除、拼图排除、低清与残缺甲排除、训练隔离、训练计划 |
| 2026-07-16 | v1.1.118 | 按分片021后的当前证据再次复核下一轮模型训练启动时点：新增实拍源图已审核959/1166张，471张仅为待标注候选、488张排除、207张仍待源图审核；现阶段没有新增受审核完整mask可直接入训。启动口径不变：完成剩余5个源图质量分片后，优先按来源组互斥形成100—200张新增真实正样本、约100张hard negative、至少30张合格val，并从新来源补足33张独立test；训练/val完整mask通过原分辨率审核及来源隔离、polygon合法性和零交叠数据门后即可启动候选训练，无需等待1166张全部标注，也无需等待移动真机或Beta发布验收。本轮仅复核计划，无接口、正式数据集、manifest或模型状态变化，未执行Git提交或推送 | 训练计划、数据门禁、来源隔离、发布阻断、文档一致性 |
| 2026-07-16 | v1.1.117 | 完成实拍质量审核分片021：12页覆盖48张/11来源组，复验报告绑定分片路径、SHA-256 `22b00f5db9203743e32d6f59459ae68e0a2974d9616af1eb85b768542eaff8b8`、48条空白审核条目及全部页面哈希；48张逐文件回看原分辨率，23张拼图/社交平台海报/模板或教程页、3张失焦/破损甲局部和8张遮挡/截断/仅侧面甲面图排除，14张仅保留为待标注候选，共80个完整可见甲面。决定清单SHA-256 `a1141ed78540a1f535ed096419338561ab2f546ccdd818e3e84df2b0e55c637a`，终结报告SHA-256 `b1ab655b0552b1437b298c475a2ef97bc5804046197385ee16ca2208795e1c82`；终结器48/48及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-021` PASS。分片001—021累计959张、471张待标注、488张排除，另207张待源图审核，训练启动前剩余质量分片更新为5。ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及差异检查通过；完成度审计126标记/114 PASS、2/10门并按预期HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片021、原分辨率审核、拼版排除、低清与残缺甲排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.116 | 完成实拍质量审核分片020：13页覆盖50张/8来源组，复验报告绑定分片路径、SHA-256 `ca8ff4602d566df982eae2680f49ca27a90479dd25512c88967335b1581a18b2`、50条空白审核条目及全部页面哈希；50张逐文件回看原分辨率，21张手绘模板、九宫格或社交平台海报及3张明显失焦/像素化/视频压缩图排除，26张仅保留为待标注候选，共145个完整可见甲面。决定清单SHA-256 `06258635a82b90ffe47ad3a3a0d8a4fa048b68ab1530236cdde35535bf37e172`，终结报告SHA-256 `b2c73b4e727965aef9cb95acbed1c7fd2d41b63e30ebdd9907840c68acfa0512`；终结器50/50及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-020` PASS。分片001—020累计911张、457张待标注、454张排除，另255张待源图审核，训练启动前剩余质量分片更新为6。ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及差异检查通过；完成度审计125标记/113 PASS、2/10门并按预期HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片020、原分辨率审核、手绘模板排除、页面拼版排除、低清排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.115 | 完成实拍质量审核分片019：12页覆盖48张/8来源组，复验报告绑定分片路径、SHA-256 `aa9cedb1ef2ac9f1f27a6848cf5b6cf9f82de71039a426b7df5b1898bd538fb0`、48条空白审核条目、全部页面哈希及源图哈希；48张逐文件回看原分辨率，11张社交平台页面/拼图、4张明显失焦/像素化/视频压缩图和2张局部露出甲面图排除，31张仅保留为待标注候选，共179个完整可见甲面。终结器48/48及专项1/1通过，生成`M2-T3-REAL-MATERIAL-SOURCE-SCREENING-SHARD-019` PASS；ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及差异检查通过，完成度审计124标记/112 PASS、2/10门并按预期HOLD。分片001—019累计861张、431张待标注、430张排除，另305张待源图审核，训练启动前剩余质量分片更新为7。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片019、原分辨率审核、页面拼图排除、低清排除、局部甲面排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.114 | 再次复核下一轮模型训练启动时点：当前训练工具链可运行，但2026_7_14实拍候选仍为813张完成源图筛选、400张待标注候选、413张排除、353张待源图审核，待标注候选尚未形成受审核完整mask，立即重跑没有有效真实数据增量。训练启动口径保持不变：完成剩余8个源图质量分片后，按来源组互斥优先形成100—200张新增真实正样本、约100张hard negative、至少30张合格val，并从新来源补足33张独立test；全部训练/val真值通过原分辨率完整甲面审核和数据门后即可启动候选训练，无需等待1166张全部标注，也无需等待移动真机或Beta发布验收。本轮仅复核计划，无接口/状态变化，未执行Git提交或推送 | 训练计划、数据门禁、来源隔离、发布阻断、文档一致性 |
| 2026-07-16 | v1.1.113 | 完成实拍质量审核分片018：12页覆盖46张/5来源组，复验报告绑定分片路径、SHA-256 `16e29e4143c72289fb0062d22144cf06b06248ff5a7e0e22a3df9d99cecec8d9`、46条空白审核条目、全部页面哈希及源图哈希；46张逐文件回看原分辨率，31张拼图/社交平台页面排版和4张明显模糊或过曝图排除，11张仅保留为待标注候选，共62个完整可见甲面。终结器46/46、专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行通过；README当前结构已正常，无需额外改写。完成度审计123标记/111 PASS、2/10门并按预期HOLD。分片001—018累计813张、400张待标注、413张排除，另353张待源图审核，训练启动前剩余质量分片更新为8。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片018、原分辨率审核、拼贴排除、模糊过曝排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.112 | 完成实拍质量审核分片017：11页覆盖42张/6来源组，复验报告绑定分片路径、SHA-256 `34757af387286472b7df4de8efa407ea74194080e48fa2ddc0d84a672b47aad2`、42条空白审核条目、全部页面哈希及源图哈希；42张逐文件回看原分辨率，29张多图拼贴/社交平台页面排版和10张手绘甲型设计模板排除，3张仅保留为待标注候选，共25个完整可见甲面。终结器42/42、专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及差异检查通过；完成度审计122标记/110 PASS、2/10门并按预期HOLD。分片001—017累计767张、389张待标注、378张排除，另399张待源图审核，训练启动前剩余质量分片更新为9。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片017、原分辨率审核、拼贴排除、模板排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.111 | 完成实拍质量审核分片016：11页覆盖43张/8来源组，复验报告绑定分片路径、SHA-256 `9f7a987da495f1f1e29a02026544c1c71b3b3372b7e48e129d5387a66131ea20`、43条空白审核条目及全部页面哈希；43张逐文件回看原分辨率，2张拼图/嵌入截图、6张明显像素化/失焦/压缩视频帧和6张边缘裁断或仅局部露出甲面图排除，29张仅保留为待标注候选，共187个完整可见甲面。终结器43/43、专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行及差异检查通过；完成度审计121标记/109 PASS、2/10门并按预期HOLD。分片001—016累计725张、386张待标注、339张排除，另441张待源图审核，训练启动前剩余质量分片更新为10。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片016、原分辨率审核、拼图排除、低清视频帧排除、残缺甲面排除、训练隔离、README复验、完成度审计、训练计划 |
| 2026-07-16 | v1.1.110 | 复核“何时开始训练模型”：训练工具链和既有409图/2142 mask正式集均可运行，旧候选已完成多轮训练，但当前357张新增保留图仍未标注且484张未完成源图审核，立即重跑不会形成有效的数据增量。明确下一轮候选训练启动口径：先完成剩余11个源图分片，再按来源组互斥形成至少100—200张新增真实正样本、约100张hard negative、至少30张合格val，并补足33张独立test；完整mask原分辨率审核与数据门通过后即可训练，不必等待全部1166张标注，也不等待移动真机/Beta发布证据。生产发布HOLD、正式训练集、manifest和接口不变，未执行Git提交或推送 | 训练计划、数据门禁、来源隔离、发布阻断、文档一致性 |
| 2026-07-16 | v1.1.109 | 完成实拍质量审核分片015：12页覆盖48张/6来源组，复验报告绑定分片路径、SHA-256 `26629fd3a5bd6d4a303f8e762cf19862a99bcd5190ffead0080bc7145b53eed6`、48条空白审核条目及全部页面哈希；48张逐文件回看原分辨率，3张拼图/页面排版、4张明显像素化/失焦/压缩图、5张边缘裁断或仅局部露出甲面图和1张无美甲主体图排除，35张仅保留为待标注候选，共278个完整可见甲面。终结器48/48及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行复验通过；完成度审计120标记/108 PASS、2/10门并按预期HOLD。分片001—015累计682张、357张待标注、325张排除，另484张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片015、原分辨率审核、拼图排除、模糊排除、残缺甲面排除、域外排除、训练隔离、README复验、完成度审计 |
| 2026-07-16 | v1.1.108 | 完成实拍质量审核分片014：11页覆盖44张/7来源组，复验报告绑定分片路径、SHA-256 `8d93e405c7c84586b905916d8d833528818a9baa183d5459e4f6fc68566614da`、44条空白审核条目及全部页面哈希；44张逐文件回看原分辨率，12张拼图或社交平台页面排版、3张明显像素化/失焦/甲缘不可稳定确认图片和1张画面边缘截断已露出甲面图排除，28张仅保留为待标注候选，共192个完整可见甲面。终结器44/44及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行复验通过；完成度审计119标记/107 PASS、2/10门并按预期HOLD。分片001—014累计634张、322张待标注、312张排除，另532张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片014、原分辨率审核、拼图排除、模糊排除、裁断排除、训练隔离、README复验、完成度审计 |
| 2026-07-16 | v1.1.107 | 完成实拍质量审核分片013：11页覆盖42张/5来源组，复验报告绑定分片路径、SHA-256 `1a6d98a660b7b048b0bf419c1ef035597e18cbcd1f66e77ea7db27665949aaab`、42条空白审核条目及全部页面哈希；42张逐文件回看原分辨率，21张拼图或社交平台页面排版、2张明显像素化/失焦图和1张画面边缘截断已露出甲面图排除，18张仅保留为待标注候选，共113个完整可见甲面。终结器42/42及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行复验通过；完成度审计118标记/106 PASS、2/10门并按预期HOLD。分片001—013累计590张、294张待标注、296张排除，另576张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式409图/2142 mask训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片013、原分辨率审核、拼图排除、模糊排除、裁断排除、训练隔离、README复验、完成度审计 |
| 2026-07-16 | v1.1.106 | 完成实拍质量审核分片012：12页覆盖45张/6来源组，复验报告绑定分片路径、SHA-256、45条空白审核条目及全部页面哈希；45张逐文件回看原分辨率，4张明显像素化、压缩涂抹或失焦图片排除，41张仅保留为待标注候选，共277个完整可见甲面。终结器45/45及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个独立代码围栏成对/31个标题/6个表格分隔行/末尾换行复验通过；完成度审计117标记/105 PASS、2/10门并按预期HOLD。分片001—012累计548张、276张待标注、272张排除，另618张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片012、原分辨率审核、模糊排除、训练隔离、README复验、完成度审计 |
| 2026-07-16 | v1.1.105 | 完成实拍质量审核分片011：10页覆盖38张/5来源组，复验报告绑定分片路径、SHA-256和38条条目；14张甲型示意模板及10张拼图/页面排版直接排除，其余14张逐文件回看原分辨率，4张明显像素化、压缩涂抹或失焦图片排除，10张仅保留为待标注候选。终结器38/38及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行通过；完成度审计116标记/104 PASS、2/10门并按预期HOLD。分片001—011累计503张、235张待标注、268张排除，另663张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片011、原分辨率审核、模板排除、拼图排除、模糊排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.104 | 完成实拍质量审核分片010：12页覆盖46张/6来源组，复验报告绑定分片路径、SHA-256和46条条目；10张拼图/页面排版直接排除，其余36张逐文件回看原分辨率，3张边缘截断甲面图和2张明显像素化/偏软图片排除，31张仅保留为待标注候选。终结器46/46及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行和diff检查通过；完成度审计115标记/103 PASS、2/10门并按预期HOLD。分片001—010累计465张、225张待标注、240张排除，另701张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片010、原分辨率审核、拼图排除、裁断排除、模糊排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.103 | 完成实拍质量审核分片009：13页覆盖49张/7来源组，复验报告绑定分片路径、SHA-256和49条条目；23张拼图/页面排版直接排除，26张非拼图候选逐文件回看原分辨率，7张失焦、像素化或甲缘细节不足图片排除，19张仅保留为待标注候选。终结器49/49及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行和diff检查通过；完成度审计114标记/102 PASS、2/10门并按预期HOLD。分片001—009累计419张、194张待标注、225张排除，另747张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片009、原分辨率审核、拼图排除、模糊排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.102 | 完成实拍质量审核分片008：11页覆盖42张/9来源组，复验报告绑定分片路径、SHA-256和42条条目；27张非拼图候选逐文件回看原分辨率，15张拼图/页面排版、7张像素化/失焦/压缩视频帧和2张边缘裁断甲面图排除，18张仅保留为待标注候选。终结器42/42及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/12个代码围栏成对/31个标题/6个表格分隔行/末尾换行和diff检查通过；完成度审计113标记/101 PASS、2/10门并按预期HOLD。分片001—008累计370张、175张待标注、195张排除，另796张待源图审核。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片008、原分辨率审核、拼图排除、模糊排除、裁断排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.101 | 完成实拍质量审核分片007：12页覆盖47张/7来源组，复验报告绑定分片路径、SHA-256和47条条目；46张非页面排版候选逐文件回看原分辨率，4张像素化/失焦/压缩视频帧和1张无手部美甲主体的人像拼接页排除，42张仅保留为待标注候选。终结器47/47及专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/Markdown结构检查和diff检查通过；完成度审计112标记/100 PASS、2/10门并按预期HOLD。分片001—007累计328张、157张待标注、171张排除，另838张待源图审核；保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片007、原分辨率审核、模糊排除、非目标域排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.100 | 完成实拍质量审核分片006：13页覆盖50张/9来源组，复验报告绑定分片路径、SHA-256和50条条目；20张非拼图候选逐文件回看原分辨率，30张拼图/页面排版和5张模糊低清排除，15张仅保留为待标注候选。终结器50/50通过，分片001—006累计281张、115张待标注、166张排除，另885张待源图审核；专项1/1、ESLint、386文件编码审计、README严格UTF-8/0 NUL/Markdown结构检查及diff检查通过，完成度审计111标记/99 PASS、2/10门并按预期HOLD。保留项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集、生产manifest和接口不变，素材不入Git，未提交或推送Git | 分片006、原分辨率审核、拼图排除、模糊排除、训练隔离、README复验 |
| 2026-07-16 | v1.1.99 | 修复根目录`README.md`格式损坏：移除误追加的UTF-16LE缓存刷新文本及全部NUL字节，将文件恢复为严格UTF-8；保持原章节结构，并把编码审计数量、v6部署512拒绝结论、67张/384 mask冻结发布测试状态、仍缺33张代表性测试图及白皮书版本更新到当前事实。README专项确认0 NUL、代码围栏成对、严格UTF-8和结尾换行，ESLint、386文件编码审计及diff检查通过。该变更只修正文档格式和状态说明，不改变接口、正式训练集、生产manifest或HOLD结论；未提交或推送Git | README、文档编码、Markdown格式、模型状态一致性 |
| 2026-07-16 | v1.1.98 | 完成实拍质量审核分片005：11页覆盖44张/7来源组，复验审核报告绑定分片路径、SHA-256和44条条目，25张非拼图候选逐文件回看原分辨率；19张拼图/页面排版、4张模糊低清和2张遮挡/仅局部甲面排除，19张仅保留为待标注候选。终结器44/44和专项1/1、ESLint、386文件编码审计通过，完成度审计110标记/98 PASS、2/10门并按预期HOLD；分片001—005累计231张、100张待标注、131张排除。新增持久规则防止混用同编号旧CSV；待标注项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`，正式训练集和生产manifest不变，素材不入Git，未提交或推送Git | 分片005、报告哈希绑定、模糊排除、残缺甲面、拼图排除、训练隔离 |
| 2026-07-16 | v1.1.97 | 完成实拍质量审核分片004：11页覆盖44张/6来源组，21张非拼图候选逐文件回看原分辨率；23张拼图/页面排版、9张裁断/遮挡/仅局部甲面和3张模糊低清排除，9张仅保留为待标注候选。终结器44/44通过，分片001—004累计187张、81张待标注、106张排除；待标注项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`。专项1/1、ESLint、386文件编码审计和diff检查通过，完成度审计109标记/97 PASS、2/10门并按预期HOLD；正式训练集、生产manifest不变，素材不入Git，未提交或推送Git | 分片004、拼图排除、模糊排除、残缺甲面、源图硬门、训练隔离 |
| 2026-07-16 | v1.1.96 | 完成实拍质量审核分片003：12页覆盖48张/13来源组并逐文件回看原分辨率，7张模糊/低清、7张裁断/遮挡/仅局部甲面、13张拼图和2张护肤品主体图排除，19张仅保留为待标注候选。终结器48/48通过，分片001—003累计143张、72张待标注、71张排除；待标注项继续固定`trainingUse=prohibited`、`annotationTruthStatus=not-started`。专项1/1、ESLint、386文件编码审计和diff检查通过，完成度审计108标记/96 PASS、2/10门并按预期HOLD；正式训练集、生产manifest和HOLD不变，素材不入Git，未提交或推送Git | 分片003、模糊排除、残缺甲面、拼图排除、源图硬门、训练隔离 |
| 2026-07-16 | v1.1.95 | 按严格训练标准完成实拍质量审核分片002：12页覆盖47张，27张单图逐文件回看原分辨率；2张模糊、1张甲面仅局部露出、2张非上手甲片和18张截图/拼图排除，24张仅保留为待标注候选。新增持久规则：模糊、裁断、残缺或仅局部甲面源图及派生物禁止训练；源图通过不解除`trainingUse=prohibited`，须待完整mask原分辨率验收。分片001—002累计95张、53张待标注、42张排除。专项1/1、ESLint、386文件编码审计和diff检查通过；前序全量394/394及Next.js生产构建保持通过，完成度审计107标记/95 PASS、2/10门并按预期HOLD。正式训练集、生产manifest和HOLD不变，素材不入Git，未提交或推送Git | 模糊排除、残缺甲面、源图硬门、训练隔离、原分辨率审核 |
| 2026-07-16 | v1.1.94 | 完成2026_7_14实拍质量审核分片001的源图筛选：新增审核页构建器和分片终结器，12页覆盖48张并绑定页哈希；联系表预筛后逐张回看原分辨率，29张确认完整甲面均在画面内并保留为待标注候选，19张教程图/拼图/非单张实拍排除。终结器强制48/48决策覆盖，且固定保留项`trainingUse=prohibited`、`annotationTruthStatus=not-started`，源图通过不冒充mask真值。全量394/394、ESLint、Next.js生产构建、386文件编码审计和diff检查通过；完成度审计106标记/94 PASS、2/10门并按预期HOLD。正式训练集、生产manifest和HOLD不变，素材不入Git，未提交或推送Git | 源图筛选、原分辨率审核、审核页哈希、标注候选、真值隔离 |
| 2026-07-16 | v1.1.93 | 建立近重复归并后的逐图质量审核队列：新增`build-real-material-quality-review-queue.py`，绑定原审核工作区和近重复终结报告哈希，严格扣除105张已排除候选；剩余1166张/193来源组生成26个来源组原子分片，最大50张，空审核字段不构成通过且素材不复制。专项1/1通过；正式训练集、生产manifest、`trainingUse=prohibited`和HOLD结论不变，未提交或推送Git | 质量审核队列、来源组原子分片、去重排除、原分辨率审核、素材隔离 |
| 2026-07-16 | v1.1.92 | 落地2026_7_14实拍批次A授权与近重复视觉审核。目录漂移使旧1277张清单安全拒绝，按当前1271张/196来源组重建盘点、intake和A授权；外部工作区生成28个来源组原子分片。新增近重复联系表构建器与审核终结器，20页覆盖156对并绑定页面哈希；视觉确认86对跨历史语料重复、14对批内重复、52对含非照片甲型模板、4对相关但不重复，最终排除105张并保留1166张进入逐图完整甲面审核。专项2/2、全量391/391、Python编译、ESLint、Next.js生产构建、380文件编码审计和diff检查通过；完成度审计104标记/92 PASS、2/10门并按预期HOLD。素材不入Git、所有未完成逐图审核的条目继续`trainingUse=prohibited`，正式训练集、生产manifest与HOLD不变，未提交或推送Git | A授权、目录漂移、近重复视觉审核、非照片排除、来源组隔离、素材不入Git |
| 2026-07-16 | v1.1.91 | 建立授权实拍候选原分辨率审核工作区：新增`build-real-material-review-workspace.py`，仅接受已确认A/B授权，复验授权清单、原候选intake和当前图片SHA-256；生成逐图全覆盖聚合CSV及来源组原子分片，记录逐分片/聚合哈希，大来源组可超过目标大小但不得拆组。审核状态、完整露出甲数、完整mask数、问题码、角色和备注初始为空，空字段明确不构成通过；工作区不复制图片。工作区/互斥分配专项6/6、全量389/389、Python编译、ESLint、Next.js生产构建、376文件编码审计和diff检查通过；完成度审计102标记/89 PASS、2/10门并按预期HOLD。当前仅fixture验证，未替用户授权、未处理真实素材，生产数据和HOLD不变，未提交或推送Git | 审核工作区、来源组分片、原分辨率审核、哈希复现、素材隔离 |
| 2026-07-16 | v1.1.90 | 建立授权后逐图审核与用途互斥分配审计：新增`audit-real-material-exclusive-assignment.py`，复验授权清单、原候选intake、条目聚合与当前图片SHA-256；A/B强制pass/exclude最终审核全覆盖，A可按完整来源组分配train/val/独立发布测试，B仅允许独立发布测试，C可直接归档。同一来源组跨角色、rework、漏审、越权角色或证据漂移均拒绝；val仍须独立真值审核。分配/授权专项6/6、全量387/387、Python编译、ESLint、Next.js生产构建、374文件编码审计和diff检查通过；完成度审计101标记/88 PASS、2/10门并按预期HOLD。当前仅完成工具和fixture审核，未替用户授权、未生成真实分配、未读取或复制真实素材，生产数据和HOLD不变，未提交或推送Git | 逐图审核、来源组原子性、用途互斥、测试泄漏防护、授权边界 |
| 2026-07-16 | v1.1.89 | 建立2026_7_14实拍候选A/B/C授权决策登记契约：新增`authorize-real-material-candidate-intake.py`，绑定候选intake、逐图图片与聚合条目SHA-256，映射商业训练+发布测试+回归、仅发布测试+回归、仅存档三种用途。A只授予完整视觉审核和来源隔离后的训练资格，未审核条目继续`trainingUse=prohibited`；训练与独立发布测试必须按来源组互斥分配，图片漂移时拒绝。授权专项4/4、全量383/383、Python编译、ESLint、Next.js生产构建、372文件编码审计和diff检查通过；完成度审计100标记/87 PASS、2/10门并按预期HOLD。当前未替用户选择、未生成正式授权清单、未读取或复制素材，生产数据与HOLD不变，未提交或推送Git | 素材授权、哈希证据、未审核隔离、来源组互斥、训练边界 |
| 2026-07-16 | v1.1.88 | 将候选训练证据门接入训练发布编排器：`run-training-release-pipeline.ts`新增`--candidate-mode/--candidate-validation-report`，候选模式缺报告立即失败，并将证据原样下传`train-yolo-seg.py`；流水线报告记录`trainingIntent`和证据路径。新增专项确认默认实验语义、缺报告拒绝和被拒绝证据在train步骤停止，后续评估/导出/治理不运行。流水线专项16/16、全量381/381、ESLint、Next.js生产构建、370文件编码审计与diff检查通过；完成度审计99标记/86 PASS、2/10门并按预期HOLD。生产manifest、正式数据、模型HOLD与授权边界不变，未提交或推送Git | 训练编排、候选证据、失败前置、发布阻断 |
| 2026-07-16 | v1.1.87 | 建立候选训练验证硬门：新增`audit-dataset-source-isolation.py`逐文件绑定dataset、sources.csv和split并统计跨split来源；新增`audit-candidate-training-validation.py`要求val-only来源组、至少30图、全量原分辨率审核通过、dataset/来源/审核/逐标签哈希一致、polygon合法且零交叠。`train-yolo-seg.py`增加`--candidate-mode/--candidate-validation-report`，在模型加载前复验通过决定、dataset及上游报告哈希和几何计数；默认运行明确记录`training_intent=experiment`。正式409图集实跑被正确拒绝：AI组跨train/val/test=210/45/45、缺46/46视觉审核且234个val mask有5处交叠，v10候选dry-run被拦截。生成`M2-T6-CANDIDATE-TRAINING-VALIDATION-GATE` PASS（当前正式集被拒绝）；专项5/5、全量380/380、Python编译、ESLint、Next.js生产构建、370文件编码审计和diff检查通过，完成度审计98标记/85 PASS、2/10门并按预期HOLD。未训练、未改生产manifest、未使用冻结或未授权素材，未提交或推送Git | 候选训练、来源隔离、视觉真值、哈希链、GPU前置门、发布阻断 |
| 2026-07-16 | v1.1.86 | 完成下一真实候选训练可行性预检：核对RTX 4060 Laptop 8GB、v6/v9权重、正式409图/2142 mask release readiness和实际训练入口。正式val 46图/234 mask扫描发现5处polygon交叠，来源统计又确认300张AI图的同一`ai-nail-2026-07-04`组跨train/val/test=210/45/45，故该val不能充当来源隔离模型选择或阈值真值；现有授权真实增量已在v7–v9使用且连续退化。生成`M2-T6-NEXT-CANDIDATE-PREFLIGHT` PASS（等待训练授权）；完成度审计97标记/84 PASS、2/10门并按预期HOLD，366文件编码审计和diff检查通过。未启动缺乏数据依据的v10，未读取冻结测试真值训练，也未使用`真实素材/2026_7_14`未授权素材。模型接口、生产manifest和HOLD不变，未提交或推送Git | 训练预检、数据来源隔离、验证真值、授权边界、模型质量阻断 |
| 2026-07-16 | v1.1.85 | 将验证真值视觉审核资格接入`calibrate-model-score-threshold.py`：新增`--truth-audit`，正式阈值只接受`approved_as_calibration_truth`，并校验dataset路径/SHA-256、逐标签SHA-256、expected/reviewed/pass全覆盖和rework/exclude为0；缺审核或`rejected_as_calibration_truth`分别输出未审核/已拒绝诊断，保持`manifestScoreThreshold=null`。新增2项专项覆盖未审核和显式拒绝；v6旧val带v1.1.84拒绝报告复跑输出`diagnostic_only_validation_truth_rejected`、`calibrationEligible=false`，0.20继续仅为历史诊断。生成`M2-T6-VAL-TRUTH-AUDIT-CONTRACT` PASS；校准专项6/6、全量375/375、Python编译、ESLint、生产构建、366文件编码审计通过，完成度审计96标记/83 PASS、2/10门并按预期HOLD；生产阈值、正式训练集与v6拒绝状态不变，未提交或推送Git | 阈值校准、视觉真值门、哈希绑定、模型评估、发布阻断 |
| 2026-07-16 | v1.1.84 | 对v6旧来源隔离val执行真值闭环：新增`build-validation-topology-repair-candidates.py`，绑定dataset/source report/calibration哈希，只读取val并把14个无效polygon写入隔离候选，源标签哈希不变；生成13张整图与14组逐甲2×审核证据，并由`audit-validation-truth-review.py`强制13/13覆盖。原分辨率审核仅3张通过、7张返修、3张排除，发现2张未声明交叠及漏甲、背景/雕塑误标、重复mask、皮肤污染、边缘裁断和域外空标签，正式输出`rejected_as_calibration_truth`。此前0.9376/0.9420 val mAP和0.20诊断阈值降级为不合格真值上的历史诊断，不得用于模型选择或manifest；生产阈值、正式训练集与v6拒绝状态不变。生成`M2-T6-V6-VAL-TRUTH-AUDIT` PASS（拒绝旧val真值）；专项5/5、全量373/373、Python编译、ESLint、生产构建、366文件编码审计通过，完成度审计95标记/82 PASS、2/10门、HOLD；本轮未提交或推送Git | 验证真值、原分辨率审核、拓扑隔离、阈值校准、模型评估、发布阻断 |
| 2026-07-16 | v1.1.83 | 建立来源隔离验证集专用阈值校准门：新增共享实例分割匹配内核与`calibrate-model-score-threshold.py`，绑定数据集/来源报告/指标/预测/权重SHA-256，硬拒绝test/release-test调参、val来源跨split和未知预测；少于30图、真值polygon需修复或召回/误检/候选数不合格时不输出manifest阈值。v6在来源组`more`的13张/45 mask val上部署512 box/mask mAP50=0.9376/0.9420；诊断最优confidence=0.20时40匹配、5漏检、2误检、F1=0.9195，但14个真值需拓扑修复且13<30，故`calibrationEligible=false`、`manifestScoreThreshold=null`。生成`M2-T6-V6-VAL-THRESHOLD-CALIBRATION` PASS（拒绝写入manifest）；专项6/6、全量368/368、Python编译、ESLint、生产构建、362文件编码审计通过；完成度审计94标记/81 PASS、2/10门、HOLD。生产manifest、v6拒绝和正式训练集不变，未提交或推送Git | 阈值校准、验证集隔离、测试泄漏防护、真值拓扑、模型评估、发布阻断 |
| 2026-07-16 | v1.1.82 | 将模型版本级候选置信度阈值落成完整manifest契约：`NailTextureModelManifest/Info`增加可选`scoreThreshold`，运行时对缺省值明确落为0.35并把同一阈值传入原始候选与质量排序两道过滤；显式值统一要求为0和1之间的有限数。`export-onnx.py --score-threshold`、浏览器manifest校验及`verify-model-artifact.ts`同步约束；0.30候选在模型阈值0.25下识别成功，修复第二道固定0.35导致的假配置。新增`M1-T2-SCORE-THRESHOLD` PASS标记；专项35/35、全量364/364、Python编译、ESLint、生产构建、359文件编码审计通过。完成度审计93标记/80 PASS、2/10门、HOLD；本次未把0.25写入生产manifest，v6拒绝、正式训练集和发布阻断均不变，未提交或推送Git | 模型manifest、阈值校准、后处理一致性、ONNX导出、制品验证、向后兼容、发布阻断 |
| 2026-07-16 | v1.1.81 | 新增冻结67张部署阈值逐图失败画像：confidence=0.35、mask IoU=0.50下384个真值匹配289个，漏检95、误检57、弱形状匹配76，核心/压力召回0.7761/0.6983；0.20—0.45扫描显示0.25压力召回0.7845但误检增至90，未提前改浏览器默认值。审核15张最高风险原分辨率叠加图，确认透明相邻长甲、多甲同屏、低对比漏整甲/局部识别及手指/腕表误检；冻结图片、标签、裁剪和父来源组继续禁止训练。新增2项专项测试和PASS标记；完成度审计92标记/79 PASS、2/10门、HOLD。全量364/364、Python编译、ESLint、生产构建、359文件编码审计及diff检查通过；生产manifest及正式训练集不变 | 模型错误分析、部署阈值、实例匹配、原分辨率审核、测试集隔离、训练优先级、发布阻断 |
| 2026-07-16 | v1.1.80 | 完成冻结67张发布测试的来源隔离物化与v6部署质量复评：67图/384 mask/18父组及逐文件哈希复算通过，与409张正式训练图的来源组和图片SHA-256重叠均为0；512全量box/mask mAP50=0.8370/0.8313，核心45张=0.8485/0.8523，压力22张=0.8179/0.7919，压力组退化触发拒绝。640全量诊断0.8570/0.8549不覆盖部署口径。新增评估物化器、正式质量报告构建器和4项专项测试；完成度审计改用67张质量证据并增加模型退化阻断，当前91标记/78 PASS、2/10门、HOLD。专项4/4、全量362/362、Python编译、ESLint、Next.js生产构建、357文件编码审计及diff检查通过。生产manifest、正式训练集和浏览器接口不变；未提交或推送Git | 发布测试评估、来源隔离、部署质量门、压力样本、候选拒绝、完成度审计、发布阻断 |
| 2026-07-16 | v1.1.79 | 完成受审核发布测试候选冻结：冻结门先纠正030的关节假阳性，将核心统计由269更正为268 mask；新增声明式拓扑返修器，对5张核心与8张压力图共82个mask修复无效polygon/真实遮挡交叠，13张整图及显著变更逐甲2×原分辨率审核通过，最终67张/384 mask、0返修、25排除。冻结快照含45张核心、22张压力、18个父来源组，67个图片/标注/联合哈希及清单聚合SHA-256独立复算0错误，训练用途固定prohibited；代表性门67/100、仍缺33张，v6质量指标仍只对应历史13张/102 mask。完成度审计识别冻结规模证据但保持3/10门与HOLD；新增标记后90标记/77 PASS。拓扑派生标注与冻结标注目录加入Git忽略，紧凑清单/报告仍可审计。专项7/7、全量359/359、Python编译、ESLint、Next.js生产构建、353文件编码审计及diff检查通过；未提交或推送Git | 发布测试冻结、拓扑合法性、零交叠、原分辨率复核、哈希可复现性、Git素材隔离、完成度审计、发布阻断 |
| 2026-07-16 | v1.1.78 | 只读复核 GitHub 贡献图延迟：本地 HEAD `2e9e208` 与远端默认分支完全同步，GitHub 仓库接口确认仓库为 public、非 fork、默认分支为 `JiaRu_让每一次抬手都遇见未来`，且最新提交的 author/committer 均已归属账号 `yaoyinyu`。本地默认分支按作者日期统计 7 月共118次提交，而截图仍显示此前的70次，当前证据排除未推送、错误分支、fork和邮箱未归属，符合 GitHub 最长约24小时的贡献索引刷新延迟；不通过空提交、重复推送或历史重写强制刷新。本轮未改变运行接口、模型状态、数据集状态或生产HOLD结论 | GitHub贡献归属、异步刷新、仓库治理 |
| 2026-07-16 | v1.1.77 | 完成发布测试第三十四轮暨压力返修队列清零：新增混合人工polygon构建器，按清单保留10个已审polygon并替换10个局部/无效/皮肤污染polygon，强制原图尺寸/来源组、坐标、多边形合法性和零交叠门，并生成整图及逐甲原图/overlay 2×放大证据与真实外接框提示。f075/d970/d951/6d9a最终4张/20 mask全部合法、几何20 pass/0 suspect/0 missing、零交叠并通过放大视觉复核。压力集更新为22张/116 mask通过、0返修、13排除；92父图为67张/385 mask暂通过、0返修、25排除。新增专项2/2、全量355/355、ESLint、生产构建、349文件编码审计及diff检查通过；完成度审计89标记/76 PASS、3/10门并继续HOLD。正式409图/2142 mask、生产manifest及模型接口不变 | 混合人工多边形、合法性、零交叠、逐甲2×复核、返修清零、发布阻断 |
| 2026-07-16 | v1.1.76 | 完成发布测试第三十三轮SAM单甲返修与透明相邻长甲人工多边形闭环：b1184仅重建黑甲，4/4完成、0 fallback、几何4 pass/0 suspect且零交叠，甲根指腹污染消失；eac9的v25虽9/9几何通过但视觉门拒绝皮肤/邻指合并，随后原分辨率人工绘制9甲并通过9 pass/0 suspect、合法性、零交叠及三处放大视觉复核。原分辨率接受2张/13完整mask。压力集更新为18张/96 mask通过、4返修、13排除；92父图为63张/365 mask暂通过、4返修、25排除。固化SAM持续失败时人工多边形仍须完整几何/交叠/放大视觉门的行为规则。全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计88标记/75 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | 单甲fallback、透明相邻长甲、人工多边形、几何审计、零交叠、放大视觉门、发布阻断 |
| 2026-07-16 | v1.1.75 | 完成发布测试第三十二轮三组重复/局部mask与漏小指返修：f8a/2c79各5提示一次收敛；2236经v18—v23把无名指/小指polygon相交从71.39像素降至0，并通过放大审核补齐水钻相邻透明拇指甲根、拒绝皮肤吸收中间态。三张最终均0 fallback、几何15 pass/0 suspect、polygon无相交，原分辨率接受3张/15完整mask。压力集更新为16张/83 mask通过、6返修、13排除；92父图为61张/352 mask暂通过、6返修、25排除。全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计87标记/74 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | 重复mask、透明甲根、立体装饰、漏小指、polygon交叠、放大视觉审核、发布阻断 |
| 2026-07-16 | v1.1.74 | 完成发布测试第三十一轮局部甲面/皮肤污染复核与第三批边缘裁切清退：6d9a/d951各5提示均0 fallback、几何5 pass/0 suspect且polygon无相交；原分辨率分别发现透明/白色甲尖与粉色甲根遗漏，以及拇指皮肤污染和小拇指漏甲，均继续返修。02f顶部必需甲面及6d83最右甲根触边裁断转排除，0张/0 mask误提升。压力集为13张/68 mask通过、9返修、13排除；92父图为58张/337 mask暂通过、9返修、25排除。全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计86标记/73 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | 局部甲面、透明甲尖、皮肤污染、漏甲、边缘裁切、视觉门、发布阻断 |
| 2026-07-16 | v1.1.73 | 完成发布测试第三十轮交叠甲/指腹污染复跑与第二批边缘裁切清退：d970四轮、f075一轮各5提示均0 fallback、几何5 pass/0 suspect；d970相邻polygon相交面积由约700像素降为0，但横向甲仍在指腹污染与只覆盖蓝色前段之间未收敛，f075横向甲仍吸收指腹，均继续返修。6df0/424a/a4a4/b548/cf0c因必需甲面触边裁断转排除，0张/0 mask误提升。压力集为13张/68 mask通过、11返修、11排除；92父图为58张/337 mask暂通过、11返修、23排除。全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计85标记/72 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | 交叠甲、指腹污染、局部甲面、边缘裁切、原分辨率视觉门、发布阻断 |
| 2026-07-16 | v1.1.72 | 完成发布测试第二十九轮压力返修图边缘裁切清退：初筛20张返修图，对e0ee/c0e0各运行5个SAM2.1 large多点提示，均0 fallback、几何5 pass/0 suspect，但原分辨率审核因边缘甲面不完整及缎带/皮肤污染全部拒绝；连同406b/9da2共4张从返修改为排除，0张/0 mask误提升。压力集更新为13张/68 mask通过、16返修、6排除；92父图为58张/337 mask暂通过、16返修、18排除。全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计84标记/71 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | 边缘裁切、几何假阳性、原分辨率视觉门、压力队列清理、发布阻断 |
| 2026-07-16 | v1.1.71 | 完成发布测试第二十八轮SAM2.1 large皮肤污染返修：86ac/956d/b1184共3张/14提示全部生成、0 fallback，几何13 pass/1 suspect；原分辨率只接受86ac/956d的2张/10 mask，b1184因甲根皮肤继续返修。v5/v6定位b1184提示2/3初始均返回0 mask并进入box-only fallback；辅助标注执行器新增逐文件/提示序号/模式/初始mask数明细及多mask正负点选择诊断。压力集更新为13张/68 mask通过、20返修、2排除；92父图为58张/337 mask暂通过、20返修、14排除。专项2/2、全量353/353、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计83标记/70 PASS、3/10门并继续HOLD。正式409图/2142 mask及模型接口不变 | SAM2.1 large、皮肤污染、fallback诊断、多mask选择、原分辨率视觉门、发布阻断 |
| 2026-07-16 | v1.1.70 | 只读复核最新GitHub贡献统计：截图已显示过去一年227次贡献及2026年7月JiaRu的70个提交，证明此前提交已进入活动汇总；本地HEAD、远端跟踪分支与GitHub默认分支均为`a9f5006`，默认分支为`JiaRu_让每一次抬手都遇见未来`，仓库为私有且非Fork。最新提交作者/提交者均被GitHub归属账号`yaoyinyu`，作者日期与提交日期同为2026-07-16 01:00（GMT+8），邮箱为`3181484805@qq.com`；但只读GraphQL贡献日历仍返回7月13日29次、7月14—16日0次。结合7月14—16日本地共有34个符合日期的提交及GitHub官方最长24小时刷新规则，结论仍为新一批提交尚待贡献索引刷新，不需要改邮箱、重写历史或重复推送。本轮未读取Cookie、未修改Git/GitHub设置、未提交或推送；运行接口、模型状态和生产HOLD不变 | GitHub贡献索引、默认分支、提交归属、仓库治理、隐私边界、无接口变更 |
| 2026-07-16 | v1.1.69 | 完成发布测试第二十七轮暨压力错误区域重提取v3：007/037/094/095从父截图重取完整主照片，4/4父哈希、派生哈希和稳定来源组通过，v3聚合保持35父图/35派生。SAM2完成4张/19提示、0 fallback、几何19 pass/0 suspect；原分辨率只接受7a92的1张/5 mask，其余3张因皮肤外溢继续返修。压力集更新为11张/58 mask通过、22返修、2排除；父图为56张/327 mask暂通过、22返修、14排除、17个来源组。正式训练集、模型接口和生产HOLD不变 | 区域重提取、父图稳定分组、完整甲面、皮肤污染、视觉门禁、发布阻断 |
| 2026-07-16 | v1.1.68 | 登记2026_7_14新增1277张实拍候选：1277/1277可解码，196个来源组，批内0精确重复/70对近重复，跨1053张参照0精确重复/86对近重复；新增候选intake构建器并强制授权待确认、训练禁用，14页全量联系表只作分布抽查。SAM2.1 large对eac9的box/多点对照均未通过原分辨率完整甲面门，继续返修。全量测试352/352、ESLint、生产构建、347文件编码审计及diff检查通过；完成度审计81标记/68 PASS、3/10 HOLD。正式409图/2142 mask、55张/322 mask发布测试暂通过量及生产HOLD不变 | 新增实拍候选、来源分组、授权隔离、去重、原分辨率视觉门、大模型候选拒绝、发布阻断 |
| 2026-07-14 | v1.1.67 | 新增 AI 生图风格提示词库：src/lib/ai-style-prompts.ts 包含 10 个风格各 50 段独立中文场景提示词；/ai-generate 页面风格按钮改为轮转填入提示词。ESLint、Next.js 生产构建通过 | AI 生图前端 |
| 2026-07-14 | v1.1.66 | 完成发布测试第二十六轮暨压力错误区域重提取：4个父截图重新框定主照片，移除3处相邻拼图半甲；新增区域替换合并器，4/4父哈希、派生哈希和稳定来源组通过，35图聚合保持一父一派生。SAM2完成4张/27提示、1 fallback、0错误，几何22 pass/5 suspect；原分辨率接受f8c5、bc6b、c541共3张/18 mask，eac9相邻透明长甲仍合并皮肤/邻指而继续返修。压力集更新为10张/53 mask通过、23返修、2排除，父图为55张/322 mask暂通过、23返修、14排除、17个来源组。专项12/12、全量350/350、ESLint、Next.js生产构建和344文件编码审计通过；完成度审计78标记/66 PASS、3/10 HOLD，因预期外部阻断退出1。AGENTS同步固化区域替换来源规则与“未经当前任务明确要求不提交/推送Git”。正式模型接口和生产HOLD不变 | 区域重提取、来源链、透明长甲、视觉门禁、Git行为规则、发布阻断 |
| 2026-07-14 | v1.1.65 | 完成发布测试第二十五轮暨压力派生图第二批返修：新增可复现SAM提示几何审计脚本并逐行复现上一批15/15结果；0662两次收紧袖口相邻甲，d17a确认相邻多边形交集为0，最终SAM2 10/10、0 fallback、几何10 pass/0 suspect，原分辨率接受2张/10 mask。0c2b与6be4因父主照片本身裁断必需甲面排除；4个首轮选错局部区域项保留重提取而未误排。压力集为7张/35 mask通过、26返修、2排除，父图为52张/304 mask暂通过、26返修、14排除。专项9/9、全量348/348、ESLint、Next.js生产构建和342文件编码审计通过；完成度审计77标记/65 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 几何审计脚本、压力集返修、源图裁断、区域重提取、发布阻断 |
| 2026-07-14 | v1.1.64 | 完成发布测试第二十四轮暨压力派生图首批返修：3e9b/51a2/e826保留11个完整mask，删除1个黑背景误检并补齐4个漏甲；首跑几何15/15通过但视觉门拒绝皮肤/白布污染，三次收紧复跑后SAM2完成15/15、0 fallback、几何15 pass/0 suspect，原分辨率接受3张/15 mask。压力集更新为5张/25 mask通过、30返修、0排除；父图汇总为50张/294 mask暂通过、30张返修、12张排除、16个来源组。专项7/7、全量346/346、ESLint、Next.js生产构建和340文件编码审计通过；完成度审计76标记/64 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 压力集返修、漏甲、背景误检、皮肤/白布污染、发布阻断 |
| 2026-07-14 | v1.1.63 | 定位Windows反复弹出“选择应用打开npm”的根因：裸`npm`首先命中`C:\Windows\System32\npm`零字节无扩展名文件，而有效Node.js命令位于`C:\Program Files\nodejs\npm.cmd`；Node.js v24.16.0与npm 11.13.0安装正常，无需重装。将Windows项目命令统一为`npm.cmd`或直接`node`并写入AGENTS行为规则；未删除或修改系统文件，接口、模型状态和生产HOLD不变 | Windows命令解析、npm.cmd、开发环境、行为规则 |
| 2026-07-14 | v1.1.62 | 完成发布测试第二十三轮双手10甲与手掌/腕表误检清理：076保留9个完整mask，删除1个手掌和2个腕表误检，仅重建上方拇指；SAM2完成10/10、0 fallback、几何9 pass/1 suspect，原分辨率确认10甲完整且suspect仅为斜向拇指提示中心关系，接受1张/10 mask。核心集更新为45张/269 mask通过、0返修、12排除，父图汇总为47张/279 mask暂通过、33张返修、12张排除、14个来源组；专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计75标记/63 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 双手完整甲面、手掌/腕表误检、核心队列清零、发布阻断 |
| 2026-07-14 | v1.1.61 | 用户确认Chrome已打开后再次尝试只读复核GitHub贡献页；Chrome控制运行时在标签页发现前连续两次因`Cannot redefine property: process`初始化失败，未连接、读取或操作任何页面，也未读取Cookie、密码、浏览器存储或修改账号设置。本轮没有新增网页证据，继续沿用v1.1.58的GitHub提交归属已确认、贡献索引等待刷新结论；接口、模型状态和生产HOLD不变 | Chrome连接诊断、GitHub贡献复核、隐私边界、无接口变更 |
| 2026-07-14 | v1.1.60 | 完成发布测试第二十二轮低对比紫色甲与白色摆件分离返修：047保留8个完整mask，仅重建最左紫色甲；SAM2完成9/9、0 fallback、几何9 pass/0 suspect，原分辨率并排复核确认完整甲面且无摆件污染，接受1张/9 mask。父图汇总更新为46张/269 mask暂通过、34张返修、12张排除、14个来源组；专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计74标记/62 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 低对比甲面、摆件污染、原分辨率审核、发布阻断 |
| 2026-07-14 | v1.1.59 | 完成发布测试第二十一轮交叠甲与拇指皮肤污染返修：072保留7个完整mask，重建中部两枚交叠长甲与前景蝴蝶拇指；首跑几何10/10通过但视觉门拒绝拇指下缘皮肤污染，收紧复跑后SAM2完成10/10、0 fallback、几何10 pass/0 suspect，原分辨率接受1张/10 mask。父图汇总更新为45张/260 mask暂通过、35张返修、12张排除、14个来源组；专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计73标记/61 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 交叠甲面、拇指皮肤污染、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.58 | 第三次复核GitHub贡献统计：远端最新提交`5e7ff29`已与本地一致并位于默认分支`JiaRu_让每一次抬手都遇见未来`；通过本机Git凭据发起只读GitHub REST/GraphQL查询，确认仓库为私有且非Fork、提交作者与提交者均已归属账号`yaoyinyu`、提交邮箱为`3181484805@qq.com`。GitHub贡献接口仍返回7月13日29次、7月14日0次，结合官方“符合条件的提交最多等待24小时显示”规则，当前结论为贡献索引刷新滞后，无需重写历史、改邮箱或重复推送。未读取Cookie、未修改GitHub/Git设置；接口、模型状态和生产HOLD不变 | GitHub贡献索引、私有仓库、账号归属、仓库治理、隐私边界 |
| 2026-07-14 | v1.1.57 | 完成发布测试第二十轮漏甲与重复mask联合返修：052保留3个完整甲面，将黑色蝴蝶结甲的两个重叠候选合并重建为单一完整mask，并补齐首轮漏标拇指；SAM2完成5/5、0 fallback，几何5 pass/0 suspect，原分辨率接受1张/5 mask。父图汇总更新为44张/250 mask暂通过、36张返修、12张排除、14个来源组；专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计72标记/60 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 漏甲、重复mask、蝴蝶结装饰、法式拇指、发布阻断 |
| 2026-07-14 | v1.1.56 | 完成发布测试第十九轮透明拇指牛仔布/皮肤污染定点返修：065保留4个完整手指甲面，以覆盖有色甲面和透明甲尖的轴向正点及密集污染区负点重建拇指；SAM2完成5/5、0 fallback，几何5 pass/0 suspect，原分辨率接受1张/5 mask。父图汇总更新为43张/245 mask暂通过、37张返修、12张排除、14个来源组；专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计71标记/59 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 透明延长甲、牛仔布污染、皮肤污染、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.55 | 完成发布测试第十八轮拇指皮肤污染定点返修：026保留4个完整手指甲面，以完整轴向正点和密集皮肤负点重建拇指；SAM2完成5/5、0 fallback，几何5 pass/0 suspect，原分辨率接受1张/5 mask。父图汇总更新为42张/240 mask暂通过、38张返修、12张排除、13个来源组；记录返修清单提示序号从1开始的持久规则。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计70标记/58 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 拇指、皮肤污染、提示序号、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.54 | 完成发布测试第十七轮长甲甲根皮肤污染定点返修：022保留4个完整甲面，右上长甲首次几何通过但视觉门拒绝甲根皮肤外溢，收紧后SAM2完成5/5、0 fallback，几何5 pass/0 suspect，原分辨率接受1张/5 mask。父图汇总更新为41张/235 mask暂通过、39张返修、12张排除、13个来源组；正式模型接口和生产HOLD不变。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计69标记/57 PASS、3/10 HOLD | 长甲、甲根皮肤污染、链饰甲面、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.53 | 完成发布测试第十六轮深色拇指皮肤污染定点返修：004保留4个完整甲面并收紧重建拇指，SAM2完成5/5、0 fallback，几何5 pass/0 suspect；原分辨率接受1张/5 mask。父图汇总更新为40张/230 mask暂通过、40张返修、12张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计68标记/56 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 深色甲、拇指皮肤污染、局部提示继承、视觉门禁、发布阻断 |
| 2026-07-14 | v1.1.52 | 完成发布测试第十五轮低对比污染返修与遮挡源图清退：001/047共2张/14提示SAM2完成、0 fallback，几何14 pass/0 suspect；原分辨率接受001的1张/5 mask，047因最左低对比甲仍吸收白色摆件继续返修；081因左边界裁断、083因背景手甲面被前景手与袖口遮挡转为排除。父图汇总更新为39张/225 mask暂通过、41张返修、12张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计67标记/55 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 深色甲、低对比甲、摆件污染、源图裁断、遮挡清退、发布阻断 |
| 2026-07-14 | v1.1.51 | 完成发布测试第十四轮双手10甲完整重建：078以10个完整轴向多点提示完成、0 fallback，几何10 pass/0 suspect；原分辨率确认两枚蝴蝶结甲完整合并、下手拇指补齐，接受1张/10 mask；069因左侧长甲尖被图片边界裁断转为排除。父图汇总更新为38张/220 mask暂通过、44张返修、10张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计66标记/54 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 双手10甲、立体装饰、漏甲补齐、源图裁断、发布阻断 |
| 2026-07-14 | v1.1.50 | 二次复核GitHub贡献统计：提交页已明确显示`f15b306`由账号`yaoyinyu`于2026-07-14 03:59 GMT+8提交，证明推送、默认分支和账号归属正常；同一时刻个人主页仍停留在7月70个提交、7月14日0贡献，因此纠正v1.1.48将0贡献直接归因于UTC日期的判断，当前证据指向GitHub贡献统计刷新滞后。未读取Cookie、未修改GitHub或Git设置 | GitHub贡献刷新、证据纠正、仓库治理、隐私边界 |
| 2026-07-14 | v1.1.49 | 完成发布测试第十三轮低对比单手甲返修与源图边界复核：080/091共2张/10提示SAM2完成、0 fallback，几何10 pass/0 suspect；原分辨率接受080的1张/5 mask，091因右侧小拇指甲被图片边界裁断转为排除。父图汇总更新为37张/210 mask暂通过、46张返修、9张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计65标记/53 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 低对比甲、拇指皮肤污染、源图裁断、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.48 | 复核用户已登录的 Chrome GitHub 主页：账号 `yaoyinyu` 登录正常，贡献图已显示过去一年227次贡献、7月13日29次贡献，7月活动已归集 `yaoyinyu/JiaRu` 70个提交；本地最近提交均使用 `YaoYinyu <3181484805@qq.com>`。当时7月14日格子仍为0，后续v1.1.50以GitHub提交页证据确认这是统计刷新滞后，不能直接归因于UTC日期。未读取Cookie、未改动GitHub设置、Git配置、接口或模型状态，生产HOLD不变 | GitHub登录态、贡献统计、仓库治理、隐私边界 |
| 2026-07-14 | v1.1.47 | 完成发布测试第十二轮低对比裸色/透明甲返修：065/071共2张/10提示SAM2完成、0 fallback，几何9 pass/1 suspect；原分辨率仅接受071的1张/5 mask，065因拇指仍吸收牛仔布与皮肤继续返修。父图汇总更新为36张/205 mask暂通过、48张返修、8张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计64标记/52 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 低对比裸色甲、侧向透明拇指、衣物污染、几何与视觉分离、发布阻断 |
| 2026-07-14 | v1.1.46 | 完成发布测试第十一轮同源长甲返修：025/026共2张/10提示SAM2完成、0 fallback，几何10 pass/0 suspect；原分辨率仅接受025的1张/5 mask，026因拇指仍吸收矩形皮肤区域继续返修。父图汇总更新为35张/200 mask暂通过、49张返修、8张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计63标记/51 PASS、3/10 HOLD。正式模型接口和生产HOLD不变 | 同源长甲、多点SAM提示、几何与视觉分离、皮肤污染、发布阻断 |
| 2026-07-14 | v1.1.45 | 完成发布测试第十轮双手相邻长甲返修：073共1张/9提示SAM2完成、0 fallback，几何9 pass/0 suspect；原分辨率确认带钻白色延长段和下手相邻三甲均由单一完整mask覆盖且无皮肤污染，接受1张/9 mask。父图汇总更新为34张/195 mask暂通过、50张返修、8张排除、12个来源组。专项7/7、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计62标记/50 PASS、3/10 HOLD。正式模型与数据集接口无变化，生产HOLD不变 | 双手相邻甲、多点SAM提示、完整甲面、视觉门禁、发布阻断 |
| 2026-07-14 | v1.1.44 | 完成发布测试第九轮多点返修：024与075共2张/10提示SAM2完成、0 fallback，几何9 pass/1 suspect；原分辨率确认立体钻饰与低对比裸色甲面均由单一完整mask覆盖，接受2张/10 mask。父图汇总更新为33张/186 mask暂通过、51张返修、8张排除、12个来源组。专项8/8、全量346/346、ESLint、生产构建和340文件编码审计通过，完成度审计61标记/49 PASS、3/10 HOLD；同时登录Chrome确认私有贡献已启用，7月13日29次贡献和7月70次JiaRu提交已显示，纠正v1.1.43的未决原因判断 | 多点SAM提示、完整甲面、GitHub贡献日期、视觉门禁、发布阻断 |
| 2026-07-14 | v1.1.43 | 只读诊断 GitHub 贡献图未显示：最新提交已推送且位于远端默认分支 `JiaRu_让每一次抬手都遇见未来`，提交作者邮箱为 `3181484805@qq.com`；远端仓库对未认证公开 API 不可见，因此贡献图还取决于账号是否启用私有贡献展示、该邮箱是否已绑定验证，以及 GitHub 最长约24小时的刷新延迟。本轮未修改 Git 身份、提交历史、运行接口或模型状态 | GitHub 贡献归属、私有贡献可见性、仓库治理 |
| 2026-07-14 | v1.1.42 | 贯通逐甲多正点/多负点返修契约并完成透明延长甲验证：构建器保留/新增/校验正负点并记录来源，SAM2按动态点数生成标签；067以5提示完成、几何5 pass/0 suspect，原分辨率接受1张/5个完整mask。父图汇总更新为31张/176 mask暂通过、53张返修、8张排除、11个来源组。专项8/8、全量346/346、ESLint、生产构建和340文件编码审计通过；完成度审计仍为3/10、HOLD | 多点SAM提示、透明延长甲、返修来源、视觉门禁、发布阻断 |
| 2026-07-14 | v1.1.41 | 完成发布测试第七轮受审计返修：6张/40提示SAM2完成，几何38 pass/2 suspect，原分辨率0张/0 mask新增通过，4张继续返修、2张转排除；另按遮挡规则排除085与088。父图汇总保持30张/171 mask暂通过，更新为54张返修、8张排除、11个来源组。专项6/6、全量345/345、ESLint、构建和340文件编码审计通过；完成度审计仍为3/10、HOLD | 发布测试返修、完整甲面优先、遮挡源图排除、视觉门禁、发布阻断 |
| 2026-07-14 | v1.1.40 | 修复 AR 摄像头双层启动门控：移除页面外层 `isStarted` 与重复按钮，保留 `ArView` 内唯一入口，使一次点击直接触发权限请求；补充摄像头排障顺序。浏览器验证单按钮及一次点击状态转换通过，ESLint、345项测试、生产构建、340文件编码审计和文档差异检查通过；真实摄像头画面仍待用户设备验收 | AR 试戴、摄像头启动、使用方式、故障排查 |
| 2026-07-13 | v1.1.39 | 完成发布测试第六轮受审计返修：6张/31提示SAM2与几何审计通过，原分辨率仅接受3张/16 mask，3张继续返修；049按下边界裁断规则转为排除。父图汇总更新为30张/171 mask暂通过、58张返修、4张排除、11个来源组；将“完整露出甲面必须由单一完整mask覆盖”固化到AGENTS.md与审核策略。专项6/6、全量345/345、ESLint、构建和340文件编码审计通过；完成度审计仍为3/10、HOLD | 发布测试返修、完整甲面优先、源图完整性、视觉门禁、项目指令 |
| 2026-07-13 | v1.1.38 | 完成发布测试第五轮受审计返修：7张/37提示SAM2与几何审计通过，原分辨率仅接受3张/18 mask，4张继续返修；034与070按甲面边缘裁断规则转为排除。父图汇总更新为27张/155 mask暂通过、62张返修、3张排除、10个来源组；并将“日志中的可复用经验同步到AGENTS.md”、几何审计边界与裁断图排除规则固化为项目指令，生产HOLD不变 | 发布测试返修、负点提示、源图完整性、视觉门禁、项目指令 |
| 2026-07-13 | v1.1.37 | 完成发布测试第四轮受审计返修：6张/30提示SAM2与几何审计通过，原分辨率仅接受3张/15 mask，3张污染或甲面不完整项继续返修；父图汇总更新为24张/137 mask暂通过、67张返修、1张排除、10个来源组。正式集、生产候选和HOLD状态不变 | 发布测试返修、辅助标注、视觉门禁、审核聚合、发布门禁 |
| 2026-07-13 | v1.1.36 | 发布测试第三轮返修新增逐框SAM提示模式支持及非法模式守卫；5张/24提示SAM2、几何与原分辨率审核全部通过，父图汇总更新为21张/122 mask暂通过、70张返修、1张排除、9个来源组。候选仍禁止训练，代表性test、真机、失败案例与Beta门继续HOLD | 辅助标注、发布测试返修、来源隔离、审核聚合、发布门禁 |
| 2026-07-13 | v1.1.35 | 在发布测试v3阶段完成后，将本地与GitHub默认分支从`master`精确改名为`JiaRu_让每一次抬手都遇见未来`，推送新分支、切换远端默认分支并删除旧`master`；最终本地/远端均只保留新分支。该操作只改变Git分支治理，不改变运行时接口、模型状态、数据授权、审核计数或生产HOLD | Git分支治理、默认分支、文档一致性 |
| 2026-07-13 | v1.1.34 | 完成发布测试第二轮受审计返修：6张/29提示SAM2与几何审计通过，原分辨率仅接受2张/9 mask，4张皮肤污染项继续返修；父图汇总更新为16张/98 mask暂通过、75张返修、1张排除，7个来源组不变。外部真机、失败案例、Beta与代表性test仍未满足，完成度审计继续HOLD | 发布测试返修、辅助标注、来源隔离、审核聚合、发布门禁 |
| 2026-07-13 | v1.1.33 | 将全部本地/远程分支合并到`master`并删除其余分支：实施分支正常合入，旧应用分支经冲突修复后保留AR演示桥接、识别mask视觉证据链和显式deferred审计；图片清理前备份仅以`ours`策略纳入历史，未恢复旧素材。额外将4个本地`.pt`权重和11.6MB合成ONNX移出Git跟踪但保留本机，只保留33KB smoke ONNX测试夹具。全量344项测试、ESLint、340文件编码审计及Next.js生产构建通过；本地/远程均只剩`master` | Git分支治理、AR演示、模型视觉证据、审计命令、素材与大模型排除 |
| 2026-07-13 | v1.1.32 | 按用户要求将外部素材改名映射目录从Git跟踪中移除并加入`.gitignore`；图片素材原本即未进入Git，本地映射继续保留且不影响1435张哈希验证结果。模型接口、数据授权、审核计数和生产HOLD不变 | Git素材治理、本地来源映射、仓库体积与隐私 |
| 2026-07-13 | v1.1.31 | 将外部素材根目录其余5批1435张图片统一为类型/来源/日期/四位序号命名，逐批保留可逆原名、新名、SHA-256和来源组映射；1435/1435改名后哈希一致，101张已稳定引用的发布测试图保持原命名。正式数据集与历史证据不改写，授权、标注、split和生产HOLD不变 | 外部素材管理、来源追溯、数据治理、改名工具 |
| 2026-07-13 | v1.1.30 | 新增受审计SAM提示修复工具，可按人工keep/drop/add决定重建提示并记录源提示/修复清单哈希；首批5张/25提示SAM2与几何审计通过，原分辨率审核提升4张/20 mask，1张继续返修。标注审核器支持叠加修复报告并核对polygon数/来源组；新增父图级聚合报告，强制训练禁用且覆盖92/92父图。累计14张/89 mask暂通过、77张返修、1张排除，发布HOLD不变 | 发布测试返修、辅助标注、来源隔离、审核聚合、发布门禁 |
| 2026-07-13 | v1.1.29 | 完成35张截图/拼图压力父图主照片区域提取，35/35父子哈希、裁剪坐标和稳定来源组审计通过；新增发布测试派生区域intake构建器并强制继承发布测试/长期回归授权、禁止训练。v6生成201候选，SAM2 201/201完成；原分辨率复核仅2张/10 mask通过、33张返修。92张非重复父图首轮累计10张/69 mask暂通过、81张返修、1张源图裁断排除；生产HOLD不变。同时将可重建的v6候选多边形JSON移出Git跟踪并补充忽略规则 | 发布测试数据治理、压力样本、来源隔离、辅助标注、仓库体积治理、发布门禁 |
| 2026-07-13 | v1.1.28 | 将101张新增真实发布测试素材统一改名为`real_release_20260713_001..101.jpg`并保留可逆原名/来源/哈希映射；101/101解码与哈希复核通过，排除9张跨旧批次精确重复，92张按57核心/35压力图进入独立发布测试与长期回归且禁止训练。v6+SAM2完成57张核心图候选标注，原分辨率复核仅8张/59 mask暂通过、48张返修、1张源图裁断排除；100–200张test、真机、Beta及生产HOLD不变 | 素材命名、发布测试数据治理、用途隔离、辅助标注、发布门禁 |
| 2026-07-13 | v1.1.27 | 新增真机、Beta与用户失败案例证据构建器及可填写CSV模板：真机聚合器只接受已通过且各不少于20次的性能/内存报告；Beta构建器校验100张、用户审核、图片SHA-256、修正耗时和85%直接可用率；失败案例构建器校验本地图片、来源组、类别、严重度和哈希。成功/拒绝专项6/6通过，外部证据仍未提供，生产HOLD不变 | 外部验收、真机报告、Beta质量、失败案例、隐私与证据治理 |
| 2026-07-13 | v1.1.26 | 新增实施规范最终完成度机器审计和npm入口，逐项核对用户/工程清单、进度标记、数据授权、v6精度、代表性真实test、桌面与Android手机/平板/iPhone/iPad、失败案例、Beta质量及生产资产。当前3/10门通过，正确输出HOLD和4类外部证据阻断；纠正M3-T4对已完成用户项的错误引用，生产manifest保持不变 | 完成度治理、设备验收、Beta质量、发布阻断、文档一致性 |
| 2026-07-13 | v1.1.25 | 新增来源隔离实验集增量构建器及冻结test哈希门，将7张授权派生图/41 mask加入v9，得到106图/722 mask、split=76/17/13，test 13图/102 mask联合SHA-256保持不变。v9以v6权重续训16 epochs，512 test box/mask mAP50=0.8411/0.8393，因box低于0.85且两项均较v6退化被拒绝；未导出、注册或发布，v6继续作为最佳候选 | 训练数据隔离、测试集冻结、指标门禁、候选治理 |
| 2026-07-13 | v1.1.24 | 再次只读核验 Windows 的 npm 打开方式弹窗：`npm` 仍优先命中 `C:\Windows\System32\npm`（0 字节、无扩展名），而正式 `C:\Program Files\nodejs\npm.cmd` 存在且可用。后续自动化命令固定显式调用 `npm.cmd`；未修改系统目录，无接口、模块状态、模型训练状态或发布门禁变化 | 本地开发环境、命令执行约定 |
| 2026-07-13 | v1.1.23 | 将7张审核通过的截图派生照片/41 mask安全导入正式集：intake清单支持逐图sourceGroup并继承原批次商业训练/长期回归授权，来源记录保留父文件名、父SHA-256、区域和裁剪框。正式集更新为409图/2142 mask、split=300/46/63，来源、授权、标签、split、物化和readiness门均通过；v6冻结test与发布HOLD不变 | 派生数据入库、授权继承、来源隔离、训练数据治理 |
| 2026-07-13 | v1.1.22 | 完成9张截图派生照片逐甲审核：v6高置信候选64个仅作定位，SAM2原分辨率审核7张/41 mask通过、2张返修；SAM提示支持逐图sourceGroup，新增派生图SHA-256/尺寸/父图稳定分组/多边形机器审计并通过。通过项尚未导入，正式402图/2101 mask与发布HOLD不变 | 辅助标注、派生数据治理、来源隔离、质量审计 |
| 2026-07-13 | v1.1.21 | 复核 Windows 反复弹出“选择应用打开 npm”的现象：当前命令仍优先解析到 `C:\Windows\System32\npm`（0 字节、无扩展名），正式 `C:\Program Files\nodejs\npm.cmd` 可正常返回 npm 11.13.0，Node.js v24.16.0 亦正常。继续统一使用 `npm.cmd`；本轮仅做只读复核，未删除系统文件，无接口、模块状态或发布门禁变化 | 本地开发环境、命令执行约定 |
| 2026-07-13 | v1.1.20 | 新增截图/拼图审核区域提取器与父子来源报告，9张小红书截图主照片区域9/9提取成功，记录父子SHA-256、坐标、尺寸和父图稳定分组；修复Windows GBK控制台打印Unicode文件名失败。v6生成92个候选但保持review-only，可重建候选多边形目录由Git忽略；正式集与发布HOLD不变 | 辅助标注、派生数据治理、来源隔离、Windows兼容、仓库治理 |
| 2026-07-13 | v1.1.19 | 对3张Deerplanet返修图执行25个紧框及三轮低对比定点复跑，原分辨率审核0张提升、28张继续返修；增强SAM2/FastSAM失败报告，精确定位提示序号、模式和polygon转换阶段，专项测试通过。纠正readiness快照split为294/45/63；数据集readiness通过，总体发布HOLD不变 | 辅助标注、错误诊断、数据治理、文档一致性 |
| 2026-07-13 | v1.1.18 | 诊断本机PowerShell反复弹出“选择应用打开npm”：`C:\Windows\System32\npm`为0字节无扩展名文件并在PATH解析中遮蔽正式`C:\Program Files\nodejs\npm.cmd`。项目后续Windows命令统一显式调用`npm.cmd`；本轮未删除系统文件，未改变运行时接口、模块状态或发布门禁 | 本地开发环境、命令执行约定 |
| 2026-07-13 | v1.1.17 | 对3张Deerplanet返修图执行27个SAM2逐甲紧框并对2张以19个收紧框复跑；原分辨率审核仅提升1张/8 mask，2张继续返修。正式集更新为402图/2101 mask、split=294/45/63，审核队列为80通过、5排除、28返修，来源审计与release readiness通过；发布HOLD不变 | 辅助标注、数据治理、训练授权、发布门禁 |
| 2026-07-13 | v1.1.16 | 新增浏览器本地图片上传校验器，统一编辑器与AR的JPG/PNG/WebP、10MB、320–4096像素及解码门禁；编辑器展示内联错误并收紧file accept。Playwright验证非法文件提示和合法PNG进入编辑器，控制台0错误0警告；Canvas高频回读启用willReadFrequently | 编辑器上传、AR纹理上传、浏览器性能、输入安全 |
| 2026-07-13 | v1.1.15 | 移除`.env.local.example`中启用状态的smoke manifest覆盖，默认恢复到正式manifest路径；新增配置回归测试防止smoke URL再次成为共享默认值，并纠正readiness表残留的test=62为当前293/45/63。正式ONNX与移动/Beta门禁不变 | 模型配置、发布安全、文档一致性 |
| 2026-07-13 | v1.1.14 | 以24个视觉紧框+SAM2复核6张返修图，仅提升1张/1 mask；另排除1张源画面裁断图，审核队列更新为79通过、5排除、29返修，正式集为401图/2093 mask、split=293/45/63。新增1001张Claude生成图完成解码、尺寸、批内及跨正式集去重和11页视觉总览，登记为待授权/待标注的合成候选池 | 辅助标注、数据治理、合成素材审计、训练授权 |
| 2026-07-13 | v1.1.13 | 对35张返修图执行3×3重叠分块推理，生成19图/88候选但视觉门0提升；再以33个视觉紧框+SAM2复核4张，确认3张甲面被画面截断、1张背景甲面失焦，均属源图不可恢复并排除。审核队列更新为78通过、4排除、31返修，正式数据集不变 | 辅助标注、源图质量门、数据治理 |
| 2026-07-13 | v1.1.12 | 新增跨分辨率共识筛选工具，对37张返修图生成34图/209个稳定候选并完成五页与原分辨率审核，仅提升2张/9 mask；正式集更新为400图/2092 mask、split=293/45/62，35张继续返修。v8 在冻结13张真实 test 上 box/mask mAP50=0.8487/0.8472，因 box 未达0.85且未超过v6被拒绝 | 辅助标注、数据治理、训练评估、发布门禁 |
| 2026-07-13 | v1.1.11 | 新增真实浏览器内存采样与校验工具；v6 在 Windows Chromium WebGPU 连续20次识别中 JS heap 峰值19.86MiB、首末窗口增长1.69MiB，浏览器私有内存峰值929.50MiB、首末窗口增长121.81MiB，桌面暂定稳定性门通过；移动真机内存继续待验收 | 浏览器性能、内存稳定性、设备验收 |
| 2026-07-12 | v1.1.10 | 使用 v6 对 42 张返修图生成 317 个 640 候选并完成五页逐图视觉审核，仅提升 5 张/27 mask；再对剩余 37 张执行 1024/conf10 推理并审核 458 个候选，因重复与污染未新增提升。正式集更新为 398 图/2083 mask、split=292/45/61 且数据门通过。v7 在冻结 13 张真实 test 上 box/mask mAP50=0.840/0.833，低于 v6 并因 box 未达 0.85 被拒绝 | 辅助标注、数据治理、训练评估、发布门禁 |
| 2026-07-12 | v1.1.9 | 登记第二批 113 张实拍素材的商业训练与长期回归授权，正式导入 71 图/471 mask 并按真实集合隔离来源；记录 v4/v5 拒绝及 v6 通过独立真实精度、11.03MB 资产协议和桌面 WebGPU 热推理 P95=133.7ms。因独立 test 仅 13 张且缺移动真机/Beta 验收，生产 promotion 保持 HOLD | 数据治理、训练评估、模型资产、浏览器性能、发布门禁 |
| 2026-07-12 | v1.1.8 | 按当前审核证据回填实施规范清单：MVP 范围、设备优先级、素材数量及 11 项工程能力标记完成；训练授权、真实数据闭环、真机报告和 Beta 人工审核保持未完成并指向对应 USER INPUT | 文档治理、实施清单、完成标记 |
| 2026-07-12 | v1.1.7 | 完成 real-seed-v1 独立 test 复评：box/mask mAP50=0.380/0.367，相对 512 基线退化 0.143/0.101，自动质量门拒绝候选；未导出或发布不合格模型 | 模型评估、质量门、发布阻断 |
| 2026-07-12 | v1.1.6 | 完成 real-prelabel-v3 隔离 ONNX 工程验证：11.03MB、完整性一致、ORT 双输出协议与 TypeScript fixture 解码通过；标记仅限辅助标注用途，不改变正式模型 blocked 状态 | 模型导出、端侧协议、用途隔离 |
| 2026-07-12 | v1.1.5 | 复核并纠正实拍数据现状：首批 21 张/174 个甲面已全部通过；使用 v3 常规及高召回候选复核新增 113 张素材，将隔离审核包提升至 70 张正样本、1 张 hard negative、471 个 mask，标签审计 0 错误。新增批次因缺正式训练授权继续隔离，不改变正式模型 blocked 状态 | 数据集治理、辅助标注、训练授权 |
| 2026-07-12 | v1.1.4 | 清理尚未推送的 Git 历史：将两次本地提交重写为一个不含图片、模型权重和生成型调试资产的提交；补充 `.gitignore`，移除 `weights/clip/ViT-B-32.pt` 的 Git 跟踪但保留本地文件。复核确认相对 `origin/master` 的新增对象无超过 100 MB 文件，运行时接口与功能状态不变 | 仓库治理、版本历史、资源管理 |
| 2026-07-12 | v1.1.3 | 复核 Git 推送失败：确认远端未接收本地提交，根因包含 353,976,522 字节权重文件超过 GitHub 单文件限制及大量生成调试资产；本次仅登记仓库治理风险，无运行时接口/功能状态变化 | 仓库治理、文档记录 |
| 2026-07-12 | v1.1.2 | 同步实拍素材目录纠正与人工标注导入：永久移除 1 张禁用图片，登记 19 张/156 个审核甲面和 113 张新增实拍素材初筛结果，重建来源表、split 与 YOLO 标签 | 数据集治理、训练输入、质量门 |
| 2026-07-12 | v1.1.1 | 复核端侧实施技术规范：确认总体方案仍有效，登记 Worker/ORT/letterbox 等历史缺口已完成，并明确规范与实时进度的文档定位 | 文档治理、纹理识别 |
| 2026-07-12 | v1.1.0 | 全面源码审查；增加任务前必读与任务后必更新门禁；纠正数据流、编辑器上传、图库参数、CDN、smoke 配置、隐私文案、Worker 和网络边界说明 | 全项目 |
| 2026-07-12 | v1.0.0 | 创建技术白皮书；盘点页面、HTTP API、AR、纹理识别、模型、数据集、训练和发布接口；建立任务后强制维护规则 | 全项目 |
