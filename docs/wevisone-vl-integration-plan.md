# WeVisOne-VL 本地抠图接入方案

> 状态：**已按本方案实施（2026-10-28，白皮书 v1.2.163 §5.4）**；本文保留为设计与边界依据，实现与验收证据以白皮书与当日 `dev-log/2026-10-28.md` 为准。能力仍为辅助路径：默认关闭、不计正式质量门、PRODUCT HOLD 不变。
>
> 日期：2026-10-28
>
> 事实基线：技术白皮书 v1.2.163（§3 功能状态总表、§5.4 精细抠图接口、§6 浏览器识别接口、§7 模型产物契约、§10 隐私、§11.1 阻塞项）；`model/VlM_Model/README.md` 与 `server.py`／`matting.py`／`client_example.mjs` 实际源码；`src/lib/nail-texture-recognition/*` 与 `src/components/NailArtPicker.tsx` 实际实现。

## 1. 定位与结论

WeVisOne-VL 是一个**通用视觉定位 + 像素级 matting** 模型（Qwen3-VL 底座 + 独立像素解码器，int4 量化，本机 GPU），按要求接入后承担的工作是：

> 浏览器端完成快速识别后，用户在需要更精细的甲缘时**主动触发**一次本机 GPU 抠图，把软 alpha 蒙版替换回当前候选的 mask，再走既有的纹理提取链路。

它**不是**正式纹理模型，也不改变发布状态：

- 不计入正式识别成功率、Beta 直接可用率或任何发布质量门；
- 不进入训练真值、不进入模型选择、不写入生产 manifest 或 `releaseIdentity`；
- 不自动把候选提升为「高置信」；输出仍需用户逐指确认；
- 现有琥珀色「辅助定位」声明语义不变，新增的精细抠图同样属于辅助能力。

## 2. 现状核查（接入点与硬约束）

### 2.1 服务端能力（实测源码）

| 项 | 事实 |
| --- | --- |
| 端点 | `GET /health`、`GET /stats`、`POST /matte` |
| 监听 | 默认 `127.0.0.1:8008`，无 CORS、无 TLS |
| 鉴权 | `--token` / `VLM_MATTE_TOKEN`，未设置时**完全不鉴权** |
| 并发 | 队列深度 1；忙时立即 `503`（`busy: true`），不排队 |
| 超时 | 单个任务 120s |
| 请求体上限 | 12 MB（JSON，含 base64） |
| 图片限制 | 长边 ≤ 4096；`data:` URI 或**本地路径 `imagePath`** |
| 返回 | `instances[]`：`box`（原图像素）、`box01`（归一化）、`bbox`（alpha>127 外接框）、`area`、`alphaPng`（mode L 灰度 PNG，原图尺寸）、`width`/`height` |
| 坐标 | `box` 已换算到原图像素；alpha 为**整图尺寸** |
| 耗时 | 手部特写 4 枚约 14–16.5s，5 枚 512 预算约 11.6s；冷启动加载约 9.5–13.2s |
| 资源 | 显存常驻 5.26 GiB（峰值 5.79），进程内存峰值 10.1 GiB，磁盘 9.07 GB |

**安全注意（P0）**：`/matte` 接受 `imagePath` 并由 `decode_image()` 直接打开本地文件。服务只绑回环时风险限于本机进程；一旦经隧道或反代暴露，等同任意文件读取。Next 转发层**必须只允许 `image` 字段**，重建白名单 payload，禁止透传 `imagePath`。

### 2.2 项目侧接入点

- 业务主链路：`NailArtPicker` → `recognizeNailTexturesInWorker()`（正式模型未部署，实际走 MediaPipe → 局部近景 → 人工）×→ 用户确认手指 → `extractTextureFromMaskDetailed()` 提取纹理。
- 候选结构：`NailTextureCandidate`（`cx/cy/length/width/angle/score/confidence/source/mask/suggestedFinger`），`source` 现有枚举为 `model | mediapipe | partial-closeup | saliency | manual`。
- `NailMask` 语义：`{width, height, data: Uint8Array, originX, originY, scale}`；`extractTextureFromMaskDetailed` 把 mask 栅格按 `imageWidth / mask.width` 映射回整图，`originX/originY` 恒为 0（`postprocess.ts` 实际构造）。**因此服务返回的整图 alpha 可以直接当作 mask 栅格使用，不需要原点换算。**
- `data` 目前按二值使用（非零即前景），`buildFeatheredAlphaMask` 只输出 0/255 与边缘斜坡——**软 alpha 会被丢掉**，需要一处小扩展。
- 指位推导：`inferSuggestedFingers(candidateCount)` 按数量推，4 枚→`[1,2,3,4]`，≥5→`[0..4]`；**候选数量一变，全部指位错位**。
- 质量语义：规则/辅助候选固定 `confidence: "low"`，界面显示「需复核」；不得因换了 mask 来源而改写置信度。

## 3. 拓扑选择

| 方案 | 形态 | 结论 |
| --- | --- | --- |
| A. 本机自托管（推荐先做） | Next 与 Python 服务跑在同一台带 GPU 的机器；浏览器 → `/api/nail-matte` → `127.0.0.1:8008` | 与 README 的原意一致；本地开发、内网演示可用；公网部署不可用 |
| B. GPU 主机 + 云端 Next | `VLM_MATTE_URL` 指向私网/隧道上的 GPU 主机 | 需要 HTTPS、IP 白名单、token、限流与隐私改写；单卡并发 1、单图 12–16s，公网体验差，暂不建议 |
| C. 纯浏览器 | 不上传 | 不可能：4B 模型 + int4 + 5 GiB 显存，与「浏览器本地」目标冲突 |

现有云部署（腾讯云轻量 `49.233.141.42`）**没有 GPU**，因此方案 A 下该能力只能在带 GPU 的本机使用；正式站默认必须关闭入口。代码层面 A/B 完全共用，只是 `VLM_MATTE_URL` 指向不同主机，所以先按 A 实现、用配置决定是否开放。

## 4. 推荐架构与数据流

```text
用户上传图片
  → NailArtPicker 浏览器识别（现有 Worker / MediaPipe / 局部近景 / 人工）
  → 用户看到候选（低/中置信 + 琥珀辅助声明）
  → [可选] 点击「精细抠图（本机）」
      → 浏览器：原图压到长边 ≤1600 JPEG q0.85
      → POST /api/nail-matte  { image, task, query, boxes? }
      → Next 路由：白名单校验 → 身份/限流 → 转发 127.0.0.1:8008（Bearer token，150s 超时）
      → Python：VLM matting → 整图 alpha PNG + box
      → 路由：状态码映射、脱敏、截断超大响应
      → 浏览器：alpha 解码 → 「中心包含优先、IoU≥0.15 兜底」与本地候选一一匹配
      → 命中：替换该候选 mask（保留几何、指位、置信度、source 语义）
        未命中：保留本地 mask，不新增/删除候选
  → 用户确认手指 → 既有 extractTextureFromMaskDetailed 提取纹理
```

### 4.1 两种子模式

| 模式 | 触发 | 行为 |
| --- | --- | --- |
| refine（默认） | 本地已有 1–5 个候选 | 纯文本 `task=matting`（`query="指甲"`）请求整图 alpha，按「实例中心落入候选框优先、外接框 IoU≥0.15 兜底」一一匹配后**只替换 mask** |
| detect（兜底） | 本地 0 候选（裸色/透明甲常见） | `task=matting` + `query="指甲"`，把返回实例作为 `source: "vlm-matte"` 的低置信候选追加，最多 10 个，必须逐指人工确认 |

detect 模式必须显示「未自动确认，请逐一核对」，且不允许在没有任何本地复核的情况下直接进入提取。

## 5. 服务端路由契约（新增）

`src/app/api/nail-matte/route.ts`，`runtime = "nodejs"`，`maxDuration = 180`。

```ts
// GET /api/nail-matte  → 入口可见性 + 就绪状态（不触发推理）
{ enabled: boolean, ready: boolean, busy: boolean }

// POST /api/nail-matte
// 请求（仅这四个字段，其余忽略）
{
  image: string,              // data:image/(png|jpeg|jpg|webp);base64,...
  task?: "matting" | "visual_prompt",
  query?: string,             // 默认「指甲」，≤32 字符
  boxes?: number[][],         // 仅 visual_prompt（refine 已不使用）；≤10 组，原图像素
}

// 200
{
  ok: true,
  width: number, height: number,
  instances: Array<{
    index: number,
    box: number[], box01: number[], bbox: number[],
    area: number, alphaPng: string, alphaBytes: number,
    width: number, height: number,
  }>,
  omittedInstances: number,   // 超过 10 个被截断的数量（不静默丢弃）
  model: string, quant: "int4" | "none",
  elapsedMs: number,
}
```

错误映射：

| 上游 | 下游 | 语义 |
| --- | --- | --- |
| 未配置 `VLM_MATTE_URL` | `503 {degraded:true, reason:"disabled"}` | 入口隐藏，不应被调用 |
| `503 busy` | `503 {degraded:true, reason:"busy", retryAfterSeconds:3}` | 前端**不重试**，保留本地结果 |
| 504 / 超时 | `504 {degraded:true, reason:"timeout"}` | 同上 |
| 500 | `502 {degraded:true, reason:"upstream_error"}` | 不泄露上游堆栈 |
| 401 | `503 {degraded:true, reason:"auth_misconfigured"}` | 只记服务端日志，不回显 token |
| 400 | `400 {error}` | 图片/参数不合法，提示换图 |
| 413 / 超过 8 MB | `413 {error}` | 前端先压缩 |

要求：

1. **白名单重建 payload**，绝不透传客户端 JSON（杜绝 `imagePath`）。
2. 先看 `content-length` 再 `req.json()`，超限直接拒绝，避免大对象常驻内存。
3. 复用 `src/lib/rate-limit.ts` 新增 `nailMatte` 配额（建议默认 3 次/10 分钟/IP），并纳入 `ai-quota` 的游客/账号身份口径；不引入新的身份体系。
4. 复用 `src/middleware.ts` 的 Origin 校验（POST 自动覆盖）。
5. 上游错误体只保留白名单字段，`prompt`/`response` 文本不回传（体积与信息量都无必要）。

## 6. 前端改动

### 6.1 新增模块

- `src/lib/nail-texture-recognition/vlm-refinement.ts`：图片压缩、box 换算、请求编排、alpha→mask 转换、统计与警告码。
- `src/lib/nail-texture-recognition/mask-matching.ts`：纯函数 `matchMasksToCandidates(candidates, instances, { centerPadding=0.15, minIou=0.15 })`：先按「实例中心落入候选框（外扩 15%）」匹配，再按 IoU 兜底，贪心一一匹配，**同一实例不得复用**。纯 IoU≥0.3 在本批业务图实测 0/5 命中，故不再作为唯一判据。

### 6.2 alpha → NailMask 的关键细节

```ts
// 1) 单通道 PNG 在 canvas 中解码为 RGBA：R=G=B=灰度、A=255
//    因此取红通道，不能取 alpha 通道（取 A 会得到全 255）。
const gray = imageData.data[(y * width + x) * 4];

// 2) 栅格降采样到长边 ≤1024（服务端 alpha 是整图尺寸，直接按原尺寸持有会到数十 MB）
// 3) 同时保留软 alpha 与二值几何
const alpha = new Uint8ClampedArray(width * height);   // 0..255
const data = new Uint8Array(width * height);           // 0/1，阈值 128
```

`scale = imageWidth / mask.width`，`originX/originY = 0`，与 `postprocess.ts` 现有构造保持一致。

### 6.3 软 alpha 的落地（NailMask 扩展）

`NailMask` 增加可选字段 `alpha?: Uint8ClampedArray`；`buildFeatheredAlphaMask` 在存在时取 `min(softAlpha, featheredRamp)`，不存在时行为完全不变（全部现有调用方零改动）：

```ts
alpha[index] = source ? Math.min(source[index], rampValue) : rampValue;
```

若首版不想动提取器，可先按 128 阈值二值化（软边退化为现有羽化）；但这会丢掉透明甲尖的软边，而这正是该路径的主要价值，建议一并做。

### 6.4 界面与状态

在 `NailArtPicker` 侧栏新增一块「精细抠图（本机 GPU · 实验）」：

| 状态 | 文案/行为 |
| --- | --- |
| 入口不可用 | `GET /api/nail-matte` 返回 `enabled:false` → 整块不渲染 |
| 首次使用 | 一次性说明：图片会发送到**自托管的本地抠图服务**处理，仅用于本次提取；给「继续」与「取消」 |
| 进行中 | 显示已用秒数（按 12–16s 预估）、可「取消」（`AbortController`）；明确「取消不会中断服务端已开始的推理」 |
| 成功 | 「已精细处理 N/M 个甲面」；未匹配的候选保留原结果并注明 |
| 降级 | 「服务正忙/超时，已保留本地结果」——**不自动重试、不弹二次询问** |

置信度文案不变：新来源仍显示「需复核」，不出现「自动识别成功」。

### 6.5 候选来源扩展

`NailTextureCandidateSource` 增加 `"vlm-matte"`，`SOURCE_LABELS` 增加「本机精细抠图」；`regionNeedsReview()` 与琥珀声明对其实例保持为真。

## 7. 隐私与安全（必须同步的契约变更）

1. 白皮书 §10 目前写「`/editor` 上传照片默认在浏览器本地处理…当前代码尚无实际上传通道」。接入后出现**真实上传通道**（到自托管服务），必须新增一行并改写「尚无上传通道」的表述。
2. `/privacy` 页面需增加该数据流：图片 → 本机/自托管 GPU 服务 → 仅内存处理、不落盘、不转发第三方（服务自身 README 已声明不落盘，但这是服务实现而非本项目可验证的合规保证，措辞按「服务不落盘配置」写，不写成法律承诺）。
3. 默认关闭：`VLM_MATTE_URL` 未配置即无入口；云部署（无 GPU）保持未配置。
4. token 只在服务端环境变量；`.env.local.example` 只登记占位符，不写真实值。
5. 若走方案 B，必须补：TLS 终止、IP 白名单、请求体上限、token、限流、禁用 `imagePath`、日志脱敏。

## 8. 质量与发布边界（不可放宽）

- 本能力属于**第三方通用模型辅助**，不替代正式纹理模型；白皮书 §3「美甲纹理自动识别」状态仍为 PRODUCT HOLD，§7 生产 manifest 仍 `not-deployed`。
- 不产生任何可用于模型选择、阈值校准、Beta 直接可用率的统计；一次真实运行只作为**功能验收**记录在当日 dev-log，写明图片 SHA、实例数、耗时与匹配结果。
- 实例数不稳定（README 记录同图 4 vs 5）是已知现象：**不得**用「补齐到 5」或「按最高分截断」来伪造稳定性；数量不一致就如实显示并保留本地候选。
- 软 alpha 的边界质量未经原像素审核，不得表述为「甲缘更准确」；只能说「提供了更高分辨率的软边蒙版，需人工复核」。

## 9. 测试与验收计划

单元（可在 CI 跑，无需 GPU）：

1. `mask-matching`：一一匹配、IoU 边界、同实例不复用、乱序输入、空实例。
2. alpha→mask：灰度通道取值、阈值、降采样尺寸、`scale` 计算、软 alpha 保留（`min(soft, ramp)`）。
3. 路由：mock `fetch` 覆盖 200/400/401/413/503/504/超时；断言 `imagePath` 被剥离、token 不出现在响应、超限在解析前拒绝。
4. 健康检查：未配置 URL 返回 `enabled:false`。

集成（本机 GPU，人工执行，仅记功能结论）：上传一张五指清晰照片 → refine 命中 N/M → 提取纹理 → 记录实例数、IoU、耗时、服务 `/stats`。

回归：`lint`、`typecheck`、`typecheck:tests`、全量串行 `npm.cmd test`；生产构建门按既有环境限制处理（`.next` 清理守卫），不以此功能绕过。

## 10. 分阶段实施

| 阶段 | 内容 | 预估 |
| --- | --- | --- |
| P0 | `/api/nail-matte` 路由 + `nail-matte-api.ts` + 限流/超时/白名单 + 路由单测；curl 直连验证 | 0.5 天 |
| P1 | `vlm-refinement.ts` + `mask-matching.ts` + `NailMask.alpha` 扩展 + `NailArtPicker` 入口与状态 + 单测 | 1 天 |
| P2 | `/privacy` 文案、白皮书 §3/§5/§6.1/§6.4/§10 与版本顺延、`.env.local.example`、README、dev-log | 0.5 天 |
| P3 | 本机 GPU 端到端功能验收与证据记录（不构成质量门） | 0.5 天（路由级 5/5 已完成；UI 端到端 3/5）：`int4 + max_pixels=589824 + task=matting`，路由重放单图 5 实例/16.6s、5 候选全匹配，设备峰值 7817 MiB；`/ar-tryon` UI 实跑同图 5 实例/14.3s、仅 3/5 替换，2 例因本地候选几何偏移保守保留原 mask |
| P4（可选） | 方案 B：GPU 主机 + HTTPS/白名单/限流加固 | 另议 |

命名口径：2026-10-28 早前 dev-log 标题中的「P4 真机 GPU 端到端」实指本表 **P3**（端到端验收）；本表 P4 始终是可选部署方案，两者不混用。

## 11. 风险与未决项

| 风险 | 影响 | 处置 |
| --- | --- | --- |
| 云部署无 GPU | 公网用户用不到 | 默认关闭入口；需要公网上线时先定方案 B |
| 上游声明「官方限定研究用途」 | 商用范围可能受限 | 接入前按模型卡/服务条款确认；未确认前只做本机开发与内部演示 |
| 单图 12–16s、并发 1 | 不能用于实时 AR | 只放离线提取路径，不进 `/ar-tryon` 实时帧链路 |
| 整图 alpha 体积 | 响应可达数 MB/实例 | 输入压到 ≤1600、栅格 ≤1024、实例 ≤10 并显式报告截断 |
| 实例数不稳定/误检 | 可能把皮肤或装饰当甲面 | 一一匹配 + 人工确认 + 保留本地候选，不做数量补齐 |
| `imagePath` 任意文件读取 | 暴露即高危 | 转发层白名单；方案 B 前先改服务端 |
| 软 alpha 未经审核 | 可能过度自信 | 文案只称「更精细的软边蒙版，需复核」，不宣称准确率 |

## 12. 不做的事

- 不把该模型产物写入 `public/models/`、生产 manifest 或发布登记；
- 不把其输出作为训练/验收真值，不参与阈值校准；
- 不替换或降级现有正式识别入口与琥珀提示；
- 不把「本机服务可用」表述为「自动识别已通过」或解除 PRODUCT HOLD；
- 不在正式站默认开启上传通道。
