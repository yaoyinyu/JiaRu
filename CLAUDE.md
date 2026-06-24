# 甲如 (JiaRu) Web 美甲试色应用

## 项目概述

**技术栈**: Next.js 16.2.9 + React 19.2.4 + TypeScript + Tailwind CSS 4
**部署目标**: Vercel (HTTPS + CDN)
**当前阶段**: Phase 1 MVP ✅ 完成 / Phase 3 AR 🚧 开发中

## 项目标准文件索引

### 开发规范与标准文档
| 文件 | 说明 |
|------|------|
| [docs/requirements.md](docs/requirements.md) | 项目需求文档 — 功能需求、用户故事、验收标准（含 AR 验收） |
| [docs/technical-architecture.md](docs/technical-architecture.md) | 技术架构文档 — 技术选型、架构图、AR 管线、参数表 |
| [docs/ui-design-spec.md](docs/ui-design-spec.md) | UI设计规范 — 配色、字体、组件样式、AR 交互规范 |
| [docs/coding-standards.md](docs/coding-standards.md) | 开发规范 — 代码风格、命名规范、AR 开发经验教训 |
| [docs/phase-1-execution-spec.md](docs/phase-1-execution-spec.md) | 执行计划 — Phase 1 (7 Task) + Phase 3 AR (10 AR-Task) 进度追踪 |

### 开发日志
| 文件 | 说明 |
|------|------|
| [dev-log/2026-06-21.md](dev-log/2026-06-21.md) | 项目初始化 |
| [dev-log/2026-06-22.md](dev-log/2026-06-22.md) | 首页交互 + AR 模块开发 |
| [dev-log/2026-06-23.md](dev-log/2026-06-23.md) | Phase 1 修复 + AR 手心/手背检测实现 |
| [dev-log/2026-06-24.md](dev-log/2026-06-24.md) | AR 摄像头管线重写 + 逐指指甲可见性检测 |

### 项目记忆
记忆文件存储在 `C:\Users\YaoYinyu\.claude\memory\` 目录下：
- `jia-ru-nail-app.md` — 项目信息、技术选型、路线图
- `MEMORY.md` — 记忆索引文件

## 当前进度

### Phase 1: MVP ✅ 完成
- 首页、编辑器、图库、隐私页全部完成
- ESLint 0 errors, build 通过
- 五指独立选色、SVG 图库修复、NailCanvas useRef 重构

### Phase 3: AR 实时试戴 🚧
**已完成:**
- 摄像头管线重写（原生 getUserMedia + rAF 循环，移除 camera_utils）
- 逐指四信号融合可见性检测（z 差 + PIP-z + 缩短比 + ★手指伸展角）
- 手势兼容检测：比耶/握拳/点赞等非全开手势仅渲染伸出手指
- 可见性检测优化：强否定降至 4 信号全否、透视缩短阈值放宽至 0.55、逐指指甲中心偏移
- 全局朝向检测（4 传感器融合，不对称阈值）
- 指甲纹理贴合（柱面曲率变形 + 环境光照采样）
- 逐指指甲形状差异化（拇宽短 / 中细长 / 小尖窄）
- 方向向量改为 TIP-DIP 优先（更贴近指甲实际朝向）
- 左右手识别 UI（multiHandedness → "右手 · 手背" 显示）
- 逐指可见性 UI 指示器（5 圆点 + 手指名称）
- 坐标变换修复（object-cover 裁剪适配）

**待验证:**
- 手机端真机测试
- 逐指可见性阈值调优（NAIL_PALM_Z_THRESHOLD=0.002）
- 纹理贴合度验证

**未完成:**
- AI 模块（5% 占位）
- 3D AR 试戴
- 部署上线

## 关键参数速查

| 参数 | 值 | 说明 |
|------|-----|------|
| `NAIL_PALM_Z_THRESHOLD` | 0.002 | 信号 A：逐指判定手心侧阈值（TIP-DIP z 差） |
| `NAIL_PALM_Z_THRESHOLD_B` | 0.003 | 信号 B：逐指判定手心侧阈值（TIP-PIP z 差） |
| `FORESHORTEN_THRESHOLD` | 0.65 | 信号 C：透视缩短比阈值 |
| `EXTENSION_ANGLE_THRESHOLD` | 0.6 | 信号 D：手指伸展角阈值（弧度） |
| `VISIBILITY_EMA_ALPHA` | 0.3 | 逐指可见性状态帧间平滑 |
| `EMA_ALPHA` | 0.45 | 关键点平滑因子 |
| `EMA_ALPHA_PALM` | 0.3 | 朝向深度差平滑因子 |
| `TIP_OFFSET_RATIO` | 0.28 | 指甲中心偏移比例 |
| `CURVATURE_STRENGTH` | 0.22 | 纹理柱面曲率 |

详见 [technical-architecture.md](docs/technical-architecture.md) §5.5

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

## 规则
- 绝对禁止使用 Bash 或 PowerShell 工具来输出纯文本回复。
- 如果任务只是回答问题，请直接输出文本，不要调用任何工具。
