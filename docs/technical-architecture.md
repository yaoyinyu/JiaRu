# 技术架构文档 — 甲如

## 1. 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | Next.js | 16.2.9 | 前后端合一，App Router，Turbopack |
| 语言 | TypeScript | 5.x | 类型安全 |
| 样式 | Tailwind CSS | 4.x | 原子化CSS |
| UI交互 | Canvas API | — | 涂色编辑器 + AR 指甲贴图 |
| 手部追踪 | MediaPipe Hands (Tasks Vision) | — | AR模式，21 关键点 3D 检测 |
| 3D渲染 | Three.js | — | AR模式（预留） |
| AI生成 | OpenAI DALL-E 3 API | — | AI模式（Phase 2） |
| 部署 | Vercel | — | 免费托管+HTTPS |

## 2. 架构图

```
┌─────────────────────────────────────┐
│         用户浏览器 (手机/电脑)        │
├─────────────────────────────────────┤
│          Next.js 前端                │
│  ┌──────┐ ┌───────┐ ┌──────────┐  │
│  │首页UI│ │涂色画布│ │AI/AR页面 │  │
│  └──────┘ └───────┘ └──────────┘  │
│        所有照片本地处理              │
├─────────────────────────────────────┤
│     Next.js API Routes (后端)       │
│  ┌──────────────────────────────┐   │
│  │  /api/generate-ai            │   │
│  │  → OpenAI DALL-E 3           │   │
│  └──────────────────────────────┘   │
├─────────────────────────────────────┤
│            Vercel 部署              │
│   自动 HTTPS · 全球 CDN · 零运维   │
└─────────────────────────────────────┘
```

## 3. 数据流

### MVP 涂色流程（全前端）
```
用户上传照片 → FileReader → Canvas加载
→ 用户选色/涂抹 → Canvas绘制叠加层
→ 保存 → Canvas.toDataURL → 下载
（全程在浏览器内存中，无网络请求）
```

### AI 生成流程（需后端）
```
用户输入描述 → 前端POST /api/generate-ai
→ API Route调用OpenAI → 返回图片URL
→ 前端展示 → 可保存/分享
（仅传文本，不传照片）
```

### AR 实时试戴流程
```
用户点击"开启摄像头" → getUserMedia 请求权限（手动触发，移动端必须）
→ 启动前置摄像头 video 流（facingMode: user）
→ 加载 MediaPipe HandLandmarker 模型（CDN + 超时回退）
→ requestAnimationFrame 循环检测手部 21 个关键点
→ 逐指判定指甲可见性（TIP.z vs DIP.z）
→ 仅对可见手指的指尖位置计算指甲区域
→ Canvas 覆盖层绘制半透明指甲形状/纹理
→ 跟随手指实时更新
（全程本地处理，不录制不上传）
```

## 4. 路由设计

| 路由 | 页面 | 状态 |
|------|------|------|
| `/` | 首页/功能引导 | ✅ Phase 1 |
| `/editor` | 涂色编辑器 | ✅ Phase 1 |
| `/gallery` | 预设图库 | ✅ Phase 1 |
| `/ai-generate` | AI生成（占位） | 📌 Phase 2 |
| `/ar-tryon` | AR实时试戴 | 🚧 Phase 3 开发中 |
| `/privacy` | 隐私政策 | ✅ Phase 1 |
| `/api/generate-ai` | AI生成API | 📌 Phase 2 |

---

## 5. AR 模块开发规划

### 5.1 当前状态

**状态：** Phase 3 AR 核心功能已实现，逐指指甲可见性检测已上线，待真机验证。

**已完成：**
1. ✅ 摄像头管线重写（原生 getUserMedia，移除 camera_utils 依赖）
2. ✅ 手动启动按钮（移动端 getUserMedia 必须用户手势触发）
3. ✅ rAF 推理循环（替代 useEffect 依赖数组）
4. ✅ MediaPipe Hands 手部检测（21 关键点）
5. ✅ 指甲绘制（纯色 + 纹理柱面曲率变形）
6. ✅ 逐指指甲可见性检测（isNailVisible，TIP.z vs DIP.z）
7. ✅ 全局朝向检测（4 传感器融合，仅用于状态显示）
8. ✅ 坐标变换修复（object-cover 裁剪适配）
9. ✅ CDN 超时回退机制

**待验证：**
1. 🔶 手机端真机测试（管线已重写，未测试）
2. 🔶 逐指可见性阈值调优（NAIL_PALM_Z_THRESHOLD=0.002 未实测）
3. 🔶 纹理贴合度验证

**未完成：**
1. ❌ AI 模块（5% 占位）
2. ❌ 3D AR 试戴
3. ❌ 部署上线

### 5.2 摄像头管线架构

```
用户点击「开启摄像头」
  ↓
getUserMedia({ video: { facingMode: "user" } })
  ↓
video.srcObject = stream → video.play()
  ↓
requestAnimationFrame 循环：
  ├─ video.readyState >= 2 ?
  ├─ HandLandmarker.detectForVideo(video, timestamp)
  ├─ onResults 回调：
  │   ├─ 计算 5 指可见性 (isNailVisible)
  │   ├─ 全局朝向检测 (shouldRenderNails，状态显示用)
  │   └─ paintNails（仅对可见手指贴图）
  └─ 下一帧 rAF
```

**关键设计决策：**
- 原生 getUserMedia 替代 @mediapipe/camera_utils（移动端兼容性更好）
- rAF 循环替代 useEffect 依赖触发（避免 HMR 报错）
- 手动按钮触发（移动端浏览器拦截自动 getUserMedia）

### 5.3 逐指指甲可见性检测

**原理：**
MediaPipe z 坐标（朝镜头为负，远离为正）。
- 手心朝镜头：手指肉遮挡指甲 → TIP 比 DIP 更远离镜头 → `TIP.z - DIP.z > 0`
- 手背朝镜头：指甲可见 → TIP 比 DIP 更接近镜头 → `TIP.z - DIP.z < 0` 或接近 0

**判定逻辑：**
```typescript
function isNailVisible(lm, fingerIdx): boolean {
  const tipDipDiff = lm[TIPS[fingerIdx]].z - lm[DIPS[fingerIdx]].z;
  if (tipDipDiff > NAIL_PALM_Z_THRESHOLD) return false;  // 手心侧
  return true;  // 手背/侧手
}
```

**优势：**
- 逐指独立，支持混合状态（3 指贴图 + 2 指不贴）
- 无需全局手心/手背判定
- 手稍微偏转时自然过渡

### 5.4 全局朝向检测（4 传感器融合，状态显示用）

| 传感器 | 判定依据 | 手背阈值（严格） | 手心阈值（灵敏） |
|--------|----------|:---:|:---:|
| 叉积法向量 | 手掌平面法向量 z 分量 | 0.002 | 0.0005 |
| 深度差 | palmZ - knuckleZ | 0.005 | 0.001 |
| 4 指投票 | TIP.z - PIP.z | 0.003 | 0.001 |
| 拇指位置 | TIP.x - palmCenterX | 0.02 | 0.02 |

**融合策略：**
- 手背判定严格（需要强证据）
- 手心判定灵敏（低阈值即触发）
- `palmScore >= 2` 或 `isPalmByCross + palmScore >= 1` → 手心
- 其他 → 渲染

### 5.5 关键参数表

| 参数 | 值 | 说明 |
|------|-----|------|
| `NAIL_PALM_Z_THRESHOLD` | 0.002 | TIP.z - DIP.z > 此值 = 手心侧 = 不渲染 |
| `DEPTH_DIFF_THRESHOLD_DORSUM` | 0.005 | 深度差判手背（严格） |
| `DEPTH_DIFF_THRESHOLD_PALM` | 0.001 | 深度差判手心（灵敏） |
| `CROSS_PRODUCT_Z_THRESHOLD_DORSUM` | 0.002 | 叉积判手背（严格） |
| `CROSS_PRODUCT_Z_THRESHOLD_PALM` | 0.0005 | 叉积判手心（灵敏） |
| `FINGER_Z_VOTE_THRESHOLD_DORSUM` | 0.003 | 手指投票判手背（严格） |
| `FINGER_Z_VOTE_THRESHOLD_PALM` | 0.001 | 手指投票判手心（灵敏） |
| `THUMB_X_THRESHOLD` | 0.02 | 拇指 x 偏移判定 |
| `EMA_ALPHA_PALM` | 0.3 | 深度差 EMA 平滑因子 |
| `EMA_ALPHA` | 0.45 | 指尖位置 EMA 平滑因子 |
| `OUT_OF_FRAME_THRESHOLD` | 0.1 | x/y 超出 [0.1, 0.9] = 出画面 |
| `FINGER_LENGTH_RATIOS` | 各指不同 | 指甲长度/指骨长度比 |
| `FINGER_WIDTH_RATIOS` | 各指不同 | 指甲宽度/指骨长度比 |
| `TIP_OFFSET_RATIO` | 0.15 | 指甲中心偏移比例 |
| `CURVATURE_STRENGTH` | 0.22 | 纹理柱面曲率强度 |
| `CURVATURE_STRIPS` | 12 | 竖条分片数 |

### 5.6 技术要点

#### MediaPipe HandLandmarker 关键点索引
```
0: 手腕
4: 拇指指尖      3: 拇指IP关节      2: 拇指PIP关节
8: 食指指尖      7: 食指DIP关节      6: 食指PIP关节
12: 中指指尖     11: 中指DIP关节     10: 中指PIP关节
16: 无名指指尖   15: 无名指DIP关节   14: 无名指PIP关节
20: 小指指尖     19: 小指DIP关节     18: 小指PIP关节
```

#### 指甲区域计算
```
方向向量 = DIP - PIP（或 TIP - DIP）
指甲中心 = TIP 沿手指方向偏移 15%
指甲长度 = 指骨长度 × FINGER_LENGTH_RATIOS[f]
指甲宽度 = 指骨长度 × FINGER_WIDTH_RATIOS[f]
旋转角 = atan2(fy, fx)
z 缩放 = clamp(1 - TIP.z × 0.6, 0.7, 1.5)
```

#### Canvas 绘制
```
1. 清除上一帧
2. 遍历 5 指：
   a. isNailVisible(lm, f) → false 则 continue
   b. EMA 平滑 TIP/DIP/PIP 坐标
   c. z 轴深度缩放
   d. 计算方向向量 + 指甲参数
   e. 采样环境光照
   f. 绘制底色/纹理（柱面曲率变形）
   g. 绘制高光层
3. 全局朝向检测 → 更新 orientation state（UI 显示）
```

### 5.7 验证清单

- [x] 错误日志正常工作，能看到具体失败原因
- [x] 摄像头成功启动（前置）— PC 端验证
- [x] MediaPipe 模型加载成功
- [x] 手部检测到关键点，指甲绘制在正确位置
- [x] 指甲贴合自然，旋转跟随手指方向
- [ ] 手机端摄像头成功启动（待真机测试）
- [ ] 手心朝镜头时不贴纹理（待真机验证）
- [ ] 逐指独立判定混合状态正确（待真机验证）
- [ ] 纹理与指甲位置对齐（待真机验证）
- [ ] 帧率达到 15fps+

