# JiaRu 安全审计报告

- 审计日期：2026-09-23
- 审计范围：`src/`（App Router 页面、Route Handlers、`lib/`）、`next.config.ts`、`package.json` / `package-lock.json` 依赖树、`.gitignore`、Git 历史中的密钥痕迹、`public/` 暴露面
- 审计方式：静态代码审计 + `npm audit` 依赖审计 + Git 历史检查
- 结论：**存在 1 个必须立即处理的严重漏洞（可导致服务器被完全控制）**，另有 3 个高危、5 个中危、4 个低危项

---

## 一、严重（Critical）— 立即修复

### C1. Next.js 16.2.9 存在 Windows 主机未授权远程代码执行（CVE-2026-75604）

| 项 | 内容 |
|---|---|
| 公告 | GHSA-p293-qw3h-jr36 / CVE-2026-75604 |
| 影响版本 | `next` >= 16.0.0 且 < 16.3.3（当前 `package.json` 锁定 **16.2.9**） |
| 修复版本 | **16.3.3**（npm 建议直接升到 **16.3.6**） |
| CVSS | **9.0 Critical**（AV:N / AC:H / PR:N / UI:N / S:C / C:H / I:H / A:H） |
| 缓解措施 | **官方明确：无已知缓解方案（No known workaround）** |

**为什么这一条对本项目是最高危的：**

1. 漏洞只在 **Windows 文件系统** 上触发——路由段中的反斜杠未正确转义，攻击者可用编码后的 Windows 路径分隔符穿越出增量缓存根目录，读取到 **server-reference-manifest 加密密钥**，进而 RCE。
2. 本项目的生产部署 **正是 Windows**：本地 `next start` 跑 3000 端口，且通过 **cloudflared 隧道暴露到公网**。
3. 项目使用 App Router 且未启用 Cache Components，落在公告的受影响配置内。
4. 公开漏洞研究已存在 PoC 仓库。

**同一版本还涵盖以下 Next.js 公告（升级一并修复）：**

- GHSA-89xv-2m56-2m9x — 自定义服务器上的 Server Actions SSRF
- GHSA-p9j2-gv94-2wf4 — 通过攻击者可控的 rewrite 目标主机名造成 SSRF
- GHSA-68g3-v927-f742 / GHSA-4633-3j49-mh5q — 带请求体的响应缓存混淆
- GHSA-955p-x3mx-jcvp — 内部 Server Function 端点未授权泄露
- GHSA-2xp9-vwfh-vxw4 — Image Optimization API 处理 AVIF 时未授权 RCE
- GHSA-q8wf-6r8g-63ch — Image Optimization API 处理 SVG 时 DoS
- GHSA-6gpp-xcg3-4w24 — 使用 Turbopack 且单 locale 时的中间件/代理绕过
- GHSA-m99w-x7hq-7vfj / GHSA-4c39-4ccg-62r3 — Server Actions DoS / Edge 运行时无界载荷

**修复动作：**

```bash
npm.cmd install next@16.3.6
npm.cmd run build   # 确认构建通过
npm.cmd audit       # 复验
```

> 注意：`eslint-config-next` 当前也锁定 `16.2.9`，应与 `next` 同步升级，否则 lint 规则与运行时版本不一致。

---

## 二、高危（High）

### H1. 生产环境认证链路实际不可用，且开发模式验证码可明文回传

- `src/lib/auth/sms.ts:43-56`：`SMS_PROVIDER` 未配置时，非 production 走"开发模式"，验证码通过 `console.log` 输出 **并由 `/api/auth/request-code` 的 `devCode` 字段直接返回给前端**（`request-code/route.ts:34`）。
- production 分支有守卫（未配置 → 抛错），**但前提是 `NODE_ENV=production`**。若任何一次对外演示/联调是以 `next dev` 启动并通过隧道暴露，则任何人请求任意手机号验证码即可直接读取明文验证码，登录为任意用户。
- 同时，当前 `SMS_PROVIDER` 与 `WECHAT_APP_ID/SECRET` 均未配置，说明**生产环境的登录注册事实上不可用**，所有访问都只能走游客身份（进而落进 AI 配额的游客档）。

**建议：** 确认线上/对外暴露的实例一律 `next build && next start`；把 `devCode` 返回额外加一道显式开关（如 `JIARU_DEV_SMS=1`）而非仅依赖 `NODE_ENV`；尽快接入短信服务商或明确标注"认证未上线"。

### H2. 缺少全局安全响应头

`next.config.ts` 只给 `/ar-demo`、`/ar-tryon` 配了 `Permissions-Policy`，**没有为全站配置**：

- 无 `Content-Security-Policy` → XSS 无纵深防御
- 无 `X-Frame-Options` / `frame-ancestors` → 点击劫持
- 无 `X-Content-Type-Options: nosniff` → MIME 嗅探
- 无 `Referrer-Policy` → 来源泄漏
- 无 `Strict-Transport-Security` → 降级攻击

**建议：** 在 `headers()` 中增加 `source: "/(.*)"` 的通用安全头（CSP 需为 onnxruntime-web / three.js / MediaPipe 的 WASM 与 worker 放行 `script-src 'self' 'wasm-unsafe-eval' blob:`）。

### H3. 内部错误信息直接回显给客户端

三处把异常原文拼进响应体：

- `src/lib/auth/http.ts:53` — `服务器错误: ${msg}`
- `src/app/api/generate-ai/route.ts:151` — `服务器错误: ${msg}`
- `src/app/api/generate-seedream/route.ts:154` — `服务器错误: ${msg}`

另外 `agnes-image-api.ts:156` / `seedream-image-api.ts` 会把上游供应商错误原文（截断 500 字符）作为 `Agnes API 错误: ...` 返回。

**风险：** 数据库路径（如 `无法打开用户数据库 E:\...`）、文件系统结构、供应商内部错误码外泄，为攻击者提供侦察信息。

**建议：** 500 分支统一返回固定文案，详细信息只写服务端日志。

---

## 三、中危（Medium）

### M1. 缺少 IP / 全局级速率限制，短信与图形验证码可被刷

- 验证码发送只有**按手机号**的节流：60 秒间隔、单日 10 条（`sms.ts:13-15`）。**没有按 IP、没有全局上限**，攻击者可用大量不同手机号发起轰炸。
- `GET /api/auth/captcha` 无任何限流，可无限签发；验证码 4 字符、字符集 30 个（约 81 万组合），单次最多试 5 次后可**立即换一个新的**继续试。
- captcha 记录不绑定 IP 或会话，`captchaId` 可以跨请求复用。

**建议：** 增加按 IP 的令牌桶限流（captcha 签发、request-code、verify-code 各一套）；captcha 校验失败计入 IP 维度；接入生产级人机验证（腾讯云/阿里云验证码）。

### M2. refresh token 30 天静态有效，无轮换、无重放检测

- `service.ts` 已实现 `rotateTokens()`（撤销旧会话再签发），但 `/api/auth/refresh` 与 `requireUserWithRenewal` 实际走的是 `renewFromRefresh()`（**不撤销、不轮换**，仅剩 15 天内才滑动重签）。
- 结果：一个 30 天有效的 refresh token 被盗后可长期使用，服务端无法检测重复使用、也没有按会话的强制下线能力（只有主动 logout 才 revoke）。

**建议：** 对来自浏览器的 refresh 改回轮换语义，并记录"已使用的 refresh jti"，发现重放即撤销整条会话链。

### M3. 无显式 CSRF 防护，仅依赖 `SameSite=Lax`

所有写操作（verify-code / logout / bind-phone / PATCH /api/me / DELETE identities）都用 Cookie 鉴权，`sameSite: "lax"` 能挡住跨站 POST，但：

- 没有任何 `Origin` / `Sec-Fetch-Site` 校验层；
- 老浏览器、同站子域、以及未来若引入 `SameSite=None` 的场景会失效。

**建议：** 增加 middleware，对非 GET/HEAD 请求校验 `Origin` 是否在白名单内。

### M4. 已登录用户可枚举已注册手机号

`service.ts:279-282` `bindPhone()` 在验证码校验**之前**先查 `getUserByIdentity("phone", phone)`，命中他人即返回 `409 该手机号已绑定其他账号`。攻击者登录任意账号后即可批量探测号码是否已注册，构成用户隐私泄漏。

**建议：** 把该检查移到验证码校验之后；或直接返回不区分的通用错误。

### M5. 付费 AI 接口对游客开放，游客身份可被伪造

- `/api/generate-ai`、`/api/generate-seedream` 允许匿名调用（`generate-ai/route.ts:109-116`）。
- 游客身份键取自 `x-forwarded-for` 首段（`ai-quota.ts:112-119`），该头可任意伪造 → **每 IP 5 次/日的软限制可绕过**。
- 真正的硬约束只有全局 200 次/日熔断（`AI_QUOTA_GLOBAL_DAILY`），且计数在失败时**不返还**（设计正确）。

`ai-quota.ts` 的模块注释已诚实标注"游客 IP 可伪造，游客额度只是软约束"——这是已知取舍，但需知悉：在隧道/反向代理场景下若未正确设置可信代理，`x-forwarded-for` 完全由客户端控制。**建议**在公网部署时把游客身份改为由可信代理注入的真实 IP，或直接关闭游客生成（`AI_QUOTA_GUEST_DAILY` 无法设 0，需代码支持）。

---

## 四、低危（Low）

| 编号 | 位置 | 问题 |
|---|---|---|
| L1 | `cookies.ts:43-47` | `getClientIp()` 无条件信任 `x-forwarded-for`，审计日志（`audit_logs.ip`）与限流身份可被污染 |
| L2 | `ar-demo/page.tsx:32-37` | iframe 无 `sandbox` 属性，且 `allow="camera; microphone"` 指向 `http://localhost:8080`（明文 HTTP 的本地 Python 服务） |
| L3 | `jwt.ts:61-70` | 未校验 `iss` / `aud`，也未校验 `sub`/`sid` 的类型（仅判空）。当前不可利用，属加固项 |
| L4 | `captcha.ts:28` | 验证码 store 是模块级 `Map`，虽在 `createCaptcha()` 时惰性清理过期项，但 5 分钟窗口内无条数上限，高频请求会造成内存增长 |

---

## 五、审计通过的部分（无问题）

以下项目经逐项检查确认安全，无需改动：

| 项 | 结论 |
|---|---|
| **SQL 注入** | `src/lib/auth/db.ts` 全部使用 `node:sqlite` 预编译语句与 `?` 占位符，**零字符串拼接**，无注入面 |
| **硬编码密钥** | 全仓扫描（排除 `node_modules`）无 `sk-`/`AKIA`/`ghp_`/私钥等模式；唯一命中的 `e2e/review11-browser-regression.spec.ts:16` 是 Playwright 测试专用常量 |
| **密钥入库** | `git ls-files` 与 `git log --all -- .env.local` 均显示 `.env.local` **从未被跟踪**；`.gitignore` 的 `.env*` + `!.env.local.example` 规则正确 |
| **前端密钥泄漏** | 仅 `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL` 一个公开变量，不含凭据；`AGNES_API_KEY`、`VOLCENGINE_ARK_API_KEY`、`JWT_SECRET` 等全部只在服务端读取 |
| **XSS** | 全 `src/` 无 `dangerouslySetInnerHTML` / `innerHTML` / `eval` / `document.write` |
| **出站请求** | `agnes-image-api.ts` 与 `seedream-image-api.ts` 均强制校验 base URL 必须为 `https:` 且不得内嵌认证信息；返回的 `imageUrl` 强制要求以 `https://` 开头 |
| **文件路径穿越** | 所有 Route Handler 均不读取用户可控路径，无 fs 边界暴露 |
| **摄像头隐私** | `ArView.tsx:939` 与 `:1198` 在卸载与错误路径上均调用 `getTracks().forEach(t => t.stop())`，流释放完整 |
| **头像/文件上传** | `image-upload-validation.ts` 有 MIME 白名单、10MB 上限、320–4096 分辨率校验；图片仅转 Data URI 客户端处理，不落服务器 |
| **第三方供应链** | `public/vendor`、`public/models` 均为本地资产，无 unpkg / jsDelivr / cdnjs 等外链脚本 |
| **Captcha 设计** | 答案只存服务端、一次性、错 5 次作废、SVG 用 polyline 点阵渲染不含 `<text>` 明文，设计正确 |
| **Git 暴露面** | `data/`、`certificates/`、`*.pem`、`model/reports/` 等敏感目录均已隔离 |

---

## 六、建议的修复顺序

1. **立即**：升级 `next`（及 `eslint-config-next`）到 16.3.6 → C1
2. **本周**：补齐全站安全响应头 → H2；统一 500 错误脱敏 → H3
3. **本周**：确认对外实例一律 production 模式，收紧 `devCode` 开关 → H1
4. **上线前**：接入 IP 级限流 → M1；refresh token 轮换 → M2；CSRF Origin 校验 → M3
5. **排期**：手机号枚举修复 → M4；游客配额与可信代理 → M5；L1–L4 加固

---

> 本报告为静态审计结论，未进行动态渗透测试与运行时验证。
