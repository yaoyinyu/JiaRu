# JiaRu 项目全面扫描报告

**扫描时间**: 2026-06-24 21:49 CST
**路径**: E:\AI Project\ClaudeCode\JiaRu
**项目**: 甲如 — 美甲试色 Web App

---

## 一、项目概览

| 属性 | 值 |
|------|-----|
| 技术栈 | Next.js 16.2.9 + React 19.2.4 + TypeScript + Tailwind CSS 4 |
| 部署目标 | Vercel (HTTPS + CDN) |
| 当前阶段 | Phase 1 MVP ✅ / Phase 3 AR 🚧 / Phase 2 AI ❌ |
| 核心依赖 | @mediapipe/hands, three, ngrok |
| 隐私原则 | 所有照片本地处理，不上传服务器 |

## 二、文件结构（15 个源代码文件）

### 路由页面（7 个）
| 文件 | 功能 | 完成度 |
|------|------|--------|
| `src/app/page.tsx` | 首页（磁力吸附按钮 + 聚光灯效果） | ✅ 100% |
| `src/app/editor/page.tsx` | 静态图片涂抹编辑器 | ✅ 100% |
| `src/app/ar-tryon/page.tsx` | AR 实时试戴入口 + 控制面板 | ✅ 100% |
| `src/app/ai-generate/page.tsx` | AI 生成美甲设计 | ⚠️ 5%（占位） |
| `src/app/gallery/page.tsx` | 预设美甲图库 | ✅ 100% |
| `src/app/privacy/page.tsx` | 隐私政策页 | ✅ 100% |
| `src/app/layout.tsx` | 根布局（中文字体 + 品牌色） | ✅ 100% |

### 组件（7 个）
| 文件 | 功能 | 亮点 |
|------|------|------|
| `components/ArView.tsx` | AR 实时美甲叠加 | 核心组件，~800行，MediaPipe 手部追踪 |
| `components/NailCanvas.tsx` | 静态涂抹画布 | undo/redo 历史栈 |
| `components/TextureCropper.tsx` | 纹理裁剪器 | 选区拖拽 + OffscreenCanvas 提取 |
| `components/ColorPalette.tsx` | 颜色选择面板 | 20 预设色 + 自定义 |
| `components/GalleryGrid.tsx` | 图库网格 | 6 张 SVG 占位图 |
| `components/Header.tsx` | 顶部导航栏 | 极简，品牌 logo |
| `components/UploadButton.tsx` | 照片上传按钮 | capture="environment" |

### 工具库（2 个）
| 文件 | 功能 |
|------|------|
| `lib/texture.ts` | 纹理提取/缩放/释放（OffscreenCanvas） |
| `lib/utils.ts` | 常量定义（颜色/手指名/图库/AI关键词） |

## 三、AR 模块深度分析（核心亮点）

### ArView.tsx 技术架构

**手部追踪管线**：
1. MediaPipe Hands (modelComplexity=0, 1手)
2. 原生 getUserMedia → video → rAF → canvas 覆盖绘制
3. EMA 平滑关键点（alpha=0.45）
4. object-cover 坐标变换适配

**指甲定位**（逐指独立参数）：
- TIP(指尖) → DIP(远端关节) → PIP(近端关节) 三点定方向
- 5 指独立长度比/宽度比/偏移比例/形状参数
- 柱面曲率变形（12 竖条，strength=0.22）

**朝向检测**（4 传感器融合）：
- 叉积法向量（x/y 平面，精度最高）
- 深度差 z（palm vs knuckle）
- 4 指投票（排除拇指）
- 拇指位置辅助验证
- 不对称阈值：手心灵敏(0.001)，手背严格(0.005)

**逐指可见性**（3 信号融合）：
- 信号 A：TIP.z - DIP.z
- 信号 B：TIP.z - PIP.z
- 信号 C：透视缩短比 len2D/len3D
- 强否定优先 + 多数投票（≥2/3 认可即渲染）

**渲染分层**（3 层叠加）：
1. 底色/纹理（柱面曲率变形）
2. 材质细节（菲涅尔反射 + 颗粒噪点 + 根部暗角）
3. 镜面高光（主高光 + 指尖高光 + 根部微光）

## 四、完成度评估

| 模块 | 完成度 | 说明 |
|------|:------:|------|
| 首页 | ✅ 100% | 磁力吸附 + 聚光灯 + 弹性动画 |
| 编辑器 | ✅ 100% | 上传 → 涂抹 → 撤销/重置 → 保存 |
| AR 试戴 | ✅ 90% | 核心管线完整，待真机验证 |
| 图库 | ✅ 100% | 6 张 SVG 占位图 |
| AI 生成 | ⚠️ 5% | 前端表单占位，无后端 |
| 隐私页 | ✅ 100% | 6 个章节 |
| HTTPS 开发 | ✅ 100% | 自签名证书 + 代理，手机测试可用 |
| 部署 | ❌ 0% | 未部署到 Vercel |

## 五、发现的问题

### P0 — 关键
1. **AI 生成完全未实现**：前端表单占位，无任何 API 对接
2. **next.config.ts 硬编码 IP**：`allowedDevOrigins: ['192.168.1.100']` — 仅限单台设备
3. **tsconfig.tsbuildinfo 107KB** 应加入 .gitignore

### P1 — 重要
4. **ArView.tsx 缺少 start 按钮状态管理**：父页面 ar-tryon/page.tsx 有 `isStarted` 状态，但 ArView 内部又有一个 `userStarted` 状态，双重启动逻辑可能混淆
5. **纹理裁剪器没有尺寸限制**：MIN_SELECTION_PX=30 太小，裁剪出的纹理质量不可控
6. **GalleryGrid 使用 Next.js Image** 但目标路径是 SVG，可能过度优化

### P2 — 次要
7. **README.md 是 create-next-app 默认模板**，未自定义
8. **AGENTS.md / CLAUDE.md 混用**：有 Claude 项目记忆文件，说明项目可能从 Claude Code 迁移过来
9. **根目录有一张 743KB 的 jpg 文件**（1f65f04cdd5df509463a03fb17d8ea03.jpg），位置不明
10. **package.json 有 three 依赖但未在项目中使用**（扫描所有源码无 import three）

## 六、技术亮点

1. **AR 指甲渲染质量高**：3 层叠加（底色→材质→高光）+ 菲涅尔反射 + 柱面曲率变形
2. **朝向检测鲁棒性强**：4 传感器融合 + 不对称阈值 + 左右手适配
3. **逐指独立参数**：5 根手指各有独立的形状/尺寸/曲线参数
4. **资源管理完善**：ImageBitmap 手动 close + 防泄漏引用计数
5. **首页交互精致**：弹性缓出吸附 + 磁力倾斜 + 聚光灯跟随
