# 甲如：集成准备清单（接口清单 · 工具 · 问题与漏洞优先级 · 测试标准）

> 建立日期：2026-10-27 · 状态：**本轮已执行修复并通过验证的部分在 §1 逐条标注**
>
> 用途：为把 `docs/product-ui-redesign-proposal.md` 的新前端交互设计正式集成到业务流程做准备，同时明确「已检出问题」的来源、接口范围、测试通过标准与漏洞优先级，据此确定修复与集成的执行顺序和验收条件。
>
> 事实优先级按白皮书 §1.2：当前工作区源码／机器可读报告／自动化测试结果 > 白皮书 > 其他文档。本文件所有「当前状态」均来自 2026-10-27 本轮实测或源码逐行复核。

---

## 1. 问题清单与来源

### 1.1 来源清单（权威入口）

| 来源 | 路径 | 提供的问题类别 |
| --- | --- | --- |
| S1 安全审计报告 | `docs/security-audit-2026-09-23.md`（含 2026-09-24 实测复核 §6） | 1 Critical / 3 High / 5 Medium / 4 Low，共 13 项 |
| S2 项目问题报告 | `docs/issue-report-2026-10-16.md` | 产品修复、模型主线阻断、延后项（e2e 覆盖薄） |
| S3 技术白皮书 | `docs/technical-whitepaper.md` §3／§4／§10／§11.1—§11.4 | 功能状态、接口契约、已知限制、隐私文案缺口 |
| S4 清理任务卡 | `docs/cleanup-tasks.md` | lint 0 problems 目标、残留文件 |
| S5 开发日志 | `dev-log/2026-10-26.md` 第 7—8 项 | 工程门基线、文档漂移四项 |
| S6 交互设计提案 | `docs/product-ui-redesign-proposal.md` §1 | 面向正式站的 6 类结构性问题 P1—P6 |
| S7 本轮机器检测 | lint / typecheck / audit:encoding / test / build 实测 | 可复现的当前缺陷与基线 |

### 1.2 安全审计 13 项：当前复核状态（S1 → S7）

> 审计日期 2026-09-23，此后有多轮修复。下表逐项给出 2026-10-27 复核结论与证据位置，避免按旧报告直接排期。

| 编号 | 项 | 状态 | 复核证据 |
| --- | --- | --- | --- |
| C1 | Next 16.2.9 Windows RCE（CVE-2026-75604） | **已修复** | `next` 与 `eslint-config-next` 均 16.3.6；构建输出 `▲ Next.js 16.3.6 (Turbopack)` |
| H1 | 开发模式验证码明文回传 | **已修复** | `src/lib/auth/sms.ts:52-53`：`NODE_ENV=production` 直接禁用 + `JIARU_DEV_SMS=1` 显式开关；`:88` 未配置服务商时拒绝发送 |
| H2 | 全站安全响应头缺失 | **部分** | `next.config.ts` 已加 `nosniff` / `X-Frame-Options` / `Referrer-Policy` / `COOP` / `X-DNS-Prefetch-Control`；**CSP 与 HSTS 仍缺**（见 §1.4 N-2） |
| H3 | 内部错误原文回显 | **已修复** | `src/lib/auth/http.ts:47-55` 固定文案「服务器内部错误，请稍后重试」并只写服务端日志；三条路由 grep `服务器错误` 零命中 |
| M1 | 无 IP 限流 | **已修复** | `src/lib/rate-limit.ts` 令牌桶；`captcha 30/5min`、`requestCode 5/10min`、`verifyCode 20/10min`、`bindPhone 10/10min`、`oauthStart 20/10min` |
| M2 | refresh token 不轮换 | **已修复** | `src/lib/auth/service.ts:129-167`：`jti` 轮换 + 宽限位（并发安全）+ 宽限外判重放并吊销整条会话 + 审计日志 |
| M3 | 无 CSRF 防护 | **已修复** | `src/middleware.ts`：`matcher: /api/:path*`，非 GET/HEAD/OPTIONS 校验 `Origin` 白名单 |
| M4 | 已登录用户可枚举已注册手机号 | **已修复** | `src/lib/auth/service.ts:339` 先 `consumeValidatedCode(phone, code)`，`:340` 才查归属 |
| M5 | 游客配额与身份伪造 | **已修复（本轮补齐最后一项）** | 身份伪造：`ai-quota.ts:120-127` + `rate-limit.ts:81` 仅在 `JIARU_TRUST_PROXY=1` 时采信代理头；`=0` 关闭游客生成：本轮 `intFromEnv` 修复（§1.3 E-2） |
| L1 | `getClientIp` 无条件信任 XFF | **已修复** | `src/lib/auth/cookies.ts:52`、`src/lib/rate-limit.ts:81`、`src/lib/request-origin.ts:19` 共用 `JIARU_TRUST_PROXY` 门禁 |
| L2 | `ar-demo` iframe 无 sandbox | **已修复** | `src/app/ar-demo/page.tsx:39` `sandbox="allow-scripts allow-same-origin allow-forms allow-popups"` |
| L3 | JWT 未校验 iss/aud | **已修复** | `src/lib/auth/jwt.ts:98-100` 校验 `JWT_ISSUER` / `JWT_AUDIENCE` |
| L4 | captcha Map 无条数上限 | **已修复** | `src/lib/auth/captcha.ts:19,155` `CAPTCHA_MAX_PENDING = 5000` 硬上限 + 过期清理 |

### 1.3 本轮修复项（已执行并通过验证）

| ID | 问题 | 来源 | 修复 | 验证 |
| --- | --- | --- | --- | --- |
| **E-1** | `npm.cmd run lint` 退出码 1、2654 条问题；其中约 99% 来自 `.backup-consumer-*/restored-app/**`（备份内的 `.next` 构建产物与 vendor bundle）与 `output/**`——两者均由 `.gitignore` 隔离、从不入库，但默认 `eslint` 无参数运行会扫全工作区 | S5 + S7 | `eslint.config.mjs` 的 `globalIgnores` 与 `.gitignore` 对齐，新增 `output/**`、`.backup-consumer-*/**` | lint **2654 → 2 → 0 problems**，退出码 0 |
| **E-2** | `AI_QUOTA_GUEST_DAILY=0` 无法生效：审计 §M5 明确要求"直接关闭游客生成（`AI_QUOTA_GUEST_DAILY` 无法设 0，需代码支持）"，而 `intFromEnv` 的 `parsed < 1` 把 `0` 回退成默认 5，运营无法关停匿名付费接口 | S1-M5 | `src/lib/ai-quota.ts`：`intFromEnv` 增加 `allowZero`，三条"次数上限"接受 `0`；并发上限仍要求 ≥1；`0` 态改用"已关闭"文案而非"已用完" | `tests/ai-quota-guard.test.ts` 11 → **14 项全过**，新增 3 组零值/并发用例 |
| **E-3** | `src/app/login/page.tsx:163` `window.location.href` 警告（S2 §1.3 记录的"既有登录页警告"） | S2 + S7 | 定向 `eslint-disable` + 说明注释：目标是 Route Handler（服务端 302 到微信授权页），`router.push()` 会取 RSC 负载而非跟随重定向，行为保持不变 | lint 0 |
| **E-4** | `design/consumer-v1/app.mjs` `respawnRipple` 死代码（§8.11 整页重渲染清理后的残留补偿函数） | S7 | 全仓仅剩定义、零调用点 → 删除 | lint 0；`node --check` 语法通过 |
| **E-5** | 白皮书 §5.1 仍写游客身份键为「`x-forwarded-for` 首段」，与 M5 修复后的源码不符 | S3 vs 源码 | 修订 §5.1，补登记 `JIARU_TRUST_PROXY` 口径与 `guest:<hash("unknown")>` 共享桶 | 白皮书 v1.2.157 |
| **E-6** | 白皮书 §5.1 未登记配额 `0` 语义 | S3 vs 源码 | 补"配额环境变量（v1.2.157 修订）"段：旧值（`0` 回退 5）→ 新值（`0` 关闭），并记录并发仍 ≥1 | 白皮书 v1.2.157 |
| **E-7** | 白皮书 §9 工程门只有命令清单，无通过标准与环境陷阱 | S3 + S7 | 补通过标准：lint 必须 0 problems；test/build 串行；build 沙箱批量删除守卫的处理方式；含裸 `python` 子进程的 PATH 要求 | 白皮书 v1.2.157 |

### 1.4 未决项（已识别，本轮不修，按 §5 排期）

| ID | 问题 | 来源 | 为什么不本轮修 |
| --- | --- | --- | --- |
| **N-1** | e2e 覆盖薄：仅 3 个 Playwright 规格（`profile-edit`、`review11-browser-regression` + `helpers`/`seed-auth`） | S2 §3 | 需要可运行的浏览器会话与真实设备门禁；应随设计提案 §13.3 的 T1—T6 步数断言一起补，单独补会与设计改造重复返工 |
| **N-2** | CSP 与 HSTS 仍缺（H2 残留） | S1-H2；`next.config.ts:15` 注释 | 审计明确要求"严格 CSP 须验证 WASM、worker、blob 及摄像头兼容性后另行实施"；HSTS 依赖 HTTPS 域名（当前公网地址为 HTTP，§11.4）。属**有意为之的未决**，不是遗漏 |
| **N-3** | 未设 `JIARU_TRUST_PROXY=1` 时，`resolveClientIp` 返回 `"unknown"`，所有客户端共享同一个限流桶与游客配额桶 | S7 复核 `rate-limit.ts:81` | 是审计修复的显式取舍（"宁紧勿松"）。但直连部署下 captcha 30/5min 为**全局**共享，需部署侧明确决策：要么在 Nginx 后启用 `JIARU_TRUST_PROXY=1`，要么放宽兜底。不能由前端单方面改 |
| **N-4** | `src/middleware.ts` 约定在 16.3.6 已提示废弃、建议迁移 `proxy`（构建输出已显示 `ƒ Proxy (Middleware)`） | S5；本轮构建输出 | 属框架约定迁移，需评估 `matcher` 与 Origin 校验在 `proxy.ts` 下的等价性后再动，避免改动鉴权拦截面 |
| **N-5** | 文档漂移：README 模型状态停留在 candidate29／循环015 且称"生产构建仍待解决"；`docs/technical-architecture.md` 仍写 Next 16.2.9；`/privacy` 文案与已有账户体系、Seedream 数据流不一致 | S5 第 8 项；S3 §10 | 属文档同步，不影响集成接线；但 `/privacy` 涉及对外承诺，需产品口径确认后再改，不能由工程单方面重写 |
| **N-6** | 游客仍可直接触达付费生图接口，唯一硬约束为全局 200 次/日熔断且为进程内存态、重启清零 | S1 §6.3 | 本轮已交付关闭手段（E-2：`AI_QUOTA_GUEST_DAILY=0`），是否关停属部署与运营决策 |
| **N-7** | 设计提案 P4 依赖的服务端能力缺失：任务队列与结果持久化（§11.3-5）、作品/收藏云同步（§11.3-2） | S3 §11.3 | 需要后端，纯前端无法补齐；UI 不得预留可点击的假入口 |
| **N-8** | webpack 构建出现 `Circular dependency between chunks with runtime (123, webpack-runtime)` 告警 | S7（本轮 `--webpack` 构建输出） | 只在诊断用的 webpack 路径出现，默认 Turbopack 构建未见；属构建器差异，需先确认 Turbopack 构建门闭合后再评估是否处理 |

---

## 2. 现有接口清单

### 2.1 页面路由（12 个，构建输出为权威来源）

| 路由 | 渲染 | 页面角色 | 跨页入参 |
| --- | --- | --- | --- |
| `/` | ○ Static | 首页与功能入口 | — |
| `/gallery` | ○ Static | 灵感图库 | — |
| `/ai-generate` | ○ Static | AI 生图（Agnes / Seedream pro / lite） | `?gallery=<id>`、`?collect=<id>` |
| `/ar-tryon` | ○ Static | AR 试戴（纯色／纹理） | `?gallery=<id>`、`?collect=<id>` |
| `/nail-analysis` | ○ Static | 个性化分析推荐 | — |
| `/editor` | ○ Static | 图片试色编辑器 | `?gallery=<id>`、`?preset=<色名>` |
| `/login` | ○ Static | 登录／注册 | — |
| `/account` | ○ Static | 账号与偏好 | — |
| `/privacy` | ○ Static | 隐私说明 | — |
| `/ar-demo` | ○ Static | 独立 AR 演示桥接（iframe，外网不可用，§11.4） | `?embedded=` |
| `/device-benchmark` | ○ Static | 移动真机基准 | — |
| `/_not-found` | ○ Static | 404 | — |

### 2.2 API 路由（15 个，全部 ƒ Dynamic）

| 分组 | 路由 | 鉴权 | 限流 |
| --- | --- | --- | --- |
| 认证 | `POST /api/auth/request-code` | 无 | requestCode |
| | `POST /api/auth/verify-code` | 无 | verifyCode |
| | `GET /api/auth/captcha` | 无 | captcha |
| | `POST /api/auth/refresh` | refresh Cookie | — |
| | `POST /api/auth/logout` | access Cookie | — |
| | `POST /api/auth/bind-phone` | 登录 | bindPhone |
| | `GET /api/auth/oauth/wechat` | 无 | oauthStart |
| | `GET /api/auth/oauth/wechat/callback` | 无（state 校验） | — |
| | `GET /api/auth/oauth/wechat/status` | 无 | — |
| 档案 | `GET/PATCH /api/me` | 登录 | — |
| | `GET/POST /api/me/identities` | 登录 | — |
| | `DELETE /api/me/identities/[provider]` | 登录 | — |
| | `GET/PATCH /api/me/improvement` | 登录 | — |
| 生图 | `POST /api/generate-ai` | 可选（游客可调用，见 N-6） | AI 配额 |
| | `POST /api/generate-seedream` | 可选（同上） | AI 配额 |

中间件：`src/middleware.ts`，`matcher: /api/:path*`，对非 GET/HEAD/OPTIONS 校验 `Origin`；微信回调路径显式豁免。

### 2.3 前端组件契约（`src/components/`）

| 组件 | 关键 Props / 导出 | 消费页面 |
| --- | --- | --- |
| `AppShell` | `{ eyebrow, title, description, children, wide?, shiftUp? }` | 全部 App Router 页面外壳 |
| `Header` | 无参；内部固定 5 项导航（首页／灵感／AI 设计／AR 试戴／个性化）+ 登录 + 上传试色 CTA | `AppShell` |
| `UploadButton` | `{ onUpload }` | `/editor`、`/nail-analysis` |
| `NailCanvas` | `{ imageUrl, selectedColor?, nailColors?, activeFinger?, brushSize }` | `/editor` |
| `ColorPalette` | `{ selectedColor, onSelectColor }` | `/editor`、`/ar-tryon` |
| `TextureCropper` | `{ imageUrl, onConfirm, onCancel }` | `/ar-tryon` |
| `NailArtPicker` | `{ imageUrl, onConfirm, onCancel }`，产出 `NailAssignment { texture, diagnostics?, finger }` | `/ar-tryon` |
| `ArView` | `{ nailColors, nailTextures?, mode?, nailAdjustments? }`，`NailFitAdjustment { lengthScale 0.75–1.40, widthScale 0.70–1.45, rootOffset ±0.20 }` | `/ar-tryon` |
| `NailAnalysisForm` / `NailAnalysisResult` | `{ value, onChange, disabled? }` / `{ result }` | `/nail-analysis` |
| `ProfileEditor` / `ProfileSkeleton` | `{ user, onSaved }` | `/account` |
| `GalleryGrid` / `GalleryInspirationCard` | 内部读 `GALLERY_IMAGES` | `/gallery`、`/editor` |
| `Icon` | `{ name: IconName }`——全站内联 SVG，禁用 emoji | 全站 |
| `ImprovementProgramToggle` | 无参；写 localStorage + `/api/me/improvement` | `/privacy`、`/account` |
| `AmbientMotion` | 无参；环境动效 | `AppShell` |

约定缺口（集成时必须先补）：`nailColors`／`nailTextures` 与 `NailAssignment.finger` 只是普通数组与 `number`，**类型层未强制长度 5 或索引 0..4**（白皮书 §4.5 已登记），调用方需自行校验。

### 2.4 Worker 与识别库契约

```ts
// §6.3 Worker 消息契约
interface RecognizeNailTextureRequest {
  id: string; imageBitmap: ImageBitmap; maxCandidates: number;
  workerTimeoutMs?: number; includeLowConfidenceCandidates?: boolean;
  preferModel: boolean; manifestUrl?: string;
}
interface RecognizeNailTextureResponse {
  id: string; candidates: NailTextureCandidate[];
  backend: "model" | "fallback"; elapsedMs: number;
  warnings: string[]; modelVersion?: string; modelInfo?: NailTextureModelInfo;
}
// §6.4 纹理提取
extractTexture(imageUrl, { x, y, w, h }): Promise<ImageBitmap>
clampTextureSize(bitmap, maxSize?): Promise<ImageBitmap>
disposeTexture(bitmap): void
disposeAllTextures(bitmaps): void
```

调用方必须在超时／取消／卸载／换图时释放 `ImageBitmap` 与 Worker；必须分别处理异常与 `warnings`，不能只检查是否返回候选。正式模型 `deploymentStatus: "not-deployed"`，会话创建前返回 `model_not_deployed` 并走 fallback。

### 2.5 存储与运行时资产

| 项 | 位置 / 键 | 说明 |
| --- | --- | --- |
| 收录图库 | IndexedDB `jiaru-gallery` / store `collects` | 浏览器本地，跨设备不同步 |
| 原型偏好（设计提案） | localStorage `jiaru-consumer-design-v1` | 仅 `design/consumer-v1` 原型，不读旧版键 |
| 改进计划开关 | localStorage + `/api/me/improvement` | 账号与设备双向同步未实现（§10） |
| 用户库 | SQLite `data/jiaru-user.db`（`JIARU_DB_PATH` 可覆盖） | 生产换 Postgres 只需替换 `src/lib/auth/db.ts` |
| MediaPipe 资产 | `public/vendor/mediapipe/hands/` | 同源加载，部署不可缺失 |
| 模型 manifest | `public/models/nail-texture-seg/manifest.json` | `deploymentStatus: not-deployed` |
| 图库素材 | `public/nail-gallery/ai-look-1..6.jpg` | Seedream pro 生成，AI 素材常显标识 |

### 2.6 环境变量（源码实际读取）

| 变量 | 用途 |
| --- | --- |
| `AGNES_API_KEY` / `AGNES_API_BASE_URL` / `AGNES_IMAGE_MODEL` | Agnes 生图 |
| `VOLCENGINE_ARK_API_KEY` / `ARK_BASE_URL` / `ARK_SEEDREAM_PRO_MODEL` / `ARK_SEEDREAM_LITE_MODEL` / `ARK_IMAGE_WATERMARK` | Seedream 生图 |
| `AI_QUOTA_GUEST_DAILY` / `AI_QUOTA_USER_DAILY` / `AI_QUOTA_GLOBAL_DAILY` / `AI_QUOTA_GLOBAL_CONCURRENCY` | 生成配额（前三条支持 `0`＝关闭，并发须 ≥1） |
| `JWT_SECRET` / `JIARU_REFRESH_GRACE_SEC` / `JIARU_DB_PATH` | 会话与存储 |
| `SMS_PROVIDER` / `JIARU_DEV_SMS` | 短信验证码 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信 OAuth |
| `JIARU_TRUST_PROXY` | 是否采信代理头（`1` 才采信） |
| `JIARU_ALLOWED_ORIGINS` | CSRF Origin 白名单附加项 |
| `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL` | 唯一公开变量，不含凭据 |

### 2.7 URL 参数契约（设计提案 §3.2 的收敛目标）

| 现状 | 提案目标 | 兼容要求 |
| --- | --- | --- |
| `/editor?gallery=` | `/editor?look=<id>&from=gallery` | 旧参数继续解析 |
| `/editor?preset=` | `/editor?look=<id>&from=analysis` | 旧参数继续解析 |
| `/ai-generate?gallery=\|?collect=` | `/ai-generate?look=<id>&from=<route>` | 旧参数继续解析 |
| `/ar-tryon?gallery=\|?collect=` | `/ar-tryon?look=<id>&from=<route>` | 旧参数继续解析 |

兼容层为纯前端映射；现有测试与文档中的旧 URL 行为必须保持一致，不得因集成而破坏 §4 路由契约。

---

## 3. 可用工具清单

### 3.1 npm 脚本（`package.json`）

| 类别 | 脚本 | 用途 |
| --- | --- | --- |
| 开发／构建 | `dev`、`build`、`start` | `--experimental-https` 开发；生产先 `build` 再 `start` |
| 静态检查 | `lint`、`typecheck`、`typecheck:tests`、`audit:encoding` | ESLint（默认扫全工作区）、双 tsconfig 类型检查、文本编码审计 |
| 测试 | `test`、`test:ci` | 全量 `tests/*.test.ts`（`--test-concurrency=1`）；CI 为 13 个稳定套件 |
| 就绪度与审计 | `audit:mvp-readiness`(+`:deferred`/`:refresh`)、`audit:nail-texture-completion` | MVP 就绪、端侧推理完成度审计 |
| 证据构建器 | `build:nail-texture-device-acceptance`、`build:nail-texture-mobile-memory`、`build:nail-texture-beta-review`、`build:nail-texture-release-product-quality`、`build:nail-texture-failure-cases` | 真机验收、内存原始采样、Beta 复核、发布质量、失败案例 |

### 3.2 `scripts/*.ts` 工具（42 个，按用途分组）

| 组 | 工具 |
| --- | --- |
| 校验（verify-*） | `verify-model-artifact`、`verify-model-output-fixture`、`verify-browser-integration`、`verify-recognition-performance`、`verify-recognition-memory`、`verify-texture-quality-gate`、`verify-real-model-readiness`、`verify-training-release`、`verify-evaluation-artifacts`、`verify-nail-detection`、`batch-verify-nail-detection`、`run-real-model-final-audit` |
| 审计（audit-*） | `audit-text-encoding`、`audit-release-rollback`、`audit-nail-texture-mvp-readiness`、`audit-nail-texture-local-inference-completion`、`audit-failure-classification` |
| 构建（build-*） | `build-model-output-fixture`、`build-nail-detection-fixture`、`build-nail-texture-{device-acceptance,mobile-memory-raw,beta-review,release-product-quality,user-failure-cases}`、`build-real-model-first-run-record`、`build-release-decision-report`、`build-release-history-manifest`、`build-release-trace-index`、`build-initial-release-trace-draft`、`build-active-learning-release-trace-draft`、`build-debug-sample-active-learning-handoff`、`build-reviewed-batch-release-handoff` |
| 发布治理 | `register-model-release`、`switch-model-release`、`promote-approved-release`、`run-release-governance-pipeline`、`run-training-release-pipeline`、`register-release-trace-index`、`compare-training-releases`、`compare-nail-debug`、`summarize-failure-cases`、`refresh-nail-texture-mvp-readiness` |

> `scripts/**` 在 `eslint.config.mjs` 中属 `globalIgnores`（"本地冻结证据与一次性审核脚本单独验真"），其正确性由 `npm.cmd test` 中的对应测试守护，不进 lint。

### 3.3 测试与浏览器资产

| 资产 | 数量 | 说明 |
| --- | --- | --- |
| `tests/*.test.ts` | 332 个文件 | 本轮全量 **1202/1202 通过**（修复后复跑见 §6） |
| `test:ci` 套件 | 13 个 | 可用稳定夹具／临时目录独立执行；历史 83/83 |
| e2e（Playwright） | 3 个规格 + `helpers.ts` / `seed-auth.ts` | 覆盖薄弱（N-1） |
| 设计原型预览 | `node scripts/serve-consumer-design.mjs` → `http://127.0.0.1:4318` | 本机 prototype，`design/consumer-v1/`，未注册正式路由 |
| 设计原型验证脚本 | `output/design-verify-*.mjs` 等（本地，不入库） | 新拟态 80/80、动效 93 项、就地更新 49 项等历史记录 |

---

## 4. 漏洞与缺口优先级

### 4.1 优先级定义

| 级别 | 定义 | 处置要求 |
| --- | --- | --- |
| **P0** | 直接导致安全事件、数据越权、资金损失，或使质量门/工程门失效 | 本轮修完并复验，不得延后 |
| **P1** | 影响集成接线正确性、或使既有契约与源码/文档不一致 | 集成开始前必须闭合 |
| **P2** | 影响可维护性、可观测性或后续效率，不影响当前功能正确性 | 集成同批次处理 |
| **P3** | 依赖外部系统、真实设备或产品决策，工程侧无法单方面闭环 | 登记为未决，给出触发条件与责任人边界 |

### 4.2 优先级表

| 级别 | 项 | 来源 | 状态 |
| --- | --- | --- | --- |
| P0 | C1 Next RCE | S1 | 已修复（升级前） |
| P0 | H1 验证码明文回传 | S1 | 已修复 |
| P0 | H3 错误原文回显 | S1 | 已修复 |
| P0 | M3 CSRF | S1 | 已修复 |
| P0 | M4 手机号枚举 | S1 | 已修复 |
| P0 | **M5 游客配额无法关闭** | S1 | **本轮修复（E-2）** |
| P0 | L1 XFF 信任 / L2 iframe / L3 iss-aud / L4 Map 上限 | S1 | 已修复 |
| P1 | **E-1 lint 门禁失效**（2654 条噪音，退出码 1） | S5/S7 | **本轮修复** |
| P1 | **E-5 / E-6 / E-7 白皮书与源码不一致** | S3 | **本轮修复** |
| P1 | M2 refresh 轮换 | S1 | 已修复（升级前） |
| P1 | M1 IP 限流 | S1 | 已修复（升级前） |
| P2 | **E-3 登录页警告**、**E-4 原型死代码** | S2/S7 | **本轮修复** |
| P2 | H2 残留：CSP / HSTS | S1 | **未决（N-2）**——需先验证 WASM/worker/blob/摄像头兼容；HSTS 依赖 HTTPS 域名 |
| P2 | N-3 未设可信代理时全局共享限流/配额桶 | S7 | **未决**——需部署侧决策，不能前端单方面改 |
| P2 | N-4 `middleware` → `proxy` 约定迁移 | S5 | **未决**——需评估 Origin 校验等价性 |
| P2 | N-1 e2e 覆盖薄 | S2 | **未决**——随设计提案 §13.3 步数断言一并补 |
| P3 | N-5 文档漂移（README / technical-architecture / `/privacy`） | S5/S3 | **未决**——`/privacy` 涉及对外承诺，需产品口径 |
| P3 | N-6 游客可触达付费接口 | S1 §6.3 | **未决**——关闭手段已交付（E-2），是否关停为运营决策 |
| P3 | N-7 服务端能力缺失（任务队列、云同步） | S3 §11.3 | **未决**——依赖后端；UI 不得预留假入口 |

> **不可放宽项（任何级别都不得因集成而降低）**：正式纹理模型 PRODUCT HOLD；源图筛选与完整 mask 原分辨率审核；来源隔离与冻结测试集角色；真机/Beta/发布质量门；数据角色与训练授权边界。

---

## 5. 修复与集成的执行顺序

| 阶段 | 内容 | 依赖 | 门禁 |
| --- | --- | --- | --- |
| **R0（本轮已完成）** | E-1 门禁修复、E-2 配额零值、E-3 登录页、E-4 死代码、E-5/E-6/E-7 白皮书同步 | 无 | §6 全项通过 |
| **R1 集成前置** | ① 类型层补齐 5 槽位约束（`nailColors`/`nailTextures`/`finger`）；② N-4 评估 `middleware`→`proxy`；③ N-3 部署侧决策并落配置；④ 设计提案 **P0**（壳层与 12 状态组件） | R0 | 类型检查通过；`Origin` 拦截等价性回归；lint 0 |
| **R2 主线串联** | 设计提案 **P1**（`?look=` 收敛 + 兼容层 + Mission Bar + 批量配色） | R1 | 旧 URL 行为零回归；§6 全项通过 |
| **R3 移动与无障碍** | 设计提案 **P2**（工具坞、安全区、键盘避让、焦点、reduced-motion） | R1 | 触控与键盘回归；axe 严重/中等 0 |
| **R4 覆盖补齐** | N-1：按设计提案 §13.3 的 T1—T6 步数断言补 e2e；方案库 `/looks`（设计提案 P3） | R2/R3 | Playwright 关键路径绿；步数确定性（3 次标准差 0） |
| **R5 依赖后端** | N-2 CSP（先 Report-Only 再强制）、N-7 任务队列与云同步 | 后端/HTTPS 域名 | CSP 报告零阻断后转强制；新接口按 §1.3 同步白皮书 |
| **R6 文档与合规** | N-5：README、`technical-architecture.md`、`/privacy` | 产品口径确认 | 文档与源码一致；`/privacy` 与实际数据流一致 |

排序原则：**先恢复门禁可信度（R0），再闭合契约不一致（R1），再做纯前端集成（R2—R4），依赖外部系统的排最后（R5—R6）**。任何阶段不得以降低质量门换取进度。

---

## 6. 测试通过标准

### 6.1 逐命令通过线

| 命令 | 通过标准 | 本轮实测 |
| --- | --- | --- |
| `npm.cmd run lint` | **0 problems（0 error / 0 warning）**，退出码 0 | 修复前 2654 problems（exit 1）→ **修复后 0 problems（exit 0）** |
| `npm.cmd run typecheck` | 退出码 0，无输出 | **0** |
| `npm.cmd run typecheck:tests` | 退出码 0 | 见 §6.2 |
| `npm.cmd run audit:encoding` | `failures: []` | **`failures: []`** |
| `npm.cmd test` | `fail 0`、`skipped 0`、`cancelled 0`，退出码 0 | 修复前 **1202/1202**；修复后 **1205/1205**（新增 3 组配额零值用例） |
| `npm.cmd run test:ci` | 13 套件全过，0 跳过 | **83/83** |
| `npm.cmd run build` | 退出码 0，输出完整路由清单且与 §2.1/§2.2 一致 | 修复前基线 **exit 0**（路由清单完整）；**修复后未闭合，见 §6.4** |

### 6.2 执行约束（写入白皮书 §9）

1. `npm.cmd test` 与 `npm.cmd run build` **必须串行**；并行高负载会产生临时目录或进程竞争型假失败。并行失败时先逐文件串行复验，只有串行结果可作为阶段验收结论。
2. 含裸 `python` 子进程的命令（含 `npm.cmd test` 与 `audit:nail-texture-completion`）必须把 `C:\Users\YaoYinyu\AppData\Local\Programs\Python\Python313` 显式置于当前进程 `PATH` 首位；默认 Python 缺依赖造成的失败保留为环境失败，修正环境后串行重跑。
3. Windows 下必须显式使用 `npm.cmd`，不得调用裸 `npm`。
4. `npm.cmd run build` 在带批量删除守卫的沙箱中可能因 `.next/turbopack` 一次性删除超 500 文件而失败（`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]`）。这是**宿主环境限制而非项目缺陷**：先用 PowerShell `Remove-Item -Recurse -Force .next` 清理后串行重跑，不得据此放宽断言或跳过构建。
5. 新增本地产物目录必须同步进 `eslint.config.mjs` 的 `globalIgnores`，不得靠"基线有噪音"放行。
6. `next build --webpack` **不能充当构建门**：默认堆在静态生成阶段 OOM（与 `docs/issue-report-2026-10-16.md` §1.3 记录一致）；提高 `--max-old-space-size` 后会出现"编译完成但不进入静态生成、无路由清单"的早退（退出码 0 具有误导性）；继续加大会触发栈溢出（`0xC00000FD`）。只有默认 Turbopack 构建输出完整路由清单且退出码 0 才算通过。

### 6.4 构建门本轮未闭合（如实记录）

| 时间 | 命令 | 结果 |
| --- | --- | --- |
| 修复前基线 | `npm.cmd run build`（先清 `.next`） | **exit 0**，输出 12 页面 + 15 API 路由 + `ƒ Proxy (Middleware)`，即 §2.1/§2.2 清单 |
| 修复后第一次 | `npm.cmd run build` | exit 1，`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] count:500 threshold:500 target=.next/turbopack`——宿主沙箱批量删除守卫，**非项目缺陷** |
| 修复后第二次 | `Remove-Item -Recurse -Force .next` 后重跑 | 清理命令三次因审批超时未执行，未取得结果（不绕过审批重试） |
| 修复后第三次 | `npm.cmd run build -- --webpack` | 编译有告警，随后 `FATAL ERROR: Committing semi space failed. Allocation failed - JavaScript heap out of memory`（exit 134），与既有记录一致 |
| 修复后第四次 | `--max-old-space-size=8192 --webpack` | 退出码 0 但输出仅到 `Compiled with warnings`，**无静态生成、无路由清单** → 不认定为通过 |
| 修复后第五次 | `--max-old-space-size=12288 --webpack` | 栈溢出 `0xC00000FD` |

**结论**：修复后的生产构建门**本轮未闭合**。原因是宿主环境限制与 webpack 路径的既有内存问题，均非本次修复引入；本轮修复内容已由 lint 0、双 typecheck 0、编码审计 0、全量测试 1205/1205、CI 套件 83/83 覆盖，且 `design/consumer-v1/app.mjs` 经 `node --check` 语法校验通过。**须在下一次可清理 `.next` 的环境中串行重跑 `npm.cmd run build`（默认 Turbopack）后闭合此门**，不得以本表任何一行替代。原基线成功记录保留在 `output/build-baseline-20261027.txt`，本轮失败记录保留在 `output/build-verify-*.txt`。

### 6.3 集成阶段的附加通过标准

| 项 | 通过线 | 来源 |
| --- | --- | --- |
| 路由兼容 | §2.7 旧参数行为零回归，相关测试全过 | 设计提案 §3.2 |
| 状态覆盖 | 12 类状态在涉及的每个页面都有实例，覆盖率 100% | 设计提案 §9.1 |
| 就地更新 | 6 类交互不触发整页重渲染或滚动重置 | 设计提案 §8.2-4 |
| 降级声明 | fallback／AI 素材／未验收能力声明常显且不可关闭 | 白皮书 §4.6 |
| 步数确定性 | 关键路径 3 次运行步数标准差 = 0 | 设计提案 §13.3 |
| 包体 | 共享 UI 层 gz 增量 ≤30KB | 设计提案 §13.5 |

---

## 7. 新前端交互设计的接线点

| 设计提案项 | 依赖的现有接口 | 风险 |
| --- | --- | --- |
| 左 rail / 底部 tab（P0） | `AppShell` props、`Header` 导航数组、`styles` CSS Modules | 低：仅壳层 |
| 12 状态组件（P0） | 上传校验（`image-upload-validation.ts`）、摄像头七步诊断（`§4.5`）、`auxiliaryDetectionNotice()`、AI 四态 | 中：需与各页现有状态一一映射，不得改变既有文案语义 |
| `?look=` 收敛（P1） | §2.7 四套旧参数 + `gallery-bridge.ts` / `gallery-collection.ts` | 中：兼容层失效会破坏图库→AR/AI 链路 |
| Mission Bar 与草稿（P1） | 暂无持久层；首期用 IndexedDB（与 `jiaru-gallery` 同库不同 store） | 中：必须明示"仅本机"（N-7） |
| 批量配色（P1） | `ColorPalette`、`NailCanvas.nailColors` | 低：需先补 5 槽位类型约束 |
| 工具坞与安全区（P2） | `ArView`、`NailCanvas` 布局 | 中：AR 页摄像头画面不可被遮挡 |
| 方案库 `/looks`（P3） | IndexedDB，无服务端 | 高：不得出现不可用却可点的同步入口 |
| 长任务化（P4） | `POST /api/generate-ai`：同步 HTTP，无队列 | **阻塞**：§11.3-5 未完成；UI 在队列落地前不得宣称"关页也能继续" |

---

## 8. 边界与禁止项

1. 正式纹理模型 PRODUCT HOLD：任何界面不得把 fallback 表述为"自动识别成功"，不计入正式识别成功率或 Beta 直接可用率；
2. AR 摄像头需 HTTPS 或 `localhost`；`/ar-demo` 外网必然不可用（§11.4）；
3. 跨设备同步未实现：方案库必须明示"仅本机"；
4. 不新增上传通道与第三方依赖；不改变本地优先的数据边界；
5. 不删除或弱化任何现有能力边界声明；
6. 不得用"基线噪音"或"环境限制"为真实失败开脱，也不得把环境失败改记为通过；
7. 本文件所有"已修复"结论均绑定可重放命令与输出，见 §6。

---

## 9. 「新交互界面」的指代界定

三个对象名称相近但性质完全不同，讨论"上线"前必须先锁定指代：

| 代号 | 对象 | 位置 | 当前性质 |
| --- | --- | --- | --- |
| **A1** | 正式站交互重设计**提案** | `docs/product-ui-redesign-proposal.md` | 仅文档，**未实施**：无对应代码、无版本号、无可部署产物 |
| **A2** | 消费者端**独立本机原型** | `design/consumer-v1/`，`node scripts/serve-consumer-design.mjs` → `127.0.0.1:4318` | 已实现的原型，**未注册 Next.js 正式路由、未切换旧版、未部署**（白皮书 §4.7） |
| **A3** | 正式站**现有 UI** | Next.js App Router，12 页面 + 15 API | 已实现并长期存在；本轮只改 lint 配置、配额语义、登录页注释与原型死代码，**未做任何 UI 改版** |

**指代已由用户于 2026-10-27 确认为 A2**（原默认 A1 的假设作废）。A1 是否继续推进见 §13.6 待决策项；A1 的范围为面向现有正式站的壳层、导航、状态反馈与主线串联（P0—P3），不含美甲师端、模型训练与发布及 P4 后端能力。

## 10. 「正式上线投入使用」的判定标准

### 10.1 阶段定义（避免"上线"一词歧义）

| 阶段 | 定义 | 可判定证据 |
| --- | --- | --- |
| L0 未实施 | 只有文档/设计 | 提案文档存在，无实现代码 |
| L1 已实现未部署 | 代码完成且工程门通过 | §6 全项通过 + 默认 Turbopack 构建 exit 0 且路由清单完整 |
| L2 本机／内网可访问 | 仅开发或原型预览可达 | `localhost:3000` 或 `127.0.0.1:4318` |
| L3 预发布可用 | 独立预发布环境可访问并走通核心流程 | 预发布 URL + 核心流程实测记录 |
| L4 灰度 | 仅白名单/部分用户可访问 | 灰度名单或分流配置 + 灰度期指标 |
| L5 全量 | 面向全部用户开放，且满足 §10.2 全部条件 | 全量开放记录 + §10.2 各项证据 |

### 10.2 L5（全量）判定条件

| # | 条件 | 通过线 |
| --- | --- | --- |
| 1 | 工程门 | lint 0 problems、双 typecheck 0、编码审计 `failures: []`、全量测试 0 fail/0 skip、CI 83/83、默认 Turbopack 构建 exit 0 且路由清单完整 |
| 2 | 部署形态 | `next build && next start`（非 `next dev`）；Nginx 反代；3000 不公网暴露；`JIARU_TRUST_PROXY=1`；有效 HTTPS 证书（AR 摄像头必需） |
| 3 | 功能验收 | 核心路径「选款 → 试 → 改 → 存」在目标环境实测通过；12 类状态在涉及页面覆盖 100% |
| 4 | 兼容与真机 | 桌面 Chrome/Edge + 移动触控模拟通过；Android/iOS 真机、安全区、系统键盘、原生分享验收（模拟不替代真机） |
| 5 | 安全 | 安全审计无未闭合 P0/P1；CSP 与 HSTS 按环境落地 |
| 6 | 隐私与文案 | `/privacy` 与实际数据流一致；AI 素材与 fallback 声明常显 |
| 7 | 可回滚 | 保留上一可用构建产物与回滚步骤，且回滚演练通过 |
| 8 | 观测 | 错误率、核心流程成功率、延迟有采集与阈值，灰度期达到阈值才转全量 |
| 9 | 能力解耦 | UI 上线**不得**被表述为正式纹理识别能力上线；正式模型 PRODUCT HOLD 不变 |

### 10.3 可用性指标（建议值，**待你确认，非既定指标**）

| 指标 | 建议阈值 | 说明 |
| --- | --- | --- |
| 核心流程任务完成率 | ≥95% | 灰度期实测，需先定义"完成"口径 |
| 页面 JS 错误率 | <0.1% 会话 | 需先接前端错误采集，当前无 |
| P95 LCP（桌面） | ≤2.5s | 需先接性能采集，当前无 |
| 7 日服务可用性 | ≥99.5% | 需外部探活，当前无 |

> 以上四项**当前均无采集通道**，因此不能作为已达成的指标引用；阈值本身也需你确认后才能成为"既定指标"。

## 11. 状态维度与环境划分

### 11.1 每次状态说明应包含的维度

上线阶段（L0—L5）、可访问范围（URL／账号／白名单／地区）、版本与构建指纹（commit、构建时间、路由清单）、功能开关与环境变量、已知问题、数据与隐私口径、回滚方案与保留版本数、后续计划与阻塞项、决策人与责任人。

### 11.2 环境划分

| 环境 | 入口 | 当前证据状态 |
| --- | --- | --- |
| 本机开发 | `next dev --experimental-https` → `https://localhost:3000` | 存在；自签名证书不等于正式部署证书 |
| 独立原型预览 | `127.0.0.1:4318` | 存在；仅本机、只绑定回环、CSP 禁网 |
| 测试／CI | `npm.cmd test`、`test:ci`、Playwright | 存在；本轮 1205/1205 与 83/83 通过 |
| 预发布 | — | **仓库无独立预发布环境记录，需你确认是否存在** |
| 生产 | 腾讯云轻量 `lhins-1oklqsh2`（ap-beijing-7，`49.233.141.42`），Nginx 终结 80 反代 127.0.0.1:3000 | 仅有 **2026-10-04 部署形态实测**记录；HTTP 非安全上下文，AR 摄像头不可用 |
| 临时演示 | Cloudflare quick tunnel / cpolar | 域名每次启动变化；守护脚本与重连耗时见白皮书 §11.4 |

## 12. 当前状态与信息缺口

### 12.1 可以由证据支撑的状态

| 对象 | 阶段 | 依据 |
| --- | --- | --- |
| A1 新交互界面 | **L0 未实施** | 本轮只产出提案文档与修复，无 UI 改版代码 |
| A2 独立原型 | **L2 本机预览** | 白皮书 §4.7：未切换、未部署；真机与原生分享未验收 |
| A3 正式站代码 | 工程门部分通过 | 修复后 lint/双 typecheck/编码/1205 测试/83 CI 全绿，**生产构建门未闭合**（§6.4） |
| 正式纹理模型 | PRODUCT HOLD | 白皮书 §3／§11.1，与 UI 上线相互独立 |

### 12.2 仓库无法证明、需你补充的信息

1. 「新交互界面」指 **A1 还是 A2**（或两者合并后的正式版）？
2. **预发布环境是否存在**？生产是否只有腾讯云这一台？是否还有其它环境或节点？
3. 目标上线形态：**直接全量，还是先灰度**？灰度按什么圈人（当前账号体系是否足以支撑白名单）？
4. **当前生产实际运行的版本、是否对外开放、是否已有真实外部用户**——仓库只能证明代码与配置，不能证明线上运行状态。
5. 可用性指标阈值由谁定？是否接受 §10.3 的建议值？是否已有错误/性能/探活采集？
6. 回滚期望：保留几个版本、由谁执行、可接受的恢复时长？
7. 是否确认 **UI 上线与正式模型解耦**（建议解耦，UI 上线时保留 fallback 常显声明）？

> 在以上信息补齐前，本文件不给出"已上线/灰度中/全量"等结论；任何此类表述都缺乏证据。
>
> 后续进展：§12.2 的第 1—4、7 项已于 2026-10-27 由用户答复，确认结果与新增阻断见 **§13**；第 5、6 项（指标阈值、回滚细则）仍未确认。

---

## 13. A2 独立原型全量上线专项（2026-10-27 用户确认范围）

### 13.1 已确认的决策

| 项 | 用户确认值 | 对执行的含义 |
| --- | --- | --- |
| 指代 | **A2 独立原型**（`design/consumer-v1/`） | 工作对象从正式站重设计（A1）切换为 A2 |
| 预发布环境 | **不存在** | 没有独立预发布门；验收只能在本机预览与目标托管环境两级进行 |
| 发布形态 | **直接全量，不做灰度** | 没有灰度缓冲期，**所有判定条件必须在全量前一次性闭合**，不能"先上线再修" |
| 真实用户 | **当前没有真实用户** | 全量的实际风险低，但不等于可以降低验收标准；首批用户到达时即受全量口径约束 |
| 验收手段 | 用现有几台设备做模拟 | 需先区分真机与桌面设备模拟，两者证据效力不同（§13.5） |
| 与模型关系 | **UI 正式上线不代表正式模型通过测试** | 解耦已确认：A2 上线不改变 PRODUCT HOLD，fallback 与 AI 素材声明继续常显 |

### 13.2 当前状态（源码实测）

| 维度 | 状态 | 证据 |
| --- | --- | --- |
| 阶段 | **L2 本机预览**，未上线 | `serve-consumer-design.mjs:44` 仅监听 `127.0.0.1` |
| 可访问范围 | 仅本机回环 | 同上；无对外绑定、无域名、无 HTTPS |
| 网络能力 | **页面禁止一切网络请求与表单提交** | `:27` CSP `default-src 'none'`、`connect-src 'none'`、`form-action 'none'` |
| 摄像头 | **被权限策略彻底禁用** | `:28` `Permissions-Policy: camera=(), microphone=(), geolocation=()` |
| 生成能力 | **模拟**：展示结果布局与样图，非真实生成 | `app.mjs:531` 按钮文案「预览上手结果布局」、`:347` `sample-result` |
| 账号 | **模拟登录**，不连接真实认证、不开云同步 | `app.mjs:435` 明示文案 |
| 数据持久化 | 仅 localStorage `jiaru-consumer-design-v1`；照片为内存对象 URL，刷新需重选 | 白皮书 §4.7 |
| 已通过的验收 | Chrome 核心 75+补充 12、Pixel 7 触控模拟 55、Windows Edge 补充 24 | 白皮书 §4.7（**均为模拟或桌面浏览器，不是真机**） |
| 未验收 | Android/iOS 真机、iOS Safari/WebKit、真实系统键盘与安全区、原生分享 | 同上 |

### 13.3 全量前的硬阻断

| # | 阻断 | 为什么必须处理 |
| --- | --- | --- |
| B1 | **服务形态不可对外**：只绑回环、CSP 禁网、禁表单、禁摄像头 | 直接暴露该服务即不可用；必须改为正式静态托管并重新评审响应头 |
| B2 | **核心能力为模拟**：生成、登录、个性化推荐、公开社区均未接入 | 若作为"正式产品"全量，等于向用户交付假功能，违反项目"不伪造生成、不冒充真实能力"的既有口径 |
| B3 | **真机与原生能力未验收**：iOS WebKit、安全区、系统键盘、原生分享 | 全量无灰度缓冲，移动端缺陷将直接暴露给全部用户 |
| B4 | **无域名/HTTPS 与部署回滚方案** | 若启用摄像头必须 HTTPS；直接全量更需要可执行的回滚 |

### 13.4 两条可行路径（必须先选定，否则无法排期）

| 路径 | 上线身份 | 需要做什么 | 判定 |
| --- | --- | --- | --- |
| **甲：设计预览／演示站全量** | 公开的是"设计预览"，**不承诺真实生成与账号** | 静态托管 + 域名/HTTPS；页内常显"演示环境、结果为示例"；模拟登录、样图结果保持明确标识；CSP 可继续禁网（反而更安全）；按 §13.5 验收 | **当前形态最接近，工作量最小，且不伪造能力** |
| **乙：正式产品全量** | 公开的是可用产品 | 除上述外，必须先把模拟能力替换为真实能力：生成接 `/api/generate-ai`、`/api/generate-seedream`；摄像头接 `ArView` 并放开权限（需 HTTPS）；账号接 `/api/auth/*`；收录与方案接持久层；`connect-src`/`form-action`/CSP 全面重评审 | **在能力接入前不满足全量条件**；且与 A1 正式站重设计高度重叠，需同步决策（§13.6） |

> 本文件不推荐把"模拟生成"包装成正式功能上线。若选乙，必须先完成真实能力接入并通过对应接口的实测，再谈全量。

### 13.5 设备验收口径（区分真机与模拟）

| 手段 | 证据效力 | 可关闭的门 |
| --- | --- | --- |
| 真实手机/平板（iOS Safari、Android Chrome） | **真机证据** | 可关闭真机、安全区、系统键盘、原生分享门 |
| 桌面浏览器设备模拟（含 Pixel 7 触控模拟） | **模拟证据**，报告必须标注"模拟" | 只能关闭布局、触控目标、粗指针、减少动态效果等门，**不得**据此宣称真机通过 |

验收矩阵与通过线：

| 项 | 通过线 |
| --- | --- |
| 核心流程 | 为你 → 试戴 → 创作 → 我的 → 方案卡导出/分享，全程可走通，无死路 |
| 布局 | 320px 宽无横向滚动；390×844、844/600×390 短横屏、桌面宽屏均无溢出与遮挡 |
| 触控 | 主要目标 ≥44 CSS px、间距 ≥8px；粗指针真实 tap 可达 |
| 键盘与读屏 | 可见焦点、跳到主体、弹层 Esc 关闭并回返焦点；axe 严重/中等违规 0 |
| 输入 | 中文合成输入不重建输入节点；输入时底部导航避让 |
| 动效 | `prefers-reduced-motion` 下脚本水波/爆散/回弹关闭 |
| 分享 | 支持时调系统分享；不支持或失败时降级为 PNG 下载；**用户取消不得提示成功** |
| 数据边界 | 演示路径下照片不出本机；无未声明的网络请求 |
| 真机专属 | iOS WebKit、安全区、系统键盘、原生分享**只能在真机上判通过** |

### 13.6 仍需你确认的 5 项

1. **路径甲还是乙**：上线的是"设计预览/演示站"还是"正式产品"？（唯一硬阻塞决策）
2. **托管与域名**：是否复用腾讯云 Nginx 做静态托管？是否已有域名与 HTTPS 证书？
3. **设备清单与性质**：几台设备分别是真机还是桌面模拟？型号/系统/浏览器版本？
4. **A1 去留**：若选乙，A2 与正式站重设计（A1）功能重叠，是否保留 A1？
5. **回滚细则**：建议静态目录版本化并保留最近 2 版、Nginx 切换根目录回滚、恢复时长分钟级——是否接受？由谁执行？

> 在路径甲/乙与托管形态确认前，A2 的状态保持 **L2 本机预览、未上线**；不给出"可全量"的排期承诺。
>
> 后续进展：用户已于 2026-10-27 选定**乙**，并补充"当前不对公网开放、有几台真机可供测试"。合流关系与修订后的口径见 **§14**；§13.6 第 1、3 项已答复，第 2、5 项仍未确认。

---

## 14. 乙路径与受控环境全量（2026-10-27 第二次确认）

### 14.1 A1／A2／A3 的关系与合流结论

| 代号 | 实质 | 是否具备真实功能 |
| --- | --- | --- |
| A1 | `docs/product-ui-redesign-proposal.md`——**改造现有 Next.js 正式站的方案文档**（左 rail/底部 tab、12 状态组件、任务条、`?look=` 收敛） | 方案本身无代码；其对象正式站**已有** AI 生图、AR、账号、编辑器等真实能力 |
| A2 | `design/consumer-v1/` **独立静态原型**，是视觉与交互蓝本 | 无：生成/登录/摄像头均为模拟 |
| A3 | 正式站**现行旧 UI** | 有 |

**合流结论**：选定乙后，"让 A2 成为真实产品"与"把 A2 的设计落到正式站"是同一终点。因此 **A1 不再是可独立取舍的另一条路线，而是乙的实现方式**：

> 以 **A2 的视觉与交互设计为准**，在 **Next.js 正式站**内实现（即 A1 的 P0—P3），复用现有 `/api/*`、`ArView`、`NailCanvas`、识别库、配额与限流；**不在静态原型上另起一套后端**。

理由：认证、AR、识别、配额、限流在正式站已实现且有测试覆盖；在原型上重写会重复制造攻击面与验收成本。A2 原型保留为设计参考与视觉回归基准。

### 14.2 「全量但不对公网开放」的口径修订

用户确认"直接全量"与"当前不对公网进行开放"同时成立，因此本文件把目标解释为：

- **全量**＝在目标环境内**不做灰度、一次性交付全部功能**，而不是"对全部互联网用户开放"；
- **不对公网开放**＝部署在受控范围（本机／局域网／仅自己的真机可访问），**无公网入口、无隧道暴露**；
- 阶段记为 **L4′ 受控环境全量**，区别于 §10.1 的 L5 公网全量；若日后要公网开放，仍须回到 §10.2 的完整条件（域名、HTTPS、CSP/HSTS、观测、真实用户指标）。

由此变化的门槛：公网暴露面相关项（公网域名、公网探活、真实用户指标）暂不构成阻断；**安全头、CSRF、限流、配额、错误脱敏仍保留**，不因其为内网而拆除。

### 14.3 真机验收的硬前置：AR 摄像头需要安全上下文

用户已提供真机，B3 可进入执行。但**真机在内网通过 `http://192.168.x.x:<port>` 访问时属于非安全上下文，`getUserMedia` 不可用**（白皮书 §4.1 明确：摄像头应通过 `localhost` 或正式 HTTPS 域名访问，不应使用普通局域网 HTTP 地址）。因此乙路径要测 AR，必须先选定一种 HTTPS 方案：

| 方案 | 适用 | 代价与限制 |
| --- | --- | --- |
| 内网 HTTPS 证书（内网 CA 或 mkcert，真机安装并信任根证书） | 长期内网使用，最干净 | 需在每台真机安装信任根；iOS 还需在设置中启用完全信任 |
| 自签名证书 + 真机手动信任 | 快速验证 | 每台真机都要操作；浏览器警告需逐一处理 |
| HTTPS 隧道（Cloudflare/cpolar） | 不想配证书时 | **会把服务暴露到公网**，与"不对公网开放"冲突；域名每次变化；仅在用户明确接受时可用 |

> 在 HTTPS 方案确定前，**AR 摄像头在真机上无法验收**，只能验收非摄像头流程。不能用桌面模拟或截图代替真机摄像头结论。

### 14.4 乙路径执行顺序

| 阶段 | 内容 | 出门条件 |
| --- | --- | --- |
| W0 合流与资产盘点 | 确认 A2 设计资产（`style.css` token、`app.mjs` 交互、`index.html` 结构、本地字体子集）映射到正式站组件；冻结"不再另起后端"的边界 | 映射表完成；A1/A2 合流口径确认 |
| W1 壳层与状态 | 按 A2 视觉实现左 rail/底部 tab、12 状态组件、任务条 | lint 0、双 typecheck 0、全量测试绿、**默认 Turbopack 构建 exit 0 且路由清单完整** |
| W2 真实能力接入 | 以正式站现有能力替换模拟：生成接 `/api/generate-ai`、`/api/generate-seedream`；AR 接 `ArView`；账号接 `/api/auth/*`；收录与方案明确持久层；同步放开 CSP `connect-src`/`form-action` 并重评审 | 各接口实测通过；**不再出现"模拟生成"字样冒充真实结果** |
| W3 真机验收 | 按 §13.5 矩阵在真机执行；AR 部分须先完成 §14.3 的 HTTPS 前置 | 真机证据落盘；模拟项单独标注 |
| W4 受控部署与回滚 | 受控环境部署（`next build && next start`）、版本化构建产物、回滚演练 | 回滚演练通过；无公网入口核验通过 |

### 14.5 仍需确认（4 项）

1. **真机清单**：几台、型号、系统版本、浏览器（决定 §13.5 矩阵与 iOS WebKit 覆盖）；
2. **受控部署位置与访问地址**：本机 `next start` 还是局域网服务器？真机通过什么地址访问？
3. **HTTPS 方案**：内网 CA/mkcert、自签名+真机信任，还是接受隧道（会与"不公网开放"冲突）？
4. **A2 原型去留**：建议保留为设计参考与视觉回归基准，不再投入新功能开发——是否同意？

> 在以上确认前，A2 仍为 **L2 本机预览、未上线**；乙路径尚未开始实施，本轮未编写任何实现代码。
