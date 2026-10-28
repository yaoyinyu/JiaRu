# 甲如（JiaRu）项目审查报告

> 日期：2026-10-28
>
> 审查基线：技术白皮书 v1.2.162（§2 系统概览、§3 功能状态总表、§5 HTTP API、§6.1 候选契约、§8.9、§10 隐私、§11.1 阻塞项、§11.3 未完成能力）
>
> 审查范围：`src`（120 个 TS/TSX）、`tests`（332 个 TS 用例文件、133 个 Python 用例）、`e2e`（2 个 Playwright spec）、`next.config.ts`、`deploy/`、`public/`、`package.json`、`model/VlM_Model`（拟接入服务）
>
> 审查方式：静态源码与配置实测优先；机器报告与测试记录次之；白皮书与历史文档用于交叉核对
>
> 状态：本报告为基线文档，结论变动须另立新版日期文件，不就地改写历史结论

## 1. 审查输出结构与判定标准

本报告固定六段结构，每段内部统一为「实测指标 → 问题清单（含文件:行证据）→ 严重度 → 处置建议」：

1. 代码质量
2. 架构合理性
3. 性能表现
4. 安全性
5. 依赖项
6. 技术债务

严重度定义与通过条件：

| 严重度 | 定义 | 通过条件 |
| --- | --- | --- |
| P0 阻断 | 可导致未授权访问、任意文件读取、数据泄露或发布契约被破坏 | 0 项遗留才可进入依赖它的实施阶段 |
| P1 高 | 影响正确性、可回归性或可发布性 | 本阶段关闭，或有书面风险接受记录 |
| P2 中 | 架构、性能或可维护性缺陷 | 排期关闭，允许带项推进 |
| P3 低 | 整洁性、命名、死代码、版本对齐 | 随手清理，不单独排期 |

复现要求：每条结论必须给出可复核证据（源码位置、机器报告路径或命令），不接受「代码存在即通过」。

## 2. 结论摘要

| 级别 | 数量 | 结论 |
| --- | --- | --- |
| P0 | 1 | 仅存在于拟接入的上游抠图服务，尚未进入本项目运行时；接入前必须收口 |
| P1 | 5 | 构建证据缺口、被否决模型资产公开、两个千行级组件、e2e 覆盖缺口、限流单实例假设 |
| P2 | 7 | CSP/HSTS 缺失、静态资源体积、双路由重复、模块错位、大常量模块、依赖与 SCA、仓库体积 |
| P3 | 3 | 死依赖、类型版本、文档维护成本 |

总体判定：**工程基础通过（安全核心项、类型严格度、测试规模），发布可维护性未通过（构建门与 e2e 缺口），拟接入路径安全未通过（P0 待收口）**。

## 3. 六维度结论

### 3.1 代码质量

实测指标：`any` 断言 0 处；`TODO/FIXME` 2 处；`console.log/debug/info` 3 处；最大文件 `ai-style-prompts.ts` 151.5KB、`ArView.tsx` 1248 行、`NailArtPicker.tsx` 1039 行；最新串行全量 1208/1208 pass（`output/test-ui-optimize-20261028-serial.txt`，772.7s）。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| P2 | `src/lib/nail-texture-dataset.ts`（810 行）为 Node 专用（`node:crypto`、`node:fs/promises`），`src` 内 0 处 import，仅被测试引用；数据集工具混在生产源码树 | 全量 import 搜索；文件头 1—8 行 |
| P2 | `src/lib/ai-style-prompts.ts` 151.5KB 常量模块，需确认按路由分包，避免进入公共 chunk | 文件体积 |

处置建议：把数据集工具迁至 `scripts/` 或 `model/` 侧；对提示词常量做路由级动态导入评估。两项均不阻塞模型接入。

### 3.2 架构合理性

实测指标：分层为 `src/app`（路由与页面）→ `src/lib`（纯逻辑与服务端模块）→ `src/components`；识别链已 Worker 化（`src/lib/nail-texture-recognition/client-worker.ts:88` 单例 Worker，`type: "module"`，`import.meta.url`）；服务端专用模块有显式标注（`ai-quota.ts` 头部注释）。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| P1 | 单体组件：`ArView.tsx` 1248 行、`NailArtPicker.tsx` 1039 行，几何测算、状态机、渲染与交互同文件，回归面大 | 行数实测 |
| P2 | 两条付费生图路由各自实现参数校验、身份识别、配额预留与错误映射，接入第三个引擎会复制第三份 | `src/app/api/generate-ai/route.ts`、`src/app/api/generate-seedream/route.ts` |
| P2 | 四条定位路径（Worker 模型 / MediaPipe / 局部近景 / 人工）在组件内串联，回退顺序与界面文案耦合 | `NailArtPicker.tsx:247-370` |

处置建议：新增能力一律抽独立模块与独立组件（本次接入计划已按此执行）；生图路由的公共中间层作为后续重构项，不在本次范围内。

### 3.3 性能表现

实测指标：`public/` 合计 84.37MB，其中 `public/models/nail-texture-seg-candidate57-test` 48.34MB（stage1 43.8MB + stage2 5.67MB）、`nail-texture-seg-synthetic-v1` 11.09MB、MediaPipe 自托管资源约 23MB；`public/models/nail-texture-seg` 目录 0.00MB（仅 manifest，无权重）。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| P1 | 被否决模型 `candidate57` 的 ONNX 位于 `public/`，构建即公网可下载；manifest 自带 `testOnly: true` 与 `deploymentAuthorized: false` | 目录实测；`public/models/nail-texture-seg-candidate57-test/manifest.json` |
| P2 | MediaPipe 同时保留 simd / 非 simd 两套 wasm 与 3 个 tflite，无按需或压缩策略 | 目录实测 |
| P2 | 缺端到端 P95、完整流程峰值内存与重复运行稳定性基线（正式发布门同样缺） | 白皮书 §11.1 |

处置建议：把仅测试用的模型资产移出 `public/`（保留本地归档与哈希记录），生产构建只保留 manifest 与批准权重；性能基线随正式发布门补测。

### 3.4 安全性

实测通过项：SQL 全参数化且列名走固定白名单（`src/lib/auth/db.ts:309-315`）；JWT 固定 `alg=HS256`、校验 `iss/aud`、`timingSafeEqual` 比对（`src/lib/auth/jwt.ts:76-100`）；生产环境缺 `JWT_SECRET` 直接抛错（`src/lib/auth/config.ts:14-16`）；写请求强制 Origin 校验（`src/middleware.ts:61-67`）；Nginx 与应用双层限流（`deploy/nginx/jiaru.conf:19-21`）；付费路由配额与预算熔断（`src/lib/ai-quota.ts`）；`.env.local` 未被 git 跟踪。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| **P0** | 拟接入服务 `/matte` 接受 `imagePath` 直读本地文件，且未设 token 时 `authorized()` 恒真、无 CORS、无 TLS | `model/VlM_Model/server.py:167`、`:95-99`、`:230` |
| P1 | 被否决模型权重公开可下载，属资产治理与信息暴露（非代码漏洞） | `public/models/nail-texture-seg-candidate57-test/` |
| P2 | 无 CSP、无 HSTS；有 `X-Frame-Options: SAMEORIGIN` 但缺 `frame-ancestors` | `next.config.ts:17-23`；`deploy/nginx/jiaru.conf:34-38` |
| P2 | 限流与配额均为进程内存态，重启清零、多实例失效；`JIARU_TRUST_PROXY≠1` 时全部归 `unknown`（保守共享额度） | `src/lib/rate-limit.ts:93`、`src/lib/ai-quota.ts:145` |

处置建议：P0 必须在接入实施的第一步关闭（转发层白名单 + 强制 token + 仅回环绑定）；CSP 与 HSTS 随正式域名启用一并上线；限流改为共享存储属后续扩容前置条件。

### 3.5 依赖项

实测指标：直接依赖 5 个（`@mediapipe/hands`、`next`、`onnxruntime-web`、`react`、`react-dom`、`three`）；`next` 与 `react` 为精确版本锁定，`onnxruntime-web` 与 `three` 为 `^` 浮动；存在 `package-lock.json`；无依赖漏洞扫描脚本。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| P2 | 无 SCA（依赖漏洞扫描）环节；`next@16.3.6` 为较新大版本，升级需跟随 breaking change | `package.json`、scripts 无对应命令 |
| P3 | `three@^0.184.0` 全仓 0 处 import，为死依赖 | 全量 import 搜索 |
| P3 | `onnxruntime-web ^1.27.0` 未锁 minor；`@types/node ^20` 与实际 Node 24 不一致 | `package.json` |

处置建议：移除 `three`；锁定 `onnxruntime-web` minor；`@types/node` 对齐运行时；把 SCA 纳入发布门。

### 3.6 技术债务

实测指标：git 跟踪 1591 个文件，其中 `model/` 645 个；本地工作区磁盘占用约 181GB（数据集、训练输出、辅助材料）；`e2e` 仅 2 个 spec（`profile-edit.spec.ts`、`review11-browser-regression.spec.ts`）；最近一次生产构建失败于删除 `.next/turbopack` 触发宿主批量删除守卫。

| 级别 | 问题 | 证据 |
| --- | --- | --- |
| P1 | 生产构建门未闭合，v1.2.160—162 三轮改动无对应构建成功证据 | `output/build-redesign-final-20261027.txt`（失败）；`output/build-redesign-20261027.txt`（13:20 成功，早于三轮改动） |
| P1 | e2e 仅覆盖账号档案与一次回归，摄像头 + WASM + 模型链路无自动化浏览器覆盖 | `e2e/` 实测 |
| P2 | 仓库与工作区体积大（跟踪 1591 文件 / 本地约 181GB），克隆与检索成本高 | `git ls-files`、目录实测 |
| P3 | 文档体系重（白皮书 230,654 字节 + 归档数 MB + 日均日志 30—60KB），维护与上手成本高 | 文件实测 |

处置建议：构建门在可清理 `.next` 的环境串行重跑并留证；e2e 至少补一条「无模型部署时的降级链路」用例（本次接入将新增一条可复用的浏览器验证点）。

## 4. 关键问题优先级总表

| 编号 | 级别 | 问题 | 处置阶段 | 关闭条件 |
| --- | --- | --- | --- | --- |
| S-01 | P0 | 上游 `/matte` 的 `imagePath` 与无鉴权 | 模型接入 P0 | 转发层仅允许 `image/task/query/boxes`；`imagePath` 不可达；服务以 token 启动 |
| T-01 | P1 | 生产构建门未闭合 | 独立任务 | 可清理环境下 `npm.cmd run build` exit 0 并留证 |
| P-01 | P1 | `candidate57` 测试资产在 `public/` | 独立清理 | 资产移出 `public/`，本地归档保留哈希；构建产物不含该文件 |
| Q-01 | P1 | `ArView.tsx` / `NailArtPicker.tsx` 单体 | 持续重构 | 新增能力不再进入这两个文件（本次以独立组件落地） |
| T-02 | P1 | e2e 覆盖缺口 | 独立任务 | 至少覆盖降级链路与纹理提取主路径 |
| S-02 | P1 | 限流并发假设（单实例） | 扩容前置 | 多实例部署前改为共享存储或网关统一限流 |
| S-03 | P2 | 无 CSP/HSTS | 域名与证书启用时 | 生产 HTTPS 响应含 CSP 与 HSTS |
| P-02 | P2 | `public/` 84.37MB 静态资源 | 随 P-01 | 生产静态资源仅保留必要项 |
| A-01 | P2 | 双生图路由重复 | 后续重构 | 抽出共享校验/配额中间层 |
| Q-02 | P2 | 数据集模块错位 | 后续重构 | 迁出 `src/lib`，生产树不再含 Node 工具 |
| D-01 | P2 | 无 SCA | 发布门 | CI 或本地门含依赖漏洞扫描 |
| D-02 | P3 | `three` 死依赖 | 随手清理 | `package.json` 与锁文件移除 |
| D-03 | P3 | 类型与运行时版本不对齐 | 随手清理 | `@types/node` 对齐 Node 版本；`onnxruntime-web` 锁 minor |
| Q-03 | P3 | 文档维护成本 | 持续 | 按白皮书 §1.4 体积门槛执行归档 |

## 5. 与模型接入计划的关系

模型接入（WeVisOne-VL 精细抠图）只依赖两条前置结论：

1. **S-01 必须先行关闭**，否则新增路由会把本机文件读取面暴露给浏览器会话；
2. **Q-01 的规避要求**：新增能力必须落在独立模块与独立组件，不得继续增大 `NailArtPicker.tsx`。

其余 P1/P2 项与接入无技术依赖，作为独立清理任务排期：

- P-01（candidate57 资产）与 D-02（`three` 死依赖）在同一清理批次执行，先备份、后移动、再复验构建；
- T-01（构建门）在该批次后统一取证，避免两批改动混在同一份构建证据里；
- T-02、A-01、Q-02、D-01 属后续阶段，不在本次范围。

## 6. 复现命令

```powershell
# 规模与分层
(Get-ChildItem 'src' -Recurse -Include '*.ts','*.tsx').Count
Get-ChildItem 'src' -Recurse -Include '*.ts','*.tsx' | Sort-Object Length -Descending | Select-Object -First 15

# 静态资源与模型资产
Get-ChildItem 'public' -Recurse -File | Sort-Object Length -Descending | Select-Object -First 12
Get-ChildItem 'public/models' -Directory | ForEach-Object { (Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1MB }

# 质量指标
Select-String -Path 'src/**/*.ts','src/**/*.tsx' -Pattern ':\s*any\b|as any' -AllMatches
Select-String -Path 'src/**/*.ts','src/**/*.tsx' -Pattern 'TODO|FIXME|HACK' -AllMatches

# 测试与构建证据
Get-Content 'output/test-ui-optimize-20261028-serial.txt' -Tail 10
Get-ChildItem 'output' -Filter 'build-*.txt' | Sort-Object LastWriteTime -Descending
```

## 7. 复核节奏

- 本报告结论在每次接口、状态、配置、数据或模型契约变更后复核一次，变更记入当日 `dev-log/YYYY-MM-DD.md`；
- 优先级表关闭项须附可重放证据（命令输出、报告路径、构建日志），不接受口头确认；
- 报告本身不并入技术白皮书正文，白皮书只登记与接口/状态相关的结论指针。
