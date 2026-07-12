# 甲如（JiaRu）技术白皮书

> 文档版本：v1.1.9
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
| 图片试色编辑器 | `/editor` | 已完成 | 本地上传、逐指选色、Canvas 涂抹与本地保存链路存在；上传校验仍需补强 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 待验证 | 前后端已实现；依赖有效密钥、联网和当前模型可用性，尚无正式服务可用性承诺 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 单手摄像头、关键点、指甲绘制、手心/手背识别已实现；依赖 CDN，仍需多设备真机验收 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | 支持手动裁剪和多候选纹理分配；贴合质量需继续实测 |
| 视频自适应展示 | `calculateCoverVideoLayout()` | 已完成 | 保持比例，采用居中 cover 裁切，不拉伸 |
| 美甲纹理自动识别 | `recognizeNailTextures()` | 进行中 | 浏览器推理、Worker、后处理和 fallback 已实现；v6 真实候选已通过独立真实精度门与桌面 WebGPU 性能门，但尚未晋升生产 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()` | 已完成 | 模型不可用时仍可返回候选，但质量不等同正式模型 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 阻塞 | v6 候选 ONNX 已在隔离导出目录通过精度、资产、协议和桌面性能门；生产 manifest 仍未切换，代表性真实 test 仅 13 张且移动真机/Beta 质量门未完成 |
| 数据集治理 | `model/datasets/nail-texture-v1` | 进行中 | 正式有效集为 393 图、2056 个 mask，split=289/45/59；第二批授权后导入 71 图（70 正样本、1 hard negative）和 471 个 mask，并按 deerplanet/more/other 集合隔离来源；剩余 42 张继续返修 |
| 训练/评估/导出 | `model/training/*` | 进行中 | v4 与 v5 已按门禁拒绝；v6 独立真实 test box/mask mAP50=0.853/0.848，11.03MB FP32 ONNX 和浏览器 WebGPU 热推理门通过，尚缺代表性样本规模与真机/Beta 验收 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门和审计脚本，尚未完成正式模型发布闭环 |
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

1. 上传或拍摄清晰的手部图片；界面提示 JPG/PNG/WebP，但当前文件选择器实际为 `accept="image/*"`；
2. 选择拇指至小指之一；
3. 选择颜色，可将当前颜色应用到全部手指；
4. 在 Canvas 上点击或拖动完成局部涂色；
5. 使用组件提供的撤销、重置和保存能力。

数据边界：上传文件通过 `URL.createObjectURL()` 留在浏览器，页面卸载或更换文件时释放对象 URL。

已知限制：`/editor` 当前没有运行时 MIME、文件大小、最小分辨率和解码失败提示校验；浏览器可能允许选择界面提示之外的图片格式。该限制只影响编辑器，`/ar-tryon` 的纹理上传另有 PNG/JPEG/WebP 和 10 MB 校验。

核心组件接口：

```ts
<UploadButton onUpload={(file: File) => void} />

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
4. 点击“开启摄像头”，授权摄像头权限；
5. 将手放入画面并展示手背，系统根据手部关键点绘制指甲；
6. 手心、手背或不确定状态会显示对应提示，手心状态不绘制指甲纹理。

上传约束：PNG/JPEG/WebP，最大 10 MB。摄像头画面只在内存中处理，不录制、不上传。

运行约束：当前 `maxNumHands: 1`、`modelComplexity: 0`，检测和跟踪阈值均为 `0.5`。`hands.js`、WASM 和相关 MediaPipe 文件从固定版本的 jsDelivr URL 加载，脚本等待超时为 15 秒；离线、CSP 限制或 CDN 故障会导致 AR 无法启动。

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

重要：当前 `.env.local.example` 的实际值就是 smoke manifest。直接复制该文件会启用烟雾模型，而不是正式模型。正式环境必须删除该覆盖项以使用代码默认路径，或显式改为正式 manifest；在正式 ONNX 缺失期间，两种方式都不能产生正式模型能力。

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
| 图片 | 393 |
| mask | 2056 |
| 有效 mask | 2056 |
| train / val / test | 289 / 45 / 59 |
| 错误文件 | 0 |
| warning 文件 | 2 |

2026-07-12 实拍数据同步：首批素材的有效来源目录已由误写的 `真实素材/2027_7_11` 纠正为 `真实素材/2026_7_11`。用户明确禁用的 `ca2d14573bfe3c0c83cdc3100e074b3c.jpg` 已从有效图片、原始标注、YOLO 标签、来源表和 split 中移除；其余 21 张审核通过图片共 174 个甲面已覆盖旧 fallback 标注并通过来源审计与标签审计。第二批 `真实素材/2026_7_12` 共 113 张已获得用户选择 A 的商业模型训练与长期回归授权；视觉复核通过的 70 张正样本和 1 张 hard negative（471 个 mask）已正式导入，42 张返修项未导入。导入时按 deerplanet、more 和其他集合细分 `sourceGroup`，重新切分为 289/45/59，来源授权、标签、split 比例及训练 readiness 均通过。

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
| 训练 | `train-yolo-seg.py` |
| 评估 | `evaluate.py`、`assess-model-metrics.py` |
| 导出/量化 | `export-onnx.py`、`quantize-onnx-int8.py` |
| 浏览器烟雾模型 | `build-browser-smoke-model.py` |
| 发布门 | `scripts/verify-*.ts`、`scripts/run-*-pipeline.ts` |
| 发布治理 | `register-model-release.ts`、`switch-model-release.ts`、`promote-approved-release.ts` |

真实训练在本地 Python/Ultralytics/PyTorch 环境执行，不需要在训练循环中调用 GPT。GPT 或其他视觉模型只能作为素材生成、辅助标注或审核工具，生成结果必须经过授权与人工质量控制。

### 8.3 real-prelabel-v3 隔离工程验证

`nail-texture-seg-real-prelabel-v3` 仅用于提高人工审核候选召回率，不是正式发布候选。其 512 FP32 ONNX 已完成以下轻量工程检查：

- 文件大小 11,566,101 字节（11.03MB），低于 15MB MVP 上限、高于 8MB 理想值；
- manifest SHA-256 `280a2ff809231ee07130ea350469b26ccd34ab086904c5434c7fa095e1dbb4b8` 与实际文件一致；
- ONNX Runtime 实际输出为 `[1,37,5376]` 和 `[1,32,128,128]`；
- TypeScript 后处理 fixture 解码得到 5 个带 mask 候选；
- 因训练中使用第二批隔离标注且该批次正式授权未确认，该产物保留在被 Git 忽略的 `model/exports/`，不得覆盖生产 manifest、注册或 promotion。

仅使用当前授权正式集训练的 `nail-texture-seg-real-seed-v1` 已在 46 张独立 test 上复评：box mAP50 为 0.380，mask mAP50 为 0.367；相对 512 合成基线分别下降 0.143 和 0.101，均超过 0.02 退化上限。质量门按预期拒绝该候选，因此不继续导出、注册或发布。

### 8.4 真实候选 v4–v6 结论

- v4 使用 393 图混合集继续训练，独立原 test 的 box/mask mAP50=0.429/0.397，未通过质量门，未导出或发布。
- v5 使用 92 张真实图构建来源隔离实验集（66/13/13），以 deerplanet 集合作为从未参与训练的 test；512 评估 box/mask mAP50=0.848/0.836，box 略低于 0.85 冻结门槛，资产门通过但发布门正确拒绝。
- v6 在相同无泄漏实验集上以 640 训练、512 部署评估；13 张独立真实 test、102 个 mask 的 box/mask mAP50=0.853/0.848，超过 0.85/0.75 门槛。FP32 ONNX 为 11,566,102 字节（11.03MB），SHA-256 为 `d122da819a4b1c70a954a55d84b26ed53fc33fb9bd8374a9e69c0e106909e57d`，ORT 输出 `[1,37,5376]` / `[1,32,128,128]`，TypeScript fixture 解码 7 个带 mask 候选。
- Chromium + WebGPU 采集 29 次热推理：端到端 P50/P95/最大值为 108.9/133.7/159.5ms，Worker P95 为 100ms，低于桌面 800ms 门槛；冷启动单次约 4.10s，仅作为加载基线，不混入热推理统计。
- v6 是当前首个同时通过独立真实精度、模型资产、输出协议和桌面热性能门的正式候选，但独立 test 仅 13 张，尚未达到规范建议的 100–200 张代表性真实测试集；Android/iPhone/iPad 与 Beta 人工直接可用率也未验收，因此生产 promotion 保持 HOLD。

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

验收原则：

- 单元测试通过不等于真实设备通过；
- synthetic/smoke 模型通过不等于真实模型质量通过；
- 数据 readiness 通过不等于训练指标或用户体验通过；
- 摄像头、WebGPU、移动端裁切和手心/手背识别必须进行目标浏览器真机测试。

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

1. v6 正式候选已产出并通过当前精度/资产/桌面性能门，但生产 manifest 尚未切换；13 张独立真实 test 不足以替代 100–200 张代表性测试集，正式模型审计继续 blocked；
2. AI 生图依赖外部模型与密钥，尚未完成生产环境可用性、成本和内容安全验证；
3. AR 摄像头和朝向识别仍需要更多手机、浏览器、光线和肤色组合的真机验收。
4. `.env.local.example` 当前默认指向 smoke manifest，复制后容易误把测试模型当成正式模型。

### 11.2 未完成或占位能力

1. 真实灵感图库与内容后台；
2. 用户账户、云端项目保存、跨设备同步；
3. 订单、门店、商品、预约、支付等业务后端；
4. 正式 3D 指甲网格、遮挡、光照和物理材质试戴；
5. AI 生图的供应商抽象、任务队列、结果持久化和配额系统；
6. 正式模型监控、线上质量回流和自动回滚闭环。
7. 图库款式到编辑器/AR 的参数消费和纹理传递；
8. AI 生成结果一键进入图库、编辑器或 AR 的集成链路；
9. 编辑器上传文件的 MIME、大小、分辨率和解码错误校验。

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
