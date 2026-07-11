# 甲如（JiaRu）技术白皮书

> 文档版本：v1.0.0  
> 基线日期：2026-07-12  
> 文档状态：持续维护  
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

### 1.2 强制维护流程

以后每完成一项会影响功能、接口、使用方式、配置、数据结构、模型、脚本或部署方式的任务，必须在结束任务前同步更新本文档：

1. 更新对应模块的状态、接口或使用说明；
2. 若新增或修改 HTTP/TypeScript/Worker/模型接口，更新相应契约；
3. 更新“已知限制与待办”；
4. 在“版本与变更记录”追加一条记录；
5. 在当天唯一的 `dev-log/YYYY-MM-DD.md` 中记录任务摘要；
6. 执行与风险相匹配的验证，并记录验证结论，不得把“代码存在”直接写成“生产可用”。

仅修改注释、拼写或不影响行为的格式调整时，可只追加简短变更记录；如果确认完全不影响白皮书内容，应在当天开发日志注明“白皮书无需变更”及原因。

## 2. 系统概览

甲如是基于 Next.js App Router 的美甲设计与试戴应用。核心处理原则是“图片与摄像头数据尽量留在浏览器本地”，仅 AI 文生图功能向服务端发送文字描述。

### 2.1 技术栈

| 层级 | 技术 | 当前版本/方式 |
| --- | --- | --- |
| Web 框架 | Next.js App Router | 16.2.9 |
| UI | React | 19.2.4 |
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS + CSS Modules | Tailwind 4 |
| 手部关键点 | MediaPipe Hands | 浏览器端 |
| 纹理模型推理 | ONNX Runtime Web | 1.27.0，WebGPU/WASM |
| 图形处理 | Canvas、OffscreenCanvas、ImageBitmap | 浏览器端 |
| 3D 依赖 | Three.js | 0.184.0，当前未形成正式 3D 试戴链路 |
| AI 生图 | OpenAI Images HTTP API | 当前代码使用 `dall-e-3`，依赖服务端密钥 |

### 2.2 逻辑数据流

```text
用户照片 ──> 本地编辑器 / 本地纹理识别 ──> ImageBitmap 纹理 ──┐
摄像头 ────> MediaPipe 手部关键点 ───────> 指甲几何 ─────────┼─> Canvas AR 合成
文字描述 ──> POST /api/generate-ai ──────> 外部图像 API ─────┘   （仅文字离开设备）
```

## 3. 功能状态总表

| 模块 | 用户入口/接口 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| 首页与统一导航 | `/` | 已完成 | 提供功能入口与统一视觉框架 |
| 灵感图库 | `/gallery` | 占位 | 当前使用本地占位素材，尚无真实内容管理后端 |
| 图片试色编辑器 | `/editor` | 已完成 | 本地上传、逐指选色、Canvas 涂抹与本地保存链路可用 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 待验证 | 前后端已实现；依赖有效密钥、联网和当前模型可用性，尚无正式服务可用性承诺 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 摄像头、手部关键点、指甲绘制、手心/手背识别已实现；仍需多设备真机验收 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | 支持手动裁剪和多候选纹理分配；贴合质量需继续实测 |
| 视频自适应展示 | `calculateCoverVideoLayout()` | 已完成 | 保持比例，采用居中 cover 裁切，不拉伸 |
| 美甲纹理自动识别 | `recognizeNailTextures()` | 进行中 | 浏览器推理、Worker、后处理和 fallback 已实现；正式模型产物缺失 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()` | 已完成 | 模型不可用时仍可返回候选，但质量不等同正式模型 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 阻塞 | manifest 已存在，但正式 `nail-texture-seg-v1.onnx` 不存在，最终审计为 blocked |
| 数据集治理 | `model/datasets/nail-texture-v1` | 进行中 | 当前 readiness 报告通过：323 图、1521 有效 mask；仍有 1 个 warning，且数据质量需持续人工审核 |
| 训练/评估/导出 | `model/training/*` | 进行中 | 脚本链路已建立；正式可发布模型尚未产出 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门和审计脚本，尚未完成正式模型发布闭环 |
| 隐私说明 | `/privacy` | 已完成 | 已说明本地图片/摄像头处理和 AI 文本传输边界 |
| 用户账户、云同步、商城/门店 | 无 | 未完成 | 当前没有对应后端接口或数据模型 |

## 4. 页面与用户使用接口

### 4.1 启动与访问

```powershell
cd "E:\AI Project\Codex\JiaRu"
npm.cmd install
npm.cmd run dev
```

默认访问 `https://localhost:3000`。开发脚本使用 `next dev --experimental-https`；若本机自签名证书生成失败，Next.js 可能回退至 HTTP。摄像头应通过 `localhost` 或正式 HTTPS 域名访问，不应使用普通局域网 HTTP 地址。

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

1. 上传清晰的手部 PNG/JPEG/WebP 图片；
2. 选择拇指至小指之一；
3. 选择颜色，可将当前颜色应用到全部手指；
4. 在 Canvas 上点击或拖动完成局部涂色；
5. 使用组件提供的撤销、重置和保存能力。

数据边界：上传文件通过 `URL.createObjectURL()` 留在浏览器，页面卸载或更换文件时释放对象 URL。

核心组件接口：

```ts
<UploadButton onUpload={(file: File) => void} />

<NailCanvas
  imageUrl={string}
  nailColors={string[5]}
  activeFinger={0 | 1 | 2 | 3 | 4}
  brushSize={number}
/>

<ColorPalette
  selectedColor={string}
  onSelectColor={(color: string) => void}
/>
```

### 4.3 `/gallery` 灵感图库

状态：占位。

当前使用 `src/lib/utils.ts` 中的 `GALLERY_IMAGES` 和 `public/nail-gallery/placeholder-*.svg`。没有数据库、上传管理、分页、搜索、收藏或真实素材授权接口。后续接入真实图库时应至少补充：资源 ID、来源授权、缩略图、原图、标签、创建时间、审核状态和删除策略。

### 4.4 `/ai-generate` AI 生图

状态：待验证。

使用方式：输入 1～500 字符描述，或选择预设风格，点击生成；成功后可下载图片。前端只发送文字，不发送用户照片。

前置条件：

```env
OPENAI_API_KEY=有效的服务端密钥
```

限制：当前代码固定请求 `dall-e-3`、`1024x1024`、`standard`，超时 30 秒。该模型名称和接口可用性属于外部依赖，正式部署前必须重新确认并完成联网实测。

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

主要组件：

```ts
<ArView
  nailColors={string[5]}
  nailTextures={(ImageBitmap | null)[5]}
  mode={"color" | "texture"}
/>
```

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

主入口位于 `src/lib/nail-texture-recognition/index.ts`：

```ts
async function recognizeNailTextures(
  source: ImagePixels,
  options?: RecognizeNailTexturesOptions
): Promise<NailTextureRecognitionResult>
```

`ImagePixels` 的结构为 `{ width: number; height: number; data: Uint8ClampedArray }`，与浏览器 `ImageData` 的核心像素字段兼容。

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

环境变量：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg/manifest.json
```

开发烟雾验证可临时指向：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg-smoke/manifest.json
```

烟雾/合成模型只验证工程链路，不得用于宣称真实美甲识别质量。

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

调用方应在超时、取消、页面卸载或更换图片时释放 `ImageBitmap` 和 Worker 资源。

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

当前结论：正式 ONNX 文件缺失，`real-model-final-audit-report.json` 的决策为 `blocked`。现有 synthetic 与 smoke 模型只能作为工程测试资源。

## 8. 数据集与训练接口

### 8.1 数据集契约

数据集根目录：`model/datasets/nail-texture-v1`。

核心版本：`nail-texture-dataset/v1`。标注以多边形 mask 为主，可转换为 YOLO segmentation 格式。必须维护素材来源、授权、哈希、审核状态、数据切分和负样本信息。

当前 readiness 快照：

| 指标 | 当前值 |
| --- | ---: |
| 图片 | 323 |
| mask | 1521 |
| 有效 mask | 1521 |
| train / val / test | 232 / 45 / 46 |
| 错误文件 | 0 |
| warning 文件 | 1 |

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

## 10. 隐私、安全与资源管理

- `/editor` 上传照片在浏览器本地处理；
- `/ar-tryon` 摄像头帧在浏览器内存中处理，不录制、不上传；
- 自动纹理识别默认在浏览器 Worker/主线程中运行；
- `/api/generate-ai` 只接收文字，但会把增强后的文字发送给外部图像服务；
- `OPENAI_API_KEY` 只能存在于服务端环境变量；
- `ImageBitmap`、对象 URL、MediaStream track、Worker 和动画帧循环必须在取消或卸载时释放；
- 用户素材、训练图片、大模型权重和生成数据默认不应加入 Git；应通过 `.gitignore`、对象存储或独立数据盘管理；
- 正式 API 上线前需增加鉴权、限流、内容安全、审计、费用保护和错误信息脱敏。

## 11. 已知限制与下一阶段

### 11.1 阻塞项

1. 正式 `nail-texture-seg-v1.onnx` 尚未产出，正式模型审计 blocked；
2. AI 生图依赖外部模型与密钥，尚未完成生产环境可用性、成本和内容安全验证；
3. AR 摄像头和朝向识别仍需要更多手机、浏览器、光线和肤色组合的真机验收。

### 11.2 未完成或占位能力

1. 真实灵感图库与内容后台；
2. 用户账户、云端项目保存、跨设备同步；
3. 订单、门店、商品、预约、支付等业务后端；
4. 正式 3D 指甲网格、遮挡、光照和物理材质试戴；
5. AI 生图的供应商抽象、任务队列、结果持久化和配额系统；
6. 正式模型监控、线上质量回流和自动回滚闭环。

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
| 2026-07-12 | v1.0.0 | 创建技术白皮书；盘点页面、HTTP API、AR、纹理识别、模型、数据集、训练和发布接口；建立任务后强制维护规则 | 全项目 |
