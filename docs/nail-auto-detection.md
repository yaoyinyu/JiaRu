# 美甲参考图自动识别技术方案

**创建时间**: 2026-06-24
**目标**: 用户上传美甲参考图后，自动检测图中的指甲区域，无需手动框选
**涉及文件**: `src/components/NailArtPicker.tsx`（重写自动检测逻辑）

---

## 1. 问题分析

### 1.1 当前方案的问题

现有的 `NailArtPicker` 需要用户手动「添加选区 → 拖拽定位 → 调整大小/旋转 → 分配手指」，操作步骤多、上手门槛高。

### 1.2 自动识别的可行性

AR 管线中的 `paintNails()` 函数已经实现了完整的指甲区域计算逻辑：

```
输入: MediaPipe 21 个关键点 (TIP/DIP/PIP)
输出: 每指的指甲中心(cx,cy)、大小(nl,nw)、旋转角(angle)
```

这套逻辑完全可以用在静态参考图上——只需将关键点来源从视频帧改为上传的图片。

### 1.3 复用 AR 管线的优势

| 组件 | AR 管线 (ArView.tsx) | 参考图识别 (NailArtPicker) |
|------|---------------------|--------------------------|
| 关键点来源 | 摄像头视频帧 | 上传的静态图片 |
| 关键点检测 | MediaPipe Hands | 同一 MediaPipe Hands 实例 |
| 指甲几何计算 | paintNails() 内部 | ★ 复用完全相同的公式 |
| 用户交互 | 自动贴合 | ★ 自动检测→用户确认 |

---

## 2. 技术方案

### 2.1 总体流程

```
用户上传参考图
  ↓
NailArtPicker 挂载
  ├── 显示「⏳ 正在检测指甲区域...」加载状态
  ├── 加载 MediaPipe Hands CDN（首次）
  ├── 创建临时 Hands 实例
  ├── 在图片上运行手部检测
  │
  ├── ✅ 检测到 → 计算 5 指指甲区域
  │   └── 使用与 ArView 完全相同的几何公式：
  │       方向 = TIP - DIP
  │       中心 = TIP - normalize(TIP-DIP) * len * TIP_OFFSET_RATIO
  │       大小(L) = len * FINGER_LENGTH_RATIOS[f]
  │       大小(W) = len * FINGER_WIDTH_RATIOS[f]
  │       旋转 = atan2(fy, fx)
  │
  └── ❌ 检测失败 → 回退手动模式
      └── 显示「添加选区」按钮 + 提示"未检测到指甲，请手动添加"
  ↓
用户看到自动标注的指甲选区
  ├── 每个选区显示在对应指甲位置
  ├── 已自动分配对应手指（拇指→拇、食指→食...）
  ├── 用户可以：
  │   ├── 点击选区 → 调整位置/大小/旋转
  │   ├── 修改手指分配
  │   ├── 添加/删除选区
  │   └── 点击「完成分配」确认
  └──
```

### 2.2 静态图片 MediaPipe 检测

```typescript
async function detectHandsOnImage(
  imageElement: HTMLImageElement
): Promise<Landmark[][] | null> {
  // 1. 确保 CDN 加载
  if (!window.Hands) {
    await loadScript(CDN_HANDS_URL);
  }

  // 2. 创建临时 Hands 实例（与 ArView 相同的 locateFile）
  const hands = new window.Hands({
    locateFile: (f) => CDN_BASE + f,
  });
  hands.setOptions({
    maxNumHands: 1,
    modelComplexity: 1,   // 静态图片用更高精度
    minDetectionConfidence: 0.5,
  });

  // 3. 用 canvas 中转（MediaPipe 兼容 HTMLCanvasElement）
  const canvas = document.createElement('canvas');
  canvas.width = imageElement.naturalWidth;
  canvas.height = imageElement.naturalHeight;
  canvas.getContext('2d')!.drawImage(imageElement, 0, 0);

  // 4. 发送检测请求，Promise 化
  const results = await new Promise<HandResults>((resolve, reject) => {
    const timeout = setTimeout(() => {
      hands.close();
      reject(new Error('检测超时'));
    }, 30000);

    hands.onResults((res) => {
      clearTimeout(timeout);
      resolve(res);
    });

    hands.send({ image: canvas }).catch((err) => {
      clearTimeout(timeout);
      hands.close();
      reject(err);
    });
  });

  hands.close();
  return results.multiHandLandmarks ?? null;
}
```

### 2.3 指甲区域计算（与 ArView 一致）

```typescript
function computeNailRegionsFromLandmarks(
  lm: Landmark[],
  canvasW: number,
  canvasH: number,
  scale: number  // canvas像素 / 原始像素
): NailRegion[] {
  const regions: NailRegion[] = [];

  for (let f = 0; f < 5; f++) {
    const tip = lm[TIPS[f]];
    const dip = lm[DIPS[f]];
    const pip = lm[PIPS[f]];
    if (!tip || !dip) continue;

    // 归一化坐标 → canvas 像素坐标
    // MediaPipe 返回的 x,y 是相对于原始图像尺寸的归一化值 [0,1]
    const tipX = tip.x * canvasW;
    const tipY = tip.y * canvasH;
    const dipX = dip.x * canvasW;
    const dipY = dip.y * canvasH;

    // 方向向量 TIP-DIP（与 ArView 的 paintNails 一致）
    let fx = tipX - dipX;
    let fy = tipY - dipY;
    const rawLen = Math.sqrt(fx * fx + fy * fy);
    if (rawLen < 5) continue;

    // 指甲中心（沿 TIP-DIP 方向偏移 TIP_OFFSET_RATIO）
    const cx = tipX - (fx / rawLen) * (rawLen * TIP_OFFSET_RATIO);
    const cy = tipY - (fy / rawLen) * (rawLen * TIP_OFFSET_RATIO);

    // 指甲大小（使用逐指解剖参数）
    const nl = rawLen * FINGER_LENGTH_RATIOS[f];
    const nw = rawLen * FINGER_WIDTH_RATIOS[f];

    // 旋转角度
    const angle = Math.atan2(fy, fx);

    regions.push({
      id: generateId(),
      cx, cy, angle, nl, nw,
      assignedFinger: f,  // ★ 自动分配对应手指
    });
  }

  return regions;
}
```

**坐标系说明**:
- `tip.x`（归一化 0-1）→ `tip.x * canvasW`（canvas 像素）→ 与 NailArtPicker 的 `regions[].cx` 坐标系统一
- 所有常量复用 ArView 的同一套（`TIP_OFFSET_RATIO`, `FINGER_LENGTH_RATIOS`, `FINGER_WIDTH_RATIOS`）

### 2.4 用户交互

自动检测出选区后：

| 场景 | 用户行为 | 系统响应 |
|------|----------|----------|
| 检测准确 | 直接点「完成分配」 | 提取纹理，跳转到 AR |
| 某指检测不准 | 点击该选区 → 调整位置/大小/旋转 | 立即更新 |
| 分配手指错误 | 点击该选区 → 点底部手指按钮 | 重新分配 |
| 多余选区 | 选中 → 点「删除」 | 移除 |
| 漏检 | 点「添加选区」手动添加 | 出现新选区 |
| 完全没检测到 | 见「检测失败」回退模式 | 纯手动模式 |

### 2.5 与现有组件的关系

```
NailArtPicker 结构（修改后）:

┌─────────────────────────────────────┐
│  useEffect → autoDetectNails()      │
│    ├── 加载 CDN → 创建 Hands       │
│    ├── 检测手部 → 计算指甲区域      │
│    └── setRegions(detected)        │
│                                     │
│  UI:                                │
│  ├── 检测中 → 遮罩 + 加载动画      │
│  ├── 检测完成 → 显示选区 + 可编辑   │
│  └── 检测失败 → 纯手动添加模式       │
└─────────────────────────────────────┘
```

---

## 3. 验收标准

### A. 功能验收（需真机/PC）

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 自动检测指甲区域 | 上传含清晰手部的参考图 | 5 个指甲选区自动显示在对应位置 |
| A2 | 手指自动分配 | 查看选区标签 | 拇指→拇，食指→食 ... 自动对应 |
| A3 | 选区位置准确 | 观察选区是否覆盖指甲 | 选区与指甲轮廓对齐 |
| A4 | 无手图片的降级 | 上传不包含手的图片 | 显示「未检测到手指，请手动添加」|
| A5 | 手动调整 | 拖拽选区/改大小/改分配 | 功能正常 |
| A6 | 确认提取 | 点「完成分配」 | 纹理提取到对应手指 |
| A7 | AR 贴合 | 切换到摄像头 | 纹理在对应手指上渲染 |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors |
| B3 | 几何公式与 ArView 一致 | 代码审查 | 方向/中心/大小/旋转公式完全一致 |
| B4 | 坐标映射正确 | 代码审查 | MediaPipe 归一化坐标 → canvas 像素 → 显示 |
| B5 | CDN 加载容错 | 代码审查 | 失败时回退手动模式 |

---

## 4. 验收追踪

- [ ] B1: TypeScript 编译
- [ ] B2: ESLint
- [ ] B3: 几何公式一致
- [ ] A1: 自动检测指甲
- [ ] A2: 手指自动分配
- [ ] A4: 无手降级
- [ ] A7: AR 贴合
