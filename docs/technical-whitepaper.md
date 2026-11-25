# 甲如（JiaRu）技术白皮书

> 文档版本：v1.2.465
> 基线日期：2026-11-25
> 商用完成门：PRODUCT HOLD
> 适用范围：产品页面、前端组件、浏览器端识别、AR 试戴、服务端 API、数据集、训练、模型发布与验证

## 1. 文档定位与维护规则

本文档只登记当前功能状态、活跃接口、生效合同与当前限制，不收录历史过程、逐版本流水或已结项实验。事实冲突时按以下优先级确认：

1. 当前源码、`package.json`、manifest 与实际文件；
2. 当前机器可读审计报告；
3. 自动化测试与最近一次真机/浏览器验证；
4. 本白皮书；
5. 历史归档。

模块登记采用「状态、入口、输入、输出、错误与降级、配置与限制、当前证据」七项。新事实直接替换旧段；同一结论只维护一处。任务读取、日志格式、Goal 结构与版本同步规则见 `AGENTS.md`。

## 2. 系统概览

甲如是基于 Next.js App Router 的美甲设计与试戴应用。默认浏览器本地处理照片与摄像头帧；AI 生图仅上传文字及用户主动提供的参考图。当前生产形态为本地开发与单实例部署，公网演示与隧道为辅助通道。

### 2.1 当前技术栈

| 层级 | 技术 | 当前版本/方式 |
| --- | --- | --- |
| Web 框架 | Next.js App Router | 16.3.6 |
| UI | React | 19.2.4 |
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS 4 + CSS Modules | 当前品牌令牌见§4.8 |
| 手部关键点 | MediaPipe Hands | 0.4.1675469240，同源静态资源 |
| 纹理推理 | ONNX Runtime Web | 1.27.0，生产仅 WASM |
| AI 生图 | Agnes Images HTTP API | `agnes-image-2.5-flash` |
| AI 生图第二引擎 | 火山方舟 Ark Images | Seedream 5 pro / lite |
| 部署 | Nginx 反向代理 + `next start` | 应用仅监听 `127.0.0.1:3000` |

## 3. 功能状态总表

| 模块 | 当前入口 | 状态 | 当前结论/主要缺口 |
| --- | --- | --- | --- |
| 首页与统一导航 | `/` | 已完成 | 新拟态品牌框架；桌面/移动导航同构，个性化分析由首页风格卡直达 |
| 登录与账号原型 | `/login`、`/account`、`/api/auth/*`、`/api/me` | 进行中 | 手机号/微信身份、JWT+SQLite、配额与限流已具备；真实短信、生产部署与一致性治理待补 |
| 灵感图库 | `/gallery` | 已完成 | 6 张 Seedream 素材本地落盘；收录区五态、删除撤销与跨页链路可用 |
| 图片试色编辑器 | `/editor` | 进行中 | 甲面框+纹理套装贴合、对象面板、会话草稿、原尺寸导出可用；hover 细节与真机体验待复核 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 已完成 | Agnes 2.5 Flash 主链路验收通过；身份与配额保护已接入 |
| AI 生图（Seedream） | `/ai-generate`、`POST /api/generate-seedream` | 待验证 | pro/lite 服务端与脚本端到端通过；浏览器视觉确认待用户复核 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 单手关键点、朝向、甲面几何与校准可用；多设备真机验收未完成 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | 纹理提取、甲根保护、逐指校准与复核流可用；真人实拍与多机型验收未完成 |
| 独立 AR 演示 | `/ar-demo` | 占位 | 本机 Python demo iframe 桥接；公网不可用 |
| 个性化分析推荐 | `/nail-analysis` | 待验证 | 纯本地规则引擎可用；真实照片与真机验收待补 |
| 美甲纹理自动识别 | `/ar-tryon`、`/editor`、`/nail-analysis` | 已发布（商用 HOLD） | 生产模型 `nail-texture-seg-geometry64-browser-aa4-v2`，WASM 单后端，业务发布门通过 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()` | 已实现 | 模型失败或 manifest 回退时进入辅助定位与人工确认 |
| 本机自研业务候选 | `/api/nail-matte`、`model/training/serve-nail-candidate.py` | 已验证 | Python/GPU 对照通道可用，浏览器业务已发布，本机通道保留对照与回退 |
| 本机精细抠图 | `NailArtPicker`、`POST /api/nail-matte` | 已实现 | WeVisOne-VL 辅助抠图可用，默认关闭，用户主动触发 |
| 合成/烟雾模型 | `/models/nail-texture-seg-smoke/` | 占位 | 仅工程链路验证 |
| 正式纹理模型 | `public/models/nail-texture-seg/manifest.json` | 业务已发布 / 商用 HOLD | `deploymentStatus=deployed`；商用完成门未闭合 |
| 纹理边缘覆盖率抗锯齿 | `edge-refine.ts`、`extract-mask-texture.ts` | 已接入 | 4×4 覆盖率与侧缘保护为当前默认；真机与未见来源待验 |
| 数据集治理 | `model/datasets/nail-texture-v1` | 进行中 | 现行真值 v5/范围 v3、100 名义图/634 甲；发布角色仍待重建 |
| 验证真值当前快照 | 外部 `validation-truth-index-v1.json` | 已完成 | 30 图/144 mask 规范校准真值，禁止训练 |
| 规范候选训练数据与输入门 | `materialize-canonical-candidate-training-dataset.py` 等 | 已完成 | 第二候选输入 PASS；授权仅限本次候选训练 |
| 候选三路训练发布编排 | `run-training-release-pipeline.ts` | 进行中 | candidate5 发布拒绝；下一候选须使用全新隔离数据 |
| 移动真机基准与证据门 | `/device-benchmark` | 工程门已完成 | 报告与身份绑定机制可用；四类真机样本未采集 |
| 训练/评估/导出 | `model/training/*` | 进行中 | 当前侧缘头与端头候选仍未达门 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 注册/切换/回滚/质量门工具链可用；无合格生产资产 |
| 隐私说明 | `/privacy` | 产品文案已完成 | 法律合规审核待外部；需补充云端识别与最新账户口径 |
| 用户账户 | `/login`、`/account`、`/api/me` | 进行中 | Phase 1 注册登录与资料编辑可用；商户与云同步未开始 |

## 4. 页面与用户使用接口

### 4.1 启动与访问

```powershell
cd "E:\AI Project\Codex\JiaRu"
npm.cmd install
npm.cmd run dev
```

默认访问 `https://localhost:3000`。生产流程为 `npm.cmd run build` 后 `npm.cmd run start`。生产验证命令：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

云端部署为腾讯云轻量服务器 + Nginx 反向代理，应用仅监听 `127.0.0.1:3000`，80 端口由 Nginx 终结；`JIARU_TRUST_PROXY=1` 时采信 `X-Real-IP` 与最右 XFF。摄像头需 HTTPS 或 `localhost`。

### 4.2 `/editor` 图片试色

状态：进行中。

- 入口：上传 JPG/PNG/WebP、≤10MB、宽高 320–4096。
- 识别：浏览器级联产出甲面框；0 候选时可经本机精细抠图兜底；支持「本地 | 云端」模式切换。
- 贴合：`src/lib/nail-texture-sets.ts` 5 套真实纹理套装，甲尖朝上、自带 alpha；`computeTextureRenderPlan` 长宽比保真。
- 交互：对象面板、撤销栈、会话草稿、原尺寸导出；`?gallery=` 灵感自动贴合，`?preset=` 仅预选。
- 组件：`NailCanvas`、`TextureSetPicker`、`EditorObjectPanel`；纯逻辑在 `src/lib/canvas/placements.ts`、`editor-texture-state.ts`。
- 限制：hover 视觉细节与真机体验待复核；无云端项目保存。

### 4.3 `/gallery` 灵感图库

状态：已完成。

- 素材：`public/nail-gallery/ai-look-1..6.jpg`，Seedream 生成，原分辨率审核通过。
- 交互：卡片点击弹出「试戴方式」选择；试色、AI 相似款、AR 试戴三个出口。
- 收录：IndexedDB `jiaru-gallery`，五态状态模型、单条删除 5 秒撤销、清空确认。
- 限制：无服务端数据库、分页、搜索或跨设备同步。

### 4.4 `/ai-generate` AI 生图

状态：已完成。

- 输入：1–520 字描述（Seedream 1–300），可选参考图 Data URI；比例 8 档、尺寸 1K–4K。
- 引擎：Agnes 默认，Seedream pro/lite 可选；每引擎独立设置。
- 交互：请求快照、取消、上一版折叠、错误分类、收录到图库。
- 提示词：10 风格×50 段；图生图使用独立系统提示词与场景锁定约束。
- 限制：内容审核、幂等、持久化与计费统计未实现。

### 4.5 `/ar-tryon` AR 试戴

状态：待验证。

- 输入：单纹理手动裁剪或参考图自动识别；PNG/JPEG/WebP、≤10MB、320–4096。
- 识别：浏览器模型优先，失败后 MediaPipe/局部近景/人工添加级联；云端模式为可选辅助通道。
- 贴合：甲根固定校准、独立长横轴投影、宽度与长度解耦、逐指 180° 翻转与撤销。
- 渲染：MediaPipe Hands 21 关键点 + 4 传感器朝向；`NailGeometry` 支持透视剪切与侧转。
- 材质：甲根颜色保护与放大侧缘保护为生产默认；`NEXT_PUBLIC_AR_ROOT_COLOR_PROTECTION=off` 可构建回退。
- 手势候选：M1 甲板朝向先验、M2 ROI 丢手兜底与双手按钮、M3 关键帧 Stage-A 分割融合，均默认关闭；M4 工程门已冻结，物理验收待用户采集。
- 限制：真人实拍、四类移动真机、多机型性能与长会话验收未完成。

### 4.6 `/nail-analysis` 个性化分析推荐

状态：待验证。

- 输入：五指清晰手背照片，复用上传校验。
- 计算：甲面候选、手型/甲床比例、肤色 ITA° 与底调、指甲健康启发式、场景问卷规则推荐。
- 输出：甲型/长度/色系/理由/置信度；可跳转 `/editor?preset=` 预选套装。
- 限制：真实照片与真机验收待补；健康观察不构成医疗诊断。

### 4.7 消费者端独立设计预览

状态：待验证（独立预览）。

- 入口：`node scripts/serve-consumer-design.mjs`，`http://127.0.0.1:4318`。
- 范围：`design/consumer-v1/` 原型，不注册正式路由；新拟态品牌适配、动效、可访问性与本地数据隔离已验证。
- 限制：摄像头、真实生成、账号、跨设备同步与公开社区未接入；Android/iOS 真机与原生分享待验。

### 4.8 正式站新设计系统

状态：已完成。

- 品牌：米白/墨/珊瑚令牌，双光源新拟态阴影，`src/app/globals.css`。
- 导航：桌面顶部 5 项 + 2 圆形图标；移动底部 5 项；`aria-current` 支持。
- 基元：`src/components/ui/primitives.tsx`、`AppDialog`、`ConfirmDialog`、`StatusRegion`、`UploadTrigger`。
- 字体：`public/fonts/jiaru-editorial-serif.woff2`，OFL 子集。
- 限制：视觉评审与真机验收仍待执行。

## 5. HTTP API 契约

### 5.1 `POST /api/generate-ai`

- 请求字段：`prompt` 1–520；可选 `image` Data URI、`ratio` 8 档、`size` 1K–4K。
- 响应：`{"imageUrl":"https://..."}`；错误统一 `{"error":"..."}`。
- 状态码：400/401/429/500/502/503/504，语义见源码 `src/app/api/generate-ai/route.ts`。
- 配额：登录 20/日、游客 5/日、全局 200/日、并发 3；`AI_QUOTA_*` 可覆盖。
- 身份：`requireUser` + 预算熔断；代理头仅在 `JIARU_TRUST_PROXY=1` 时采信。
- 未实现：内容审核记录、幂等、持久化与计费统计。

### 5.2 `POST /api/generate-seedream`

- 请求字段：`prompt` 1–300；`model` pro/lite；可选 `image`、`ratio`、`size`。
- 响应：`{"imageUrl":"https://..."}`；Ark URL 24 小时过期。
- 状态码与错误映射同 §5.1，另含 Ark 顶层 `error{code,message}`。
- 配置：`VOLCENGINE_ARK_API_KEY`、`ARK_SEEDREAM_PRO_MODEL`、`ARK_SEEDREAM_LITE_MODEL`、`ARK_BASE_URL`、`ARK_IMAGE_WATERMARK`。
- 限制：浏览器视觉呈现待确认；内容审核与计费未实现。

### 5.3 `GET/PATCH /api/me`

- GET：`{"user":{user,identities,consent}}`。
- PATCH：`nickname`、`bio`、`contact`、`contactType`、`avatar`、`ageGroup`；字段校验与审计记录见 `src/lib/profile/profile.ts`。
- 交互：`/account` 查看态/编辑态、头像压缩、保存取消、成功失败反馈。
- 限制：未接入对象存储与跨设备同步。

### 5.4 `GET/POST /api/nail-matte`

- 配置：`VLM_MATTE_URL`、`VLM_MATTE_TOKEN`；`NAIL_CANDIDATE_URL`/`NAIL_CANDIDATE_TOKEN` 优先。
- GET：`{"enabled","ready","busy","backend"}`。
- POST：`image` Data URI、`task`、`query`、`boxes`；请求体 ≤8MB。
- 响应：`instances[]`、`omittedInstances`、`model`、`quant`、`elapsedMs`。
- 错误：503 disabled/busy/auth、504 timeout、502 upstream、400/413/429。
- 安全：白名单重建请求体，不透传 `imagePath`；仅回环部署。
- 当前状态：路由级 5/5；UI 自动流程已接入，默认关闭。

### 5.5 `GET/POST /api/nail-detect-ark` 与 `/api/nail-matte-cloud`

- 方舟后端：`ARK_VISION_MODEL` + `VOLCENGINE_ARK_API_KEY`；POST `{image,width,height}`，响应 `{ok,boxes,model,elapsedMs}`。
- 云端自托管 matte：与 `/api/nail-matte` 同构，转发 `NAIL_CLOUD_MATTE_URL`/`TOKEN`。
- 共享：一次性隐私确认、会话级模式、固定低置信候选、错误脱敏。
- 限制：真实端到端待用户配置后实测。

## 6. 浏览器端美甲纹理识别接口

### 6.1 对外入口

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

- `ImagePixels`：`{width,height,data}`。
- 主要选项：`preferModel`、`manifestUrl`、`maxCandidates`、`workerTimeoutMs`、`includeLowConfidenceCandidates`、`debugOutputs`、`signal`。
- 返回：`candidates[]`、`backend`、`elapsedMs`、`modelVersion`、`warnings`。
- 候选来源：`model`、`mediapipe`、`partial-closeup`、`saliency`、`manual`、`vlm-matte`、`cloud-ark`、`cloud-matte`。
- `mask`：二值几何 + 可选软边 `alpha` + 独立 `coverageAlpha`。
- M3 粗分割内部入口：`runStageACoarse()`，仅 Stage A，供 AR 关键帧融合使用。

### 6.2 运行策略

1. Worker 默认 `preferModel=true`；直接调用需显式开启。
2. 后端按 manifest `backendPreferences`，当前生产仅 `wasm`。
3. 模型失败进入 fallback，规则候选固定低置信并隐藏于正式 UI。
4. MediaPipe/局部近景/人工候选使用透明椭圆或矩形裁剪。
5. 候选确认后 `NailAssignment[]` 返回，`ImageBitmap` 所有权转移给页面。
6. 生产 manifest 为 `nail-texture-seg-geometry64-browser-aa4-v2`，`deployed`；发布登记与切换由 `register-model-release.ts`/`switch-model-release.ts` 管理。

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

调用方须处理异常、`warnings`、超时与资源释放；取消以 `AbortError` 拒绝且不执行 fallback。

### 6.4 纹理提取接口

```ts
extractTexture(imageUrl, { x, y, w, h }): Promise<ImageBitmap>
clampTextureSize(bitmap, maxSize?): Promise<ImageBitmap>
disposeTexture(bitmap): void
disposeAllTextures(bitmaps): void
```

- 普通裁剪最大边默认 256；自动路径支持 mask、羽化、反光修复与诊断。
- `referenceIsDirected` 控制方向推断；人工 180° 翻转可撤销。
- 4×4 覆盖率与放大侧缘保护为当前默认；甲根颜色保护已接入生产渲染。
- 限制：真实相机逐指画质与长会话仍待验收。

## 7. 模型产物契约

- manifest：`public/models/nail-texture-seg/manifest.json`。
- 当前版本：`nail-texture-seg-geometry64-browser-aa4-v2`，`deploymentStatus=deployed`，`backendPreferences=["wasm"]`。
- Stage A：`geometry64-browser-v1-stage-a-512-fp32.onnx`，11,538,755 字节，SHA `0a6b842e…b4e78`。
- Stage B：`geometry64-browser-v1-stage-b-radius-presence-fp32.onnx`，1,495,223 字节，SHA `e63d50f0…97ef`。
- `stage2.mode="radial-refine"`：2048 角×129 径向，`presenceThreshold=0`，`nmsIoUThreshold=0.7`。
- `edgeRefinement`：`radial-coverage-v1`，`samples=4`。
- `scoreThreshold=0.35`，模型版本级阈值，正式阈值仍须新来源校准。
- 发布要求：manifest 校验、文件存在、张量契约一致、fixture/真实图片/浏览器/性能门、版本与回滚记录。
- 商用完成门：同一 `releaseIdentity` 全部当前门 `ok=true` 且 `decision=complete` 前保持 HOLD。

## 8. 数据集与训练接口

### 8.1 数据集契约

- 根目录：`model/datasets/nail-texture-v1`。
- 现行真值：`batch037/cumulative-training-truth-index-v5.json`，100 名义图/634 甲。
- 来源：`E:\AI Project\Codex\JiaRu_image\真实素材\美甲图片素材`，已获商业使用授权。
- 角色隔离：train/val/test/holdout 与父血缘受保护；已消费留出不回训。
- 物化与审计：`materialize-canonical-candidate-training-dataset.py`、`audit-candidate-training-input.py`、`train-yolo-seg.py --candidate-mode`。
- 限制：当前无批准发布候选；旧 val30/test100 只作受保护历史回归。

### 8.2 训练主流程

```text
素材入库与授权审计
  -> 标注/人工复核
  -> 标签审计与数据切分
  -> materialize 训练数据
  -> train-yolo-seg.py
  -> evaluate.py / assess-model-metrics.py
  -> export-onnx.py
  -> 浏览器 fixture 与性能验证
  -> 发布注册、切换与回滚验证
```

关键脚本分类见 `model/training/` 与 `scripts/`；正式候选必须使用来源隔离校准与全新正负留出。

### 8.3–8.9 当前研发口径

- 真值 v5/范围 v3：100 图/634 甲。
- 等权侧缘头五折：397/634，低于 539/634 门。
- 两端逐像素头首折：98/115。
- 浏览器上传链：634 甲一一匹配，原图 2px 严格 0/634，平均 Boundary IoU 0.316。
- 本机业务候选：几何 64 轮权重已接入 `/api/nail-matte`，仅作对照与回退。
- 现行研发与下一步只读 `docs/nail-texture-current-goal.md`；历史候选与逐轮实验见 `docs/archive/`。

## 9. 验证与质量门

基础工程门：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

- `lint`：0 problems。
- `test` 与 `build`：串行执行；含 Python 子进程时先置 Python313 于 PATH 首位。
- 纹理识别与发布另按范围执行 `scripts/verify-*.ts` 与 `audit-nail-texture-local-inference-completion.ts`。
- 移动真机验收从 `/device-benchmark` 20 次同会话样本开始；内存来自 Profiler/Instruments，完整流程见 `docs/mobile-device-acceptance-runbook.md`。
- 当前完成度审计：18 门 6 通过，`releaseIdentity=null`，`decision=hold`。

## 10. 隐私、安全与资源管理

- `/editor`、`/ar-tryon`、`/nail-analysis` 默认浏览器本地处理。
- AI 生图仅上传文字与用户主动提供的参考图；第三方数据边界以实际服务条款为准。
- `AGNES_API_KEY`、`VOLCENGINE_ARK_API_KEY` 只存服务端环境变量，文档与源码不记录真实密钥。
- `ImageBitmap`、对象 URL、MediaStream、Worker 与动画帧须在卸载或取消时释放。
- 模型权重、数据集、训练输出与可重建报告留在本地，由 `.gitignore` 隔离。
- 正式 API 上线前需补鉴权、限流、内容安全、审计与费用保护。
- `/privacy` 产品文案需补充云端识别与最新账户口径；法律合规审核待外部。

## 11. 已知限制与下一阶段

### 11.1 阻塞项

- **模型质量**：严格联合 397/634，独立来源校准与正负发布留出未建立。
- **AR 试戴**：真人实拍、四类移动真机、多机型性能与长会话验收未完成。
- **生产与发布**：浏览器业务已发布，商用完成门 HOLD。
- **来源与留出**：独立 val≥30、全新正负留出、真机与 Beta 验收待建立。
- **历史资产**：被取代轮次的过程 RAW 与部分 checkpoint 已按登记退役；完整重放前须检查保留清单。

### 11.2 未完成或占位能力

1. 真实灵感图库与内容后台；
2. 真实短信、生产部署与账户一致性治理；
3. 订单、门店、预约、支付等业务后端；
4. 正式 3D 指甲网格与物理材质试戴；
5. AI 生图供应商抽象、任务队列、持久化与配额系统；
6. 模型监控、线上质量回流与自动回滚闭环；
7. 编辑器成品共享与服务端持久项目协议。

### 11.3 外网演示与内网穿透已知限制

- `/ar-demo` 依赖访问者本机 Python demo，公网 HTTPS 下被混合内容策略拦截。
- 摄像头在有效 TLS 隧道域名下可用。
- 识别依赖 WASM；WebGPU 未启用。
- AI 生图依赖外部 API 可达性。
- 隧道域名动态变化；稳定性与资源一致性详见当日日志与运行手册。

## 12. 新模块对接登记模板

```md
### 模块名称

- 状态：已完成 / 待验证 / 进行中 / 占位 / 未完成 / 阻塞
- 入口：
- 输入：
- 输出：
- 错误与降级：
- 配置与限制：
- 当前证据：
```

## 13. 版本与变更记录

版本顺延与当日变更记录规则见 `AGENTS.md`§3.2。具体变更查 `dev-log/YYYY-MM-DD.md`；历史实验、变更与数据契约执行史查 `docs/archive/` 对应归档。
