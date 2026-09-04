# 甲如 JiaRu — 让每一次抬手都遇见未来

**Web 端美甲试色应用**，无需下载安装，手机/电脑浏览器直接访问。上传照片涂色、文字描述 AI 生成、或打开摄像头 AR 实时试戴——在指尖预览美甲效果。

[![Next.js](https://img.shields.io/badge/Next.js-16.2.9-black?logo=next.js)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19.2.4-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4.x-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/license-private-red)](./LICENSE)

---

## 功能概览

| 模块 | 入口 | 状态 | 说明 |
| --- | --- | :---: | --- |
| 首页 | `/` | ✅ | 品牌展示 + 四大功能入口 |
| 涂色编辑器 | `/editor` | ✅ | 上传照片 → 五指独立选色 → Canvas 涂抹 → 本地保存 |
| AI 美甲生图 | `/ai-generate` | ✅ | 文字描述（+ 可选手部参考图图生图）+ 10 种风格提示词库（各 50 段） → 生成引擎可选（Agnes Image 2.1 Flash 默认 / 火山方舟 Seedream 5.0 pro·lite）；用户已完成真实功能验收并再次确认 |
| 灵感图库 | `/gallery` | ✅ | 6 张 Seedream 灵感图；卡片三入口（试色 / AI 相似款 / AR 试戴）打通到 `/editor`、`/ai-generate`、`/ar-tryon` 链路，AI 生成结果可一键本地 IndexedDB 收录至「我的收录」区块（无服务端后台；真实内容后台见待规划） |
| AR 纯色试戴 | `/ar-tryon` | 🚧 | 摄像头实时手部追踪 + 五指贴色 |
| AR 纹理试戴 | `/ar-tryon` | ⛔ | 上传参考图 → 美甲识别/mask 提取 → 纹理贴合；正式识别模型尚未发布 |
| 独立 AR 演示 | `/ar-demo` | 📌 | 桥接外部 Python demo 的 iframe 占位 |
| 登录/账号 | `/login`、`/account` | ✅ | 手机号+验证码登录即注册、微信 OAuth 登录；账号页管理档案、登录方式、改进计划偏好（初始版已落地，商户/云同步后续规划） |
| 隐私政策 | `/privacy` | ✅ | 完整静态说明页：核心原则（本地优先/数据由你掌控/不追踪）+ 用户改进计划开关（默认开启，可关闭）+ 各功能数据流向（试色/AI/AR/识别）+ 第三方服务与用户权利；法律合规审核仍待外部 |

> ✅ 已完成 　 📌 待验证 　 🚧 进行中 　 ⛔ 发布阻塞 　 ❌ 未开始

### 正式美甲识别模型状态

> **当前产品保持 HOLD。** 浏览器 Worker、WebGPU/WASM、候选排序、五指分配和 mask 纹理提取管线已经存在，但生产 ONNX 尚不存在；模型不可用时的规则 fallback 仅是降级辅助，不能表述为正式识别成功。

> **当前最高优先级：** 全力完成高质量正式美甲识别模型并接入发布链路。AI美甲生图已通过用户验收，除阻断性故障外不再占用当前研发主线。

- 已拒绝的 candidate5 不会部署或复用；它虽然通过 val30 和冻结 test100 正样本门，但在训练后全新100张困难负样本三变体审计中分别误检3/4/3张。
- candidate6 当前权威训练真值为120张/636个完整甲面mask；候选训练数据已物化为train280（120正样本+160空标签困难负样本）、val30/144 mask、test0，并通过独立输入深审。物化报告SHA-256为`3725ecf9…0209`，输入深审SHA-256为`e7dd1028…83cb`，数据文件树SHA-256为`acafc332…41d7`。
- candidate6 已按精确授权完成GPU训练：640、100 epochs上限、patience 20、自动batch、CUDA 0、8 workers，实际第71轮早停、最佳轮次51；最佳权重SHA-256为`5b169328…f800`。部署512的规范val30已校准候选阈值0.50，冻结test100也已完成评估并因下述逐实例质量门失败而正式否决。
- candidate6 已被冻结test100逐实例完整识别门否决：虽然部署512的full/core/stress mask mAP50为0.9621/0.9733/0.9286，但仅匹配491/554个完整甲面，漏63枚，41/100图存在漏甲，并有18个重复、30个额外候选和29个无效预测mask；仅38/100图可直接完整提取。该权重不得导出、登记或部署。
- candidate7 已完成200张/1123 mask正样本+160张困难负样本训练、A/B架构val30选择及一次性冻结test100。被选中的A权重SHA-256为`567ac8b9…e355`，总体mask mAP50为0.9517，但逐实例门仅匹配440/554、完整mask397、57/100图漏甲、29/100图可直接提取，因此正式否决且未导出/登记/部署。
- 项目范围图像与本机计算资源已有持续商业使用授权，不再逐批等待清单、训练启动或freeze确认；train/val/test/holdout角色隔离、原分辨率完整甲面、独立困难负样本三变体零误检等质量门不变。
- candidate8全新隔离来源31张已收敛为10张/87 mask训练真值、19张质量排除、2张隔离；与candidate7基线合并为210张/1210 mask正样本，加入160困难负样本后规范train370/val30/test0输入审计PASS。
- candidate8 nano已完成训练并在val30锁定阈值0.55；冻结test100逐实例召回提升至0.870、漏甲降至72，但完整mask与漏甲图片率仍未过门。高容量分支仅用val30比较后淘汰。当前继续补充全新来源完整甲面真值，两个分支均未导出或部署。
- candidate9已从既有真实素材中盘出75张/22来源组/预计552甲面的全新未审增量；当前先做源图质量门和完整mask终审，审核前全部禁止训练。
- candidate18—21：candidate18直接微调冻结test100识别门失败；candidate19/20常规微调在val30否决；candidate21（alpha0.60权重插值学生）为当前最优识别基线，冻结test100实例召回0.93682、完整mask 0.84116、缺图率0.20、可提取53/100，但完整率/缺图率/唯一性门仍未过，产品继续HOLD。
- candidate22/23：直接学生训练与预注册插值对照，均未优于candidate21而在val30否决，未运行冻结test100、未导出/登记/部署。
- candidate24/25均已在val30否决：candidate24为128匹配/16漏检/27误检，candidate25最佳点仅与candidate21的128/16/19打平；candidate27三种候选复核器也未能在保持召回时降低误检，三者均未运行冻结test100、未导出或部署。当前改为candidate28“完整美甲识别优先”：新困难负样本计划暂停在70/160，训练时只使用既有批准集合的有限来源平衡子集；`01138…_7`与超长透明甲`01130…_10`两张五甲人工polygon使补强索引达到62张/429 mask。发布侧独立困难负样本三变体零误检门不变。
- candidate28已物化为274张正样本/1652 mask并完成v5全分辨率边界训练，但部署512的val30在阈值0.50仅122匹配/22漏检/12误检，未保持candidate21的128匹配而在val阶段否决。candidate21与candidate28按预注册alpha插值后，alpha0.15在阈值0.45取得128匹配/16漏检/16误检并锁为candidate29；其在已消费test100受保护回归上为519/554匹配、467完整mask，但完整mask比例0.84296、缺甲图率0.20、加权伪实例率0.11372仍未过正式门，不得导出或部署。
- candidate30改为从已审计train角色生成确定性的“全部甲面联合近景”增强（polygon零丢失零裁断、20%上下文、裁剪面积不高于原图85%），从candidate29 alpha0.15初始化，继续以来源隔离val30为唯一选择证据：须保持至少128匹配、至多16漏检并把误检严格降到16以下。尚未开始训练。
- 正式发布还需生产ONNX登记、真实浏览器回归、Android手机/平板、iPhone/iPad真机、至少100张Beta人工审核和双版本回滚验证。只有完成度审计返回`ok=true`且`decision=complete`才解除HOLD。

---

## 快速开始

### 前置要求

- **Node.js** ≥ 20（当前开发环境 v24.16.0）
- **npm** ≥ 10（Windows 下必须使用 `npm.cmd` 而非裸 `npm`，避免触发 System32 零字节文件）

### 本地开发

```powershell
# 1. 克隆仓库
git clone https://github.com/yaoyinyu/JiaRu.git
cd JiaRu

# 2. 安装依赖
npm.cmd install

# 3. 启动开发服务器（自动启用 HTTPS）
npm.cmd run dev
```

浏览器打开 `https://localhost:3000`。

> **注意：** 摄像头功能必须通过 `localhost` 或正式 HTTPS 域名访问，普通局域网 HTTP 地址无法使用。首次启动时 Next.js 可能生成自签名证书，浏览器需手动信任。

### 生产构建

```powershell
npm.cmd run build
npm.cmd run start
```

### 验证命令

```powershell
npm.cmd run lint          # ESLint 检查
npm.cmd run test           # 全量测试（当前 163 个测试文件，串行执行）
npm.cmd run audit:encoding # 文本文件编码审计（当前 485 个文件）
npm.cmd run build          # Next.js 生产构建
```

---

## 项目结构

```
JiaRu/
├── src/
│   ├── app/                      # Next.js App Router 页面
│   │   ├── page.tsx              # 首页（品牌 + 功能入口卡片）
│   │   ├── layout.tsx            # 根布局
│   │   ├── editor/page.tsx       # 涂色编辑器
│   │   ├── gallery/page.tsx      # 灵感图库
│   │   ├── ai-generate/page.tsx  # AI 文生图
│   │   ├── ar-tryon/page.tsx     # AR 实时试戴
│   │   ├── ar-demo/page.tsx      # 独立 AR 演示桥接
│   │   ├── privacy/page.tsx      # 隐私政策
│   │   ├── login/page.tsx        # 登录页（手机号+验证码 / 微信）
│   │   ├── account/page.tsx      # 账号页（档案/登录方式/改进计划/退出）
│   │   ├── api/generate-ai/route.ts  # AI 生图 API（Agnes）
│   │   ├── api/generate-seedream/route.ts  # AI 生图 API（火山方舟 Seedream）
│   │   ├── api/auth/             # 认证 API（验证码/人机验证/微信 OAuth/登出/绑手机）
│   │   └── api/me/               # 账号 API（档案/登录方式/改进计划偏好）
│   │
│   ├── components/               # 可复用组件
│   │   ├── ArView.tsx            # AR 核心：摄像头 + MediaPipe + 指甲绘制（~1150 行）
│   │   ├── NailCanvas.tsx        # 涂色画布组件
│   │   ├── ColorPalette.tsx      # 颜色选择器（20 种预设色 + 自定义取色）
│   │   ├── UploadButton.tsx      # 图片上传按钮
│   │   ├── TextureCropper.tsx    # 纹理手动裁剪器
│   │   ├── NailArtPicker.tsx     # 纹理自动识别与五指分配
│   │   ├── GalleryGrid.tsx       # 图库网格
│   │   ├── Header.tsx            # 顶部导航
│   │   ├── AppShell.tsx          # 页面壳（导航 + 页脚）
│   │   ├── Icon.tsx              # 内联 SVG 矢量图标组件（15 个图标）
│   │   └── FlowingShell.tsx      # 流式布局壳
│   │
│   ├── lib/                      # 工具与核心逻辑
│   │   ├── utils.ts              # 通用工具（颜色、图片、AI 风格名称等）
│   │   ├── ai-style-prompts.ts   # AI 生图风格提示词库（10 风格 × 50 段）
│   │   ├── ai-hand-anatomy-prompt.ts  # AI 生图两套系统提示词（文生图/图生图互斥）
│   │   ├── agnes-image-api.ts    # Agnes 图像 API 客户端（文生图/图生图）
│   │   ├── seedream-image-api.ts # 火山方舟 Seedream 图像 API 客户端（扁平 body/Ark 错误体系）
│   │   ├── seedream-image-size.ts # Seedream 尺寸档位表（档位×比例→显式宽高像素）
│   │   ├── seedream-prompt.ts    # Seedream 专用精简系统提示词（独立于 Agnes）
│   │   ├── texture.ts            # 纹理处理（裁剪、缩放、释放）
│   │   ├── ar-hand-orientation.ts # AR 手部朝向检测（4 传感器融合）
│   │   ├── ar-video-layout.ts    # 视频自适应布局（cover 裁切）
│   │   ├── image-upload-validation.ts # 图片上传校验（MIME/大小/分辨率/解码）
│   │   ├── nail-geometry.ts       # 指甲几何计算
│   │   ├── nail-detection-fixture.ts  # 检测夹具
│   │   ├── nail-image-detection.ts    # 图片端指甲检测
│   │   ├── nail-texture-dataset.ts    # 纹理数据集工具
│   │   ├── nail-texture-debug-sample.ts    # 调试样本
│   │   ├── nail-texture-debug-priority.ts  # 调试优先级
│   │   ├── auth/                 # 用户认证库（SQLite/JWT/图形验证码/短信/微信 OAuth/登录即注册）
│   │   └── nail-texture-recognition/     # 浏览器端美甲纹理识别子系统
│   │       ├── index.ts          # 公共 barrel（Worker/主线程入口）
│   │       ├── recognize.ts      # 主识别流程
│   │       ├── model-runtime.ts  # ONNX Runtime Web 推理
│   │       ├── preprocess.ts     # 输入预处理（letterbox 等）
│   │       ├── postprocess.ts    # 后处理（NMS、mask 解码）
│   │       ├── quality.ts        # 候选质量排序
│   │       ├── finger-assignment.ts  # 候选→五指分配
│   │       ├── extract-mask-texture.ts # 带 mask 纹理提取
│   │       ├── fallback-adapter.ts   # 模型不可用时的传统降级
│   │       ├── input-scaling.ts      # 输入缩放
│   │       ├── client-worker.ts      # Worker 客户端
│   │       ├── types.ts              # 类型定义
│   │       ├── debug.ts/debug-artifacts.ts/debug-compare.ts # 调试工具
│   │       └── first-run-record.ts   # 首跑记录验证
│   │
│   └── workers/
│       └── nail-texture-recognition.worker.ts  # Web Worker 入口
│
├── model/                        # 模型训练与数据集
│   ├── datasets/nail-texture-v1/ # 基础正式集（409 图/2142 mask）
│   ├── training/                 # 训练脚本、标注辅助、审计工具
│   └── reports/                  # 审计报告
│
├── scripts/                      # 审计/验证/发布治理脚本
├── tests/                        # 测试文件（当前 350+ 项）
├── docs/                         # 项目文档（见下方索引）
├── dev-log/                      # 开发日志（按天，2026-06-21 至今）
├── public/
│   ├── models/                   # 浏览器端模型（smoke ONNX 等）
│   └── nail-gallery/             # 灵感图库素材（AI 生成 JPG；旧占位 SVG 保留未删）
├── weights/                      # 本地权重（不上传 Git）
├── certificates/                 # 本地开发证书
└── 辅助材料/                     # 参考资料
```

---

## 核心特性详解

### 🖐️ AR 实时试戴

核心技术管线：

```
用户点击「开启摄像头」（单按钮，一次点击即触发权限请求）
  → getUserMedia 获取前置摄像头视频流
  → MediaPipe Hands 加载 21 关键点手部模型（CDN）
  → requestAnimationFrame 循环：
      ├─ 4 传感器融合全局朝向检测（叉积/深度差/4 指投票/拇指位置）
      ├─ 5 指逐指可见性判定（TIP.z vs DIP.z + 透视缩短比 + 伸展角）
      ├─ 贝塞尔路径指甲形状（每指独立参数：尖端收窄/侧面曲线/根部凸起）
      ├─ 纹理柱面曲率变形（12 条分片 + 三层高光 + 环境光照）
      └─ 手指可见性指示器 + 朝向 UI
```

**关键能力：**
- **逐指独立判定：** 每指独立判断可见性，支持混合状态（如 3 指贴图 + 2 指不贴）
- **手势兼容：** 支持 ✌️ 比耶 / 👍 点赞 / 👊 握拳 / 🤘 摇滚 / ☝️ 食指 / 🤙 打电话等任意手势
- **两层防御：** 全局门控（手心侧不贴图）+ 逐指过滤
- **指甲差异化：** 每指独立形状参数（尖端收窄/侧面曲线/根部凸起）
- **解剖校准：** 基于真实甲床比例的逐指长度/宽度比
- **左右手识别：** 逐指可见性指示器 UI + 手指名称

### 🎨 涂色编辑器

纯前端 Canvas 涂色引擎：
- 上传校验：JPG/PNG/WebP、≤10MB、320–4096px、解码门禁
- 五指独立选色：20 种预设流行色 + 自定义取色器
- 涂抹 + 撤销 + 重置 + 本地保存（全程浏览器内存，无网络请求）

### 🤖 AI 文生图 / 图生图（已验证）

- 前端状态机：`idle → loading → success/error`
- 10 种预设风格（甜美风/欧美风/日系/极简/复古/节日/水墨/几何/花草/金属）
- 每风格 50 段独立中文场景提示词，点击轮转填入
- 用户输入 1–520 字符 + 自动附加美甲场景后缀
- **生成引擎可选**：Agnes（默认）/ 火山方舟 Seedream 5.0 Pro / Seedream 5.0 Lite；切换引擎时尺寸档位与提示词上限联动
- **画面比例**（1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9）与**输出尺寸档位**可选，实时显示最终像素尺寸（默认 1K+1:1 ≈ 1024x1024，参考 Agnes「输出尺寸参考」表）；Seedream 档位随模型不同（pro：1K/1.5K/2K，lite：2K/3K/4K），比例经「档位×比例→显式宽高像素」换算后随请求发送
- **参考图（可选）**：上传手部照片（浏览器端压缩至最长边 1024 的 JPEG），结合提示词走图生图——在参考图手部指甲上直接绘制美甲样式，保持手部姿势与场景不变；不上传则按文字直接生成（行为与历史一致）
- 后端 API Route：Agnes 走 `/api/generate-ai`（需 `AGNES_API_KEY`）；Seedream 走 `/api/generate-seedream`（需 `VOLCENGINE_ARK_API_KEY` 与两个 Model ID），两条链路完全独立互不影响
- Seedream 使用独立精简系统提示词（约 100 字核心手部约束，提示词上限 300 字，符合火山方舟建议），区别于 Agnes 的长提示词
- 超时与重试：Agnes 180 秒总超时、503 退避重试；Seedream 240 秒总超时、429/500/503 退避重试
- 仅发送文字描述；只有上传参考图时图片才发送给第三方（仅用于本次生成，不存储）；Seedream 生成图片默认不添加"AI 生成"水印（可用 `ARK_IMAGE_WATERMARK=true` 开启）

### 👤 用户系统（初始注册登录已落地）

- **登录即注册**：手机号+验证码或微信扫码，任一方式首次验证通过即自动创建账号并绑定
- 手机号+验证码：发送前需通过自研 SVG 图形验证码（人机验证），60 秒节流 / 单日 10 条 / 尝试 5 次锁定；未配置短信服务商时进入开发模式（接口返回 devCode 仅供本地联调）
- 微信 OAuth：`GET /api/auth/oauth/wechat` 授权跳转 + `/callback` 回调登录，state 存 httpOnly Cookie 防 CSRF；首次登录须在 `/account` 补绑手机号；未配置 `WECHAT_APP_ID/SECRET` 时按钮显示「未配置」
- 认证实现：自研 HS256 JWT（access 2h + refresh 30d）+ SQLite 会话表（可踢下线），数据库 `data/jiaru-user.db`（Node 内置 `node:sqlite`，生产换 Postgres 时仅替换 `src/lib/auth/db.ts` 边界）
- `/account` 账号页：档案查看、登录方式管理（解绑，至少保留一种）、账号级「用户改进计划」偏好（与 `/privacy` 开关联动）、退出登录
- 完整设计见 [`docs/user-system-plan.md`](docs/user-system-plan.md)（v0.2）；商户体系、云端作品/配额、注销导出为后续 Phase 1 项

### 🧠 浏览器端纹理识别（发布阻塞）

完整浏览器端 ONNX Runtime Web 推理管线：
- ONNX Runtime Web 推理（WebGPU 优先 → WASM 降级）
- Web Worker 隔离（15 秒超时 + 自动 fallback）
- 候选质量排序 + 五指分配 + mask 纹理提取
- 浏览器运行时与既有桌面性能证据可继续复用，但它们不等同于生产识别模型已经发布
- 冻结 test100 正样本集为100张/554 mask；它只能评估候选，不能用于阈值选择
- candidate5 已被训练后全新困难负样本留出否决，禁止部署或改名复用
- candidate6 正样本真值为120张/636 mask，训练、val30校准和冻结test100审计均已完成；候选因逐实例完整识别门失败而否决
- candidate7、candidate8均已完成训练与冻结test100并因逐实例完整识别门失败而否决；candidate8已显著降低漏甲，但仍需全新来源正样本继续补强
- 正式模型不可用时可以进入规则降级或人工框选，但 UI 必须明确告知降级，不能显示为“模型识别成功”

---

## 环境变量

| 变量 | 说明 | 必须 |
| --- | --- | :---: |
| `AGNES_API_KEY` | Agnes API 密钥（仅服务端读取） | AI 生成功能需要 |
| `AGNES_API_BASE_URL` | Agnes API 基础地址 | 否（默认 `https://apihub.agnes-ai.com/v1`） |
| `AGNES_IMAGE_MODEL` | Agnes 图片模型 ID | 否（默认 `agnes-image-2.1-flash`） |
| `VOLCENGINE_ARK_API_KEY` | 火山方舟 API 密钥（仅服务端读取） | Seedream 引擎需要 |
| `ARK_SEEDREAM_PRO_MODEL` | Seedream 5.0 pro Model ID（控制台查询） | Seedream 引擎需要 |
| `ARK_SEEDREAM_LITE_MODEL` | Seedream 5.0 lite Model ID（控制台查询） | Seedream 引擎需要 |
| `ARK_BASE_URL` | 火山方舟基础地址 | 否（默认 `https://ark.cn-beijing.volces.com/api/v3`） |
| `ARK_IMAGE_WATERMARK` | Seedream 生成图是否添加"AI 生成"水印 | 否（默认关闭） |
| `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL` | 浏览器端纹理模型 manifest 路径 | 否（有默认值） |
| `JWT_SECRET` | JWT 签名密钥（生产必须 ≥16 位随机字符串；未配置时本地开发用内置回退密钥，生产构建直接报错） | 用户系统生产必需 |
| `JIARU_DB_PATH` | 用户数据库文件路径 | 否（默认 `<项目根>/data/jiaru-user.db`） |
| `SMS_PROVIDER` | 短信服务商（留空进入开发模式，验证码经接口返回仅供本地联调；生产留空会拒绝发送） | 生产短信必需 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信开放平台「网站应用」OAuth 2.0 凭证（需认证企业主体） | 微信登录需要 |

```powershell
# 复制模板
copy .env.local.example .env.local
# 编辑 .env.local 填入密钥
```

---

## 文档索引

### 核心文档

| 文档 | 说明 |
| --- | --- |
| [技术白皮书](docs/technical-whitepaper.md) v1.1.592 | 模块状态、接口契约、使用方式、已知限制——项目唯一总入口 |
| [技术架构](docs/technical-architecture.md) | 技术选型、架构图、AR 管线、关键参数表 |
| [需求文档](docs/requirements.md) | 功能需求、用户故事、验收标准 |
| [UI 设计规范](docs/ui-design-spec.md) | 品牌色、字体、组件样式、AR 交互规范 |
| [开发规范](docs/coding-standards.md) | 代码风格、命名规范、工作流程 |
| [用户管理系统文档](docs/user-system-plan.md) | 角色权限/资源/配额/流程/API/合规/分阶段路线（v0.2，初始注册登录已实现） |

### AR 专项文档

| 文档 | 说明 |
| --- | --- |
| [全局朝向门控修复](docs/global-render-gate-fix.md) | 两层防御体系（全局门控 + 逐指过滤） |
| [逐指可见性增强](docs/finger-visibility-enhancement.md) | 三信号融合 + 时序平滑 |
| [逐指识别与左右手](docs/finger-hand-identification.md) | UI 指示器 + 指甲形状差异化 |
| [手势兼容检测](docs/gesture-compatible-detection.md) | 手指伸展角信号 D 四信号融合 |
| [手心/手背朝向检测](docs/palm-orientation-spec.md) | 4 传感器融合方案 |
| [指甲检测优化](docs/nail-detection-optimization.md) | 6 项参数/逻辑改进 |
| [指甲纹理分配器](docs/nail-art-picker.md) | 上传图 → MediaPipe → 5 指分配 |

### 开发日志

从项目启动至今的完整开发记录： [`dev-log/`](dev-log/)（2026-06-21 至今，共 53 天）

---

## 隐私与数据

**核心原则：数据默认在浏览器本地处理，用户改进计划默认开启、可随时关闭。**

| 功能 | 数据处理 |
| --- | --- |
| 涂色编辑器 | 照片默认在浏览器 Canvas 本地处理，保存为本地 PNG |
| AR 试戴 | 摄像头帧默认仅存内存，不录制 |
| AI 生图 | 默认仅发送文字描述到服务端；上传参考图时该图片也会发送（仅用于本次生成） |
| 纹理识别 | 浏览器 Worker 本地推理 |
| 用户改进计划 | 开关默认开启：手部照片等数据可能被上传用于产品改进；关闭后不再上传任何数据（开关位于 `/privacy`，登录用户可在 `/account` 同步） |
| 用户系统 | 登录信息（手机号/微信身份、JWT 会话）仅存服务端数据库，用于登录与账号管理；核心功能不登录也可用，账号数据不出售 |

完整说明见 [`/privacy`](http://localhost:3000/privacy)（最后更新 2026-08-19）。AI 生图会把你的文字描述转发给第三方图像生成服务（Agnes AI）；只有当你上传参考图时，该图片才会被发送并仅用于本次生成、不用于训练或存储。生成结果由浏览器直接访问第三方图片地址；描述中请勿输入身份证号、电话等个人信息。项目不使用 Cookie 追踪、无广告追踪，联系邮箱 `3181484805@qq.com`。

---

## 路线图

### Phase 1: MVP ✅ 完成

- [x] 首页、编辑器、图库、隐私页
- [x] ESLint 0 errors、350+ 测试通过、生产构建通过

### Phase 2: AI 生成 ✅ 完成

- [x] Agnes Image 2.1 Flash API 集成、10 风格 × 50 段提示词库
- [x] 前端状态机、错误处理、图片保存
- [x] 用户真实生图功能验收通过（2026-08-10；2026-08-12再次确认）

### Phase 3: AR 实时试戴 🚧 核心功能完成，待真机验证

- [x] 摄像头管线、MediaPipe 手部检测
- [x] 逐指可见性判定（4 信号融合）
- [x] 全局朝向检测（4 传感器融合）
- [x] 贝塞尔路径指甲形状
- [x] 纹理柱面曲率变形
- [x] 手势兼容检测
- [x] 左右手识别 + 反转手按钮
- [ ] 手机端多设备真机测试
- [ ] 阈值实测调优
- [ ] 3D AR 试戴（Three.js 已安装）

### Phase 4: 纹理识别模型 ⛔ 正样本补强中，发布HOLD

- [x] 浏览器端 ONNX Runtime Web 推理管线
- [x] 正式数据集（409 图/2142 mask）
- [x] 浏览器Worker、WebGPU/WASM、候选后处理与mask提取管线
- [x] 独立发布测试集冻结到 100 张/554 mask（核心 78 张、压力 22 张）
- [x] candidate5完成训练、val30和冻结test100审计，但被训练后全新困难负样本留出否决
- [x] 补足 33 张来源隔离的代表性发布测试图并完成逐甲真值终审
- [x] candidate6正样本160张精确商业训练授权
- [x] candidate6高质量训练真值与当前候选输入终审（120张/636 mask）
- [x] candidate6训练集物化与来源隔离输入深审
- [x] 按精确输入、基座与参数授权完成candidate6 GPU训练（最佳权重`5b169328…f800`）
- [x] 仅用来源隔离val30校准候选阈值0.50
- [x] candidate7完成200正样本/1123 mask+160困难负样本训练、A/B val30选择和一次性冻结test100审计
- [x] candidate8全新来源正样本完整mask终审、训练、val30校准与冻结test100评估（逐实例门仍失败）
- [x] candidate24/25与candidate27复核器均在val30阶段否决，未消费冻结test100
- [x] 将训练重心切换为完整甲面正真值，困难负样本扩充暂停在70/160且不降低发布零误检门
- [x] `01130…_10`超长透明甲五甲全量人工polygon返修通过，candidate9补强规范真值v32达62张/429 mask
- [ ] candidate28继续补齐透明、低对比、侧视和超长甲的完整mask，并在形成有效增量后训练
- [x] candidate28全分辨率边界训练完成并在val30否决（122匹配/22漏检/12误检）
- [x] candidate29预注册alpha插值锁定alpha0.15（val30为128匹配/16漏检/16误检），受保护回归test100仍HOLD
- [ ] candidate30用甲面联合近景增强训练并以val30为唯一选择证据
- [x] candidate56复用candidate52深审输入完成512方形stage1训练（最佳权重SHA-256 `64628504…c272`），单stage1与联合candidate55边界精修两条链均在来源隔离val30拒绝，未读取test100
- [x] candidate57低置信带组合门val30通过（129匹配/15漏检/16误检、边界F1 `0.6139459`）并锁定不可反调复合运行时，详见白皮书§12.11
- [ ] 通过冻结test100逐实例完整识别门（candidate6、candidate7、candidate8、candidate29均已否决；candidate57锁定运行时已完成冻结test100验收，实例召回率`0.95848375`与完整mask率`0.86462094`通过，漏检图片率`0.13`与加权杂散率`0.04693141`仍失败，产品HOLD）
- [ ] 训练后另建、原子冻结并终审不少于100张全新未见困难负样本
- [ ] 部署512三变体达到误检图片0、误检检测0、相对原图delta 0
- [ ] 导出并登记生产ONNX，接入`/ar-tryon`正式多纹理识别和像素级mask提取
- [ ] 移动真机 WebGPU 性能验证
- [ ] Beta 人工质量审核（100 张）
- [ ] 两个独立批准版本的回滚验证与最终`ok=true / decision=complete`审计

### 待规划

- [ ] Vercel 部署 + 域名绑定
- [ ] 真实灵感图库与内容后台
- [ ] 用户系统 Phase 1 剩余项：商户体系、云端作品/收藏/历史、AI 配额、注销导出、游客数据合并
- [ ] 正式 API 鉴权、限流、内容安全
- [ ] ArView.tsx 拆分（1150 行 → 多模块）

---

## 技术栈

| 层级 | 技术 | 版本 |
| --- | --- | --- |
| 框架 | Next.js App Router | 16.2.9 |
| UI | React | 19.2.4 |
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS | 4.x |
| 手部关键点 | MediaPipe Hands | 浏览器端，CDN 加载 |
| 纹理推理 | ONNX Runtime Web | 1.27.0（WebGPU/WASM） |
| 3D | Three.js | 0.184.0（已安装，未使用） |
| AI 生图 | Agnes Image 2.1 Flash + 火山方舟 Seedream 5.0（pro/lite，引擎可选） | 服务端 API |
| 部署 | Vercel | 待配置 |
