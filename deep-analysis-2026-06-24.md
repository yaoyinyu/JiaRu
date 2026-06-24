# 甲如 (JiaRu) 深度代码分析报告

**分析时间**: 2026-06-24 22:16 CST
**分析范围**: 全部 15 个源代码文件 + 配置文件 + 资产

---

## 一、架构总览

```
JiaRu/
├── src/app/                    # Next.js App Router (7 pages)
│   ├── layout.tsx              # 根布局
│   ├── page.tsx                # 首页（磁力吸附交互）
│   ├── globals.css             # Tailwind + 品牌色
│   ├── editor/page.tsx         # 静态涂抹编辑器
│   ├── ar-tryon/page.tsx       # AR 入口 + 控制面板
│   ├── ai-generate/page.tsx    # AI 生成（占位）
│   ├── gallery/page.tsx        # 图库
│   └── privacy/page.tsx        # 隐私政策
├── src/components/             # 7 个 React 组件
│   ├── ArView.tsx              # ★ 核心：AR 实时美甲叠加 (~900行)
│   ├── NailCanvas.tsx          # 静态涂抹画布
│   ├── TextureCropper.tsx      # 纹理裁剪器
│   ├── ColorPalette.tsx        # 颜色选择面板
│   ├── GalleryGrid.tsx         # 图库网格
│   ├── Header.tsx              # 顶部导航
│   └── UploadButton.tsx        # 照片上传按钮
├── src/lib/                    # 2 个工具库
│   ├── texture.ts              # 纹理提取/缩放/释放
│   └── utils.ts                # 常量定义
└── public/nail-gallery/        # 6 张 SVG 占位图
```

**数据流**: 所有页面共享 `nailColors` 状态 → AR 和编辑器均可操作 5 指独立颜色/纹理。

---

## 二、首页 page.tsx — 物理引擎级交互

### 核心技术栈

| 技术 | 实现 |
|------|------|
| 光标追踪 | `pointermove` → `st.current.cursor` |
| 光晕跟随 | RAF 线性插值 `s.light.x += (cx - s.light.x) * 0.065` |
| 磁力吸附 | 200px 感应半径 + 三次多项式缓动 `ease = force²(3-2force)` |
| 弹性捕获 | `elasticOut(t) = 2^(-9t)·sin((t-0.075)·2π/0.35) + 1` |
| 点击反馈 | CSS transition `cubic-bezier(0.34,1.56,0.64,1)` |

### 关键设计决策

1. **RAF 驱动而非 React state**：按钮位置/倾斜/发光全部通过 `useRef` 可变状态 + RAF 直接操作 DOM style，避免 React 重渲染开销。只有 `showHint` 用了 state（因为不随 RAF 变化）。

2. **双层捕获逻辑**：
   - 捕获进入：光标距按钮中心 < 100px
   - 捕获退出：光标距按钮中心 > 160px（滞后 60px 防抖）
   - 捕获动画：`elasticOut(captureP)` 从捕获起点弹性插值到按钮中心

3. **点击锁定机制**：`clickLock` 防止点击动画期间 RAF 覆盖按钮 transform。

4. **聚光灯效果**：400px 径向渐变跟随光标，捕获时缩小并变亮。

### 潜在问题

- **性能**: RAF 每帧计算 2 个按钮的 `getBoundingClientRect()` + 数学运算，现代设备无压力，但低端 Android 可能掉帧。
- **移动端**: 只有 `pointermove` 事件，无 `touchmove` 单独处理。不过 Pointer Events API 已统一触屏和鼠标，理论上 OK。
- **`showHint` 依赖**: `useEffect` 的 deps 只有 `[showHint]`，闭包捕获旧值。但因为 `setShowHint(false)` 后立即读 `st.current.cursor` 在另一个 effect 里，所以无实际问题。

---

## 三、ArView.tsx — 核心引擎深度分析

这是整个项目的技术核心，约 900 行，包含 MediaPipe 手部追踪 + 实时渲染管线。

### 3.1 初始化管线（7 步）

```
用户点击 → 加载 CDN → 请求摄像头 → 绑定 video → 创建 Hands → 注册 onResults → 启动 RAF 推理循环
```

**亮点**：
- 3 层摄像头降级（`facingMode: "user"` → 无 facingMode → `video: true`）
- 详细的错误分类（Permission / NotFound / NotReadable）
- 视频就绪三重检查（`onloadedmetadata` → `video.play()` → `readyState >= 3`）
- 脚本加载 15s 超时

### 3.2 坐标变换管线

这是最复杂的部分，涉及 4 个坐标系之间的转换：

| 坐标系 | 来源 | 范围 | 说明 |
|--------|------|------|------|
| 原始视频帧 | MediaPipe | [0,1] 归一化 | landmark 原始输出 |
| 视频像素 | video.videoWidth × Height | [0, vw] × [0, vh] | 未裁剪的原始分辨率 |
| object-cover 裁剪 | CSS 显示区域 | [0, cw] × [0, ch] | canvas 内部尺寸 |
| canvas 像素 | getBoundingClientRect | [0, cw] × [0, ch] | 渲染目标 |

**变换公式**：
```javascript
// 1. 判断裁剪模式
if (videoRatio > containerRatio) {
  // 视频更宽 → 左右裁剪
  scale = cvs.height / vh;
  offsetX = -(vw * scale - cvs.width) / 2;
} else {
  // 视频更高 → 上下裁剪
  scale = cvs.width / vw;
  offsetY = -(vh * scale - cvs.height) / 2;
}

// 2. 归一化 → canvas 像素
tx2px(nx) = nx * vw * scale + offsetX;
ty2py(ny) = ny * vh * scale + offsetY;

// 3. 重新归一化到 canvas 坐标系（供后续算法使用）
lm[i].x = tx2px(raw.x) / cvs.width;
lm[i].y = ty2py(raw.y) / cvs.height;
```

**深度分析**：这个变换非常精巧，确保了无论 video 原始分辨率如何（480×640 / 720×960 / 1080×1920），landmark 都能正确映射到 canvas 显示区域。

### 3.3 手部追踪参数

| 参数 | 值 | 说明 |
|------|-----|------|
| maxNumHands | 1 | 只跟踪一只手 |
| modelComplexity | 0 | 轻量模型（~10ms/帧） |
| minDetectionConfidence | 0.5 | 检测阈值 |
| minTrackingConfidence | 0.5 | 追踪阈值 |
| 推理方式 | rAF 驱动 | 每帧发送，无丢帧逻辑 |

**潜在问题**：
- rAF 驱动意味着每秒发送 60 次 `handsInst.send()`，但 MediaPipe 内部有帧率控制（默认 ~15fps），所以实际不会 60fps 推理。但 `sending` 标志位只防止并发发送，不防止堆积。
- 没有 `requestIdleCallback` 或帧率自适应，低端设备可能卡顿。

### 3.4 朝向检测 — 4 传感器融合

这是 ArView 最精妙的算法之一。

#### 传感器 1：叉积法向量（权重 2）

```javascript
// 手掌向量：掌心(0) → 食指根部(5)
const v5 = [lm[5].x - lm[0].x, lm[5].y - lm[0].y];
// 小鱼际向量：掌心(0) → 小指根部(17)
const v17 = [lm[17].x - lm[0].x, lm[17].y - lm[0].y];
// 叉积 z = v5x * v17y - v5y * v17x
const crossZ = v5x * v17y - v5y * v17x;
```

**原理**：右手坐标系下，手掌向量 × 小鱼际向量。手背朝镜头 → 叉积为正；手心朝镜头 → 叉积为负。基于 x/y 平面，不受 z 精度影响，**精度最高**。

**不对称阈值**：
- 手背：`crossZ < -0.002`（Right）或 `> 0.002`（Left）— 严格
- 手心：`crossZ > 0.0005`（Right）或 `< -0.0005`（Left）— 灵敏

#### 传感器 2：深度差（权重 1）

```javascript
palmZ = mean([lm[0].z, lm[5].z, lm[9].z, lm[17].z]);  // 掌根区
knuckleZ = mean([lm[2].z, lm[6].z, lm[10].z, lm[14].z, lm[18].z]);  // 指关节
smoothDepthDiff = ema(palmZ - knuckleZ, 0.3);
```

**原理**：手心朝镜头 → 掌根比指关节更近 → palmZ > knuckleZ → depthDiff > 0。

#### 传感器 3：4 指投票（权重 1）

```javascript
for (f of [1,2,3,4]) {
  dz = lm[TIPS[f]].z - lm[PIPS[f]].z;
  if (dz < -0.003) dorsumVotes++;   // 指尖比指关节更远 → 手背
  if (dz > 0.001) palmVotes++;       // 指尖比指关节更近 → 手心
}
```

排除拇指（结构特殊，z 值不稳定）。

#### 传感器 4：拇指位置辅助（权重 1）

```javascript
palmCenterX = mean([lm[0].x, lm[5].x, lm[9].x, lm[17].x]);
thumbOffsetX = lm[4].x - palmCenterX;
// 右手：拇指在左侧 → thumbOffsetX < -0.02 → 手心
// 右手：拇指在右侧 → thumbOffsetX > 0.02 → 手背
```

**决策融合**：
```javascript
if (palmScore >= 2) → 手心（阻止渲染）
if (isPalmByCross && palmScore >= 1) → 手心（叉积单独判定）
if (dorsumScore > 0) → 手背（渲染）
else → 非手心态（仍渲染，降置信度）
```

**设计哲学**：**手心严格阻止，其他都渲染**。手心是确定性遮挡（指甲朝内看不见），手背/侧手/模糊态宁可误渲染也不漏渲染。

### 3.5 逐指可见性 — 3 信号融合

每个手指独立判定是否可见（指甲是否朝向镜头）。

#### 信号 A：TIP-DIP 深度差

```javascript
sigA = (tip.z - dip.z) <= 0.002;
```

手心侧：TIP 比 DIP 更远离镜头 → 差值 > 0 → 不可见。
手背侧：TIP 比 DIP 更接近镜头 → 差值 < 0 → 可见。

#### 信号 B：TIP-PIP 深度差（印证 A）

```javascript
sigB = (tip.z - pip.z) <= 0.004;
```

PIP 比 DIP 更靠近指根，受远端弯曲影响更小，提供独立印证。

#### 信号 C：透视缩短比（精度最高）

```javascript
len2D = sqrt(dx² + dy²);       // 2D 投影长度
len3D = sqrt(dx² + dy² + dz²); // 3D 实际长度
ratio = len2D / len3D;         // 0~1
sigC = ratio > 0.55;           // 接近 1 = 手指平行镜头 = 手背
```

**原理**：手心朝镜头时，手指指向镜头 → 2D 投影显著缩短 → ratio 小。手背朝镜头时，手指平行镜头 → 2D ≈ 3D → ratio ≈ 1。

#### 投票策略

```javascript
if (!sigA && !sigB && !sigC) return false;  // 三信号全否定 → 隐藏
return votes >= 2;                           // ≥2 认可 → 可见
```

**强否定优先**：三信号全部否定才隐藏（减少混合态漏判），否则多数投票。

#### 帧间平滑

```javascript
visibleSmooth = ema(visibleSmooth, rawVis ? 1 : 0, 0.3);
if (visibleSmooth < 0.5) continue;  // 阈值隐藏
```

### 3.6 指甲定位与尺寸

#### 方向向量

```javascript
// 优先 TIP-DIP（最贴近指甲实际朝向）
direction = TIP - DIP;
// 降级：DIP-PIP
// 最终降级：垂直向下 (0, -1)
```

#### 指甲中心计算

```javascript
// 从指尖向手根方向偏移
offsetRatio = [0.22, 0.28, 0.28, 0.26, 0.24];  // 拇→小
nailCenter = tip - direction.normalize() * (length * offsetRatio);
```

拇指最短（0.22），小指最长（0.24），符合真实甲床占比。

#### 尺寸计算

```javascript
fingerLength = rawLen * zScale * FINGER_LENGTH_RATIOS[f];
fingerWidth  = rawLen * zScale * FINGER_WIDTH_RATIOS[f];

// 逐指长度比：[0.50, 0.55, 0.58, 0.54, 0.48]  // 拇指最短，中指最长
// 逐指宽度比：[0.52, 0.48, 0.46, 0.44, 0.36]  // 拇指最宽，小指最窄
```

#### Z 轴深度缩放

```javascript
zScale = clamp(1 - tip.z * 0.6, 0.7, 1.5);
```

指甲离镜头越近（z 越小）→ 越大。

### 3.7 渲染管线 — 3 层叠加

#### 第 1 层：底色/纹理

**纯色模式**：
```javascript
drawNailShape(ctx, nl, nw, fingerIdx);  // 贝塞尔路径
ctx.fillStyle = color;
ctx.globalAlpha = 0.85;
ctx.fill();
```

**纹理模式**：
```javascript
drawCurvedTexture(ctx, tex, nl, nw);
// 12 竖条柱面曲率变形：中心宽、边缘窄（抛物线缩放）
```

#### 第 2 层：材质细节

1. **菲涅尔反射**：边缘亮、中心暗的线性渐变，模拟曲面边缘高反射
2. **颗粒纹理**：OffscreenCanvas 生成随机噪点（128±15），alpha=18
3. **根部暗角**：从上到下的渐变，底部暗 25%

#### 第 3 层：镜面高光

1. **主高光**：纵向椭圆，位置偏移 (-hw*0.25, -hl*0.05)，alpha = 0.18~0.4
2. **指尖高光**：自由缘细亮线
3. **根部微光**：甲上皮附近散射

**环境光照采样**：在指甲中心位置取 8×8 区域平均亮度，用于调节菲涅尔和高光的强度。

### 3.8 指甲形状 — 逐指贝塞尔曲线

```
          指尖收窄 (tipNarrow)
         ╱                    ╲
    ────╱                        ╲────
       ╲                          ╱
        ╲                        ╱
         ───────────────────────
              根部凸起 (rootBulge)
```

每根手指独立参数：
- **指尖收窄**：拇指最大(0.12，扁平)，小指最小(0.06，尖细)
- **侧面曲线**：控制贝塞尔控制点距离，越小侧线越直
- **根部凸起**：控制指甲根部曲线下凸程度

### 3.9 资源管理

```javascript
// 启动时
let dead = false;  // 卸载标志

// 清理
return () => {
  dead = true;
  cancelAnimationFrame(rafLoop);
  handsInst?.close();
  mediaStream?.getTracks().forEach(t => t.stop());
};
```

**问题**：`dead` 标志防止卸载后继续执行，但没有清理已排队的 `handsInst.send()` 调用。如果 RAF 循环在清理后还有一帧未发送，可能造成短暂错误。

### 3.10 双重启动状态

**问题**：父页面 `ar-tryon/page.tsx` 有 `isStarted` 状态，ArView 内部又有 `userStarted` 状态。

```javascript
// ar-tryon/page.tsx
const [isStarted, setIsStarted] = useState(false);
// ...
{isStarted && <ArView ... />}

// ArView.tsx
const [userStarted, setUserStarted] = useState(false);
// 内部 startBtnRef 控制摄像头启动
```

当 `isStarted` 变为 true 时，ArView 挂载 → `userStarted` 初始为 false → 显示"开启摄像头"按钮 → 用户点击 → `userStarted` 变为 true → 启动摄像头管线。

**分析**：这种双重状态实际上有合理的设计意图：
- `isStarted` = 用户同意进入 AR 模式（页面级别）
- `userStarted` = 用户点击启动摄像头（组件级别，需要手势触发权限）

但在 UI 上可能造成混淆：用户点击页面的"开启摄像头"后，ArView 内部还有一个"开启摄像头"按钮。

---

## 四、编辑器 NailCanvas.tsx — 静态涂抹

### 核心机制

1. **图片加载**：`new Image()` → 等比缩放至 max 400px → `drawImage`
2. **绘制**：`arc()` 画圆点 + `drawLine()` 插值画线（步长 5px）
3. **撤销**：`ImageData` 历史栈（最多 20 帧）
4. **保存**：`canvas.toDataURL("image/png")` → `<a download>`

### 潜在问题

- **无橡皮擦**：只能覆盖，不能擦除特定区域
- **history 用 state 存储**：每次 `setHistory` 触发组件重渲染。20 帧 × 400×600×4 bytes ≈ 19.2MB state。用 `useRef` + `useState` 组合可能更高效。
- **触摸支持**：有 `onTouchStart/Move/End`，但 `handleStart` 中 `e.preventDefault()` 可能阻止页面滚动（在移动设备上体验不佳）。

---

## 五、TextureCropper.tsx — 纹理裁剪器

### 核心机制

1. **图片适配**：`fitScale()` 限制最大 1024px
2. **选区拖拽**：Pointer Events API（统一触屏/鼠标）
3. **遮罩绘制**：选区外 4 个矩形半透明遮罩
4. **纹理提取**：`OffscreenCanvas` 缩放 + `createImageBitmap()`

### 亮点

- `clampRect()` 防止选区越界
- `normalizeRect()` 支持任意方向拖拽
- 键盘快捷键（Esc 取消，Enter 确认）
- 资源清理：`cancelled` 标志防止卸载后 `URL.revokeObjectURL`

---

## 六、颜色管理与状态架构

### 颜色数据流

```
ar-tryon/page.tsx (state: nailColors[], nailTextures[])
    │
    ├── nailColors[5] → ArView (prop) → paintNails() → ctx.fillStyle / drawCurvedTexture()
    │
    └── nailTextures[5] → ArView (prop) → paintNails() → drawCurvedTexture()
                              │
                              └── TextureCropper → extractTexture() → OffscreenCanvas → ImageBitmap
```

### ImageBitmap 生命周期

```
upload → TextureCropper → extractTexture() → createImageBitmap()
    │
    ├─→ 设置到 nailTextures state
    ├─→ ArView 消费（每帧 drawImage）
    └─→ 卸载时 disposeAllTextures() → bitmap.close()
```

**引用计数**：`handleCropConfirm` 和 `applyTextureToAll` 都有引用计数逻辑（`!updated.some((t) => t === old)`），确保同一 bitmap 不被重复 close。

---

## 七、配置与安全分析

### next.config.ts

```typescript
const nextConfig = {
  allowedDevOrigins: ['192.168.1.100'],  // ⚠️ 硬编码单设备 IP
};
```

**问题**：`allowedDevOrigins` 限制 Next.js dev server 的 CORS 来源。硬编码 `192.168.1.100` 意味着只能在特定设备的浏览器访问 dev server。换设备/换 WiFi 就需要改配置。

### .gitignore

```
*.pem                    # 证书文件已忽略 ✅
1f65f04cdd5df509463a03fb17d8ea03.jpg  # 不明图片已忽略 ✅
*.tsbuildinfo            # TS 构建缓存已忽略 ✅
backup_ar_working/       # 备份目录已忽略 ✅
```

**良好实践**：敏感文件和临时文件都已正确忽略。

### package.json

| 依赖 | 用途 | 使用情况 |
|------|------|---------|
| `@mediapipe/hands` | 手部追踪 | ✅ 实际使用 |
| `@mediapipe/camera_utils` | 摄像头工具 | ❌ 已弃用（代码注释明确） |
| `@mediapipe/drawing_utils` | 绘图工具 | ❌ 未使用 |
| `three` ^0.184.0 | 3D 渲染 | ❌ 未使用（源码无 import） |
| `ngrok` ^5.0.0-beta.2 | 内网穿透 | ⚠️ 可能未使用 |

**建议**：清理未使用的依赖减小 bundle size。

---

## 八、UI/UX 分析

### 设计一致性

- 品牌色 `#E8A0BF` 贯穿全站（首页按钮、编辑器、AR 控件、Header）
- 圆角 `rounded-2xl` / `rounded-3xl` 统一
- 粉色渐变 `from-[#E8A0BF] to-[#D4749D]` 作为主 CTA 样式
- 中文字体链 `"PingFang SC", "Microsoft YaHei", "Noto Sans SC"` 跨平台覆盖

### 响应式

- 最大宽度 `max-w-md` / `max-w-[480px]` 限制为手机尺寸
- AR 视图 `aspect-[3/4]` 竖屏比例
- `max-w-[400px]` 编辑器 canvas

**结论**：这是一个**移动端优先**的应用，桌面端体验可能不佳（内容居中窄栏）。

### 隐私设计

- 首页底部常驻"所有照片本地处理"提示
- AR 页面有"摄像头画面仅在内存中处理"说明
- AI 页面强调"只发送文字描述"
- 隐私政策页 6 个章节详细说明数据流向

---

## 九、技术亮点总结

1. **AR 渲染质量**：3 层叠加（底色→材质→高光）+ 菲涅尔反射 + 柱面曲率变形，在纯 Canvas 2D 下实现了接近原生 3D 的效果
2. **朝向检测鲁棒性**：4 传感器融合 + 不对称阈值 + 权重分配，远超简单的 z 坐标判断
3. **逐指可见性**：3 信号融合 + EMA 平滑 + 强否定优先策略，混合手态（部分手心部分手背）也能正确处理
4. **坐标变换**：object-cover 裁剪适配 + 归一化坐标变换，确保不同分辨率视频都能正确映射
5. **首页交互**：物理引擎级磁力吸附 + 弹性捕获 + 聚光灯跟随，体验精致
6. **资源管理**：ImageBitmap 手动 close + 引用计数 + 卸载清理，防止 GPU 内存泄漏
7. **降级策略**：摄像头 3 层降级 + 错误分类 + 用户友好提示

---

## 十、待优化项

### 高优先级
1. **清理未使用依赖**：`@mediapipe/camera_utils`、`@mediapipe/drawing_utils`、`three`、`ngrok`
2. **next.config.ts allowedDevOrigins** 改为动态或通配
3. **ArView 双重启动状态** 合并为单一状态机
4. **AI 生成** 至少对接一个真实 API（如 DeepSeek DALL-E）

### 中优先级
5. **RAF 帧率自适应**：低端设备降低 MediaPipe 推理频率
6. **history 用 useRef** 替代 useState（NailCanvas 撤销栈）
7. **纹理裁剪 MIN_SELECTION_PX** 提高至 60+
8. **GalleryGrid SVG 优化**：Next.js Image 对 SVG 无意义

### 低优先级
9. **README.md** 替换为项目自定义文档
10. **部署到 Vercel** 完成最后一公里
11. **暗色模式**：当前全站浅粉色，缺乏对比
