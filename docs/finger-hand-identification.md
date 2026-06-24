# 逐指识别与左右手识别 — 技术方案

**创建时间**: 2026-06-24
**目标**: 实现左右手识别、单根手指识别、每指指甲形状差异化渲染
**对应组件**: `src/components/ArView.tsx`

---

## 1. 现状分析

### 1.1 已实现的功能

| 功能 | 状态 | 说明 |
|------|:----:|------|
| Handedness 读取 | ✅ | `multiHandedness` → `"Left" / "Right"` |
| Handedness 用于朝向检测 | ✅ | 叉积/拇指位置根据左右手翻转符号 |
| 手指索引 (0-4) | ✅ | TIPS[5], DIPS[5], PIPS[5] |
| 逐指可见性判定 | ✅ | 三信号融合 + 时序平滑 |
| 逐指宽长比 | ✅ | `FINGER_LENGTH_RATIOS[5]`, `FINGER_WIDTH_RATIOS[5]` |

### 1.2 缺失的功能

| 功能 | 缺失 | 影响 |
|------|:----:|------|
| Handedness UI 显示 | ❌ | 用户看不到当前是左手还是右手 |
| 逐指可见性 UI 显示 | ❌ | 用户看不到每根手指的识别状态 |
| 手指特定指甲形状 | ❌ | 5 指指甲形状相同（只有大小不同），不真实 |
| 单指独立交互 | ❌ | 不能在 AR 界面中单独操作某根手指 |

---

## 2. 技术方案

### 2.1 左右手识别 + UI 显示

**现状**: `handedness` 变量在 `onResults` 回调中读取，仅传入 `shouldRenderNails()` 用于朝向检测，未暴露到 UI。

**改进**:

```
onResults 回调中:
  const handedness = res.multiHandedness?.[h]?.label ?? null;
  
  // 新增: 存储到 state 用于 UI 显示
  setHandLabel(handedness === "Right" ? "右手" : handedness === "Left" ? "左手" : null);
```

```
UI 显示:
  "🖐️ 右手 · 手背"    (手背朝镜头)
  "✋ 右手 · 手心"    (手心朝镜头)
  "🤚 右手 · 侧手"    (侧手)
```

**关键决策**：CSS `scaleX(-1)` 只影响显示，不影响 MediaPipe 的原始帧处理。handedness 基于原始帧，始终正确。不需要镜像补偿。

### 2.2 逐指指甲形状差异化

**现状**: `drawNailShape()` 对所有手指使用相同的参数：

```typescript
const tipNarrow = 0.08 * nw;   // 指尖收窄比例
const cpLen = hl * 0.55;        // 侧面曲线控制点长度
```

**改进**: 添加手指特定形状参数数组

```typescript
// 每指指甲形状参数 [thumb, index, middle, ring, pinky]
FINGER_TIP_NARROW = [0.12, 0.08, 0.07, 0.08, 0.06]   // 指尖收窄
FINGER_SIDE_CURVE = [0.50, 0.55, 0.55, 0.52, 0.45]   // 侧面曲线控制点比率
FINGER_ROOT_BULGE = [0.06, 0.08, 0.08, 0.07, 0.05]   // 根部凸起
```

各指解剖学特征：

| 手指 | 指甲特征 | tipNarrow | sideCurve | rootBulge |
|------|---------|:---------:|:---------:|:---------:|
| 拇指 | 宽短、指尖平、根部宽 | 0.12 | 0.50 | 0.06 |
| 食指 | 长、椭圆、轻微锥形 | 0.08 | 0.55 | 0.08 |
| 中指 | 最长、窄椭圆 | 0.07 | 0.55 | 0.08 |
| 无名指 | 中等、圆润 | 0.08 | 0.52 | 0.07 |
| 小指 | 最小、尖窄 | 0.06 | 0.45 | 0.05 |

`drawNailShape` 改为接收 `fingerIdx`：

```typescript
function drawNailShape(ctx, nl, nw, fingerIdx) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;
    const tipNarrow = FINGER_TIP_NARROW[fingerIdx] * nw;
    const cpLen = hl * FINGER_SIDE_CURVE[fingerIdx];
    const rootBulge = hl * FINGER_ROOT_BULGE[fingerIdx];
    
    ctx.moveTo(hw - tipNarrow, -hl);
    ctx.quadraticCurveTo(0, -hl - hl * 0.15, -(hw - tipNarrow), -hl);
    ctx.bezierCurveTo(
      -(hw + cpLen * 0.3), -hl * 0.6,
      -(hw + cpLen * 0.3), hl * 0.3,
      -hw, hl + rootBulge
    );
    ctx.quadraticCurveTo(0, hl + rootBulge + hl * 0.06, hw, hl + rootBulge);
    ctx.bezierCurveTo(
      hw + cpLen * 0.3, hl * 0.3,
      hw + cpLen * 0.3, -hl * 0.6,
      hw - tipNarrow, -hl
    );
    ctx.closePath();
}
```

视觉差异：
- 拇指 → 更宽的指尖平台，根部稍凸
- 食指 → 标准椭圆，曲线流畅
- 中指 → 最窄长，侧线接近直线
- 无名指 → 圆润对称
- 小指 → 最小，尖窄，根部微凸

### 2.3 逐指可见性状态 UI 显示

在底部状态栏添加每指可见性指示器：

```
    手背 右手           ← 朝向 + 左右手
  [●][○][●][●][○]       ← 5 指可见性
  拇  食  中  无  小     ← 手指名称
```

显示规则：
- ● (绿色圆)：该指纹甲可见 → 正在贴图
- ○ (灰色圆)：该指纹甲不可见 → 跳过

### 2.4 handedness 在朝向检测中的镜像补偿

**问题**: 前置摄像头自拍模式下：
- CSS `scaleX(-1)` 镜像视频进行显示
- MediaPipe 处理原始（未镜像）帧
- handeness 标签始终正确（基于原始帧）

**结论**: 当前不需要镜像补偿，handedness 使用正确。

### 2.5 与现有架构的关系

```
onResults 回调:
  ├── 读取 multiHandedness → handedness: "Left"|"Right"|null
  ├── 传入 shouldRenderNails()     ← 用于朝向检测（已有）
  ├── setHandLabel()               ← 新增：UI 显示
  ├── 4 传感器融合判定
  ├── 全局门控检查
  │
  └── paintNails():
      ├── 每指可见性判定 (已有)
      ├── visibleSmoothRef → setFingerVisibility() ← 新增：每指状态 UI
      ├── drawNailShape(nl, nw, f)  ← 修改：传入 fingerIdx
      └── 材质 + 高光

UI 底部状态栏:
  ├── 朝向指示器 (已有，增加手标签)
  └── 每指可见性指示器 (新增)
```

---

## 3. 参数表（新增/修改）

| 参数 | 值 | 说明 |
|------|:---:|------|
| `FINGER_TIP_NARROW[5]` | [0.12,0.08,0.07,0.08,0.06] | 每指指尖收窄系数 |
| `FINGER_SIDE_CURVE[5]` | [0.50,0.55,0.55,0.52,0.45] | 每指侧面曲线控制点比率 |
| `FINGER_ROOT_BULGE[5]` | [0.06,0.08,0.08,0.07,0.05] | 每指根部凸起系数 |

---

## 4. 验收标准

### A. 功能验收（需 PC/手机摄像头实测）

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 左右手显示正确 | 右手正对镜头 | 底部显示「右手」 |
| A2 | 切换左右手 | 换成左手 | 显示切换为「左手」 |
| A3 | 逐指可见性指示 | 手背朝镜头五指张开 | 5 个绿点，全部可见 |
| A4 | 逐指可见性变化 | 缓慢翻手 | 绿点逐个变灰，与贴图同步 |
| A5 | 手指名称标识 | 查看底部指示器 | 拇/食/中/无/小 五字显示 |
| A6 | 指甲形状差异化 | 观察 5 指甲形状 | 拇指宽短、小指尖窄、中指最长 |
| A7 | 朝向+左右手联动 | 翻手 | "🖐️ 右手 · 手背" ↔ "✋ 右手 · 手心" |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint ArView.tsx | `npx eslint src/components/ArView.tsx` | 0 errors |
| B3 | Handedness 状态同步 | 代码审查 | `handLabel` state 从 `multiHandedness` 同步 |
| B4 | 指甲形状逐指参数 | 代码审查 | `FINGER_TIP_NARROW` / `SIDE_CURVE` / `ROOT_BULGE` 三数组 |
| B5 | drawNailShape 接收 fingerIdx | 代码审查 | 函数签名含手指索引参数 |
| B6 | 全局门控保留 | 代码审查 | `if(decision.render)` 仍在 |

### C. 回归验收

| # | 验收项 | 预期结果 |
|---|--------|----------|
| C1 | `npm run build` | 通过，0 错误 |
| C2 | 手心朝镜头不贴图 | 五指不显示 |
| C3 | 手背五指贴图 | 五指均渲染 |
| C4 | 编辑器/图库/AI 页面 | 正常加载 |

---

## 5. 文件修改清单

| 文件 | 修改 |
|------|------|
| `src/components/ArView.tsx` | ① 新增 `handLabel` state + UI显示 ② 新增三组逐指形状参数 ③ 修改 `drawNailShape` 签名 ④ 新增逐指可见性 UI 指示器 |
| `docs/technical-architecture.md` | 更新 §5.5 参数表 + §5.6 指甲形状 |
| `CLAUDE.md` | 更新关键参数表 |
| `dev-log/2026-06-24.md` | 追加记录 |

---

## 6. 回退方案

如果逐指形状差异化效果不理想：
1. 回退到统一形状：注释 `FINGER_TIP_NARROW` 数组，使用原常量 `0.08`
2. 如果 handedness UI 显示异常：暂时注释 handLabel 相关代码

---

## 7. 验收追踪

- [x] **B1**: TypeScript 编译 ✅ — `npm run build` 0 错误
- [x] **B2**: ESLint ✅ — ArView.tsx 0 errors
- [x] **B3**: Handedness 状态同步 ✅ — `setHandLabel()` 从 `multiHandedness` 同步
- [x] **B4**: 指甲形状逐指参数 ✅ — `FINGER_TIP_NARROW[5]`, `FINGER_SIDE_CURVE[5]`, `FINGER_ROOT_BULGE[5]`
- [x] **B5**: drawNailShape 接收 fingerIdx ✅ — 逐指形状差异化渲染
- [x] **B6**: 全局门控保留 ✅ — `if(decision.render)` 在第 950 行
- [x] **C1**: 回归验收 ✅ — build 通过，所有路由编译正常
- [ ] **A1**: 左右手显示（需真机测试）
- [ ] **A2**: 切换左右手（需真机测试）
- [ ] **A3**: 逐指可见性指示（需真机测试）
- [ ] **A5**: 手指名称标识（需真机测试）
- [ ] **A6**: 指甲形状差异化（需真机测试）
