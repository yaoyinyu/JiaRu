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
| AI 美甲生图 | `/ai-generate` | ✅ | 文字描述 + 10 种风格提示词库（各 50 段） → Agnes Image 2.1 Flash 生成；用户已完成真实功能验收并再次确认 |
| 灵感图库 | `/gallery` | 📌 | SVG 占位素材浏览，后续接入真实内容后台 |
| AR 纯色试戴 | `/ar-tryon` | 🚧 | 摄像头实时手部追踪 + 五指贴色 |
| AR 纹理试戴 | `/ar-tryon` | ⛔ | 上传参考图 → 美甲识别/mask 提取 → 纹理贴合；正式识别模型尚未发布 |
| 独立 AR 演示 | `/ar-demo` | 📌 | 桥接外部 Python demo 的 iframe 占位 |
| 隐私政策 | `/privacy` | 📌 | 静态说明页 |

> ✅ 已完成 　 📌 待验证 　 🚧 进行中 　 ⛔ 发布阻塞 　 ❌ 未开始

### 正式美甲识别模型状态

> **当前产品保持 HOLD。** 浏览器 Worker、WebGPU/WASM、候选排序、五指分配和 mask 纹理提取管线已经存在，但生产 ONNX 尚不存在；模型不可用时的规则 fallback 仅是降级辅助，不能表述为正式识别成功。

> **当前最高优先级：** 全力完成高质量正式美甲识别模型并接入发布链路。AI美甲生图已通过用户验收，除阻断性故障外不再占用当前研发主线。

- 已拒绝的 candidate5 不会部署或复用；它虽然通过 val30 和冻结 test100 正样本门，但在训练后全新100张困难负样本三变体审计中分别误检3/4/3张。
- candidate6 正样本商业训练授权清单共160张/预计971枚甲面；截至技术白皮书 v1.1.388，已有99张/519个完整甲面通过原分辨率终审，尚余61张/预计452枚甲面。
- 当前权威真值索引仍为`trainingUse=prohibited-until-materialization-audit`，因此尚未启动 candidate6 训练、val30阈值校准、冻结test100推理或生产模型导出。
- candidate6 训练完成后，还必须另建不少于100张全新未见困难负样本，并在部署尺寸512下对原图、裁右下12%和模糊右下角三种变体同时达到误检图片数0、误检检测数0、相对原图delta 0。
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
│   │   └── api/generate-ai/route.ts  # AI 生图 API
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
│   │   └── FlowingShell.tsx      # 流式布局壳
│   │
│   ├── lib/                      # 工具与核心逻辑
│   │   ├── utils.ts              # 通用工具（颜色、图片、AI 风格名称等）
│   │   ├── ai-style-prompts.ts   # AI 生图风格提示词库（10 风格 × 50 段）
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
│   └── nail-gallery/             # 图库占位 SVG
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

### 🤖 AI 文生图（已验证）

- 前端状态机：`idle → loading → success/error`
- 10 种预设风格（甜美风/欧美风/日系/极简/复古/节日/水墨/几何/花草/金属）
- 每风格 50 段独立中文场景提示词，点击轮转填入
- 用户输入 1–500 字符 + 自动附加美甲场景后缀
- 后端 API Route → Agnes Image 2.1 Flash（需 `AGNES_API_KEY`）
- 180 秒总超时（AbortController），503 按 1/2/4 秒指数退避重试
- 仅发送文字描述，不发送用户原图

### 🧠 浏览器端纹理识别（发布阻塞）

完整浏览器端 ONNX Runtime Web 推理管线：
- ONNX Runtime Web 推理（WebGPU 优先 → WASM 降级）
- Web Worker 隔离（15 秒超时 + 自动 fallback）
- 候选质量排序 + 五指分配 + mask 纹理提取
- 浏览器运行时与既有桌面性能证据可继续复用，但它们不等同于生产识别模型已经发布
- 冻结 test100 正样本集为100张/554 mask；它只能评估候选，不能用于阈值选择
- candidate5 已被训练后全新困难负样本留出否决，禁止部署或改名复用
- candidate6 正样本真值当前为99张/519 mask，剩余61张；完成训练物化审计前保持训练禁用
- 正式模型不可用时可以进入规则降级或人工框选，但 UI 必须明确告知降级，不能显示为“模型识别成功”

---

## 环境变量

| 变量 | 说明 | 必须 |
| --- | --- | :---: |
| `AGNES_API_KEY` | Agnes API 密钥（仅服务端读取） | AI 生成功能需要 |
| `AGNES_API_BASE_URL` | Agnes API 基础地址 | 否（默认 `https://apihub.agnes-ai.com/v1`） |
| `AGNES_IMAGE_MODEL` | Agnes 图片模型 ID | 否（默认 `agnes-image-2.1-flash`） |
| `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL` | 浏览器端纹理模型 manifest 路径 | 否（有默认值） |

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
| [技术白皮书](docs/technical-whitepaper.md) v1.1.372 | 模块状态、接口契约、使用方式、已知限制——项目唯一总入口 |
| [技术架构](docs/technical-architecture.md) | 技术选型、架构图、AR 管线、关键参数表 |
| [需求文档](docs/requirements.md) | 功能需求、用户故事、验收标准 |
| [UI 设计规范](docs/ui-design-spec.md) | 品牌色、字体、组件样式、AR 交互规范 |
| [开发规范](docs/coding-standards.md) | 代码风格、命名规范、工作流程 |

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

**核心原则：图片和摄像头数据尽量留在浏览器本地。**

| 功能 | 数据处理 |
| --- | --- |
| 涂色编辑器 | 照片在浏览器 Canvas 本地处理，保存为本地 PNG |
| AR 试戴 | 摄像头帧仅存内存，**不录制、不上传** |
| AI 生图 | 仅发送文字描述到服务端，**不发送原图** |
| 纹理识别 | 浏览器 Worker 本地推理，不上传 |

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
- [ ] candidate6完整甲面真值终审（当前99张/519 mask，剩余61张/预计452 mask）
- [ ] 训练集物化与来源隔离审计后训练candidate6
- [ ] 仅用来源隔离val30校准阈值，并通过冻结test100正样本门
- [ ] 训练后另建、精确授权、原子冻结并终审不少于100张全新未见困难负样本
- [ ] 部署512三变体达到误检图片0、误检检测0、相对原图delta 0
- [ ] 导出并登记生产ONNX，接入`/ar-tryon`正式多纹理识别和像素级mask提取
- [ ] 移动真机 WebGPU 性能验证
- [ ] Beta 人工质量审核（100 张）
- [ ] 两个独立批准版本的回滚验证与最终`ok=true / decision=complete`审计

### 待规划

- [ ] Vercel 部署 + 域名绑定
- [ ] 真实灵感图库与内容后台
- [ ] 用户账户、云同步
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
| AI 生图 | Agnes Image 2.1 Flash | 服务端 API |
| 部署 | Vercel | 待配置 |
