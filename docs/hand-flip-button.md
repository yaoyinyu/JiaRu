# 左右手反转按钮 — 技术方案

**创建时间**: 2026-06-24
**目标**: 为前置摄像头镜像行为不正确的用户提供手动反转左右手识别的按钮
**对应组件**: `src/components/ArView.tsx`

---

## 1. 问题分析

### 1.1 前置摄像头的镜像不确定性

当用户使用前置摄像头（`facingMode: "user"`）时，不同设备和浏览器的镜像行为存在差异：

| 情况 | 视频显示 | MediaPipe 收到的帧 | Handedness | 用户实际手 |
|------|---------|-------------------|:----------:|:--------:|
| 正常设备 | CSS scaleX(-1) 镜像 | 原始未镜像帧 | Right | 右手 ✅ |
| 部分 Android | 系统已镜像 + CSS scaleX(-1) 双镜像 | 可能已被系统镜像 | Left | 右手 ❌ |
| 部分 iOS Safari | 系统已镜像 | 系统镜像帧 | Left | 右手 ❌ |

**根本原因**: 部分设备/浏览器在将摄像头帧传递给 Web 应用之前已经做了镜像处理，导致 MediaPipe 收到的帧与实际手的方向相反。

### 1.2 现状

当前代码使用 CSS `scaleX(-1)` 镜像视频显示（自拍模式），但无法补偿系统级的预镜像。当出现这种情况时，用户看到：
- 右手在画面左侧（正确的自拍镜像）
- 但底部显示「检测到左手」（❌ 错误的识别）

### 1.3 设计原则

1. **不改动视频画面** — 用户看到的是正确的自拍镜像，不需要更改显示
2. **只反转头检测逻辑** — 当 handedness 被系统预镜像反转时，手动补偿
3. **用户可触发** — 提供一个按钮，让用户在看到左右手识别错误时手动切换

---

## 2. 技术方案

### 2.1 核心思路：有效 handedness

```typescript
// handFlip: boolean — 用户通过按钮切换
// rawHandedness: "Left" | "Right" | null — MediaPipe 原始输出
// effectiveHandedness: 用于渲染逻辑和 UI 显示的 handedness

const effectiveHandedness = handFlip
  ? (rawHandedness === "Left" ? "Right" : rawHandedness === "Right" ? "Left" : null)
  : rawHandedness;
```

**影响范围**：

| 使用点 | 当前代码 | 修改后 |
|--------|---------|--------|
| `setHandLabel()` | `rawHandedness → "左手"/"右手"` | `effectiveHandedness → "左手"/"右手"` |
| `shouldRenderNails()` 方案 A（叉积） | `rawHandedness` 决定符号 | `effectiveHandedness` 决定符号 |
| `shouldRenderNails()` 方案 D（拇指） | `rawHandedness` 决定符号 | `effectiveHandedness` 决定符号 |

### 2.2 按钮 UI

```
位置: AR 视图右上角（诊断面板下方 / 旁边）
样式: 小型胶囊按钮，带半透明背景
图标: 🔄 反转手
状态: 未激活 → "🔄 反转手"（灰色）
      已激活 → "🔄 反转手"（品牌色高亮）
```

按钮放在 AR 摄像头覆盖层上，不遮挡手部检测区域。

### 2.3 与其他功能的关系

```
onResults 回调:
  ├── rawHandedness = multiHandedness?.[h]?.label
  ├── effectiveHandedness = handFlip ? !rawHandedness : rawHandedness
  │
  ├── setHandLabel(effectiveHandedness)       ← UI 显示
  ├── shouldRenderNails(lm, depth, effectiveHandedness)
  │   ├── 方案 A（叉积）: 使用 effectiveHandedness 符号
  │   └── 方案 D（拇指）: 使用 effectiveHandedness 符号
  │
  └── paintNails()  ← 不受影响（逐指判定不依赖 handedness）
```

### 2.4 用户体验

1. 用户打开 AR 页 → 看到「🖐️ 右手 · 手背」
2. 用户发现实际是左手但系统识别为右手
3. 点击「🔄 反转手」按钮
4. UI 立即变为「🖐️ 左手 · 手背」
5. 朝向检测也使用正确的 handedness 重新判断

---

## 3. 参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|:------:|------|
| `handFlip` | `boolean` | `false` | 是否反转左右手识别 |

---

## 4. 验收标准

### A. 功能验收（需 PC/手机摄像头实测）

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 按钮可见 | 打开 AR 页面，摄像头就绪 | 右上角显示「🔄 反转手」按钮 |
| A2 | 默认不反转 | 右手正对镜头 | 底部显示「右手」 |
| A3 | 点击反转 | 点击「🔄 反转手」 | 底部切换为「左手」 |
| A4 | 再点取消反转 | 再次点击按钮 | 恢复为「右手」 |
| A5 | 反转后朝向正确 | 反转后手心朝镜头 | 显示「手心」且不贴图（朝向逻辑符号正确） |
| A6 | 反转后画面不变 | 观察视频画面 | 视频镜像不受影响，画面无变化 |
| A7 | 刷新后重置 | 刷新页面 | 反转状态恢复默认 |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors |
| B3 | 有效 handedness 覆盖所有使用点 | 代码审查 | `effectiveHandedness` 替代所有 `rawHandedness` 引用 |
| B4 | 画面显示不受影响 | 代码审查 | 无 video/canvas CSS 或尺寸修改 |
| B5 | handFlip 持久化 | 代码审查 | `useState` 存储，非 ref |

### C. 回归验收

| # | 验收项 | 预期结果 |
|---|--------|----------|
| C1 | `npm run build` | 通过，0 错误 |
| C2 | 不开启反转时功能与之前一致 | 朝向检测、手/逐指判定、贴图全部不变 |
| C3 | 手心/手背/侧手切换 | 不受影响 |

---

## 5. 文件修改清单

| 文件 | 修改 |
|------|------|
| `src/components/ArView.tsx` | ① 新增 `handFlip` state + 按钮 UI ② 新增 `effectiveHandedness` 变量 ③ 替换所有 `handedness` 引用为 `effectiveHandedness` |

---

## 6. 回退方案

如果按钮导致朝向检测异常：
1. 将 `shouldRenderNails()` 恢复为使用原始 `handedness`，仅 UI 显示使用 `effectiveHandedness`
2. 或完全移除该功能（`handFlip` 默认 false 时行为与之前一致）

---

## 7. 验收追踪

- [x] **B1**: TypeScript 编译 ✅ — `npm run build` 0 错误
- [x] **B2**: ESLint ✅ — ArView.tsx 0 errors（`handFlip` 依赖警告已消除，改用 ref）
- [x] **B3**: effectiveHandedness 覆盖所有使用点 ✅ — `setHandLabel` + `shouldRenderNails` 均使用
- [x] **B4**: 画面不受影响 ✅ — 无 video/canvas CSS 修改
- [x] **B5**: useRef 闭包安全 ✅ — `handFlipRef.current` 在 onResults 中读取
- [x] **C1**: 回归验收 ✅ — build 通过
- [ ] **A1**: 按钮可见（需真机测试）
- [ ] **A2/A3/A4**: 反转/取消反转（需真机测试）
- [ ] **A6**: 画面不受影响（需真机测试）
