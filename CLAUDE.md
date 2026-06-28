# 甲如 (JiaRu) Web 美甲试色应用

## 项目概述

**技术栈**: Next.js 16.2.9 + React 19.2.4 + TypeScript + Tailwind CSS 4
**部署目标**: Vercel (HTTPS + CDN)
**当前阶段**: Phase 1 MVP ✅ 完成 / Phase 2 AI ✅ 完成 / Phase 3 AR 🚧 核心功能完成，待真机验证

## 项目标准文件索引

### 开发规范与标准文档
| 文件 | 说明 |
|------|------|
| [docs/requirements.md](docs/requirements.md) | 项目需求文档 — 功能需求、用户故事、验收标准（含 AR 验收） |
| [docs/technical-architecture.md](docs/technical-architecture.md) | 技术架构文档 — 技术选型、架构图、AR 管线、参数表 |
| [docs/ui-design-spec.md](docs/ui-design-spec.md) | UI设计规范 — 配色、字体、组件样式、AR 交互规范 |
| [docs/coding-standards.md](docs/coding-standards.md) | 开发规范 — 代码风格、命名规范、AR 开发经验教训 |
| [docs/phase-1-execution-spec.md](docs/phase-1-execution-spec.md) | 执行计划 — Phase 1 (7 Task) + Phase 3 AR (10 AR-Task) 进度追踪 |
| [docs/global-render-gate-fix.md](docs/global-render-gate-fix.md) | 全局朝向门控修复 — 两层防御体系 |
| [docs/finger-visibility-enhancement.md](docs/finger-visibility-enhancement.md) | 逐指可见性增强 — 三信号融合 + 时序平滑 |
| [docs/finger-hand-identification.md](docs/finger-hand-identification.md) | 逐指识别与左右手识别 — UI + 指甲形状差异化 |
| [docs/hand-flip-button.md](docs/hand-flip-button.md) | 反转手按钮 — 前置摄像头镜像补偿 |
| [docs/hand-flip-orientation-fix.md](docs/hand-flip-orientation-fix.md) | 反转手朝向修复 — shallRenderNails 用原始 handedness |
| [docs/nail-detection-optimization.md](docs/nail-detection-optimization.md) | 指甲检测优化 — 6 项参数/逻辑改进 |
| [docs/gesture-compatible-detection.md](docs/gesture-compatible-detection.md) | 手势兼容检测 — 手指伸展角信号 D 四信号融合 |
| [docs/palm-orientation-spec.md](docs/palm-orientation-spec.md) | 朝向检测技术方案 — 4 传感器融合（已实现） |
| [docs/palm-orientation-improvement.md](docs/palm-orientation-improvement.md) | 朝向检测改进 — 不对称阈值 + 宽松策略 |
| [docs/palm-orientation-review.md](docs/palm-orientation-review.md) | 朝向检测评审 — 早期方案评审记录 |
| [docs/nail-art-picker.md](docs/nail-art-picker.md) | 指甲纹理分配器 — 上传图→MediaPipe→5 指分配 |
| [docs/nail-auto-detection.md](docs/nail-auto-detection.md) | 指甲自动检测 — 纹理自动分配流程 |

### 开发日志
| 文件 | 说明 |
|------|------|
| [dev-log/2026-06-21.md](dev-log/2026-06-21.md) | 项目初始化 |
| [dev-log/2026-06-22.md](dev-log/2026-06-22.md) | 首页交互 + AR 模块开发 |
| [dev-log/2026-06-23.md](dev-log/2026-06-23.md) | Phase 1 修复 + AR 手心/手背检测实现 |
| [dev-log/2026-06-24.md](dev-log/2026-06-24.md) | AR 功能完整开发：6 修复 + 5 功能 + 手势兼容 + 逐指 4 信号融合 |
| [dev-log/2026-06-25.md](dev-log/2026-06-25.md) | 项目扫描审计 + 冲突修复 + ESLint 8→0 errors |
| [dev-log/2026-06-28.md](dev-log/2026-06-28.md) | 清理任务 + Phase 2 AI 生成模块完成 |

### 项目记忆
记忆文件存储在 `C:\Users\YaoYinyu\.claude\memory\` 目录下：
- `jia-ru-nail-app.md` — 项目信息、技术选型、路线图
- `MEMORY.md` — 记忆索引文件

## 当前进度

### Phase 1: MVP ✅ 完成
- 首页、编辑器、图库、隐私页全部完成
- ESLint 0 errors, build 通过
- 五指独立选色、SVG 图库修复、NailCanvas useRef 重构

### Phase 2: AI 生成 ✅ 完成
- API 路由 `/api/generate-ai`（DALL-E 3 集成）
- 前端状态机：idle → loading → success/error
- 10 个预设风格 + 字数统计（500 字符）
- 图片保存（fetch → blob → download）
- 错误处理：400/401/429/503/504/500
- 30s 超时（AbortController）
- Prompt 增强：用户输入 + 美甲场景词后缀
- 隐私保护：API Key 仅服务端，不发送原图
- **待姚哥配置 `OPENAI_API_KEY`** 后即可使用

### Phase 3: AR 实时试戴 🚧 核心功能完成，待真机验证

**已完成:**
- 摄像头管线（原生 getUserMedia + rAF 循环 + 三级降级 + 手动按钮 + CDN 超时回退）
- 全局朝向检测（4 传感器融合：叉积/深度差/4 指投票/拇指位置 + 不对称阈值 + 宽松策略）
- 逐指 4 信号融合可见性检测（A:z 差-DIP / B:z 差-PIP / C:透视缩短比 / D:★手指伸展角）
- 手势兼容检测（✌️比耶/👍点赞/👊握拳/🤘摇滚/☝️食指指/🤙打电话 — 任意手势）
- 两层渲染防御（全局门控 + 逐指过滤）
- 指甲形状逐指差异化（FINGER_TIP_NARROW/SIDE_CURVE/ROOT_BULGE — 每指 3 参数）
- 指甲大小解剖校准（FINGER_LENGTH/WIDTH_RATIOS — 基于真实甲床比例）
- 方向向量 TIP-DIP 优先（更贴近指甲实际朝向）
- 指甲纹理贴合（柱面曲率变形 12 条 + 材质细节 + 三层高光 + 环境光照）
- 左右手识别 UI + 逐指可见性指示器（5 圆点 + 手指名称）
- 反转手按钮（前置摄像头镜像补偿，不反转画面）
- 贝塞尔路径指甲形状 + 三维贴图（object-cover 坐标修复）

**待验证:**
- 手机端真机测试
- 逐指可见性阈值调优（NAIL_PALM_Z_THRESHOLD=0.002）
- 纹理贴合度验证

**未完成:**
- AI 模块（5% 占位）
- 3D AR 试戴
- 部署上线

### 2026-06-25 修复工作

- ✅ 修复 `dev-log/2026-06-24.md` Git 合并冲突标记
- ✅ 修复 8 个 ESLint errors → 0 errors（commit `71fb430`）
  - `ar-tryon/page.tsx`: ref 更新移到 useEffect
  - `TextureCropper.tsx`: 用 imgLoaded state 替代 ref 渲染期访问
  - `NailArtPicker.tsx`: let→const + 移除 `window as any`
- ✅ 项目全面扫描审计（17 份 docs + 4 份 dev-log + 26 commits）

### 2026-06-28 清理 + Phase 2

- ✅ 清理未使用依赖（camera_utils / drawing_utils / ngrok，移除40包）
- ✅ 清理根目录残留文件到 .archive/
- ✅ 修复 12 个 ESLint warnings → 0（commit `88b48ee`）
- ✅ Phase 2 AI 生成模块（commit `7486ba0`）
  - API 路由 `/api/generate-ai`（DALL-E 3）
  - 前端页面重写（状态机 + loading + 错误处理 + 保存）
  - `.env.local.example` 追踪到 git
- ✅ 所有验收标准达成

## 关键参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| `NAIL_PALM_Z_THRESHOLD` | 0.002 | 信号 A：逐指判定手心侧阈值（TIP-DIP z 差） |
| `NAIL_PALM_Z_THRESHOLD_B` | 0.004 | 信号 B：逐指判定手心侧阈值（TIP-PIP z 差） |
| `FORESHORTEN_THRESHOLD` | 0.55 | 信号 C：透视缩短比阈值 |
| `EXTENSION_ANGLE_THRESHOLD` | 0.6 | 信号 D：手指伸展角阈值（弧度 ≈ 35°） |
| `VISIBILITY_EMA_ALPHA` | 0.3 | 逐指可见性状态帧间平滑 |
| `VISIBILITY_SMOOTH_THRESHOLD` | 0.5 | 可见性判定阈值 |
| `EMA_ALPHA` | 0.45 | 关键点平滑因子 |
| `EMA_ALPHA_PALM` | 0.3 | 朝向深度差平滑因子 |
| `TIP_OFFSET_RATIO` | 0.28 | 默认偏移（被 FINGER_OFFSET_RATIOS 覆盖） |
| `FINGER_OFFSET_RATIOS` | [0.22,0.28,0.28,0.26,0.24] | 逐指指甲中心偏移 |
| `FINGER_LENGTH_RATIOS` | [0.50,0.55,0.58,0.54,0.48] | 逐指甲长度比（解剖校准） |
| `FINGER_WIDTH_RATIOS` | [0.52,0.48,0.46,0.44,0.36] | 逐指甲宽度比（解剖校准） |
| `FINGER_TIP_NARROW` | [0.12,0.08,0.07,0.08,0.06] | 逐指尖端收窄参数 |
| `FINGER_SIDE_CURVE` | [0.50,0.55,0.55,0.52,0.45] | 逐指侧面曲线参数 |
| `FINGER_ROOT_BULGE` | [0.06,0.08,0.08,0.07,0.05] | 逐指根部凸起参数 |
| `CURVATURE_STRENGTH` | 0.22 | 纹理柱面曲率 |
| `DEPTH_DIFF_THRESHOLD_DORSUM` | 0.005 | 深度差判手背（严格） |
| `DEPTH_DIFF_THRESHOLD_PALM` | 0.001 | 深度差判手心（灵敏） |
| `CROSS_PRODUCT_Z_THRESHOLD_DORSUM` | 0.002 | 叉积判手背（严格） |
| `CROSS_PRODUCT_Z_THRESHOLD_PALM` | 0.0005 | 叉积判手心（灵敏） |

详见 [technical-architecture.md](docs/technical-architecture.md) §5.5

## Git 历史概览

| 日期 | Commit 数 | 关键内容 |
|------|:---------:|----------|
| 06-21 | 1 | 项目初始化 |
| 06-22 | 11 | Phase 1 MVP + AR 基础 + 摄像头管线重写 |
| 06-23 | 0 | 文档整理 |
| 06-24 | 13 | AR 核心功能（朝向+逐指+手势+渲染+UI） |
| 06-25 | 1 | 冲突修复 + ESLint 修复 |
| 06-28 | 4 | 清理 + Phase 2 AI 生成模块 |

## 待办清单

### 高优先级
- [ ] 真机测试（手机端摄像头启动、帧率、阈值均未验证）
- [ ] 逐指可见性阈值实测调优（所有参数为估算值，需真机校准）
- [ ] 纹理贴合度验证（坐标变换已修复，未实测）
- [ ] 帧率达标验证（目标 15fps+）
- [ ] 姚哥配置 OPENAI_API_KEY 后测试 AI 生成

### 中优先级
- [ ] Vercel 部署 + 域名绑定
- [ ] 3D AR 试戴（Three.js 已安装，需 3D 指甲模型 + 光照渲染）

### 低优先级
- [ ] 拆分 ArView.tsx（1153 行 → 多模块）

## 工作说明

### 开发流程
1. **每次开始工作前**：先查看 `dev-log/` 中的最新日志了解进度
2. **每次完成功能后**：更新当天的开发日志，记录完成事项
3. **遇到技术决策**：记录到 `docs/` 对应文档中
4. **重大问题**：记录到项目记忆中
5. **文档同步**：功能变更后同步更新对应 docs/ 文件

### 沟通原则
- 用户是代码小白，所有技术解释需通俗易懂
- 重大操作前需确认，避免不可逆操作
- 每次修改范围要小，确保可回退

### 隐私原则（核心）
- 所有照片处理在浏览器本地完成
- AI生成仅发送文字描述，不发送原图
- AR摄像头画面仅存内存，不录制不上传
