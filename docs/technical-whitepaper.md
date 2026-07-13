# 甲如（JiaRu）技术白皮书

> 文档版本：v1.1.52
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
| 美甲纹理自动识别 | `recognizeNailTextures()` | 进行中 | 浏览器推理、Worker、后处理和 fallback 已实现；v6 已通过独立真实精度、桌面 WebGPU 性能及20次桌面内存稳定性门，但尚未晋升生产 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()` | 已完成 | 模型不可用时仍可返回候选，但质量不等同正式模型 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 阻塞 | v6 候选 ONNX 已在隔离导出目录通过精度、资产、协议和桌面性能门；92张真实发布测试父图已完成核心/压力首轮及十五轮受审计返修，但目前仅39张派生/原图、225 mask通过视觉复核，尚不能替代冻结13张test或解除移动真机/Beta门 |
| 数据集治理 | `model/datasets/nail-texture-v1` | 进行中 | 正式训练集仍为409图、2142个mask，split=300/46/63。新增101张真实素材中9张跨旧批次精确重复排除；其余92张仅用于独立发布测试与长期回归，57张核心图与35张压力图均完成首轮处理。十五轮修复累计再提升29张/156 mask，当前累计39张/225 mask暂通过、41张返修、12张源图裁断或遮挡排除，训练用途始终禁止。1001张Claude生成图仍为未授权、未标注的合成候选池 |
| 训练/评估/导出 | `model/training/*` | 进行中 | v4、v5、v7、v8 与 v9 已按门禁拒绝；v6 独立真实 test box/mask mAP50=0.853/0.848，11.03MB FP32 ONNX 和浏览器 WebGPU 热推理门通过，尚缺代表性样本规模与真机/Beta 验收 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门、最终完成度审计和外部验收证据构建器；首跑识别 mask 叠加图可沿最终审计、trace、历史清单与候选对比追溯，证据减少会进入人工复核；当前审计3/10门通过并输出HOLD，尚未完成正式模型发布闭环 |
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

使用方式：输入 1～500 字符描述，或选择预设风格，点击生成；成功后前端显示外部服务返回的远程图片 URL，并尝试跨域下载，失败时在新窗口打开图片。前端只向本项目 API 发送文字，不发送用户照片。

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
  "labels": ["nail_texture"]
}
```

正式发布要求：

- manifest 通过结构校验；
- ONNX 文件存在，文件名与 manifest 一致；
- 输入/输出名称和张量形状与后处理契约一致；
- 通过 fixture、真实图片、浏览器集成和性能门；
- 具备版本、SHA-256、体积、指标、发布和回滚记录。

当前结论：v6 正式候选 ONNX 已在隔离导出目录通过资产、输出协议、独立真实精度与桌面 WebGPU 性能门，但生产 manifest 仍指向缺失的 `nail-texture-seg-v1.onnx`，因此 `real-model-final-audit-report.json` 的生产决策继续为 `blocked`。现有 synthetic 与 smoke 模型仍只能作为工程测试资源，v6 在代表性测试集、移动真机和 Beta 人工门完成前也不得 promotion。

## 8. 数据集与训练接口

### 8.1 数据集契约

数据集根目录：`model/datasets/nail-texture-v1`。

核心版本：`nail-texture-dataset/v1`。标注以多边形 mask 为主，可转换为 YOLO segmentation 格式。必须维护素材来源、授权、哈希、审核状态、数据切分和负样本信息。

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

外部素材根目录随后完成统一命名治理。除已被发布测试清单和标注稳定引用、继续保留`real_release_20260713_001..101.jpg`的101张发布测试图外，其余5个批次1435张图片统一采用`素材类型_来源_YYYYMMDD_四位序号.原扩展名`：300张早期生成图、1001张Claude新增生成图、21张首批真实训练素材和113张第二批真实训练素材均完成两阶段安全改名。5份本地映射清单逐图保存原名、新名、SHA-256和来源组，改名后1435/1435复算哈希一致且无临时文件；素材及改名映射目录均由`.gitignore`排除，不进入Git。正式数据集内部副本、标注及历史报告继续保留导入时稳定名称，通过SHA-256映射追溯，不改写历史证据；该治理不改变授权、split、标注审核或生产HOLD状态。

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
| 数据盘点 | `audit-image-corpus.py`、`audit-labels.ts`、`audit-phase1-readiness.ts` |
| 数据准备 | `convert-annotations.ts`、`split-dataset.ts`、`materialize-training-dataset.ts` |
| 辅助标注 | `sam-assisted-nail-annotation.py` |
| 审核区域提取 | `extract-reviewed-image-regions.py` |
| 发布测试派生区域intake | `build-release-test-region-intake.py`；继承发布测试/长期回归授权，禁止训练，校验stress父项、父子哈希、派生文件和一父一主区域 |
| 发布测试提示修复 | `build-reviewed-sam-repair-prompts.py`；按人工keep/drop/add决定重建提示，支持逐新增框选择SAM提示模式，记录源提示/修复清单哈希并保持候选隔离 |
| 发布测试审核聚合 | `build-release-test-annotation-review.py`、`build-release-test-review-summary.py`；叠加修复报告、核对polygon数/来源组并将派生决定映射回父图 |
| 派生区域标注审计 | `verify-reviewed-region-annotations.ts` |
| 派生区域入库构建 | `build-reviewed-region-intake-batch.ts` |
| 训练 | `train-yolo-seg.py` |
| 评估 | `evaluate.py`、`assess-model-metrics.py` |
| 来源隔离实验集增量构建 | `extend-source-isolated-dataset.py`；从已审计快照加入授权样本，禁止新增项进入 test，并对冻结 test 图片与标签做逐文件联合 SHA-256 校验 |
| 导出/量化 | `export-onnx.py`、`quantize-onnx-int8.py` |
| 浏览器烟雾模型 | `build-browser-smoke-model.py` |
| 发布门 | `scripts/verify-*.ts`、`scripts/run-*-pipeline.ts` |
| 发布治理 | `register-model-release.ts`、`switch-model-release.ts`、`promote-approved-release.ts` |
| 最终完成度审计 | `audit-nail-texture-local-inference-completion.ts`；核对实施规范清单、全部关键证据和生产资产，缺证据时输出HOLD及责任方 |
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
- v6 是当前首个同时通过独立真实精度、模型资产、输出协议和桌面热性能门的正式候选，但冻结独立 test 仍仅13张。2026-07-13新增92张来源隔离真实发布测试父图均已完成核心/压力两路首轮处理及十五轮受审计返修，累计仅39张/225 mask暂通过、41张返修、12张源图裁断或遮挡排除；在真值冻结与代表性审核完成前不得把“13+92”直接计为105张合格test。Android/iPhone/iPad 与 Beta 人工直接可用率也未验收，因此生产 promotion 保持 HOLD。
- v7 将新增 5 张审核图并入来源隔离实验集，规模更新为 97 图、672 mask，train/val/test=69/15/13；冻结 deerplanet test 保持 13 图/102 mask 不变。以 v6 权重继续训练后，512 test 的 box/mask mAP50=0.840/0.833，box 低于 0.85 且两项均较 v6 退化，因此质量门拒绝；未导出 ONNX、未注册、未发布，v6 继续作为最佳候选。
- v8 将跨分辨率共识后新增的 2 张/9 mask 并入来源隔离实验集，规模更新为 99 图/681 mask，train/val/test=70/16/13；冻结 deerplanet test 仍为 13 图/102 mask。以 v6 权重续训 16 epochs 后 early stop，512 test box/mask mAP50=0.8487/0.8472；box 低于 0.85，且两项均未超过 v6，质量门拒绝。未导出 ONNX、未注册、未发布。
- v9 从已审计 v8 快照安全加入 7 张截图派生图/41 mask，规模更新为 106 图/722 mask，train/val/test=76/17/13。新增项仅进入 train/val；冻结 13 图/102 mask test 的图片和标签联合 SHA-256 前后均为 `7af1a82c8b20608b486ed7e744366a842a722f86519e49ba0b34cf922984059e`。以 v6 权重续训 16 epochs 后 early stop，512 test box/mask mAP50=0.8411/0.8393，分别较 v6 下降 0.0116/0.0084；box 未达 0.85 且两项均未改善，质量门拒绝。未导出 ONNX、未注册、未发布，v6 保持最佳候选。

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
- `scripts/build-nail-texture-beta-review.ts`
- `scripts/build-nail-texture-user-failure-cases.ts`

验收原则：

- 单元测试通过不等于真实设备通过；
- synthetic/smoke 模型通过不等于真实模型质量通过；
- 数据 readiness 通过不等于训练指标或用户体验通过；
- 摄像头、WebGPU、移动端裁切和手心/手背识别必须进行目标浏览器真机测试。

`npm.cmd run audit:mvp-readiness:deferred`只用于明确排除真实数据与真实模型资产的工程脚手架阶段；它会把数据集、训练授权和浏览器模型资产三项标为`deferred`，不能替代严格`audit:mvp-readiness`，也不能作为实施规范最终完成、生产 promotion 或发布解锁证据。

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

1. v6 正式候选已产出并通过当前精度/资产/桌面性能门，但生产 manifest 尚未切换；新增92张来源隔离发布测试父图已完成首轮及十五轮受审计返修，但仅39张/225 mask暂通过，41张返修、12张源图裁断或遮挡排除，尚未形成冻结真值，因此原13张独立真实test仍不足以替代100–200张代表性测试集；同时仍缺用户典型失败案例和至少100张Beta人工质量审核，正式模型审计继续blocked；
2. AI 生图依赖外部模型与密钥，尚未完成生产环境可用性、成本和内容安全验证；
3. AR 摄像头和朝向识别仍需要更多手机、浏览器、光线和肤色组合的真机验收；纹理识别桌面内存基线已建立，但 Android手机、Android平板、iPhone和iPad峰值内存仍未测量。

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
